"""
Sentiment analysis over reviews_raw -> reviews_processed.

Model: cardiffnlp/twitter-roberta-base-sentiment (pretrained, no fine-tuning).
LABEL_0 = negative, LABEL_1 = neutral, LABEL_2 = positive.

sentiment_score is mapped to -1.0..+1.0 as (P(positive) - P(negative)),
which is more informative than the pipeline's raw top-label confidence.
"""

import torch
from sqlalchemy import text
from tqdm import tqdm
from transformers import pipeline

from db.retry import bulk_upsert
from db.session import get_session

MODEL_NAME = "cardiffnlp/twitter-roberta-base-sentiment"
LABEL_MAP = {"LABEL_0": "negative", "LABEL_1": "neutral", "LABEL_2": "positive"}
BATCH_SIZE = 50


def get_device():
    if torch.cuda.is_available():
        return 0
    if torch.backends.mps.is_available():
        return "mps"
    return -1


def load_pipeline():
    return pipeline(
        "sentiment-analysis",
        model=MODEL_NAME,
        tokenizer=MODEL_NAME,
        top_k=None,
        truncation=True,
        max_length=512,
        device=get_device(),
    )


def score_texts(pipe, texts):
    results = pipe(texts, batch_size=BATCH_SIZE)
    scored = []
    for review_scores in results:
        scores = {LABEL_MAP[r["label"]]: r["score"] for r in review_scores}
        label = max(scores, key=scores.get)
        sentiment_score = scores["positive"] - scores["negative"]
        scored.append((label, sentiment_score))
    return scored


def fetch_pending(session, limit):
    return session.execute(
        text(
            """
            SELECT r.id, r.review_text
            FROM reviews_raw r
            LEFT JOIN reviews_processed rp ON rp.review_id = r.id
            WHERE rp.sentiment_label IS NULL
            ORDER BY r.id
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).fetchall()


def upsert_sentiment(session, rows_with_scores):
    rows = [(r["review_id"], r["label"], r["score"]) for r in rows_with_scores]
    bulk_upsert(
        session,
        """
        INSERT INTO reviews_processed (review_id, sentiment_label, sentiment_score)
        VALUES %s
        ON CONFLICT (review_id) DO UPDATE
        SET sentiment_label = EXCLUDED.sentiment_label,
            sentiment_score = EXCLUDED.sentiment_score
        """,
        rows,
    )


def run(batch_size=BATCH_SIZE):
    session = get_session()
    total = session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM reviews_raw r
            LEFT JOIN reviews_processed rp ON rp.review_id = r.id
            WHERE rp.sentiment_label IS NULL
            """
        )
    ).scalar()

    if total == 0:
        print("No pending reviews — sentiment already up to date.")
        return

    print(f"{total} reviews pending sentiment analysis. Loading model...")
    pipe = load_pipeline()

    with tqdm(total=total, desc="Sentiment") as pbar:
        while True:
            rows = fetch_pending(session, batch_size)
            if not rows:
                break
            texts = [r.review_text or "" for r in rows]
            scored = score_texts(pipe, texts)
            payload = [
                {"review_id": r.id, "label": label, "score": score}
                for r, (label, score) in zip(rows, scored)
            ]
            upsert_sentiment(session, payload)
            pbar.update(len(rows))

    session.close()
    print("Sentiment analysis complete.")


if __name__ == "__main__":
    run()
