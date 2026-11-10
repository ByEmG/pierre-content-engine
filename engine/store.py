"""SQLite storage for notes, drafts, usage and small key-value state."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    text TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'telegram',
    used INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    pillar TEXT NOT NULL,
    topic_id TEXT,
    note_ids TEXT,
    angle TEXT,
    hook TEXT,
    body TEXT,
    card_text TEXT,
    score INTEGER,
    score_detail TEXT,
    passes INTEGER,
    image_path TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    scheduled_for TEXT,
    posted_at TEXT,
    linkedin_urn TEXT
);
CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    task TEXT,
    model TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER
);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
"""


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


class Store:
    def __init__(self, path: Path | str):
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    # key-value
    def get(self, key: str, default=None):
        row = self.db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set(self, key: str, value) -> None:
        self.db.execute("INSERT OR REPLACE INTO kv(key, value) VALUES(?, ?)", (key, json.dumps(value)))
        self.db.commit()

    # notes
    def add_note(self, text: str, source: str = "telegram") -> int:
        cur = self.db.execute(
            "INSERT INTO notes(created_at, text, source) VALUES(?, ?, ?)", (iso(now_utc()), text, source)
        )
        self.db.commit()
        return cur.lastrowid

    def recent_notes(self, days: int) -> list[sqlite3.Row]:
        since = iso(now_utc() - timedelta(days=days))
        return self.db.execute(
            "SELECT * FROM notes WHERE used=0 AND created_at>=? ORDER BY created_at DESC", (since,)
        ).fetchall()

    def mark_notes_used(self, ids: list[int]) -> None:
        if ids:
            self.db.executemany("UPDATE notes SET used=1 WHERE id=?", [(i,) for i in ids])
            self.db.commit()

    # drafts
    def add_draft(self, **fields) -> int:
        fields.setdefault("created_at", iso(now_utc()))
        for k in ("score_detail", "note_ids"):
            if k in fields and not isinstance(fields[k], str):
                fields[k] = json.dumps(fields[k])
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        cur = self.db.execute(f"INSERT INTO drafts({cols}) VALUES({marks})", tuple(fields.values()))
        self.db.commit()
        return cur.lastrowid

    def update_draft(self, draft_id: int, **fields) -> None:
        for k in ("score_detail", "note_ids"):
            if k in fields and not isinstance(fields[k], str):
                fields[k] = json.dumps(fields[k])
        sets = ", ".join(f"{k}=?" for k in fields)
        self.db.execute(f"UPDATE drafts SET {sets} WHERE id=?", (*fields.values(), draft_id))
        self.db.commit()

    def draft(self, draft_id: int) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()

    def drafts_since(self, days: int, statuses: tuple[str, ...]) -> list[sqlite3.Row]:
        since = iso(now_utc() - timedelta(days=days))
        marks = ",".join("?" for _ in statuses)
        return self.db.execute(
            f"SELECT * FROM drafts WHERE created_at>=? AND status IN ({marks})", (since, *statuses)
        ).fetchall()

    def due_posts(self, now: datetime) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT * FROM drafts WHERE status='scheduled' AND scheduled_for<=? ORDER BY scheduled_for",
            (iso(now),),
        ).fetchall()

    def scheduled_slots(self) -> set[str]:
        rows = self.db.execute("SELECT scheduled_for FROM drafts WHERE status='scheduled'").fetchall()
        return {r["scheduled_for"] for r in rows}

    # usage
    def log_usage(self, task: str, model: str, input_tokens: int, output_tokens: int) -> None:
        self.db.execute(
            "INSERT INTO usage(created_at, task, model, input_tokens, output_tokens) VALUES(?,?,?,?,?)",
            (iso(now_utc()), task, model, input_tokens, output_tokens),
        )
        self.db.commit()
