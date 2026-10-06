"""
ReviewIQ FastAPI backend — 6 endpoints over the data/NLP/ML pipeline built in
db/, nlp/, ml/, and rag/. Every endpoint here reads data that's already been
computed and stored (M2-M6) - nothing in this file re-runs a model.

Run locally: uvicorn api.main:app --reload
"""

from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api import queries
from db.session import get_session
from rag.chatbot import ask as rag_ask
from rag.chatbot import get_embedder

app = FastAPI(title="ReviewIQ API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def preload_embedder():
    # rag.chatbot.get_embedder() lazily downloads+loads all-MiniLM-L6-v2
    # (~90MB) on first use and caches it in a module-level global. Without
    # this, whoever sends the first /api/chat request after any server
    # restart (including Render's free-tier cold start) eats that ~15-20s
    # load time themselves. Loading it here moves that cost into the
    # server's own startup instead, before any real request arrives.
    get_embedder()


class ChatRequest(BaseModel):
    question: str
    business_id: int


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/businesses")
def list_businesses():
    session = get_session()
    try:
        return queries.list_businesses(session)
    finally:
        session.close()


@app.get("/api/overview")
def overview(business_id: int = Query(...)):
    session = get_session()
    try:
        result = queries.get_overview(session, business_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Business not found")
        return result
    finally:
        session.close()


@app.get("/api/reviews")
def reviews(
    business_id: int = Query(...),
    sentiment: Optional[str] = Query(None, description="positive | negative | neutral"),
    topic_id: Optional[int] = Query(None),
    suspicious_only: bool = Query(False),
    min_rating: Optional[int] = Query(None, ge=1, le=5),
    max_rating: Optional[int] = Query(None, ge=1, le=5),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    page: int = Query(1, ge=1),
):
    session = get_session()
    try:
        return queries.get_reviews(
            session,
            business_id,
            sentiment=sentiment,
            topic_id=topic_id,
            suspicious_only=suspicious_only,
            min_rating=min_rating,
            max_rating=max_rating,
            date_from=date_from,
            date_to=date_to,
            page=page,
        )
    finally:
        session.close()


@app.get("/api/compare")
def compare(ids: str = Query(..., description="comma-separated business ids, e.g. 1,2,3")):
    try:
        business_ids = [int(x) for x in ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="ids must be comma-separated integers")
    if not business_ids:
        raise HTTPException(status_code=400, detail="ids must not be empty")

    session = get_session()
    try:
        return queries.get_compare(session, business_ids)
    finally:
        session.close()


@app.get("/api/trends")
def trends(business_id: int = Query(...)):
    session = get_session()
    try:
        if queries.get_business(session, business_id) is None:
            raise HTTPException(status_code=404, detail="Business not found")
        return queries.get_trends(session, business_id)
    finally:
        session.close()


@app.get("/api/complaints")
def complaints(business_id: int = Query(...)):
    session = get_session()
    try:
        if queries.get_business(session, business_id) is None:
            raise HTTPException(status_code=404, detail="Business not found")
        return queries.get_complaints(session, business_id)
    finally:
        session.close()


@app.post("/api/chat")
def chat(body: ChatRequest):
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")
    try:
        return rag_ask(body.question, body.business_id)
    except RuntimeError as e:
        # e.g. GROQ_API_KEY missing
        raise HTTPException(status_code=500, detail=str(e))
