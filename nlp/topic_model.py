"""
Topic modeling over reviews_raw -> reviews_processed, fully unsupervised (BERTopic).

Design choices (see .CLAUDE/nlp_progress.md for the reasoning):
- Embeddings: sentence-transformers all-MiniLM-L6-v2, computed once and reused for both
  BERTopic's clustering and (later) nlp/embeddings.py's pgvector column.
- Topic count: NOT forced to a fixed number. HDBSCAN finds whatever topics actually
  exist in the data; BERTopic's nr_topics="auto" only merges topics whose c-TF-IDF
  representations are near-duplicates, which is a principled de-dup rather than an
  arbitrary target count.
- c-TF-IDF keyword extraction uses a custom stopword list on top of sklearn's English
  list, because generic restaurant-review filler ("food", "restaurant", "place",
  "order") appears in nearly every review and would otherwise dominate every topic's
  label without adding any separating signal. Bigrams are included so complaint
  phrases ("cold food", "slow service") survive as single features.
- Outlier reduction: HDBSCAN assigns a "-1 / noise" bucket by default. Reviews land
  there via reduce_outliers(..., strategy="embeddings") rather than being silently
  dropped from the topic breakdown.
- UMAP is seeded (random_state=42) so re-running this script is reproducible.
"""

import json
import os

from bertopic import BERTopic
from hdbscan import HDBSCAN
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, CountVectorizer
from sqlalchemy import text
from umap import UMAP

from db.retry import bulk_upsert, write_batches
from db.session import get_session

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
MIN_TOPIC_SIZE = 30
MODELS_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")
MODEL_DIR = os.path.join(MODELS_ROOT, "topic_model")
ASSIGNMENTS_CACHE = os.path.join(MODELS_ROOT, "topic_assignments.json")

DOMAIN_STOPWORDS = {
    "food", "restaurant", "place", "order", "ordered", "ordering",
    "got", "went", "came", "really", "definitely", "also", "one",
    "would", "us", "ve", "didn", "don", "time", "just", "get",
}
ALL_STOPWORDS = list(ENGLISH_STOP_WORDS.union(DOMAIN_STOPWORDS))


def fetch_reviews(session):
    rows = session.execute(
        text("SELECT id, review_text FROM reviews_raw ORDER BY id")
    ).fetchall()
    return rows


def build_topic_model():
    vectorizer_model = CountVectorizer(
        stop_words=ALL_STOPWORDS, ngram_range=(1, 2), min_df=5
    )
    umap_model = UMAP(
        n_neighbors=15, n_components=5, min_dist=0.0, metric="cosine", random_state=42
    )
    hdbscan_model = HDBSCAN(
        min_cluster_size=MIN_TOPIC_SIZE,
        metric="euclidean",
        cluster_selection_method="eom",
        prediction_data=True,
    )
    return BERTopic(
        vectorizer_model=vectorizer_model,
        umap_model=umap_model,
        hdbscan_model=hdbscan_model,
        nr_topics="auto",
        calculate_probabilities=False,
        verbose=True,
    )


def topic_label(topic_model, topic_id, nr_words=4):
    if topic_id == -1:
        return "Other / Uncategorized"
    words = [w for w, _ in topic_model.get_topic(topic_id)][:nr_words]
    return ", ".join(words) if words else "Other / Uncategorized"


def upsert_topics(session, payload):
    rows = [(p["review_id"], p["topic_id"], p["topic_label"]) for p in payload]
    bulk_upsert(
        session,
        """
        INSERT INTO reviews_processed (review_id, topic_id, topic_label)
        VALUES %s
        ON CONFLICT (review_id) DO UPDATE
        SET topic_id = EXCLUDED.topic_id,
            topic_label = EXCLUDED.topic_label
        """,
        rows,
    )


def write_assignments(payload):
    return write_batches(upsert_topics, payload)


def compute_and_cache():
    """Run the expensive part (encode, cluster, reduce outliers) once, then
    save the model and the resulting assignments to disk before touching the
    DB at all. This way a DB hiccup during the write never costs a recompute."""
    session = get_session()
    rows = fetch_reviews(session)
    session.close()
    print(f"Fetched {len(rows)} reviews.")

    # Fit on substantive text only; very short reviews (<15 chars) are still
    # assigned a topic afterward via transform(), just not used to shape the clusters.
    fit_rows = [r for r in rows if r.review_text and len(r.review_text) >= 15]
    print(f"Fitting on {len(fit_rows)} reviews (excluding {len(rows) - len(fit_rows)} too-short).")

    print(f"Encoding with {EMBEDDING_MODEL_NAME}...")
    embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)
    fit_texts = [r.review_text for r in fit_rows]
    fit_embeddings = embedder.encode(fit_texts, show_progress_bar=True, batch_size=128)

    print("Fitting BERTopic...")
    topic_model = build_topic_model()
    topics, _ = topic_model.fit_transform(fit_texts, embeddings=fit_embeddings)

    n_topics = len(set(topics) - {-1})
    n_outliers = sum(1 for t in topics if t == -1)
    print(f"Discovered {n_topics} topics before outlier reduction ({n_outliers} outliers).")

    print("Reducing outliers...")
    topics = topic_model.reduce_outliers(fit_texts, topics, strategy="embeddings", embeddings=fit_embeddings)
    topic_model.update_topics(fit_texts, topics=topics, vectorizer_model=topic_model.vectorizer_model)

    n_topics_final = len(set(topics) - {-1})
    n_outliers_final = sum(1 for t in topics if t == -1)
    print(f"Final: {n_topics_final} topics, {n_outliers_final} still unassigned.")

    label_cache = {}

    def get_label(tid):
        if tid not in label_cache:
            label_cache[tid] = topic_label(topic_model, tid)
        return label_cache[tid]

    payload = [
        {"review_id": r.id, "topic_id": int(tid), "topic_label": get_label(int(tid))}
        for r, tid in zip(fit_rows, topics)
    ]

    # Assign topics to the too-short reviews via transform() on the fitted model.
    short_rows = [r for r in rows if not (r.review_text and len(r.review_text) >= 15)]
    if short_rows:
        print(f"Assigning topics to {len(short_rows)} short reviews...")
        short_texts = [r.review_text or "" for r in short_rows]
        short_embeddings = embedder.encode(short_texts, batch_size=128)
        short_topics, _ = topic_model.transform(short_texts, embeddings=short_embeddings)
        payload += [
            {"review_id": r.id, "topic_id": int(tid), "topic_label": get_label(int(tid))}
            for r, tid in zip(short_rows, short_topics)
        ]

    os.makedirs(MODELS_ROOT, exist_ok=True)
    topic_model.save(MODEL_DIR, serialization="safetensors", save_ctfidf=True, save_embedding_model=True)
    print(f"Model saved to {MODEL_DIR}")

    with open(ASSIGNMENTS_CACHE, "w") as f:
        json.dump(payload, f)
    print(f"{len(payload)} assignments cached to {ASSIGNMENTS_CACHE}")

    return payload


def run():
    if os.path.exists(ASSIGNMENTS_CACHE):
        print(f"Found cached assignments at {ASSIGNMENTS_CACHE} - skipping recompute, writing to DB only.")
        with open(ASSIGNMENTS_CACHE) as f:
            payload = json.load(f)
    else:
        payload = compute_and_cache()

    print(f"Writing {len(payload)} topic assignments to reviews_processed...")
    write_assignments(payload)

    os.remove(ASSIGNMENTS_CACHE)
    print("Topic modeling complete.")


if __name__ == "__main__":
    run()
