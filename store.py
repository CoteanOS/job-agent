"""
Tiny SQLite state store. Keeps the agent stateless-safe: if the Pi reboots
mid-run, nothing is lost and nothing is double-applied.

Status lifecycle:
  seen      -> scraped, letter not yet made
  pending   -> letter made, waiting for your tap on Telegram
  approved  -> you tapped approve, submit in progress / done
  submitted -> form actually submitted ok
  rejected  -> you tapped reject
  error     -> something failed (message has the reason)
"""
import sqlite3
from contextlib import contextmanager
import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    url         TEXT UNIQUE NOT NULL,   -- dedup key
    title       TEXT NOT NULL,
    company     TEXT NOT NULL,
    description TEXT NOT NULL,
    letter      TEXT,
    pdf_path    TEXT,
    status      TEXT NOT NULL DEFAULT 'seen',
    note        TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


@contextmanager
def _conn():
    c = sqlite3.connect(config.DB_FILE)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with _conn() as c:
        c.executescript(_SCHEMA)


def already_seen(url: str) -> bool:
    with _conn() as c:
        return c.execute("SELECT 1 FROM jobs WHERE url=?", (url,)).fetchone() is not None


def add_job(url, title, company, description) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO jobs(url,title,company,description) VALUES(?,?,?,?)",
            (url, title, company, description),
        )
        if cur.lastrowid:
            return cur.lastrowid
        return c.execute("SELECT id FROM jobs WHERE url=?", (url,)).fetchone()["id"]


def set_letter(job_id, letter, pdf_path):
    with _conn() as c:
        c.execute("UPDATE jobs SET letter=?, pdf_path=?, status='pending', "
                  "updated_at=datetime('now') WHERE id=?", (letter, pdf_path, job_id))


def set_status(job_id, status, note=None):
    with _conn() as c:
        c.execute("UPDATE jobs SET status=?, note=?, updated_at=datetime('now') "
                  "WHERE id=?", (status, note, job_id))


def get(job_id):
    with _conn() as c:
        return c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()


if __name__ == "__main__":
    init()
    print("db ready at", config.DB_FILE)
