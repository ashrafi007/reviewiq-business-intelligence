"""
Insert reviews harvested via the browser hybrid-scraping workflow into Postgres.

The hybrid workflow (see .CLAUDE/scraping_progress.md) harvests review cards
from a real, logged-in Chrome session via a JS snippet, then downloads a JSON
array of {reviewer_name, rating, date_text, review_text} to ~/Downloads.
This script loads that file, converts it to the DB's row shape, and upserts
the business + reviews using the same dedupe-safe helpers as the automated
Playwright flow.

Usage:
    python -m scraper.insert_from_json <json_path> \
        --name "..." --address "..." --category "..." \
        --rating <float> --total-reviews <int> --listing-url "..."
"""

import argparse
import json
from datetime import datetime

from db.session import get_session
from scraper.google_maps_scraper import (
    insert_reviews,
    parse_relative_date,
    parse_star_rating,
    upsert_business,
)


def convert_review(raw, scraped_at):
    return {
        "review_rating": parse_star_rating(raw.get("rating")),
        "review_text": (raw.get("review_text") or "").strip(),
        "review_date": parse_relative_date(raw.get("date_text") or "", scraped_at),
        "reviewer_name": raw.get("reviewer_name"),
        "has_owner_response": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("json_path")
    parser.add_argument("--name", required=True)
    parser.add_argument("--address", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--rating", type=float, required=True)
    parser.add_argument("--total-reviews", type=int, required=True)
    parser.add_argument("--listing-url", required=True)
    args = parser.parse_args()

    with open(args.json_path) as f:
        raw_reviews = json.load(f)

    scraped_at = datetime.utcnow()
    reviews = [convert_review(r, scraped_at) for r in raw_reviews]
    reviews = [r for r in reviews if r["review_text"]]

    business_info = {
        "name": args.name,
        "address": args.address,
        "overall_rating": args.rating,
        "total_reviews": args.total_reviews,
        "listing_url": args.listing_url,
        "category": args.category,
    }

    session = get_session()
    business_id = upsert_business(session, business_info)
    inserted = insert_reviews(session, business_id, reviews)
    session.close()

    print(f"{args.name}: {len(raw_reviews)} harvested, {len(reviews)} valid, {inserted} newly inserted (business_id={business_id})")


if __name__ == "__main__":
    main()
