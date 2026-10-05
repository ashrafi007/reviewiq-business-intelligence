# ML Models Progress (Step 3 / M5)

_Last updated: 2026-10-04_

## Structural note: notebook, not scripts

Per explicit user request, both models now live in **`ml/notebooks/model_development.ipynb`** instead of standalone `.py` scripts. `ml/fake_review_detector.py` and `ml/rating_forecast.py` were deleted (not archived) after the notebook was built and validated. **If M9 (GitHub Actions weekly cron) needs to re-run these models on a schedule, they'll need to be rewritten as scripts (or run headlessly via `jupyter nbconvert --execute`)** — flagged to the user at the time, they chose notebook-only anyway. Don't assume the old scripts still exist.

## ML Model 1 — Fake Review Detector (XGBoost): COMPLETE, v2 deployed

All 12,043 reviews scored, `is_suspicious` written to `reviews_processed`. Model saved to `ml/models/fake_review_model_v2.pkl` (dict with `model`, `threshold`, `features` keys — threshold matters, see below).

**v1 — fixed a label-leakage bug in the spec before building anything.** The spec's rule-based label is:
```
is_suspicious = (sentiment_score < -0.3 AND review_rating >= 4) OR (sentiment_score > 0.3 AND review_rating <= 2)
```
but the spec's feature list included `sentiment_score` and `review_rating` as two of the 8 model inputs — training on the exact two columns that define the label would let XGBoost trivially re-derive the threshold rule (~100% accuracy, zero actual signal learned). Fixed: train on **writing-style features only**, never on sentiment_score/review_rating. Also dropped `is_verified` (reviewer profile photo) — never scraped, not in `reviews_raw`.

v1 features (5): `text_length`, `exclamation_count`, `caps_ratio`, `complaint_count`, `entity_count`.
v1 results: PR-AUC 0.027, precision 0.03 / recall 0.25 at default threshold — honest (no leakage) but weak.

**v2 — feature engineering pass, built and deployed in the notebook.** Added 6 more non-leaky stylistic features: `word_count`, `avg_word_len`, `superlative_count` (curated word list: amazing/terrible/perfect/worst/...), `all_caps_words`, `repeated_punct` (`!!+`, `??+`, `...+`), `generic_phrase_count` (curated template-phrase list: "highly recommend", "never again", "waste of money"...). Also tuned the decision threshold via precision-recall curve instead of using the default 0.5.

**v2 results (real, measured — not inflated):**
- PR-AUC: 0.027 → **0.036** (+34% relative, the right metric for this 1.5% class imbalance)
- Precision at best-F1 threshold: 0.043 → **0.077** (nearly doubled)
- Tuned threshold: **0.791** (not the default 0.5 — must be loaded alongside the model; it's saved in the same `.pkl` dict)
- Final deployed flag rate: **315 / 12,043 (2.6%)** flagged suspicious — far more credible for a dashboard than v1's 1,915 (15.9%), which was implausibly high
- Feature importance (v2): exclamation_count (0.25) > generic_phrase_count (0.14) ≈ superlative_count (0.14) > avg_word_len (0.08) > caps_ratio ≈ text_length (0.07 each) > entity_count (0.06) ≈ all_caps_words (0.06) ≈ word_count (0.05) > repeated_punct ≈ complaint_count (0.04 each)

**Data quality note (applies to both v1 and v2):** 318 / 12,043 reviews (2.6%) have `review_rating IS NULL` (scraper's star-rating regex occasionally missed on the Google Maps DOM). Excluded from training (no ground truth available) but still scored by the fitted model — scoring only needs the style features, not rating/sentiment.

**For the dashboard:** still present `is_suspicious` as an experimental/weak signal, not a confident fraud detector — v2 is a real, explainable improvement (generic phrases and superlatives genuinely correlate with the mismatch label) but the underlying task remains hard on a 1.5% base rate. Don't oversell it.

## ML Model 2 — Rating Forecast (Prophet): COMPLETE

All 50 businesses forecasted, next 4 weeks each (200 rows total) in the `forecasts` table (`business_id`, `week`, `yhat`, `yhat_lower`, `yhat_upper`).

Reads `weekly_stats` (materialized view, refreshed at the start of each run — it does NOT auto-update when `reviews_processed` changes). Every business had well over the spec's 8-week minimum (worst case: 9 distinct weeks) because `week` is derived from each review's actual posted date, not from when we scraped — most businesses have 15-25 weeks of real history. No businesses needed to be skipped.

**Design choice:** only the 4 future predicted weeks are written to `forecasts`, not Prophet's in-sample fit — `weekly_stats` already holds the real historical `avg_rating`, so storing fitted-not-actual values for the past would just be a redundant, lossier copy.

**Bug fixed:** Prophet rejects timezone-aware `ds` columns (`ValueError: Column ds has timezone specified`). The `week` column coming back from `DATE_TRUNC('week', review_date)` via SQLAlchemy/psycopg2 carries tz info that pandas picks up; fixed with `pd.to_datetime(df["ds"]).dt.tz_localize(None)`.

**Process note on apparent "hangs":** mid-run, progress looked stalled (CPU time on the main Python process barely moving for minutes). This was **not a bug** — Prophet's actual MCMC/optimization work happens in a separate compiled Stan binary subprocess (`prophet/stan_model/prophet_model.bin`), invisible to `ps` on the parent PID. Checking `pgrep -P <main_pid>` revealed the real worker process actively burning CPU. If a future script built on Prophet looks stuck, check for stan subprocess children before assuming a dead connection or infinite loop.

**Bug found during M8 browser verification, fixed 2026-10-04:** the original unconstrained linear-growth Prophet config (`changepoint_prior_scale=0.1`, default seasonality) produced forecasts up to 89.7 on a 1-5 star scale — ratings have no real trend/seasonal signal to extract from 9-25 sparse, irregularly-spaced weekly points spanning years, and Prophet extrapolated garbage. Fixed with `growth="logistic"` (`cap=5, floor=1`), all auto-seasonality disabled, and `changepoint_prior_scale` dropped to 0.01. Full writeup and before/after numbers in `.CLAUDE/dashboard_progress.md`. All 200 forecast rows now verified within [1, 5], max week-to-week change 0.02 stars.

The notebook's Prophet section has the full 50-restaurant loop commented out (already re-run once for real with the corrected model; commented to avoid an accidental multi-minute rerun on every notebook execution) with the real stored result for one example restaurant shown live instead. Uncomment to force a full rerun — it's idempotent (upserts on `(business_id, week)`).

**M5 (both ML models) is fully complete, including the v2 improvement pass.**

## Not started yet
- M6 — RAG chatbot (needs `GROQ_API_KEY`, still empty in `.env`)
- M7-M9 — FastAPI, React dashboard, GitHub Actions cron (**note:** M9 will need these models as scripts again, or nbconvert — see structural note above)

## Key files
- `ml/notebooks/model_development.ipynb` — **the only source of truth for both models now.** 18 cells, real embedded outputs from an actual run against the live DB (not fabricated/placeholder output). Re-running cells top-to-bottom is safe/idempotent (all writes are upserts).
- `ml/models/fake_review_model_v2.pkl` — joblib dict: `{"model": XGBClassifier, "threshold": 0.791, "features": [...]}`. Must use the saved threshold, not 0.5, when scoring new reviews.
- `db/models.py` — added `Forecast` (table `forecasts`, unique on `(business_id, week)` for safe upserts).
