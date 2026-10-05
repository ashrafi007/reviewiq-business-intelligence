# ReviewIQ

Restaurant review intelligence platform for 50 NYC restaurants (~12,000 Google Maps reviews): sentiment analysis, unsupervised topic modeling, complaint/entity extraction, a fake-review detector, a rating forecast, and a RAG chatbot grounded in the actual reviews — all surfaced through a React dashboard.

**Live:**
- Dashboard: https://frontend-amber-three-74.vercel.app
- API: https://reviewiq-api-shoc.onrender.com ([docs](https://reviewiq-api-shoc.onrender.com/docs))

> Backend is on Render's free tier and sleeps after 15 min idle — the first request after a while takes 30-60s to wake up.

## What it does

- **Overview** — rating, sentiment score, topic breakdown, top complaints, 4-week rating forecast, owner-response impact
- **Review Feed** — filterable/paginated review browser (sentiment, topic, rating, date, flagged)
- **Competitors** — side-by-side comparison of up to 3 restaurants, radar chart across 5 aspects (food/service/price/ambiance/packaging) derived from the complaint taxonomy
- **Trends** — sentiment/rating history + forecast, topic mentions month-over-month, day-of-week review volume
- **Chatbot** — ask natural-language questions about a restaurant's reviews, answers grounded in and cited from the actual review text

## Architecture

```
scraper/   Playwright scraper (Google Maps) → businesses, reviews_raw
nlp/       sentiment, topic modeling (BERTopic), complaints/entities, embeddings
ml/        fake-review detector (XGBoost) + rating forecast (Prophet)
rag/       chatbot: pgvector similarity search + Groq LLM
api/       FastAPI backend, 7 endpoints over everything above
frontend/  React + Vite dashboard
db/        SQLAlchemy models, schema, connection/retry helpers
```

Data flows one direction: scrape → NLP → ML → Postgres, and the API/dashboard only ever read what's already been computed — no model runs at request time except embedding the chatbot's question.

## Tech stack

| Layer | Tech |
|---|---|
| Scraping | Playwright (Python), playwright-stealth |
| Database | PostgreSQL + pgvector, hosted on Supabase |
| NLP | HuggingFace Transformers (sentiment), BERTopic (UMAP + HDBSCAN), sentence-transformers |
| ML | XGBoost (fake-review detector), Prophet (rating forecast) |
| RAG | pgvector cosine search + Groq (`openai/gpt-oss-120b`) |
| API | FastAPI |
| Frontend | React, Vite, TailwindCSS, Recharts, react-router-dom |
| Automation | GitHub Actions (weekly cron) |
| Deployment | Render (API), Vercel (frontend) |

## API endpoints

`GET /api/businesses` · `GET /api/overview` · `GET /api/reviews` · `GET /api/compare` · `GET /api/trends` · `GET /api/complaints` · `POST /api/chat` · `GET /health`

## Local development

```bash
# Backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt          # full pipeline (scraper + NLP + ML + API)
# or: pip install -r requirements-api.txt  # just the API, if you're not touching the pipeline
cp .env.example .env                     # fill in DATABASE_URL, GROQ_API_KEY
python -m db.create_tables               # one-time schema setup
uvicorn api.main:app --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run dev                              # proxies /api to localhost:8000
```

### Running the pipeline

```bash
python -m scraper.google_maps_scraper 50   # scrape all 50 restaurants
python -m nlp.sentiment
python -m nlp.topic_model                  # full fit; add --incremental for new-reviews-only
python -m nlp.complaint_extractor
python -m nlp.embeddings
python -m nlp.topic_labels                 # clean display names for topics (needs GROQ_API_KEY)
python -m ml.run_models                    # score fake-review flags, refit forecasts
```

ML model training/exploration lives in `ml/notebooks/model_development.ipynb`; `ml/run_models.py` only applies what's already trained there.

## Automation

`.github/workflows/scrape.yml` runs the full pipeline weekly (Sunday, UTC) via GitHub Actions: scrape → sentiment → topic assignment → complaints → embeddings → ML scoring/forecast → CSV export. Needs `DATABASE_URL` and `GOOGLE_AUTH_STATE` repo secrets — see `.CLAUDE/automation_progress.md` for setup.

## Known limitations

- **Fake-review detector** (`is_suspicious` / "unusual-style" badge) is a real but weak signal — ~8% precision on its tuned threshold. Shown in the UI as an experimental flag, not a confident fraud detector.
- **Topic clustering** is fully unsupervised across 6 cuisines, so most discovered topics are cuisine/dish identity rather than aspect categories (service/price/ambiance), and a few small clusters are driven by one restaurant's name or a specific staff member rather than a general theme.

Full build history, bugs found/fixed, and design decisions are in `.CLAUDE/*_progress.md`.
