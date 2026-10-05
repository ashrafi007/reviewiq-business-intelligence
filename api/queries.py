"""
Database query functions backing the FastAPI endpoints in api/main.py.

Kept separate from main.py so route handlers stay thin (parse params, call a
query function, return it) and the SQL is easy to find/test independently.
"""

from sqlalchemy import text


def list_businesses(session):
    rows = session.execute(
        text(
            """
            SELECT id, name, category, address, city, overall_rating, total_reviews, listing_url
            FROM businesses
            ORDER BY name
            """
        )
    ).mappings().all()
    return [dict(r) for r in rows]


def get_business(session, business_id):
    row = session.execute(
        text("SELECT * FROM businesses WHERE id = :bid"), {"bid": business_id}
    ).mappings().first()
    return dict(row) if row else None


def get_overview(session, business_id):
    business = get_business(session, business_id)
    if business is None:
        return None

    stats = session.execute(
        text(
            """
            SELECT COUNT(*) AS total_reviews,
                   AVG(rp.sentiment_score) AS avg_sentiment,
                   AVG(r.review_rating) AS avg_scraped_rating,
                   COUNT(*) FILTER (WHERE rp.is_suspicious) AS suspicious_count
            FROM reviews_raw r
            JOIN reviews_processed rp ON rp.review_id = r.id
            WHERE r.business_id = :bid
            """
        ),
        {"bid": business_id},
    ).mappings().first()

    sentiment_trend = session.execute(
        text(
            """
            SELECT week, avg_rating, avg_sentiment, review_count
            FROM weekly_stats
            WHERE business_id = :bid
            ORDER BY week
            """
        ),
        {"bid": business_id},
    ).mappings().all()

    topic_rows = session.execute(
        text(
            """
            SELECT rp.topic_id, rp.topic_label,
                   COALESCE(tl.display_name, rp.topic_label) AS topic_display_name,
                   COUNT(*) AS count
            FROM reviews_raw r
            JOIN reviews_processed rp ON rp.review_id = r.id
            LEFT JOIN topic_labels tl ON tl.topic_id = rp.topic_id
            WHERE r.business_id = :bid AND rp.topic_label IS NOT NULL
            GROUP BY rp.topic_id, rp.topic_label, tl.display_name
            ORDER BY count DESC
            """
        ),
        {"bid": business_id},
    ).mappings().all()
    total_topic_reviews = sum(t["count"] for t in topic_rows) or 1
    topic_distribution = [
        {
            "topic_id": t["topic_id"],
            "topic_label": t["topic_display_name"],
            "count": t["count"],
            "pct": round(t["count"] / total_topic_reviews * 100, 1),
        }
        for t in topic_rows
    ]

    complaint_rows = session.execute(
        text(
            """
            SELECT unnest(rp.complaints) AS complaint, COUNT(*) AS count
            FROM reviews_raw r
            JOIN reviews_processed rp ON rp.review_id = r.id
            WHERE r.business_id = :bid
            GROUP BY complaint
            ORDER BY count DESC
            LIMIT 5
            """
        ),
        {"bid": business_id},
    ).mappings().all()

    forecast_rows = session.execute(
        text(
            """
            SELECT week, yhat, yhat_lower, yhat_upper
            FROM forecasts
            WHERE business_id = :bid
            ORDER BY week
            """
        ),
        {"bid": business_id},
    ).mappings().all()

    # Owner-response insight, computed per-business (not globally across all 50 -
    # a business-specific "does responding help here" is more useful for a single
    # restaurant's dashboard than a cross-dataset average would be).
    owner_response_rows = session.execute(
        text(
            """
            SELECT r.has_owner_response, AVG(r.review_rating) AS avg_rating, COUNT(*) AS n
            FROM reviews_raw r
            WHERE r.business_id = :bid AND r.review_rating IS NOT NULL
            GROUP BY r.has_owner_response
            """
        ),
        {"bid": business_id},
    ).mappings().all()
    owner_response_insight = {
        str(r["has_owner_response"]).lower(): {
            "avg_rating": round(float(r["avg_rating"]), 2),
            "count": r["n"],
        }
        for r in owner_response_rows
    }

    return {
        "business": business,
        "total_reviews": stats["total_reviews"],
        "avg_sentiment": round(float(stats["avg_sentiment"]), 3) if stats["avg_sentiment"] is not None else None,
        "avg_scraped_rating": round(float(stats["avg_scraped_rating"]), 2) if stats["avg_scraped_rating"] is not None else None,
        "suspicious_count": stats["suspicious_count"],
        "sentiment_trend": [dict(r) for r in sentiment_trend],
        "topic_distribution": topic_distribution,
        "top_complaints": [dict(r) for r in complaint_rows],
        "owner_response_insight": owner_response_insight,
        "rating_forecast": [dict(r) for r in forecast_rows],
    }


def get_reviews(
    session,
    business_id,
    sentiment=None,
    topic_id=None,
    suspicious_only=False,
    min_rating=None,
    max_rating=None,
    date_from=None,
    date_to=None,
    page=1,
    page_size=20,
):
    conditions = ["r.business_id = :bid"]
    params = {"bid": business_id}

    if sentiment:
        conditions.append("rp.sentiment_label = :sentiment")
        params["sentiment"] = sentiment
    if topic_id is not None:
        conditions.append("rp.topic_id = :topic_id")
        params["topic_id"] = topic_id
    if suspicious_only:
        conditions.append("rp.is_suspicious = true")
    if min_rating is not None:
        conditions.append("r.review_rating >= :min_rating")
        params["min_rating"] = min_rating
    if max_rating is not None:
        conditions.append("r.review_rating <= :max_rating")
        params["max_rating"] = max_rating
    if date_from is not None:
        conditions.append("r.review_date >= :date_from")
        params["date_from"] = date_from
    if date_to is not None:
        conditions.append("r.review_date <= :date_to")
        params["date_to"] = date_to

    where_clause = " AND ".join(conditions)

    total = session.execute(
        text(f"""
            SELECT COUNT(*) FROM reviews_raw r
            JOIN reviews_processed rp ON rp.review_id = r.id
            WHERE {where_clause}
        """),
        params,
    ).scalar()

    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    rows = session.execute(
        text(f"""
            SELECT r.id AS review_id, r.reviewer_name, r.review_rating, r.review_text, r.review_date,
                   r.has_owner_response, rp.sentiment_label, rp.sentiment_score,
                   rp.topic_id, COALESCE(tl.display_name, rp.topic_label) AS topic_label,
                   rp.complaints, rp.entities, rp.is_suspicious
            FROM reviews_raw r
            JOIN reviews_processed rp ON rp.review_id = r.id
            LEFT JOIN topic_labels tl ON tl.topic_id = rp.topic_id
            WHERE {where_clause}
            ORDER BY r.review_date DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    ).mappings().all()

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size if total else 0,
        "reviews": [dict(r) for r in rows],
    }


# The spec's radar chart axes (Food Quality / Service / Delivery / Price / Ambiance)
# don't map onto our topics (cuisine-based, not aspect-based - see nlp_progress.md),
# but they map cleanly onto the complaint taxonomy, which IS aspect-oriented. Each
# aspect score = 100 * (1 - that aspect's complaint rate among the business's
# reviews) - a business with no complaints in a category scores 100 on it.
ASPECT_COMPLAINT_MAP = {
    "Food Quality": ["cold food", "small portions"],
    "Service": ["slow service", "rude staff", "wrong order"],
    "Price": ["overpriced"],
    "Ambiance": ["dirty", "noisy"],
    "Packaging": ["bad packaging"],
}


def get_aspect_scores(session, business_id, total_reviews):
    if not total_reviews:
        return {aspect: None for aspect in ASPECT_COMPLAINT_MAP}
    counts = session.execute(
        text(
            """
            SELECT unnest(rp.complaints) AS complaint, COUNT(*) AS count
            FROM reviews_raw r
            JOIN reviews_processed rp ON rp.review_id = r.id
            WHERE r.business_id = :bid
            GROUP BY complaint
            """
        ),
        {"bid": business_id},
    ).mappings().all()
    complaint_counts = {row["complaint"]: row["count"] for row in counts}

    scores = {}
    for aspect, complaint_list in ASPECT_COMPLAINT_MAP.items():
        aspect_complaint_count = sum(complaint_counts.get(c, 0) for c in complaint_list)
        rate = aspect_complaint_count / total_reviews
        scores[aspect] = round(max(0.0, 1 - rate) * 100, 1)
    return scores


def get_compare(session, business_ids):
    results = []
    for bid in business_ids:
        business = get_business(session, bid)
        if business is None:
            continue
        stats = session.execute(
            text(
                """
                SELECT COUNT(*) AS total_reviews,
                       AVG(rp.sentiment_score) AS avg_sentiment,
                       AVG(r.review_rating) AS avg_scraped_rating,
                       COUNT(*) FILTER (WHERE rp.is_suspicious) AS suspicious_count
                FROM reviews_raw r
                JOIN reviews_processed rp ON rp.review_id = r.id
                WHERE r.business_id = :bid
                """
            ),
            {"bid": bid},
        ).mappings().first()
        top_complaint = session.execute(
            text(
                """
                SELECT unnest(rp.complaints) AS complaint, COUNT(*) AS count
                FROM reviews_raw r
                JOIN reviews_processed rp ON rp.review_id = r.id
                WHERE r.business_id = :bid
                GROUP BY complaint
                ORDER BY count DESC
                LIMIT 1
                """
            ),
            {"bid": bid},
        ).mappings().first()
        results.append(
            {
                "business": business,
                "total_reviews": stats["total_reviews"],
                "avg_sentiment": round(float(stats["avg_sentiment"]), 3) if stats["avg_sentiment"] is not None else None,
                "avg_scraped_rating": round(float(stats["avg_scraped_rating"]), 2) if stats["avg_scraped_rating"] is not None else None,
                "suspicious_count": stats["suspicious_count"],
                "top_complaint": top_complaint["complaint"] if top_complaint else None,
                "aspect_scores": get_aspect_scores(session, bid, stats["total_reviews"]),
            }
        )
    return results


def get_trends(session, business_id):
    weekly = session.execute(
        text(
            """
            SELECT week, avg_rating, avg_sentiment, review_count
            FROM weekly_stats
            WHERE business_id = :bid
            ORDER BY week
            """
        ),
        {"bid": business_id},
    ).mappings().all()

    topic_trend_rows = session.execute(
        text(
            """
            SELECT COALESCE(tl.display_name, rp.topic_label) AS topic_label,
                   COUNT(*) FILTER (WHERE r.review_date >= CURRENT_DATE - INTERVAL '30 days') AS this_month,
                   COUNT(*) FILTER (
                       WHERE r.review_date >= CURRENT_DATE - INTERVAL '60 days'
                         AND r.review_date < CURRENT_DATE - INTERVAL '30 days'
                   ) AS last_month
            FROM reviews_raw r
            JOIN reviews_processed rp ON rp.review_id = r.id
            LEFT JOIN topic_labels tl ON tl.topic_id = rp.topic_id
            WHERE r.business_id = :bid AND rp.topic_label IS NOT NULL
            GROUP BY rp.topic_id, COALESCE(tl.display_name, rp.topic_label)
            HAVING COUNT(*) FILTER (WHERE r.review_date >= CURRENT_DATE - INTERVAL '60 days') > 0
            ORDER BY this_month DESC
            """
        ),
        {"bid": business_id},
    ).mappings().all()
    topic_trends = []
    for t in topic_trend_rows:
        this_m, last_m = t["this_month"], t["last_month"]
        pct_change = None
        if last_m:
            pct_change = round((this_m - last_m) / last_m * 100, 1)
        topic_trends.append(
            {
                "topic_label": t["topic_label"],
                "this_month": this_m,
                "last_month": last_m,
                "pct_change": pct_change,
            }
        )

    forecast = session.execute(
        text(
            """
            SELECT week, yhat, yhat_lower, yhat_upper
            FROM forecasts
            WHERE business_id = :bid
            ORDER BY week
            """
        ),
        {"bid": business_id},
    ).mappings().all()

    dow_rows = session.execute(
        text(
            """
            SELECT EXTRACT(DOW FROM r.review_date)::int AS dow,
                   AVG(r.review_rating) AS avg_rating,
                   AVG(rp.sentiment_score) AS avg_sentiment,
                   COUNT(*) AS count
            FROM reviews_raw r
            JOIN reviews_processed rp ON rp.review_id = r.id
            WHERE r.business_id = :bid AND r.review_date IS NOT NULL
            GROUP BY dow
            """
        ),
        {"bid": business_id},
    ).mappings().all()
    dow_by_index = {r["dow"]: r for r in dow_rows}
    dow_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    day_of_week = [
        {
            "day": dow_names[i],
            "avg_rating": round(float(dow_by_index[i]["avg_rating"]), 2) if i in dow_by_index else None,
            "avg_sentiment": round(float(dow_by_index[i]["avg_sentiment"]), 3) if i in dow_by_index else None,
            "count": dow_by_index[i]["count"] if i in dow_by_index else 0,
        }
        for i in range(7)
    ]

    return {
        "weekly_stats": [dict(r) for r in weekly],
        "topic_trends": topic_trends,
        "forecast": [dict(r) for r in forecast],
        "day_of_week": day_of_week,
    }


def get_complaints(session, business_id, examples_per_complaint=3):
    complaint_counts = session.execute(
        text(
            """
            SELECT unnest(rp.complaints) AS complaint, COUNT(*) AS count
            FROM reviews_raw r
            JOIN reviews_processed rp ON rp.review_id = r.id
            WHERE r.business_id = :bid
            GROUP BY complaint
            ORDER BY count DESC
            """
        ),
        {"bid": business_id},
    ).mappings().all()

    results = []
    for row in complaint_counts:
        examples = session.execute(
            text(
                """
                SELECT r.review_text, r.review_date, r.review_rating
                FROM reviews_raw r
                JOIN reviews_processed rp ON rp.review_id = r.id
                WHERE r.business_id = :bid AND :complaint = ANY(rp.complaints)
                ORDER BY r.review_date DESC
                LIMIT :n
                """
            ),
            {"bid": business_id, "complaint": row["complaint"], "n": examples_per_complaint},
        ).mappings().all()
        results.append(
            {
                "complaint": row["complaint"],
                "count": row["count"],
                "examples": [dict(e) for e in examples],
            }
        )
    return results
