# React Dashboard Progress (Step 6 / M8)

_Last updated: 2026-10-05_

## Post-launch fixes (2026-10-05)

- **Chatbot showing irrelevant sources** — fixed in `rag/chatbot.py`, see `.CLAUDE/rag_progress.md`.
- **Topic labels were raw keyword tokens** (e.g. "burger, burgers, fries, best") — fixed via new `nlp/topic_labels.py` + `topic_labels` DB table, see `.CLAUDE/backlog.md` item 2. Affects Overview's topic donut, Review Feed's topic badges/filter, Trends' topic-trend list — all now show clean names like "Best Burgers & Fries".
- **"Suspicious reviews" UI reframed** to "Unusual-style reviews" with honest ~8% precision copy + tooltip, red→amber styling — see `.CLAUDE/backlog.md` item 1. No model change, UI/copy only.

## M8 — React Dashboard: COMPLETE

All 5 pages built and **visually verified in a real browser** (Vite dev server + FastAPI backend both running live, navigated through every page with claude-in-chrome, clicked real controls, confirmed real network responses) — not just code-reviewed. Run locally: `uvicorn api.main:app --reload` (backend) + `npm run dev` in `frontend/` (frontend, proxies `/api` to `127.0.0.1:8000`).

| Page | Verified |
|---|---|
| Overview | ✅ stat cards, sentiment gauge, topic donut chart, top complaints, owner-response insight banner |
| Review Feed | ✅ filters (sentiment/topic/rating/date/suspicious), pagination, flagged badge, complaint tags |
| Competitors | ✅ up to 3 businesses, radar chart (aspect scores), bar chart (rating), rank text |
| Trends | ✅ weekly sentiment line, rating + 4-week-forecast line, topic trend deltas, day-of-week heatmap |
| Chatbot | ✅ dark theme, suggested-question chips, live Groq round-trip, source review cards, markdown bold rendering |

### Backend additions made to support M8
- `api/queries.py::get_aspect_scores()` / `ASPECT_COMPLAINT_MAP` — the spec's radar-chart axes (Food Quality / Service / Delivery / Price / Ambiance) don't map onto our topics (cuisine-based, not aspect-based — see `.CLAUDE/nlp_progress.md`), but they map cleanly onto the complaint taxonomy. Aspect score = `100 * (1 - that aspect's complaint rate)`. Added to `get_compare()`'s response as `aspect_scores`.
- `get_trends()` extended with `day_of_week` — `EXTRACT(DOW FROM review_date)` aggregation (count + avg rating + avg sentiment per weekday), for the Trends page's heatmap. Not in the original `get_trends()` from M7.

### Bugs found and fixed during browser verification (not caught by code review alone)
1. **Topic donut chart rendered completely empty** (`Overview.jsx`). Root cause: `npm install recharts` had pulled **recharts v3.10.1** (a recent major rewrite) while all chart code was written against the stable v2 API. In v3, `Pie` sectors mounted as empty `<g>` wrappers with no `<path>` — zero rendering, no console error. Fixed by pinning `recharts` back to `^2.15.0` (`package.json`), which also covers the Radar/Line/Bar charts used on Competitors and Trends (untested under v3 but same risk).
2. **Chatbot source cards showed blank date/text, only "rating unknown.**" Field-name mismatch: `rag/chatbot.py::ask()` returns `{date, rating, text, sentiment, similarity}` but `Chatbot.jsx` was reading `review_date`/`review_rating`/`review_text`. Fixed to match the existing (M6) API contract.
3. **Chat answers showed raw `**bold**` markdown syntax.** Groq's responses use markdown; added a small regex-based bold renderer (`renderMarkdownBold`) rather than pulling in a full markdown library for one feature.
4. **Trends charts showed raw ISO timestamps on the x-axis** (`2020-09-28T00:00:00+00:00`). Added `tickFormatter`/`labelFormatter` to slice to `YYYY-MM-DD`.

### Prophet rating-forecast bug — found during M8 verification, fixed same session (2026-10-04)
- **Symptom:** the 4-week rating forecast showed nonsensical values (e.g. 66.8★, 89.7★ for a 1–5★ rating).
- **Root cause:** `weekly_stats` buckets reviews by the calendar week of their actual posted date, and real review history per restaurant is sparse (9–25 points) and irregular — gaps of months to years between buckets. Prophet's default unconstrained linear growth (`changepoint_prior_scale=0.1`) extrapolated that trend forward unbounded over the 4-week horizon.
- **Fix (`ml/notebooks/model_development.ipynb`, `prophet_setup`/`prophet_full` cells), re-run for real against the live DB:**
  1. `growth="logistic"` with `cap=5, floor=1` — ratings can't structurally leave that range.
  2. That alone caused a *second* failure (~30/50 businesses' forecasts snapped straight to the 1.0 floor or 5.0 cap within 1–2 weeks, even with flat 4.5–5.0 history) — traced to Prophet's default `yearly_seasonality="auto"` fitting a spurious yearly cycle from as few as 9 points spread over up to 9 years. Disabled all auto-seasonality and dropped `changepoint_prior_scale` to 0.01.
  3. Defensive `float(min(max(yhat, 1.0), 5.0))` clip on write, since a star rating can never leave [1, 5] by definition.
- **Verified:** all 200 forecast rows (4 weeks × 50 businesses) now fall strictly within [1, 5]; largest week-to-week change across all 50 restaurants is 0.02 stars (previously: wild unbounded growth, or floor/cap snapping). Spot-checked live via the API and in the browser (Overview + Trends pages) — e.g. "5 Napkin Burger" went from a reported 66.8★ forecast to a stable 4.6★, matching its actual ~4.6–4.74★ ratings.
- `Trends.jsx`'s `allowDataOverflow`/`domain={[1,5]}` on the forecast chart is kept as a defensive display bound, but is no longer load-bearing — the stored data is correct now.

## Not started yet
- M9 — GitHub Actions weekly cron (will also need to account for ML being notebook-only now — see `.CLAUDE/ml_progress.md`)

## Key files
- `frontend/src/pages/{Overview,ReviewFeed,Competitors,Trends,Chatbot}.jsx` — the 5 pages
- `frontend/src/context/BusinessContext.jsx` — global business selection (Context API)
- `frontend/src/api.js` — fetch wrappers for all 6 backend endpoints
- `frontend/src/components/{StatCard,SentimentGauge,Loading}.jsx` — shared UI
- `api/queries.py::get_aspect_scores`, `get_trends`'s `day_of_week` — backend additions made for this milestone
