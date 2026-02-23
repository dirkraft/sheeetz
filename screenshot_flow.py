#!/usr/bin/env python3
"""Take a screenshot after a sequence of interactions."""
import os
import sys

os.environ["LD_LIBRARY_PATH"] = os.path.expanduser(
    "~/lib-chrome/extracted/usr/lib/x86_64-linux-gnu"
) + ":" + os.environ.get("LD_LIBRARY_PATH", "")

from playwright.sync_api import sync_playwright
from test_account import get_test_session_token

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "backend", ".env"))

BASE_URL = os.environ.get("FRONTEND_URL", "http://serrverr.tail2ec075.ts.net:5173")

token = get_test_session_token()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
    context = browser.new_context(viewport={"width": 390, "height": 844})
    context.add_cookies([{
        "name": "session_token",
        "value": token,
        "domain": "serrverr.tail2ec075.ts.net",
        "path": "/",
    }])

    page = context.new_page()
    page.goto(f"{BASE_URL}/library", wait_until="networkidle")

    # Click Add Folder
    page.click(".add-btn")
    page.wait_for_timeout(1500)

    # Navigate into sheeetz-test-library
    page.click(".folder-name:has-text('sheeetz-test-library')")
    page.wait_for_timeout(1500)

    # Select Classical — click the Select button in that row
    classical_row = page.locator(".folder-row", has_text="Classical")
    classical_row.locator(".select-btn").click()
    page.wait_for_timeout(1000)

    # Select Jazz
    jazz_row = page.locator(".folder-row", has_text="Jazz")
    jazz_row.locator(".select-btn").click()
    page.wait_for_timeout(1000)
    page.screenshot(path="/tmp/sheeetz-selected-folders.png")

    # Close picker
    page.click(".close-btn")
    page.wait_for_timeout(1000)
    page.screenshot(path="/tmp/sheeetz-library-with-folders.png")

    browser.close()

print("Done")
