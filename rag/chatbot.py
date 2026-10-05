"""
RAG chatbot: pgvector semantic search over a business's reviews + Groq LLM answer.

Step 1: embed the user's question (same model used for review embeddings, so
         they live in the same vector space - all-MiniLM-L6-v2).
Step 2: pgvector cosine similarity search, filtered to one business, top 10.
Step 3: build a grounding prompt from those reviews and call Groq.
Step 4: return the answer plus the exact source reviews used, so the UI can
         show "here's what the AI actually read" (spec's RAG chatbot page).

Model note: the spec's original model name (llama-3.3-70b-versatile) no longer
exists in Groq's catalog (checked live via client.models.list() - catalogs on
hosted-inference providers change over time). Using openai/gpt-oss-120b instead
(Groq's largest general-purpose chat model as of this build). gpt-oss models do
internal reasoning before the visible answer and will return an EMPTY string if
max_tokens is too tight (confirmed: 20 tokens -> empty, 200 -> fine) - the
MAX_TOKENS below has headroom for that, not just for the answer text itself.

Vector search needs pgvector.psycopg2.register_vector() on the raw connection
or psycopg2 can't serialize the numpy query embedding correctly (same gotcha
as nlp/embeddings.py - must unwrap SQLAlchemy's _ConnectionFairy proxy via
.dbapi_connection to get the real psycopg2 connection register_vector needs).
"""

import os
import re

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from dotenv import load_dotenv
from groq import Groq
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer
from sqlalchemy import text

from db.session import get_session

load_dotenv()

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
GROQ_MODEL = "openai/gpt-oss-120b"
TOP_K = 10
MAX_TOKENS = 1024  # generous: gpt-oss burns tokens on internal reasoning before the visible answer
FALLBACK_SOURCE_COUNT = 3
FALLBACK_MIN_SIMILARITY = 0.35  # only used if the model's "USED:" line can't be parsed
USED_LINE_RE = re.compile(r"\n?\s*USED:\s*(.+?)\s*$", re.IGNORECASE | re.DOTALL)

_embedder = None
_groq_client = None


def get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _embedder


def get_groq_client():
    global _groq_client
    if _groq_client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set in .env")
        _groq_client = Groq(api_key=api_key)
    return _groq_client


def search_reviews(session, business_id, question_embedding, top_k=TOP_K):
    register_vector(session.connection().connection.dbapi_connection)
    rows = session.execute(
        text(
            """
            SELECT r.review_text, r.review_date, r.review_rating,
                   rp.sentiment_label, rp.complaints,
                   1 - (rp.embedding <=> :qvec) AS similarity
            FROM reviews_processed rp
            JOIN reviews_raw r ON r.id = rp.review_id
            WHERE r.business_id = :business_id AND rp.embedding IS NOT NULL
            ORDER BY rp.embedding <=> :qvec
            LIMIT :top_k
            """
        ),
        {"qvec": question_embedding, "business_id": business_id, "top_k": top_k},
    ).fetchall()
    return rows


def format_rating(rating):
    return f"{rating}★" if rating is not None else "rating unknown"


def build_prompt(question, reviews):
    context = "\n\n".join(
        f"[{i}] Review ({r.review_date}, {format_rating(r.review_rating)}, {r.sentiment_label}): {r.review_text}"
        for i, r in enumerate(reviews, start=1)
    )
    return f"""You are a restaurant analytics assistant.
Answer the question using ONLY the reviews provided below.
Be specific. Cite patterns. Never make up information. If the reviews don't
contain enough information to answer, say so plainly instead of guessing.

The reviews below were retrieved by semantic similarity to the question, which
means some may share vocabulary with the question (e.g. "service") without
actually being relevant to answering it (e.g. a glowing review about a server
is not evidence for a question about complaints). Only rely on reviews that
are genuinely relevant to the question asked.

Customer Reviews:
{context}

Question: {question}

Answer in 2-3 clear sentences, written naturally for a reader who cannot see
the bracketed numbers above - do NOT mention review numbers in your answer
text. Then, on a new final line, write exactly "USED: " followed by a
comma-separated list of the bracketed numbers above for ONLY the reviews you
actually relied on to answer (e.g. "USED: 1,4,7"). If none of the reviews
were actually relevant, write "USED: none"."""


def parse_used_sources(raw_answer, reviews):
    """Split the model's trailing "USED: 1,4,7" line off the answer text and
    resolve it to the actual review rows, so the UI only shows sources the
    model says it relied on - not every review retrieval happened to surface.
    Falls back to a similarity floor if the model didn't follow the format.
    """
    match = USED_LINE_RE.search(raw_answer)
    if not match:
        clean_answer = raw_answer.strip()
        used_reviews = [r for r in reviews if r.similarity >= FALLBACK_MIN_SIMILARITY][:FALLBACK_SOURCE_COUNT]
        return clean_answer, used_reviews

    clean_answer = raw_answer[: match.start()].strip()
    used_text = match.group(1).strip()

    if used_text.lower().startswith("none"):
        return clean_answer, []

    indices = []
    for token in re.findall(r"\d+", used_text):
        idx = int(token)
        if idx not in indices:
            indices.append(idx)

    used_reviews = [reviews[i - 1] for i in indices if 1 <= i <= len(reviews)]
    if not used_reviews:
        # Model said something but it didn't parse to valid indices - same
        # similarity-floor fallback as a missing/malformed USED line.
        used_reviews = [r for r in reviews if r.similarity >= FALLBACK_MIN_SIMILARITY][:FALLBACK_SOURCE_COUNT]
    return clean_answer, used_reviews


def ask(question, business_id, top_k=TOP_K):
    session = get_session()
    try:
        embedder = get_embedder()
        question_embedding = embedder.encode(question).astype("float32")

        reviews = search_reviews(session, business_id, question_embedding, top_k)
        if not reviews:
            return {
                "answer": "I don't have any reviews for this business yet, so I can't answer that.",
                "sources": [],
            }

        prompt = build_prompt(question, reviews)
        client = get_groq_client()
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=MAX_TOKENS,
        )
        raw_answer = response.choices[0].message.content.strip()
        answer, used_reviews = parse_used_sources(raw_answer, reviews)

        sources = [
            {
                "date": str(r.review_date),
                "rating": r.review_rating,
                "text": r.review_text,
                "sentiment": r.sentiment_label,
                "similarity": round(float(r.similarity), 3),
            }
            for r in used_reviews
        ]
        return {"answer": answer, "sources": sources}
    finally:
        session.close()


if __name__ == "__main__":
    import sys

    bid = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    q = sys.argv[2] if len(sys.argv) > 2 else "What do customers love most about this place?"
    result = ask(q, bid)
    print("Q:", q)
    print("A:", result["answer"])
    print(f"\n{len(result['sources'])} sources:")
    for s in result["sources"]:
        print(f"  [{s['similarity']}] ({s['date']}, {format_rating(s['rating'])}) {s['text'][:100]}")
