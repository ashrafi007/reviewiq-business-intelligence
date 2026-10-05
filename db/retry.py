"""
Hardened DB write helper for long-running batch jobs against Supabase.

Root cause found by direct measurement: this connection has ~1s round-trip
latency to the Supabase host (ap-southeast-2, Sydney), and SQLAlchemy's default
executemany() with psycopg2 issues ONE round trip PER ROW. A 10-row batch took
9.9s (~1s/row) - so a 500-row batch needs ~8+ minutes, not "a few seconds that
then hangs." What looked like repeated silent hangs during development was
actually a too-impatient timeout killing batches that were working correctly,
just slowly. Fixed at the source with bulk_upsert() below (psycopg2's
execute_values, one round trip for the whole batch regardless of row count).

write_batches()'s per-batch timeout is kept as a genuine safety net for actual
dead connections (confirmed separately: a real 4.5-hour hang after the machine
slept, where CPU time stayed flat for hours - a different failure mode from the
per-row latency issue above). Now that writes are fast, the timeout is generous
(60s) so it only fires for a connection that is truly stuck, not merely slow.
A daemon thread (not ThreadPoolExecutor, whose workers are registered with
threading._register_atexit since Python 3.9 and would block interpreter exit)
is used so an abandoned, permanently-stuck connection never prevents the script
from finishing.
"""

import queue
import threading
import time

from psycopg2.extras import execute_values
from sqlalchemy.exc import OperationalError

from db.session import get_session


def bulk_upsert(session, sql_values_template, rows, page_size=1000):
    """One-round-trip-per-call bulk insert/upsert via psycopg2's execute_values.

    sql_values_template must contain exactly one `%s` placeholder where the
    VALUES list goes, e.g.:
        INSERT INTO t (a, b) VALUES %s ON CONFLICT (a) DO UPDATE SET b = EXCLUDED.b
    rows: list of tuples matching the column order in the INSERT.
    """
    raw_conn = session.connection().connection
    cur = raw_conn.cursor()
    execute_values(cur, sql_values_template, rows, page_size=page_size)
    session.commit()


def _run_in_thread(fn, timeout_s):
    """Run fn() in a daemon thread, wait up to timeout_s. Returns (ok, result_or_exc, timed_out)."""
    result_queue = queue.Queue(maxsize=1)

    def worker():
        try:
            result_queue.put(("ok", fn()))
        except Exception as e:  # noqa: BLE001 - we want to surface any exception to the caller
            result_queue.put(("error", e))

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout=timeout_s)
    if t.is_alive():
        return False, None, True  # abandoned - thread keeps running but we stop waiting
    status, payload = result_queue.get()
    return status == "ok", payload, False


def write_batches(write_fn, items, batch_size=1000, max_retries=4, batch_timeout=60):
    """
    Write `items` to the DB in batches via write_fn(session, batch), with:
      - a hard per-batch timeout (catches silent socket hangs no DB-side setting catches)
      - exponential backoff retries on OperationalError
      - a fresh session (and if needed, a fresh abandoned-in-place connection) per attempt

    Raises RuntimeError if a batch exhausts all retries, naming the first unwritten
    index so the caller can report how far it got.
    """
    total = len(items)
    written = 0
    for i in range(0, total, batch_size):
        chunk = items[i : i + batch_size]

        def attempt_write(chunk=chunk):
            session = get_session()
            try:
                write_fn(session, chunk)
            finally:
                session.close()

        for attempt in range(1, max_retries + 1):
            ok, payload, timed_out = _run_in_thread(attempt_write, batch_timeout)
            if ok:
                written += len(chunk)
                break
            if timed_out:
                if attempt == max_retries:
                    raise RuntimeError(
                        f"DB write hung for >{batch_timeout}s on all {max_retries} attempts "
                        f"(batch starting at item index {i}, {written}/{total} written so far)."
                    )
                print(f"  DB write hung (attempt {attempt}/{max_retries}, >{batch_timeout}s). Abandoning stuck connection, retrying fresh...")
                continue
            # payload is the exception from the worker thread
            if attempt == max_retries or not isinstance(payload, OperationalError):
                raise payload
            wait = 2**attempt
            print(f"  DB write failed (attempt {attempt}/{max_retries}): {payload}. Retrying in {wait}s...")
            time.sleep(wait)
        print(f"  {written}/{total} written.")
    return written
