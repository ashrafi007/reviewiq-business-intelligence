"""
Production entry point for the weekly cron: scores reviews for is_suspicious
with the already-trained model, and refits each restaurant's rating
forecast. This is the "run" half of ml/notebooks/model_development.ipynb -
that notebook stays the "train/explore" half; this script never retrains
anything, it only applies what's already been fit and saved.

Fake-review scoring: re-scores ALL reviews (not just new ones) every run.
With ~12k reviews this takes well under a second - cheaper and simpler than
tracking which reviews are "already scored", and avoids a scored/unscored
split ever drifting out of sync with a model file that gets swapped out.

Rating forecast: refreshes weekly_stats then refits Prophet per business.
Logistic growth (cap=5, floor=1) and disabled auto-seasonality - see
ml/notebooks/model_development.ipynb's prophet_example cell for the full
writeup of why (unconstrained growth produced forecasts up to 89.7 on a 1-5
scale; auto-seasonality then caused floor/cap snapping even after bounding
growth). Safe to re-run; upserts on (business_id, week).
"""

import logging
import os
import re

import joblib
import pandas as pd
from prophet import Prophet
from sqlalchemy import text

from db.retry import bulk_upsert
from db.session import get_session

logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
logging.getLogger("prophet").setLevel(logging.WARNING)
os.environ.setdefault("CMDSTANPY_LOGGING_LEVEL", "WARNING")

MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "fake_review_model_v2.pkl")

SUPERLATIVES = {
    "amazing", "incredible", "perfect", "best", "worst", "terrible", "awful",
    "horrible", "disgusting", "fantastic", "outstanding", "exceptional",
    "phenomenal", "unbelievable", "never", "always",
}
GENERIC_PHRASES = [
    "best ever", "worst experience", "highly recommend", "never again",
    "would not recommend", "highly recommended", "will definitely",
    "never going back", "waste of money", "waste of time",
]

MIN_WEEKS = 8
FORECAST_PERIODS = 4
RATING_FLOOR = 1.0
RATING_CAP = 5.0


# --- Fake-review scoring -----------------------------------------------

def features_v1(t):
    t = t or ""
    length = len(t)
    exclaims = t.count("!")
    letters = [c for c in t if c.isalpha()]
    caps_ratio = (sum(1 for c in letters if c.isupper()) / len(letters)) if letters else 0.0
    return length, exclaims, caps_ratio


def features_v2(t):
    t = t or ""
    tl = t.lower()
    words = t.split()
    word_count = len(words)
    avg_word_len = (sum(len(w) for w in words) / word_count) if word_count else 0.0
    superlative_count = sum(1 for w in re.findall(r"[a-z]+", tl) if w in SUPERLATIVES)
    all_caps_words = sum(1 for w in words if len(w) > 2 and w.isupper())
    repeated_punct = len(re.findall(r"(!!+|\?\?+|\.\.\.+)", t))
    generic_phrase_count = sum(1 for p in GENERIC_PHRASES if p in tl)
    return word_count, avg_word_len, superlative_count, all_caps_words, repeated_punct, generic_phrase_count


def build_features(review_text, complaints, entities):
    length, exclaims, caps_ratio = features_v1(review_text)
    word_count, avg_word_len, superlative_count, all_caps_words, repeated_punct, generic_phrase_count = features_v2(review_text)
    return {
        "text_length": length,
        "exclamation_count": exclaims,
        "caps_ratio": caps_ratio,
        "complaint_count": len(complaints or []),
        "entity_count": len(entities or []),
        "word_count": word_count,
        "avg_word_len": avg_word_len,
        "superlative_count": superlative_count,
        "all_caps_words": all_caps_words,
        "repeated_punct": repeated_punct,
        "generic_phrase_count": generic_phrase_count,
    }


def score_suspicious(session):
    if not os.path.exists(MODEL_PATH):
        print(f"No model at {MODEL_PATH} - skipping fake-review scoring.")
        return

    bundle = joblib.load(MODEL_PATH)
    model, threshold, feature_names = bundle["model"], bundle["threshold"], bundle["features"]

    rows = session.execute(
        text(
            """
            SELECT r.id AS review_id, r.review_text, rp.complaints, rp.entities
            FROM reviews_raw r
            JOIN reviews_processed rp ON rp.review_id = r.id
            """
        )
    ).fetchall()
    if not rows:
        print("No reviews to score.")
        return

    feature_rows = [build_features(r.review_text, r.complaints, r.entities) for r in rows]
    X = [[f[name] for name in feature_names] for f in feature_rows]
    proba = model.predict_proba(X)[:, 1]
    preds = proba >= threshold

    payload = [(r.review_id, bool(p)) for r, p in zip(rows, preds)]
    bulk_upsert(
        session,
        """
        INSERT INTO reviews_processed (review_id, is_suspicious)
        VALUES %s
        ON CONFLICT (review_id) DO UPDATE SET is_suspicious = EXCLUDED.is_suspicious
        """,
        payload,
    )
    print(f"Scored {len(payload)} reviews, {sum(p for _, p in payload)} flagged suspicious.")


# --- Rating forecast -----------------------------------------------------
#
# Prophet.fit() is slow enough (whole seconds per restaurant, ~50 restaurants)
# that holding one DB connection open across the whole loop risks it going
# idle long enough for Supabase to drop it mid-loop (observed directly: two
# separate runs died with "server closed the connection unexpectedly" at
# different points in the loop). Fixed by doing all DB reads up front in one
# query - the slow Prophet fitting then happens entirely in memory, no DB
# connection held open during it - and one DB write at the end.


def fetch_all_weekly_series(session):
    """One query for every business's weekly history, instead of one query
    per business - see module-level note above for why."""
    rows = session.execute(
        text("SELECT business_id, week, avg_rating FROM weekly_stats ORDER BY business_id, week")
    ).fetchall()
    by_business = {}
    for business_id, week, avg_rating in rows:
        by_business.setdefault(business_id, []).append((week, avg_rating))

    series = {}
    for business_id, week_rows in by_business.items():
        df = pd.DataFrame(week_rows, columns=["ds", "y"])
        df["ds"] = pd.to_datetime(df["ds"]).dt.tz_localize(None)
        df["cap"] = RATING_CAP
        df["floor"] = RATING_FLOOR
        series[business_id] = df
    return series


def fit_one_forecast(business_id, df):
    model = Prophet(
        growth="logistic",
        changepoint_prior_scale=0.01,
        yearly_seasonality=False,
        weekly_seasonality=False,
        daily_seasonality=False,
        seasonality_mode="additive",
    )
    model.fit(df)
    future = model.make_future_dataframe(periods=FORECAST_PERIODS, freq="W")
    future["cap"] = RATING_CAP
    future["floor"] = RATING_FLOOR
    forecast = model.predict(future)
    future_only = forecast[forecast["ds"] > df["ds"].max()]
    return [
        {
            "business_id": business_id,
            "week": row["ds"].date(),
            "yhat": float(min(max(row["yhat"], RATING_FLOOR), RATING_CAP)),
            "yhat_lower": float(min(max(row["yhat_lower"], RATING_FLOOR), RATING_CAP)),
            "yhat_upper": float(min(max(row["yhat_upper"], RATING_FLOOR), RATING_CAP)),
        }
        for _, row in future_only.iterrows()
    ]


def upsert_forecasts(session, payload):
    rows = [(p["business_id"], p["week"], p["yhat"], p["yhat_lower"], p["yhat_upper"]) for p in payload]
    bulk_upsert(
        session,
        """
        INSERT INTO forecasts (business_id, week, yhat, yhat_lower, yhat_upper)
        VALUES %s
        ON CONFLICT (business_id, week) DO UPDATE
        SET yhat = EXCLUDED.yhat, yhat_lower = EXCLUDED.yhat_lower, yhat_upper = EXCLUDED.yhat_upper
        """,
        rows,
    )


def refit_forecasts():
    session = get_session()
    session.execute(text("REFRESH MATERIALIZED VIEW weekly_stats;"))
    session.commit()
    series = fetch_all_weekly_series(session)
    total_businesses = session.execute(text("SELECT COUNT(*) FROM businesses")).scalar()
    session.close()

    payload = []
    skipped = 0
    for business_id, df in series.items():
        if len(df) < MIN_WEEKS:
            skipped += 1
            continue
        payload.extend(fit_one_forecast(business_id, df))

    session = get_session()
    try:
        upsert_forecasts(session, payload)
    finally:
        session.close()
    print(f"Wrote {len(payload)} forecast rows ({total_businesses - skipped}/{total_businesses} businesses, {skipped} skipped for < {MIN_WEEKS} weeks of history).")


def run():
    session = get_session()
    try:
        score_suspicious(session)
    finally:
        session.close()
    refit_forecasts()


if __name__ == "__main__":
    run()
