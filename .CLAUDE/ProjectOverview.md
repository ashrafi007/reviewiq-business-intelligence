# ReviewIQ — USA Restaurant Review Intelligence & RAG Chatbot
## Full Project Specification & Build Guide

> **Stack:** Python · Playwright · PostgreSQL · pgvector · HuggingFace Transformers · BERTopic · spaCy · sentence-transformers · XGBoost · Prophet · Groq API · FastAPI · React · TailwindCSS · Recharts
> **Solo:** Ash
> **Target market:** USA restaurants — English only, clean data, global Fiverr buyers
> **Goal:** Live dashboard showing sentiment trends, complaint topics, ML rating forecast, and a RAG chatbot that answers natural language questions from real reviews — deployed free, portfolio-ready, Fiverr Gig 3

---

## 1. What This Project Does

Scrapes Google Maps reviews for NYC restaurants → runs NLP sentiment analysis on every review → extracts complaint topics automatically using BERTopic → trains two ML models (fake review detector + rating forecast) → stores everything in PostgreSQL with vector embeddings → serves insights via FastAPI → displays on a React dashboard with 5 pages + RAG chatbot.

**The hero feature:** Restaurant owner types "Why did my rating drop last month?" → chatbot searches the review database semantically → finds the most relevant reviews → passes them to Groq LLM → returns a specific answer grounded in real reviews.

**Why USA:**
- English only — no translation layer, no Banglish, no multilingual models
- Massive review volume — NYC restaurants have 1,000–5,000 reviews each
- US buyers on Fiverr pay $500–2,000 for this kind of tool
- Global positioning — not limited to BD market

---

## 2. Project Name

**ReviewIQ** — Restaurant Review Intelligence
GitHub slug: `reviewiq`
Live URL target: `reviewiq.vercel.app`
Demo niche: Manhattan, New York restaurants

---

## 3. Data Source

**Google Maps** — Playwright scraper (JS-heavy, no API needed)

**Target for demo:**
- 50 restaurants in Manhattan, NYC
- 200 reviews each minimum = 10,000+ reviews
- Categories: pizza, sushi, burger, indian, italian, chinese

**Fields to extract:**
```
business_name         → "Joe's Pizza"
business_category     → "pizza restaurant"
business_address      → "7 Carmine St, New York, NY"
business_rating       → 4.6  (overall star rating)
business_total_reviews→ 3,241
review_rating         → 1-5  (individual review)
review_text           → raw English text
review_date           → date
reviewer_name         → display name
has_owner_response    → True / False
scraped_at            → timestamp
listing_url           → Google Maps URL (unique key)
```

---

## 4. PostgreSQL + pgvector Schema

### Table 1 — `businesses`
```sql
CREATE TABLE businesses (
    id                  SERIAL PRIMARY KEY,
    name                TEXT,
    category            TEXT,
    address             TEXT,
    city                TEXT DEFAULT 'New York',
    overall_rating      FLOAT,
    total_reviews       INTEGER,
    listing_url         TEXT UNIQUE,
    scraped_at          TIMESTAMP DEFAULT NOW()
);
```

### Table 2 — `reviews_raw`
```sql
CREATE TABLE reviews_raw (
    id                  SERIAL PRIMARY KEY,
    business_id         INTEGER REFERENCES businesses(id),
    review_rating       INTEGER,        -- 1-5 stars
    review_text         TEXT,
    review_date         DATE,
    reviewer_name       TEXT,
    has_owner_response  BOOLEAN DEFAULT FALSE,
    scraped_at          TIMESTAMP DEFAULT NOW()
);
```

### Table 3 — `reviews_processed`
```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE reviews_processed (
    id                  SERIAL PRIMARY KEY,
    review_id           INTEGER REFERENCES reviews_raw(id),
    sentiment_label     TEXT,           -- positive | negative | neutral
    sentiment_score     FLOAT,          -- -1.0 to +1.0
    topic_id            INTEGER,        -- BERTopic cluster ID
    topic_label         TEXT,           -- "Food Quality" | "Delivery Speed" etc.
    complaints          TEXT[],         -- ["cold food", "slow service"]
    entities            TEXT[],         -- ["pizza", "pasta", "waiter"]
    is_suspicious       BOOLEAN DEFAULT FALSE,  -- ML fake review flag
    embedding           vector(384),    -- sentence-transformer embedding
    processed_at        TIMESTAMP DEFAULT NOW()
);
```

### Table 4 — `weekly_stats` (materialized view)
```sql
CREATE MATERIALIZED VIEW weekly_stats AS
SELECT
    r.business_id,
    DATE_TRUNC('week', r.review_date)   AS week,
    COUNT(r.id)                         AS review_count,
    AVG(r.review_rating)                AS avg_rating,
    AVG(rp.sentiment_score)             AS avg_sentiment
FROM reviews_raw r
JOIN reviews_processed rp ON rp.review_id = r.id
GROUP BY 1, 2;
```

---

## 5. Scraper

**Tool:** Playwright — Google Maps is JavaScript-rendered.
requests + BeautifulSoup will NOT work.

### Scrapy structure
```
reviewiq/
└── scraper/
    ├── google_maps_scraper.py   # main Playwright scraper
    ├── restaurant_urls.py       # list of 50 target Google Maps URLs
    └── scheduler.py             # APScheduler for local dev
```

### Key scraping logic
```python
SCRAPER_SETTINGS = {
    "headless": True,
    "slow_mo":  300,
    "viewport": {"width": 1280, "height": 800}
}

# Per restaurant:
# 1. Open Google Maps URL
# 2. Click "Reviews" tab
# 3. Sort by "Newest"
# 4. Scroll down repeatedly until all reviews loaded
# 5. Extract each review card: rating, text, date, reviewer
# 6. Insert to reviews_raw (skip if review already exists by text+date+business)
# 7. sleep(random.uniform(3, 6)) between businesses
```

### Anti-detection
```python
pip install playwright-stealth
from playwright_stealth import stealth_async
await stealth_async(page)

# Also:
# Rotate user agents
# Random scroll speeds
# Never scrape more than 20 businesses per session
```

### Scheduler (GitHub Actions — production)
```yaml
name: Weekly Review Scraper
on:
  schedule:
    - cron: '0 0 * * 0'   # Every Sunday midnight UTC
  workflow_dispatch:
jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: playwright install chromium
      - name: Run scraper
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
        run: python scraper/google_maps_scraper.py
```

**Target first run:** 10,000+ reviews across 50 NYC restaurants.

---

## 6. NLP Pipeline

Four tasks run on every review in `reviews_raw`.
Results stored in `reviews_processed`.

### Task 1 — Sentiment Analysis

**Model:** `cardiffnlp/twitter-roberta-base-sentiment`
Pre-trained on English. No fine-tuning needed.

```python
from transformers import pipeline

sentiment_pipe = pipeline(
    "sentiment-analysis",
    model="cardiffnlp/twitter-roberta-base-sentiment",
    device=0  # GPU if available, else remove
)

# LABEL_0 = negative, LABEL_1 = neutral, LABEL_2 = positive
# Map score to -1.0 → +1.0 range
```

**Output per review:**
```
sentiment_label = "negative"
sentiment_score = -0.78
```

---

### Task 2 — Topic Modeling

**Library:** BERTopic

```python
from bertopic import BERTopic

topic_model = BERTopic(
    language="english",
    nr_topics=8,            # 8 topics is enough for restaurant reviews
    min_topic_size=30
)

topics, probs = topic_model.fit_transform(all_review_texts)
topic_model.save("models/topic_model")

# Expected topics for restaurant reviews:
# Topic 0: food quality, taste, delicious, bland
# Topic 1: service, staff, waiter, rude, friendly
# Topic 2: delivery, late, fast, driver, cold
# Topic 3: price, expensive, worth, cheap, overpriced
# Topic 4: ambiance, atmosphere, cozy, loud, dirty
# Topic 5: wait time, queue, reservation, crowded
# Topic 6: packaging, container, spilled, bag
# Topic 7: portion size, small, generous, enough
```

Train once. Save model. Load for inference on new reviews.

---

### Task 3 — Complaint & Entity Extractor

**Library:** spaCy

```python
import spacy
nlp = spacy.load("en_core_web_sm")

COMPLAINT_KEYWORDS = {
    "cold food":       ["cold", "not hot", "lukewarm", "stone cold"],
    "slow service":    ["slow", "took forever", "waited", "45 minutes", "an hour"],
    "rude staff":      ["rude", "impolite", "attitude", "disrespectful", "unprofessional"],
    "wrong order":     ["wrong order", "missing", "not what i ordered", "mixed up"],
    "overpriced":      ["overpriced", "expensive", "not worth", "ripoff", "too much"],
    "bad packaging":   ["spilled", "leaking", "broken", "bag was wet"],
    "small portions":  ["small portion", "tiny", "not enough food", "barely any"],
    "dirty":           ["dirty", "unclean", "gross", "disgusting", "cockroach"],
    "noisy":           ["too loud", "noisy", "can't hear", "music too loud"],
}

# spaCy extracts food entities (PRODUCT label)
# e.g. "pizza", "pasta", "chicken wings", "margarita"
```

---

### Task 4 — Vector Embeddings

**Library:** sentence-transformers

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')
# 384-dimensional embeddings
# Fast, lightweight, accurate for semantic search

embedding = model.encode(review_text)
# Store in reviews_processed.embedding via pgvector
```

---

## 7. Machine Learning Models

### ML Model 1 — Fake Review Detector (XGBoost)

Detect reviews where the text sentiment contradicts the star rating.

**Features:**
```python
features = {
    "sentiment_score":      float,      # -1.0 to +1.0 from NLP
    "review_rating":        int,        # 1-5 stars given by reviewer
    "text_length":          int,        # character count
    "exclamation_count":    int,        # number of !
    "caps_ratio":           float,      # ratio of uppercase letters
    "complaint_count":      int,        # number of complaints extracted
    "entity_count":         int,        # number of food entities mentioned
    "is_verified":          bool,       # reviewer has profile photo
}
```

**Target:**
```python
# Label reviews where:
# sentiment_score < -0.3 AND review_rating >= 4  → suspicious = True
# sentiment_score > +0.3 AND review_rating <= 2  → suspicious = True
# else                                            → suspicious = False

# Train XGBoost binary classifier on this rule-based label
# Then use model for new reviews
```

**Output:**
```
is_suspicious = True  → "⚠️ Potentially fake review"
is_suspicious = False → clean
```

Dashboard shows: "12 suspicious reviews detected this month"

---

### ML Model 2 — Rating Forecast (Prophet)

Predict what the business's average rating will be for the next 4 weeks.

```python
from prophet import Prophet

# Input: weekly_stats materialized view
# Columns: week (date), avg_rating (float)

df = pd.DataFrame({
    'ds': weekly_dates,   # Prophet expects 'ds'
    'y':  weekly_ratings  # Prophet expects 'y'
})

model = Prophet(
    changepoint_prior_scale=0.1,
    seasonality_mode='additive'
)
model.fit(df)

future   = model.make_future_dataframe(periods=4, freq='W')
forecast = model.predict(future)
# Returns: yhat (predicted), yhat_lower, yhat_upper (confidence interval)
```

**Dashboard shows:**
```
Current rating:   4.2 ★
Predicted (4wk):  3.8 ★ ↓
"Rating likely to decline if delivery complaints continue"
```

Save both models:
```
models/
├── fake_review_model.pkl    # XGBoost
└── rating_forecast/         # Prophet (saves as directory)
```

---

## 8. RAG Pipeline (Chatbot Brain)

### Step 1 — Embed user question
```python
q_embedding = SentenceTransformer('all-MiniLM-L6-v2').encode(question)
```

### Step 2 — pgvector semantic search
```sql
SELECT
    r.review_text,
    r.review_date,
    r.review_rating,
    rp.sentiment_label,
    rp.complaints,
    1 - (rp.embedding <=> $1::vector) AS similarity
FROM reviews_processed rp
JOIN reviews_raw r ON r.id = rp.review_id
WHERE r.business_id = $2
ORDER BY similarity DESC
LIMIT 10;
```

### Step 3 — Build prompt and call Groq
```python
from groq import Groq

context = "\n\n".join([
    f"Review ({r.review_date}, {r.review_rating}★): {r.review_text}"
    for r in top_reviews
])

prompt = f"""You are a restaurant analytics assistant.
Answer the question using ONLY the reviews provided below.
Be specific. Cite patterns. Never make up information.

Customer Reviews:
{context}

Question: {question}

Answer in 2-3 clear sentences."""

client = Groq()
response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",   # free tier
    messages=[{"role": "user", "content": prompt}],
    max_tokens=300
)
answer = response.choices[0].message.content
```

### Step 4 — Return to React
```json
{
  "answer": "Your rating dropped in October primarily due to delivery complaints. 31 reviews mentioned 'took over an hour' and 'food arrived cold', spiking after October 8th.",
  "sources": [
    { "date": "2025-10-12", "rating": 1, "text": "Waited 90 minutes...", "sentiment": "negative" },
    { "date": "2025-10-15", "rating": 2, "text": "Food was cold when it arrived...", "sentiment": "negative" }
  ]
}
```

**Groq API:** Free tier at `console.groq.com`. No credit card needed.

---

## 9. EDA Outputs

Run in Jupyter notebook. Export all as `/data/eda_outputs.json`.

```python
# 1. Sentiment trend — weekly avg sentiment per business
# 2. Rating trend — weekly avg star rating per business
# 3. Topic distribution — % of reviews per topic
# 4. Top complaints — most frequent complaint keywords this month
# 5. Competitor comparison — avg rating + sentiment across all businesses
# 6. Owner response impact — avg rating with vs without owner response
# 7. Best/worst day of week — avg rating by day (are weekends worse?)
# 8. Rating forecast — Prophet model output for next 4 weeks
# 9. Suspicious review count — per business per month
```

---

## 10. FastAPI Endpoints

```
GET  /api/businesses
     → list of all scraped restaurants for dropdown/search

GET  /api/overview?business_id=X
     → avg_rating, avg_sentiment, total_reviews,
       sentiment_trend[], topic_distribution{},
       top_complaints[], rating_forecast[],
       suspicious_count

GET  /api/reviews?business_id=X&sentiment=negative&topic=delivery&page=1
     → paginated filtered review feed with is_suspicious flag

GET  /api/compare?ids=1,2,3
     → side-by-side: avg_rating, avg_sentiment, top_complaint,
       total_reviews, suspicious_count per business

GET  /api/trends?business_id=X
     → weekly_sentiment[], weekly_rating[], topic_trends[],
       forecast[] (Prophet output)

GET  /api/complaints?business_id=X
     → top complaints with count + 3 example reviews each

POST /api/chat
     Body:     { "question": "string", "business_id": int }
     Response: { "answer": "string", "sources": [] }
```

---

## 11. React Dashboard — 5 Pages

### Page 1: Overview
- Business search/select dropdown at top
- Sentiment score gauge: 0–100 (green/yellow/red)
- Current rating + Prophet forecast ("predicted to drop to 3.8")
- Topic breakdown donut chart (Food 40%, Service 25%, Delivery 20%, Price 15%)
- Top 3 complaint cards with count + example quote
- Suspicious review alert: "12 potentially fake reviews detected"
- Owner response insight: "Restaurants that respond earn 0.3★ higher"

### Page 2: Review Feed
- Filter bar: sentiment · topic · star rating · date range · suspicious only
- Review cards with: reviewer · date · stars · sentiment badge (green/red/yellow) · topic tag · complaint tags · full text
- Red border on suspicious reviews with ⚠️ badge
- Pagination

### Page 3: Competitor Comparison
- Select up to 3 restaurants
- Side-by-side stat cards: avg rating · sentiment · top complaint · suspicious count
- Radar chart: Food Quality vs Service vs Delivery vs Price vs Ambiance
- Bar chart: rating comparison
- "You rank #2 out of 3 on food quality"

### Page 4: Trends + Forecast
- Line chart: weekly sentiment trend (toggle between businesses)
- Line chart: weekly rating trend + Prophet forecast as dashed line
- Topic trend: "Delivery complaints up 40% this month vs last month"
- Heatmap: day of week vs avg rating
- Forecast confidence band (yhat_lower to yhat_upper)

### Page 5: RAG Chatbot
- Clean dark chat interface
- Suggested question chips:
  - "Why did my rating drop last month?"
  - "What do customers love most?"
  - "What's my biggest complaint this week?"
  - "How do I compare to Joe's Pizza?"
- User types question → loading spinner → answer appears
- Below answer: 3 source review cards (the exact reviews the AI used)
- "Powered by your actual customer reviews" disclaimer

---

## 12. File Structure

```
reviewiq/
├── scraper/
│   ├── google_maps_scraper.py
│   ├── restaurant_urls.py        # 50 NYC Google Maps URLs
│   └── scheduler.py              # APScheduler local dev
├── nlp/
│   ├── sentiment.py              # HuggingFace pipeline
│   ├── topic_model.py            # BERTopic train + inference
│   ├── complaint_extractor.py    # spaCy + keywords
│   └── embeddings.py             # sentence-transformers + pgvector
├── ml/
│   ├── fake_review_detector.py   # XGBoost classifier
│   ├── rating_forecast.py        # Prophet time series
│   └── models/
│       ├── fake_review_model.pkl
│       └── rating_forecast/
├── rag/
│   └── chatbot.py                # pgvector search + Groq call
├── eda/
│   ├── analysis.ipynb
│   └── export_eda.py
├── api/
│   └── main.py                   # FastAPI
├── frontend/
│   └── src/pages/
│       ├── Overview.jsx
│       ├── ReviewFeed.jsx
│       ├── Competitors.jsx
│       ├── Trends.jsx
│       └── Chatbot.jsx
├── data/
│   └── eda_outputs.json
├── .github/workflows/scrape.yml
├── requirements.txt
├── docker-compose.yml
└── .env
```

---

## 13. Build Order (Week by Week)

```
Week 1  → Playwright scraper running, 10,000+ reviews in reviews_raw (50 NYC restaurants)
Week 2  → Sentiment analysis + BERTopic topic modeling on all reviews
Week 3  → Complaint extractor + embeddings stored in pgvector
Week 4  → XGBoost fake review detector + Prophet rating forecast trained
Week 5  → RAG chatbot: pgvector search + Groq API working locally
Week 6  → FastAPI all 6 endpoints live locally
Week 7  → React Overview + Chatbot pages (the two that sell)
Week 8  → React Review Feed + Competitors + Trends pages
Week 9  → Deployment + GitHub Actions cron + polish + README
```

---

## 14. Deployment (All Free)

| Service | Platform | Notes |
|---|---|---|
| PostgreSQL + pgvector | Supabase | Free, supports pgvector extension |
| FastAPI | Render | Free tier, auto-deploy from GitHub |
| React | Vercel | Free, auto-deploy from GitHub |
| Scraper cron | GitHub Actions | Free, weekly Sunday run |
| LLM | Groq API | Free tier, llama-3.3-70b-versatile |
| ML models | Render disk | Stored alongside FastAPI |

**Environment variables:**
```
DATABASE_URL=postgresql://...
GROQ_API_KEY=gsk_...
```

---

## 15. Install

```bash
mkdir reviewiq && cd reviewiq
python3 -m venv venv && source venv/bin/activate

pip install playwright playwright-stealth \
            pandas sqlalchemy psycopg2-binary \
            transformers torch \
            bertopic \
            spacy \
            sentence-transformers \
            pgvector \
            xgboost scikit-learn \
            prophet \
            groq \
            fastapi uvicorn \
            python-dotenv

playwright install chromium
python -m spacy download en_core_web_sm
```

---

## 16. Milestones

| # | Milestone | Done when |
|---|---|---|
| M1 | Raw data | 10,000+ reviews across 50 NYC restaurants in reviews_raw |
| M2 | Sentiment | sentiment_label + sentiment_score on every review |
| M3 | Topics | topic_label assigned to every review, BERTopic model saved |
| M4 | Complaints | complaints[] and entities[] extracted, embeddings in pgvector |
| M5 | ML models | XGBoost fake detector + Prophet forecast both trained and saved |
| M6 | RAG | Chatbot answering questions locally from real reviews |
| M7 | API | All 6 FastAPI endpoints returning real data |
| M8 | Frontend | React deployed on Vercel, all 5 pages working |
| M9 | Automation | GitHub Actions scraper running weekly |

---

## 17. Claude Code Prompts

**Playwright scraper:**
> "Build a Playwright Python scraper for Google Maps restaurant reviews. Given a list of Google Maps restaurant URLs, for each: open the page, click the Reviews tab, sort by Newest, scroll down until all reviews load, extract review rating (1-5), review text, review date, reviewer name, and whether there is an owner response. Insert to PostgreSQL tables businesses and reviews_raw using SQLAlchemy. Skip duplicates by checking review_text + review_date + business_id uniqueness before insert. Sleep random 3-6 seconds between restaurants. Use playwright-stealth."

**NLP pipeline:**
> "Build a Python NLP pipeline that reads from reviews_raw PostgreSQL table and writes to reviews_processed. Four tasks: 1) Sentiment using cardiffnlp/twitter-roberta-base-sentiment — output label and score mapped to -1.0 to +1.0. 2) Topic assignment using saved BERTopic model loaded from models/topic_model. 3) Complaint extraction by scanning review text for keywords in COMPLAINT_KEYWORDS dict — output matched complaints as array. 4) spaCy en_core_web_sm entity extraction for food items — output as array. Process in batches of 50. Show progress bar."

**Embeddings:**
> "Build a Python script that reads review_text from reviews_processed where embedding is NULL, generates 384-dimensional embeddings using sentence-transformers all-MiniLM-L6-v2, and stores them in the pgvector embedding column. Use psycopg2 directly for the vector insert. Process in batches of 100."

**XGBoost fake review detector:**
> "Build an XGBoost binary classifier to detect suspicious reviews. Features: sentiment_score, review_rating, text_length (chars), exclamation_count, caps_ratio, complaint_count, entity_count. Label: is_suspicious = True when (sentiment_score < -0.3 AND review_rating >= 4) OR (sentiment_score > 0.3 AND review_rating <= 2). Read from reviews_processed joined with reviews_raw. Train 80/20 split. Print classification report. Save model with joblib as models/fake_review_model.pkl."

**Prophet forecast:**
> "Build a Prophet time series forecasting script. Read weekly_stats materialized view from PostgreSQL (business_id, week, avg_rating). For each business_id, train a Prophet model on the weekly avg_rating history. Predict next 4 weeks. Save forecast results (yhat, yhat_lower, yhat_upper per week) to a forecasts table in PostgreSQL. Handle businesses with fewer than 8 weeks of data by skipping them."

**RAG chatbot:**
> "Build a Python RAG chatbot function. Input: question string and business_id integer. Step 1: embed question using sentence-transformers all-MiniLM-L6-v2. Step 2: pgvector cosine similarity search on reviews_processed.embedding filtered by business_id — return top 10 most similar review texts with date and rating. Step 3: build context string. Step 4: call Groq API with model llama-3.3-70b-versatile, instruct it to answer only from context, max 300 tokens. Return answer string and source reviews list."

**FastAPI:**
> "Build a FastAPI app with CORS enabled for all origins. Six endpoints: GET /api/businesses returns all businesses. GET /api/overview?business_id returns sentiment trend from weekly_stats, topic distribution from reviews_processed, top complaints, suspicious count, Prophet forecast from forecasts table. GET /api/reviews?business_id with optional sentiment, topic, suspicious filters, paginated 20 per page. GET /api/compare?ids comma-separated returns side-by-side stats. GET /api/trends?business_id returns weekly arrays and forecast. POST /api/chat calls the RAG chatbot function."

**React Chatbot:**
> "Build a React Chatbot page component. Dark theme matching TailwindCSS dark colors. Shows 4 suggested question chips at top. Has a chat input fixed at bottom. When user submits, calls POST /api/chat, shows a spinning loader, then renders the AI answer in a message bubble. Below the answer renders 3 source review cards each showing: review date, star rating (colored), sentiment badge (green/red/yellow), and first 150 chars of review text. State managed with useState. No external chat libraries."