# NLP Pipeline Progress (Step 2)

_Last updated: 2026-10-03_

## M2 — Sentiment Analysis: COMPLETE

12,043 / 12,043 reviews scored via `nlp/sentiment.py`.

| Sentiment | Count | % |
|---|---|---|
| positive | 10,729 | 89.1% |
| negative | 810 | 6.7% |
| neutral | 504 | 4.2% |

Model: `cardiffnlp/twitter-roberta-base-sentiment`. `sentiment_score` = P(positive) - P(negative), mapped to -1.0..+1.0 (not the pipeline's raw top-label confidence).

**Schema fix needed and applied:** `reviews_processed.review_id` had no unique constraint, which `ON CONFLICT (review_id)` upserts require (all four NLP tasks write to the same row per review). Added via `ALTER TABLE reviews_processed ADD CONSTRAINT reviews_processed_review_id_key UNIQUE (review_id);` and reflected in `db/models.py` (`unique=True`).

**Reliability fix applied to `db/session.py`:** the long-running sentiment job hung silently for 4.5 hours (likely the machine slept, TCP connection to Supabase died, but psycopg2 had no OS-level timeout so it blocked forever on a read instead of erroring). Fixed by adding to the engine: `pool_pre_ping=True`, `pool_recycle=300`, and psycopg2 `keepalives` (`idle=30s`, `interval=10s`, `count=3`, so a dead connection surfaces within ~60s instead of hanging indefinitely). This applies to *all* DB access in the project, not just NLP scripts — worth keeping in mind for any future long-running job (topic modeling, embeddings, etc.).

**Process note:** background jobs piped through `tee` can report exit code 0 even when the underlying Python process crashed, because without `set -o pipefail` the shell reports `tee`'s exit status, not the piped command's. Always use `set -o pipefail` before `cmd | tee file` for long-running jobs, and verify actual row counts in the DB rather than trusting the reported exit code alone.

Scripts are resumable: `fetch_pending()` only selects reviews where `reviews_processed.sentiment_label IS NULL`, so re-running `python -m nlp.sentiment` after a crash/kill picks up exactly where it left off — no duplicate work, no data loss.

## M3 — Topic Modeling: COMPLETE

12,043 / 12,043 reviews assigned a topic via `nlp/topic_model.py` (BERTopic, fully unsupervised — user's explicit choice over guiding topics toward the spec's 8 preset categories).

**34 topics discovered** (auto-reduced from 49 via BERTopic's `nr_topics="auto"`, which merges only near-duplicate c-TF-IDF topics — not forced to a target count). All 2,337 initial HDBSCAN outliers (~19%) were reassigned to a real topic via `reduce_outliers(strategy="embeddings")`; 0 left unassigned.

Top topics by review count:
| Count | Label |
|---|---|
| 3,961 | service, great, amazing, indian |
| 1,947 | pizza, slice, crust, nyc |
| 1,319 | burger, burgers, fries, best |
| 974 | sushi, omakase, fresh, fish |
| 623 | chinese, authentic, dishes, bao |
| 533 | italian, pasta, italy, delicious |
| 367 | dumplings, soup, soup dumplings, pork |

**Observation worth keeping in mind for the dashboard:** because the corpus spans 6 very different restaurant categories (pizza/sushi/burger/indian/italian/chinese) and topic discovery was fully unsupervised, the dominant signal BERTopic found is **cuisine/restaurant identity**, not purely complaint-style aspects (service/price/delivery/ambiance) like the spec's hypothetical 8 categories. Some aspect-flavored topics exist (service, omakase experience, vegan options) but aren't as cleanly separated. The donut-chart / top-complaint-card UI pieces in the spec may need to work with these topics as-is, or a later pass could filter/re-cluster within each cuisine to surface aspect-level topics — not decided yet, flagging for when dashboard work starts.

**Root cause found during this task — important for all future bulk DB writes in this project:** repeated multi-minute "hangs" during the DB write step were misdiagnosed at first as dead/stuck connections. Direct measurement proved otherwise: this connection has ~1s round-trip latency to the Supabase host (AWS ap-southeast-2, Sydney), and SQLAlchemy's default `executemany()` via psycopg2 sends **one network round trip per row**. A 10-row test batch took 9.9s (~1s/row) — so a 500-row batch needs ~8+ minutes, not "a few seconds that then hangs." The fix: `db/retry.py`'s `bulk_upsert()` uses psycopg2's `execute_values`, which sends an entire batch (up to `page_size`, default 1000) as **one** round trip. This took the 12,043-row write from "doesn't finish in 8+ minutes" to under a minute. `nlp/sentiment.py` and `nlp/topic_model.py` both use it now — **any future NLP/ML script that writes to `reviews_processed` (embeddings, complaints, is_suspicious) should use `db.retry.bulk_upsert` from the start**, not raw `session.execute(text(...), list_of_dicts)`.

`db/retry.py` also keeps a per-batch hard timeout (`write_batches()`, 60s default) as a safety net for *genuine* dead connections — confirmed separately as a real, different failure mode (a 4.5-hour hang with flat CPU time after the machine slept). That one is a true silent hang; the per-row latency issue above is not. Both are now handled, but they're different problems with different fixes — don't conflate them if a future script acts "stuck."

**Process note on debugging a stuck background job:** `ps -o pid,etime,time,state` (elapsed wall time vs. accumulated CPU time) is the fastest way to tell "slow but working" (CPU time climbing roughly with elapsed time) from "genuinely hung" (CPU time flat while elapsed time grows). `lsof -p <pid> -i` showing the actual remote host/port and connection state (ESTABLISHED vs. not) is the next check — it ruled out a dead TCP connection and pointed at the per-row latency explanation instead.

## M4a — Complaint & Entity Extraction: COMPLETE

12,043 / 12,043 reviews processed via `nlp/complaint_extractor.py` in 36 seconds (pure regex, no model inference needed).

**Deviated from spec on purpose, with reasoning:** the spec's entity-extraction approach (spaCy `en_core_web_sm`, PRODUCT label) was tested first and failed outright — PRODUCT essentially never fires on food words ("pizza", "sushi" tagged nothing; only "45 minutes" got tagged, as TIME). Flagged to the user before proceeding; chose to replace it with a `FOOD_GAZETTEER` (curated word/phrase list) matched via a single compiled word-boundary regex. The gazetteer was built from two sources: (1) frequency analysis of actual nouns across all 12,043 reviews (top-150 list, filtered down to genuine food/drink/dish terms — things like "service", "atmosphere", "experience" were excluded as non-food); (2) a curated supplement of multi-word dish names for the dataset's 6 cuisines that single-noun frequency counting can't catch ("soup dumplings", "peking duck", "hand rolls", "tikka masala", etc.).

Results: **68.8% of reviews (8,281 / 12,043) got at least one food entity tagged** — vs. ~0% with the original spaCy approach. Top entities: pizza (1,765), sushi (1,000), burger (952), chicken (656), sauce (550).

Complaints (keyword-matched as specced, no changes needed there — this part worked as designed): **725 / 12,043 reviews (6.0%)** flagged with at least one complaint, consistent with the 6.7% negative-sentiment rate from M2. Distribution: overpriced (229), slow service (185), cold food (128), rude staff (83), small portions (49), wrong order (33), noisy (26), dirty (26), bad packaging (6).

## M4b — Vector Embeddings: COMPLETE

12,043 / 12,043 reviews embedded via `nlp/embeddings.py`. Model: sentence-transformers `all-MiniLM-L6-v2`, 384-dim, stored in `reviews_processed.embedding` (pgvector).

**Verified semantic search works end-to-end**, not just "the column is populated": queried for reviews nearest a pizza/crust review, got back 3 other pizza/crust reviews at 78-80% cosine similarity. This is the exact retrieval mechanism M6 (RAG chatbot) will use.

**Non-obvious fix required:** writing numpy vectors via `psycopg2.extras.execute_values` needs `pgvector.psycopg2.register_vector()` called on the connection first, or psycopg2 serializes the array in plain Postgres array syntax (`{1,2,3}`) which the `vector` column type rejects — it needs `[1,2,3]`. The non-obvious part: `register_vector()` must get the **raw** DBAPI connection, not SQLAlchemy's pool proxy. `session.connection().connection` returns a `sqlalchemy.pool.base._ConnectionFairy` (a proxy), and passing that directly makes `register_vector` fail deep inside psycopg2's `register_type()` with a confusing `TypeError: argument 2 must be a connection, cursor or None` — because the proxy fails psycopg2's internal `isinstance` check even though it quacks like a connection. Fix: unwrap one more level via `.dbapi_connection` to get the true `psycopg2.extensions.connection` object. See `nlp/embeddings.py::upsert_embeddings`.

**M4 (Complaints + Entities + Embeddings) is now fully complete** — every review in `reviews_processed` has sentiment, topic, complaints, entities, and embedding populated. Core NLP pipeline (M2-M4) done.

## Not started yet
- M5 — XGBoost fake review detector + Prophet rating forecast
- M6 — RAG chatbot (needs `GROQ_API_KEY`, still empty in `.env`)
- M7-M9 — FastAPI, React dashboard, GitHub Actions cron

## Key files
- `nlp/sentiment.py` — sentiment pipeline, run as `python -m nlp.sentiment`
- `nlp/topic_model.py` — topic modeling, run as `python -m nlp.topic_model`. Caches the fitted model (`models/topic_model/`) and computed assignments (`models/topic_assignments.json`) to disk *before* writing to the DB, so a DB hiccup during the write never costs a recompute — rerunning the script detects the cache and skips straight to the write. The cache file is deleted only after a fully successful write.
- `nlp/complaint_extractor.py` — complaints (keyword match) + entities (gazetteer regex match, not spaCy — see above). Run as `python -m nlp.complaint_extractor`.
- `nlp/embeddings.py` — vector embeddings, run as `python -m nlp.embeddings`. Same disk-cache-before-DB-write pattern as topic_model.py (`models/embeddings.npy` + `models/embedding_review_ids.json`, deleted on success).
- `db/session.py` — engine has pool_pre_ping/pool_recycle/keepalives/connect_timeout/statement_timeout (defense in depth against dead connections; see M2 note above).
- `db/retry.py` — shared `bulk_upsert()` (fast, one-round-trip writes via `execute_values`) and `write_batches()` (batches + hard per-batch timeout + exponential-backoff retry on `OperationalError`). Use this for any new script that writes to the DB in bulk. **For pgvector columns specifically, also call `register_vector()` on the raw `.dbapi_connection` first** — see M4b note above.
