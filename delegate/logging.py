"""Phase 4: delegation logging to a local SQLite file.

Not named after the stdlib `logging` module in spirit - this only ever
gets imported as `delegate.logging` / `.logging`, so it doesn't shadow it.
"""

from __future__ import annotations

import contextlib
import datetime
import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "delegations.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS delegations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool TEXT NOT NULL,
    backend TEXT,
    model TEXT,
    task TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    iterations INTEGER,
    success INTEGER NOT NULL,
    result_preview TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER
);
"""

# Added after the initial schema (transcript capture) - ALTER TABLE rather
# than a schema bump, since delegations.db is local/disposable and this
# keeps existing local DBs working without a manual migration step.
_MIGRATIONS = [
    "ALTER TABLE delegations ADD COLUMN transcript TEXT",
]

_RESULT_PREVIEW_LIMIT = 500

_LIST_COLUMNS = (
    "id, tool, backend, model, task, started_at, ended_at, duration_seconds, "
    "iterations, success, result_preview, prompt_tokens, completion_tokens, total_tokens"
)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute(_SCHEMA)
    for migration in _MIGRATIONS:
        try:
            conn.execute(migration)
        except sqlite3.OperationalError:
            pass  # column already exists
    return conn


def log_delegation(
    *,
    tool: str,
    backend: str | None,
    model: str | None,
    task: str,
    started_at: datetime.datetime,
    ended_at: datetime.datetime,
    iterations: int | None,
    success: bool,
    result_preview: str,
    usage: dict | None = None,
    transcript: list[dict] | None = None,
) -> int | None:
    """Best-effort log write - never raises, since a logging failure
    shouldn't take down a delegation that otherwise succeeded. Returns the
    new row's id, or None if the write failed."""
    usage = usage or {}
    try:
        with contextlib.closing(_connect()) as conn:
            cursor = conn.execute(
                """
                INSERT INTO delegations (
                    tool, backend, model, task, started_at, ended_at,
                    duration_seconds, iterations, success, result_preview,
                    prompt_tokens, completion_tokens, total_tokens, transcript
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tool,
                    backend,
                    model,
                    task,
                    started_at.isoformat(),
                    ended_at.isoformat(),
                    (ended_at - started_at).total_seconds(),
                    iterations,
                    1 if success else 0,
                    result_preview[:_RESULT_PREVIEW_LIMIT],
                    usage.get("prompt_tokens"),
                    usage.get("completion_tokens"),
                    usage.get("total_tokens"),
                    json.dumps(transcript) if transcript is not None else None,
                ),
            )
            conn.commit()
            return cursor.lastrowid
    except sqlite3.Error:
        return None


def format_usage_suffix(usage: dict | None) -> str:
    """Render a trailing '[tokens: ...]' line for a tool's return string, so
    the calling agent sees token usage without a separate
    list_recent_delegations call. Empty string if no usage is available."""
    if not usage:
        return ""
    parts = []
    if usage.get("prompt_tokens") is not None:
        parts.append(f"{usage['prompt_tokens']} prompt")
    if usage.get("completion_tokens") is not None:
        parts.append(f"{usage['completion_tokens']} completion")
    if usage.get("total_tokens") is not None:
        parts.append(f"{usage['total_tokens']} total")
    if not parts:
        return ""
    return "\n\n[tokens: " + " / ".join(parts) + "]"


def list_recent(limit: int = 20) -> list[dict]:
    # transcripts can be large; excluded here by column list, fetch via
    # get_transcript(id) instead so a routine listing call stays small.
    with contextlib.closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT {_LIST_COLUMNS} FROM delegations ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]


def get_transcript(delegation_id: int) -> list[dict] | None:
    """Full message transcript for one delegation, if it was captured with
    capture_transcript=True. None if the id doesn't exist or no transcript
    was captured for that call."""
    with contextlib.closing(_connect()) as conn:
        row = conn.execute(
            "SELECT transcript FROM delegations WHERE id = ?", (delegation_id,)
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return json.loads(row[0])
