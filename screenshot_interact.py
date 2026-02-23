#!/usr/bin/env python3
"""Take a screenshot after interacting with the page.

Usage:
    python screenshot_interact.py [url] [output.png] [--click=selector]
"""
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

url = sys.argv[1] if len(sys.argv) > 1 else BASE_URL + "/library"
output = sys.argv[2] if len(sys.argv) > 2 else "/tmp/sheeetz-screenshot.png"

click_selector = None
for arg in sys.argv:
    if arg.startswith("--click="):
        click_selector = arg.split("=", 1)[1]

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
    page.goto(url, wait_until="networkidle")

    if click_selector:
        page.click(click_selector)
        page.wait_for_timeout(2000)

    page.screenshot(path=output)
    browser.close()

print(output)
