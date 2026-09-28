"""
One-time interactive setup: opens a real (visible) browser window so you can
log into Google yourself, then saves that session for the scraper to reuse.

Run this locally (not in CI - you need to see and use the browser window):
    python -m scraper.save_google_session

Recommended: use a secondary/throwaway Google account, not your main one.
"""

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from scraper.google_maps_scraper import AUTH_STATE_PATH


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--disable-gpu"])
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        page = context.new_page()
        Stealth().apply_stealth_sync(page)
        page.goto("https://accounts.google.com/", wait_until="domcontentloaded")

        print("\nA browser window has opened.")
        print("Log into your Google account there (a secondary/throwaway account is recommended).")
        print("Once you're fully logged in, come back here and press Enter...")
        input()

        context.storage_state(path=AUTH_STATE_PATH)
        print(f"Session saved to {AUTH_STATE_PATH}")
        browser.close()


if __name__ == "__main__":
    run()
