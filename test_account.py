"""Helper to get the test/dev account safely.

Only returns credentials for dirkraft.agents@gmail.com.
Raises if the account doesn't exist or doesn't match.
"""
import os
import sqlite3
import sys

from itsdangerous import URLSafeTimedSerializer

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "backend")
DB_PATH = os.path.join(BACKEND_DIR, "sheeetz.db")
EXPECTED_EMAIL = "dirkraft.agents@gmail.com"

sys.path.insert(0, BACKEND_DIR)
from dotenv import load_dotenv
load_dotenv(os.path.join(BACKEND_DIR, ".env"))

SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")


def get_test_user_id() -> int:
    """Return the user ID for the agents test account, or raise."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT id, email FROM users WHERE email = ?", (EXPECTED_EMAIL,)
    ).fetchone()
    conn.close()

    if not row:
        raise RuntimeError(f"Test account {EXPECTED_EMAIL} not found in DB")
    return row[0]


def get_test_session_token() -> str:
    """Return a valid session token for the agents test account."""
    uid = get_test_user_id()
    serializer = URLSafeTimedSerializer(SECRET_KEY)
    return serializer.dumps({"uid": uid})
