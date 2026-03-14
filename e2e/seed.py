"""Seed a test database and print a session token.

Usage: python seed.py <db_path> <fixtures_dir> <secret_key>
Prints JSON: {"token": "...", "user_id": 2, "folder_id": 1}
"""
import json
import sqlite3
import sys
from pathlib import Path

from itsdangerous import URLSafeTimedSerializer

db_path = sys.argv[1]
fixtures_dir = sys.argv[2]
secret_key = sys.argv[3]

conn = sqlite3.connect(db_path)
conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        google_id TEXT UNIQUE NOT NULL,
        email TEXT NOT NULL,
        name TEXT NOT NULL,
        drive_token_json TEXT,
        settings_json TEXT
    )
""")
conn.execute("""
    CREATE TABLE IF NOT EXISTS library_folders (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        backend_type TEXT NOT NULL,
        backend_folder_id TEXT NOT NULL,
        folder_name TEXT NOT NULL,
        folder_path TEXT NOT NULL DEFAULT '/'
    )
""")
conn.execute("""
    CREATE TABLE IF NOT EXISTS sheets (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        library_folder_id INTEGER REFERENCES library_folders(id),
        backend_type TEXT NOT NULL,
        backend_file_id TEXT NOT NULL,
        filename TEXT NOT NULL,
        folder_path TEXT,
        is_favorite INTEGER NOT NULL DEFAULT 0,
        last_opened_at TEXT
    )
""")
conn.execute("""
    CREATE TABLE IF NOT EXISTS sheet_meta (
        id INTEGER PRIMARY KEY,
        sheet_id INTEGER NOT NULL REFERENCES sheets(id),
        key TEXT NOT NULL,
        value TEXT NOT NULL
    )
""")

conn.execute("""
    INSERT OR IGNORE INTO users (id, google_id, email, name)
    VALUES (2, 'test-google-id', 'dirkraft.agents@gmail.com', 'Test Agent')
""")
conn.execute("""
    INSERT OR IGNORE INTO library_folders (id, user_id, backend_type, backend_folder_id, folder_name, folder_path)
    VALUES (1, 2, 'local', ?, 'fixtures', ?)
""", (fixtures_dir, fixtures_dir))
conn.commit()

folder_id = conn.execute("SELECT id FROM library_folders WHERE user_id=2").fetchone()[0]
conn.close()

serializer = URLSafeTimedSerializer(secret_key)
token = serializer.dumps({"uid": 2})

print(json.dumps({"token": token, "user_id": 2, "folder_id": folder_id}))
