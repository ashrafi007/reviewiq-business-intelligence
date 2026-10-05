# FastAPI Backend Progress (Step 5 / M7)

_Last updated: 2026-10-04_

## M7 — FastAPI: COMPLETE

All 6 spec'd endpoints built and **tested live** (dev server actually started, every endpoint hit with `curl` against the real database — not just code-reviewed). Run locally: `uvicorn api.main:app --reload`.

| Endpoint | Verified |
|---|---|
| `GET /api/businesses` | ✅ returns all 50 businesses |
| `GET /api/overview?business_id=X` | ✅ avg_rating, avg_sentiment, topic_distribution, top_complaints, rating_forecast, suspicious_count |
| `GET /api/reviews?business_id=X&sentiment=&topic_id=&suspicious_only=&page=` | ✅ filtering + pagination confirmed (sentiment filter, suspicious_only filter both tested) |
| `GET /api/compare?ids=1,2,3` | ✅ side-by-side stats for multiple businesses |
| `GET /api/trends?business_id=X` | ✅ weekly_stats, topic_trends (month-over-month), forecast |
| `GET /api/complaints?business_id=X` | ✅ complaint counts + 3 example reviews each |
| `POST /api/chat` | ✅ calls `rag.chatbot.ask()` directly, real Groq round-trip confirmed working through the API layer |

404 handling and CORS (`allow_origins=["*"]` per spec) both verified with real requests.

### Deviations from the spec, with reasoning

- **`topic=delivery` style filtering → `topic_id` (integer), not a label string.** The spec's example filter value ("delivery") assumes aspect-based topics (Food/Service/Delivery/Price/...). Our topics are fully unsupervised (M3, user's explicit choice) and turned out mostly cuisine-based ("pizza, slice, crust, nyc"), not aspect-based — see `.CLAUDE/nlp_progress.md`. A free-text label filter would be fragile against auto-generated keyword-joined labels; `topic_id` is the actual primary key and unambiguous.
- **`/api/overview` and `/api/compare` return both `avg_scraped_rating` (computed from our own `reviews_raw.review_rating`) and the business's original `overall_rating`** (Google's all-time rating, from `businesses` table, based on far more reviews than we scraped per restaurant). Spec only mentioned "avg_rating" singular; kept both since they can differ meaningfully (e.g. Joe's Pizza: Google shows 4.4★ lifetime, our 338 scraped reviews average 4.44★) and collapsing to one would hide that distinction.
- **`is_suspicious` is included directly on every review row in `/api/reviews`**, not gated behind a separate check — matches spec's "red border + ⚠️ badge" UI description, which needs the flag on every row regardless of the `suspicious_only` filter state.

### Known data quirks surfaced through the API (not bugs in this layer — inherited from earlier steps)
- `review_rating: null` appears in some review rows — the 318 reviews (2.6%) with unparseable star ratings from scraping (see `.CLAUDE/ml_progress.md`). Frontend should handle a null rating gracefully (e.g. "rating unknown", same fix already applied in `rag/chatbot.py`).
- `topic_trends.pct_change` can be `null` when `last_month` count is 0 (division by zero avoided deliberately, not an error).

## Not started yet
- M8 — React dashboard (5 pages, consumes these endpoints)
- M9 — GitHub Actions weekly cron

## Key files
- `api/main.py` — FastAPI app, CORS, all 6 route handlers (thin — parse params, call queries.py, return).
- `api/queries.py` — all the actual SQL/query logic, kept separate from routing for readability/testability.
