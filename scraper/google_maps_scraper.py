"""
Google Maps restaurant review scraper.

For each restaurant in restaurant_urls.RESTAURANTS:
  1. Search Google Maps for "<name> <address>" (resolves straight to the listing).
  2. Click the Reviews tab, sort by Newest.
  3. Scroll the review feed until all reviews are loaded.
  4. Extract each review (rating, text, date, reviewer, owner response).
  5. Upsert business, insert new reviews (skip duplicates).

Selectors below were captured from a live Google Maps listing page
(2026-09-28) and may need updating if Google changes their markup.
"""

import random
import re
import time
import urllib.parse
from datetime import date, datetime, timedelta

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.models import Business, ReviewRaw
from db.session import get_session
from scraper.restaurant_urls import get_ready_entries

SCRAPER_SETTINGS = {
    "headless": True,
    "slow_mo": 300,
    "viewport": {"width": 1280, "height": 800},
    "locale": "en-US",
}

REVIEW_CARD_SELECTOR = "div.jftiEf.fontBodyMedium"
REVIEWER_NAME_SELECTOR = ".al6Kxe"
STAR_RATING_SELECTOR = '[aria-label$="star"], [aria-label$="stars"]'
REVIEW_DATE_SELECTOR = ".rsqaWe"
REVIEW_TEXT_SELECTOR = ".wiI7pd"
SEE_MORE_SELECTOR = 'button.w8nwRe.kyuRq[aria-label="See more"]'
OVERALL_RATING_SELECTOR = "div.F7nice span[aria-hidden]"
TOTAL_REVIEWS_SELECTOR = "div.F7nice"
ADDRESS_SELECTOR = 'button[data-item-id="address"]'

RELATIVE_DATE_RE = re.compile(
    r"(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago"
)


def parse_relative_date(text: str, scraped_at: datetime) -> date:
    """Google Maps shows relative dates like '3 hours ago' or 'a week ago'."""
    text = text.strip().lower()
    if text in ("new", "just now"):
        return scraped_at.date()
    if text.startswith("a ") or text.startswith("an "):
        text = "1 " + text.split(" ", 1)[1]
    match = RELATIVE_DATE_RE.search(text)
    if not match:
        return scraped_at.date()
    amount, unit = int(match.group(1)), match.group(2)
    delta_days = {
        "second": 0,
        "minute": 0,
        "hour": 0,
        "day": amount,
        "week": amount * 7,
        "month": amount * 30,
        "year": amount * 365,
    }[unit]
    return (scraped_at - timedelta(days=delta_days)).date()


def parse_star_rating(aria_label: str) -> int:
    match = re.search(r"(\d+(\.\d+)?)", aria_label or "")
    return round(float(match.group(1))) if match else None


def build_search_url(name, address):
    query = urllib.parse.quote(f"{name} {address}")
    return f"https://www.google.com/maps/search/{query}?hl=en"


def open_restaurant(page, name, address, retries=3):
    """Navigate to the listing. Google renders a reduced tab bar (no Reviews
    tab) for logged-out/anonymous sessions, so readiness is judged on the
    name (h1) and rating badge, not the Reviews tab itself."""
    url = build_search_url(name, address)
    for attempt in range(retries + 1):
        page.goto(url, wait_until="domcontentloaded")
        try:
            page.wait_for_selector("h1", timeout=20000)
            page.wait_for_selector(OVERALL_RATING_SELECTOR, timeout=20000)
            return
        except Exception:
            if attempt == retries:
                raise
            page.wait_for_timeout(3000 + attempt * 2000)


def dismiss_signin_modal(page):
    try:
        dismiss = page.get_by_text("Dismiss", exact=True).first
        if dismiss.is_visible(timeout=2000):
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
    except Exception:
        pass


def safe_click(page, locator, attempts=4, click_timeout=4000):
    """Click a locator, recovering from a sign-in modal backdrop intercepting the click."""
    last_error = None
    for _ in range(attempts):
        try:
            locator.click(timeout=click_timeout)
            return
        except Exception as e:
            last_error = e
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
    raise last_error


def click_reviews_tab(page):
    """Click the star-rating badge, which reliably reveals/opens the Reviews
    tab even for logged-out sessions where the tab isn't pre-rendered."""
    try:
        safe_click(page, page.get_by_text("Reviews", exact=True).first, attempts=1, click_timeout=3000)
    except Exception:
        safe_click(page, page.locator(TOTAL_REVIEWS_SELECTOR).first)
    page.wait_for_timeout(2500)
    page.wait_for_selector(REVIEW_CARD_SELECTOR, timeout=15000)


def sort_by_newest(page):
    sort_button = page.get_by_role("button", name=re.compile("Sort", re.I))
    for _ in range(3):
        safe_click(page, sort_button, attempts=4, click_timeout=6000)
        page.wait_for_timeout(500)
        try:
            safe_click(page, page.get_by_text("Newest", exact=True).first, attempts=1, click_timeout=3000)
            page.wait_for_timeout(1500)
            return
        except Exception:
            page.wait_for_timeout(500)
    raise RuntimeError("Could not open sort menu / select Newest")


def scroll_reviews_panel(page, max_scrolls=60):
    panel = page.locator(REVIEW_CARD_SELECTOR).first.locator(
        "xpath=ancestor::div[contains(@style,'overflow')][1]"
    )
    prev_count = 0
    stable_rounds = 0
    for _ in range(max_scrolls):
        page.mouse.wheel(0, 4000)
        page.wait_for_timeout(random.uniform(800, 1500))
        count = page.locator(REVIEW_CARD_SELECTOR).count()
        if count == prev_count:
            stable_rounds += 1
            if stable_rounds >= 3:
                break
        else:
            stable_rounds = 0
        prev_count = count


def expand_truncated_reviews(page):
    buttons = page.locator(SEE_MORE_SELECTOR)
    for i in range(buttons.count()):
        try:
            buttons.nth(i).click(timeout=1000)
        except Exception:
            pass


def extract_business_info(page, listing_url, fallback_address=None):
    page.wait_for_function(
        "() => document.querySelector('h1') && document.querySelector('h1').innerText.trim().length > 0",
        timeout=15000,
    )
    name = page.locator("h1").first.inner_text().strip()
    try:
        rating_text = page.locator(OVERALL_RATING_SELECTOR).first.inner_text()
        overall_rating = float(rating_text.replace(",", "."))
    except Exception:
        overall_rating = None
    try:
        totals_text = page.locator(TOTAL_REVIEWS_SELECTOR).first.inner_text()
        match = re.search(r"\(([\d,]+)\)", totals_text)
        total_reviews = int(match.group(1).replace(",", "")) if match else None
    except Exception:
        total_reviews = None
    try:
        address = page.locator(ADDRESS_SELECTOR).first.get_attribute("aria-label")
        address = address.replace("Address: ", "").strip() if address else None
    except Exception:
        address = None
    return {
        "name": name,
        "address": address or fallback_address,
        "overall_rating": overall_rating,
        "total_reviews": total_reviews,
        "listing_url": listing_url,
    }


def extract_reviews(page, scraped_at):
    cards = page.locator(REVIEW_CARD_SELECTOR)
    results = []
    for i in range(cards.count()):
        card = cards.nth(i)
        try:
            reviewer_name = card.locator(REVIEWER_NAME_SELECTOR).first.inner_text().split("\n")[0].strip()
        except Exception:
            reviewer_name = None
        try:
            star_aria = card.locator(STAR_RATING_SELECTOR).first.get_attribute("aria-label")
            review_rating = parse_star_rating(star_aria)
        except Exception:
            review_rating = None
        try:
            date_text = card.locator(REVIEW_DATE_SELECTOR).first.inner_text()
            review_date = parse_relative_date(date_text, scraped_at)
        except Exception:
            review_date = scraped_at.date()
        try:
            review_text = card.locator(REVIEW_TEXT_SELECTOR).first.inner_text().strip()
        except Exception:
            review_text = ""
        has_owner_response = bool(
            re.search(r"response from the owner", card.inner_text(), re.I)
        )
        if not review_text:
            continue
        results.append(
            {
                "review_rating": review_rating,
                "review_text": review_text,
                "review_date": review_date,
                "reviewer_name": reviewer_name,
                "has_owner_response": has_owner_response,
            }
        )
    return results


def upsert_business(session, business_info):
    stmt = (
        pg_insert(Business)
        .values(**business_info, city="New York")
        .on_conflict_do_update(
            index_elements=[Business.listing_url],
            set_={
                "name": business_info["name"],
                "address": business_info["address"],
                "overall_rating": business_info["overall_rating"],
                "total_reviews": business_info["total_reviews"],
            },
        )
        .returning(Business.id)
    )
    business_id = session.execute(stmt).scalar_one()
    session.commit()
    return business_id


def insert_reviews(session, business_id, reviews):
    inserted = 0
    for r in reviews:
        exists = (
            session.query(ReviewRaw.id)
            .filter_by(
                business_id=business_id,
                review_text=r["review_text"],
                review_date=r["review_date"],
            )
            .first()
        )
        if exists:
            continue
        session.add(ReviewRaw(business_id=business_id, **r))
        inserted += 1
    session.commit()
    return inserted


def scrape_restaurant(page, entry, session):
    print(f"Scraping: {entry['name']}")
    open_restaurant(page, entry["name"], entry["address"])

    listing_url = build_search_url(entry["name"], entry["address"])
    business_info = extract_business_info(page, listing_url, fallback_address=entry["address"])
    business_info["category"] = entry["category"]

    click_reviews_tab(page)
    dismiss_signin_modal(page)

    sort_by_newest(page)
    scroll_reviews_panel(page)
    expand_truncated_reviews(page)

    scraped_at = datetime.utcnow()
    reviews = extract_reviews(page, scraped_at)

    business_id = upsert_business(session, business_info)
    inserted = insert_reviews(session, business_id, reviews)
    print(f"  -> {len(reviews)} reviews found, {inserted} new")
    return inserted


def run(restaurants=None, max_businesses=20):
    restaurants = restaurants if restaurants is not None else get_ready_entries()
    if not restaurants:
        print("No restaurants configured. Fill in scraper/restaurant_urls.py first.")
        return

    restaurants = restaurants[:max_businesses]
    session = get_session()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=SCRAPER_SETTINGS["headless"],
            slow_mo=SCRAPER_SETTINGS["slow_mo"],
            args=["--disable-gpu"],
        )
        context = browser.new_context(
            viewport=SCRAPER_SETTINGS["viewport"],
            locale=SCRAPER_SETTINGS["locale"],
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        total_inserted = 0
        for entry in restaurants:
            for attempt in range(2):
                try:
                    total_inserted += scrape_restaurant(page, entry, session)
                    break
                except Exception as e:
                    print(f"  !! Failed to scrape {entry['name']} (attempt {attempt + 1}): {e}")
                    if attempt == 0:
                        time.sleep(3)
            time.sleep(random.uniform(3, 6))

        browser.close()

    session.close()
    print(f"Done. {total_inserted} new reviews inserted.")


if __name__ == "__main__":
    run()
