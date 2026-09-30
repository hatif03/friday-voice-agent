"""Persist opened repos, questions, and scans.

The browser never waits on this. A local SQLite file always records the row.
If SUPABASE_URL is set, the same row is also sent to the friday project.
The server key is SUPABASE_SERVICE_ROLE_KEY, or SUPABASE_PUBLISHABLE_KEY
when the project only allows inserts. A failure there is ignored.
"""
import os
import sqlite3
import time

import requests

_SCHEMA = """
CREATE TABLE IF NOT EXISTS repos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  login TEXT,
  slug TEXT,
  branch TEXT,
  opened_at REAL
);
CREATE TABLE IF NOT EXISTS queries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  login TEXT,
  slug TEXT,
  question TEXT,
  answer TEXT,
  created_at REAL
);
CREATE TABLE IF NOT EXISTS query_steps (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  query_id INTEGER,
  step TEXT,
  detail TEXT
);
CREATE TABLE IF NOT EXISTS scans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  login TEXT,
  slug TEXT,
  summary TEXT,
  created_at REAL
);
CREATE TABLE IF NOT EXISTS findings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scan_id INTEGER,
  path TEXT,
  kind TEXT,
  title TEXT,
  noul REAL
);
"""


def _login() -> str:
    try:
        from github_tools import github_status

        return github_status().get("login") or ""
    except Exception:
        return ""


def _db() -> sqlite3.Connection:
    os.makedirs("cache", exist_ok=True)
    conn = sqlite3.connect(os.path.join("cache", "friday.db"))
    conn.executescript(_SCHEMA)
    return conn


def _remote(table: str, row: dict) -> None:
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.environ.get("SUPABASE_PUBLISHABLE_KEY", "").strip()
    )
    if not url or not key:
        return
    try:
        requests.post(
            f"{url.rstrip('/')}/rest/v1/{table}",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json=row,
            timeout=4,
        )
    except requests.RequestException:
        return


def record_repo(slug: str, branch: str) -> None:
    login = _login()
    now = time.time()
    with _db() as conn:
        conn.execute(
            "INSERT INTO repos (login, slug, branch, opened_at) VALUES (?, ?, ?, ?)",
            (login, slug, branch, now),
        )
    _remote("repos", {"login": login, "slug": slug, "branch": branch})


def record_query(slug: str, question: str, answer: str, steps: list) -> None:
    login = _login()
    now = time.time()
    with _db() as conn:
        cursor = conn.execute(
            "INSERT INTO queries (login, slug, question, answer, created_at) VALUES (?, ?, ?, ?, ?)",
            (login, slug, question[:2000], (answer or "")[:4000], now),
        )
        query_id = cursor.lastrowid
        for step in steps or []:
            conn.execute(
                "INSERT INTO query_steps (query_id, step, detail) VALUES (?, ?, ?)",
                (query_id, str(step.get("step") or "")[:80], str(step.get("detail") or "")[:2000]),
            )
    _remote(
        "queries",
        {"login": login, "slug": slug, "question": question[:2000], "answer": (answer or "")[:4000]},
    )
    for step in steps or []:
        _remote(
            "query_steps",
            {"step": str(step.get("step") or "")[:80], "detail": str(step.get("detail") or "")[:2000], "slug": slug},
        )


def record_scan(slug: str, summary: str, findings: list) -> None:
    login = _login()
    now = time.time()
    with _db() as conn:
        cursor = conn.execute(
            "INSERT INTO scans (login, slug, summary, created_at) VALUES (?, ?, ?, ?)",
            (login, slug, (summary or "")[:2000], now),
        )
        scan_id = cursor.lastrowid
        for item in findings or []:
            noul = item.get("noul")
            conn.execute(
                "INSERT INTO findings (scan_id, path, kind, title, noul) VALUES (?, ?, ?, ?, ?)",
                (
                    scan_id,
                    str(item.get("path") or "")[:400],
                    str(item.get("kind") or "")[:40],
                    str(item.get("title") or "")[:400],
                    float(noul) if isinstance(noul, (int, float)) else None,
                ),
            )
    _remote("scans", {"login": login, "slug": slug, "summary": (summary or "")[:2000]})
    for item in findings or []:
        _remote(
            "findings",
            {
                "slug": slug,
                "path": str(item.get("path") or "")[:400],
                "kind": str(item.get("kind") or "")[:40],
                "title": str(item.get("title") or "")[:400],
                "noul": item.get("noul") if isinstance(item.get("noul"), (int, float)) else None,
            },
        )
