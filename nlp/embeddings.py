"""
Vector embeddings over reviews_raw -> reviews_processed.embedding (pgvector).

Model: sentence-transformers all-MiniLM-L6-v2, 384-dim - same model used in
nlp/topic_model.py for clustering, for consistency (one less model to keep in
sync if it's ever swapped out) and because it's what the RAG step (M6) expects
for query-time cosine similarity search.

Writing vectors needs psycopg2.extras.execute_values (via db.retry.bulk_upsert)
PLUS pgvector's psycopg2 adapter registered on the connection - without it,
psycopg2 serializes a numpy array as a plain Postgres array literal ('{1,2,3}'),
which the `vector` column type rejects; register_vector teaches it to emit the
'[1,2,3]' format pgvector expects. Must be called with the *raw* DBAPI
connection (session.connection().connection.dbapi_connection), not the
SQLAlchemy pool's _ConnectionFairy proxy that wraps it - the proxy fails
isinstance checks inside psycopg2's register_type.

Caches to disk (embeddings + aligned review_ids) before writing to the DB, same
reasoning as topic_model.py: encoding 12k reviews is the expensive part, so a
DB hiccup during the write should never force a re-encode.
"""

import json
import os

import numpy as np
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer
from sqlalchemy import text

from db.retry import bulk_upsert, write_batches
from db.session import get_session

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
MODELS_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")
CACHE_IDS = os.path.join(MODELS_ROOT, "embedding_review_ids.json")
CACHE_VECS = os.path.join(MODELS_ROOT, "embeddings.npy")


def fetch_pending(session):
    rows = session.execute(
        text(
            """
            SELECT r.id, r.review_text
            FROM reviews_raw r
            JOIN reviews_processed rp ON rp.review_id = r.id
            WHERE rp.embedding IS NULL
            ORDER BY r.id
            """
        )
    ).fetchall()
    return rows


def upsert_embeddings(session, payload):
    register_vector(session.connection().connection.dbapi_connection)
    rows = [(review_id, vec) for review_id, vec in payload]
    bulk_upsert(
        session,
        """
        INSERT INTO reviews_processed (review_id, embedding)
        VALUES %s
        ON CONFLICT (review_id) DO UPDATE
        SET embedding = EXCLUDED.embedding
        """,
        rows,
    )


def write_embeddings(review_ids, vectors):
    payload = list(zip(review_ids, vectors))
    return write_batches(upsert_embeddings, payload)


def compute_and_cache():
    session = get_session()
    rows = fetch_pending(session)
    session.close()
    print(f"{len(rows)} reviews pending embeddings.")

    if not rows:
        return [], np.empty((0, 384), dtype="float32")

    print(f"Encoding with {EMBEDDING_MODEL_NAME}...")
    embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)
    texts = [r.review_text or "" for r in rows]
    vectors = embedder.encode(texts, show_progress_bar=True, batch_size=128).astype("float32")

    review_ids = [r.id for r in rows]
    os.makedirs(MODELS_ROOT, exist_ok=True)
    np.save(CACHE_VECS, vectors)
    with open(CACHE_IDS, "w") as f:
        json.dump(review_ids, f)
    print(f"{len(review_ids)} embeddings cached to {CACHE_VECS}")

    return review_ids, vectors


def run():
    if os.path.exists(CACHE_IDS) and os.path.exists(CACHE_VECS):
        print("Found cached embeddings - skipping recompute, writing to DB only.")
        with open(CACHE_IDS) as f:
            review_ids = json.load(f)
        vectors = np.load(CACHE_VECS)
    else:
        review_ids, vectors = compute_and_cache()

    if not review_ids:
        print("No pending reviews — embeddings already up to date.")
        return

    print(f"Writing {len(review_ids)} embeddings to reviews_processed...")
    write_embeddings(review_ids, vectors)

    os.remove(CACHE_IDS)
    os.remove(CACHE_VECS)
    print("Embeddings complete.")


if __name__ == "__main__":
    run()
