from __future__ import annotations

import datetime
import sqlite3
import threading
from pathlib import Path

from .models import EPHEMERAL_TTL, Message, StaleInfo

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    session_id      TEXT NOT NULL,
    turn_id         INTEGER NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    timezone        TEXT DEFAULT 'UTC',
    ttl_class       TEXT DEFAULT 'slow',
    source_id       TEXT DEFAULT NULL,
    invalidated_at  TEXT DEFAULT NULL,
    PRIMARY KEY (session_id, turn_id)
);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
"""

MIGRATIONS = [
    ("ttl_class", "ALTER TABLE messages ADD COLUMN ttl_class TEXT DEFAULT 'slow'"),
    ("source_id", "ALTER TABLE messages ADD COLUMN source_id TEXT DEFAULT NULL"),
    ("invalidated_at", "ALTER TABLE messages ADD COLUMN invalidated_at TEXT DEFAULT NULL"),
]

_INDEXES = "CREATE INDEX IF NOT EXISTS idx_messages_source_id ON messages(source_id);"


def _migrate(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(messages)").fetchall()}
    for col_name, ddl in MIGRATIONS:
        if col_name not in existing:
            conn.execute(ddl)
    conn.commit()


_COLS = "session_id, turn_id, role, content, created_at, timezone, ttl_class, source_id, invalidated_at"
_COLS_PLACEHOLDERS = "?, ?, ?, ?, ?, ?, ?, ?, ?"


class Store:
    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._local = threading.local()
        self._write_lock = threading.Lock()
        _init = sqlite3.connect(str(self._path))
        _init.execute("PRAGMA journal_mode=WAL")
        _init.close()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self._path))
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.executescript(SCHEMA)
            _migrate(self._local.conn)
            self._local.conn.execute(_INDEXES)
        return self._local.conn

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None

    def insert(self, msg: Message) -> None:
        conn = self._conn()
        inv = msg.invalidated_at.isoformat() if msg.invalidated_at else None
        conn.execute(
            f"INSERT OR IGNORE INTO messages ({_COLS}) VALUES ({_COLS_PLACEHOLDERS})",
            (msg.session_id, msg.turn_id, msg.role, msg.content,
             msg.created_at.isoformat(), msg.timezone,
             msg.ttl_class, msg.source_id, inv),
        )
        conn.commit()

    def insert_many(self, msgs: list[Message]) -> None:
        conn = self._conn()
        rows = [
            (m.session_id, m.turn_id, m.role, m.content,
             m.created_at.isoformat(), m.timezone,
             m.ttl_class, m.source_id,
             m.invalidated_at.isoformat() if m.invalidated_at else None)
            for m in msgs
        ]
        conn.executemany(
            f"INSERT OR IGNORE INTO messages ({_COLS}) VALUES ({_COLS_PLACEHOLDERS})",
            rows,
        )
        conn.commit()

    def load_session(self, session_id: str) -> list[Message]:
        conn = self._conn()
        cursor = conn.execute(
            f"SELECT {_COLS} FROM messages WHERE session_id = ? ORDER BY turn_id ASC",
            (session_id,),
        )
        return [_row_to_message(row) for row in cursor.fetchall()]

    def load_range(self, session_id: str, start: datetime.datetime, end: datetime.datetime) -> list[Message]:
        conn = self._conn()
        cursor = conn.execute(
            f"SELECT {_COLS} FROM messages WHERE session_id = ? AND created_at BETWEEN ? AND ? "
            "ORDER BY turn_id ASC",
            (session_id, start.isoformat(), end.isoformat()),
        )
        return [_row_to_message(row) for row in cursor.fetchall()]

    def last_n(self, session_id: str, n: int) -> list[Message]:
        conn = self._conn()
        cursor = conn.execute(
            f"SELECT {_COLS} FROM messages WHERE session_id = ? ORDER BY turn_id DESC LIMIT ?",
            (session_id, n),
        )
        return list(reversed([_row_to_message(row) for row in cursor.fetchall()]))

    def session_info(self, session_id: str) -> dict | None:
        conn = self._conn()
        cursor = conn.execute(
            "SELECT COUNT(*) as count, MAX(turn_id) as max_turn, "
            "MIN(created_at) as first, MAX(created_at) as last "
            "FROM messages WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        if not row or row["count"] == 0:
            return None
        return {
            "count": row["count"],
            "max_turn": row["max_turn"],
            "first": datetime.datetime.fromisoformat(row["first"]),
            "last": datetime.datetime.fromisoformat(row["last"]),
        }

    def next_turn(self, session_id: str) -> int:
        info = self.session_info(session_id)
        if info is None:
            return 1
        return info["max_turn"] + 1

    def insert_next(self, msg: Message) -> int:
        """Atomically assign turn_id and insert. Returns the assigned turn_id."""
        conn = self._conn()
        with self._write_lock:
            turn_id = conn.execute(
                "SELECT COALESCE(MAX(turn_id), 0) + 1 FROM messages WHERE session_id = ?",
                (msg.session_id,),
            ).fetchone()[0]
            inv = msg.invalidated_at.isoformat() if msg.invalidated_at else None
            conn.execute(
                f"INSERT INTO messages ({_COLS}) VALUES ({_COLS_PLACEHOLDERS})",
                (msg.session_id, turn_id, msg.role, msg.content,
                 msg.created_at.isoformat(), msg.timezone,
                 msg.ttl_class, msg.source_id, inv),
            )
            conn.commit()
        return turn_id

    def invalidate(self, source_id: str) -> int:
        conn = self._conn()
        now_str = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat()
        cursor = conn.execute(
            "UPDATE messages SET invalidated_at = ? "
            "WHERE source_id = ? AND ttl_class = 'event' AND invalidated_at IS NULL",
            (now_str, source_id),
        )
        conn.commit()
        return cursor.rowcount

    def stale_messages(self, session_id: str, now: datetime.datetime) -> list[StaleInfo]:
        conn = self._conn()
        cursor = conn.execute(
            f"SELECT {_COLS} FROM messages WHERE session_id = ? ORDER BY turn_id ASC",
            (session_id,),
        )
        stale = []
        for row in cursor.fetchall():
            msg = _row_to_message(row)
            if msg.ttl_class == "permanent":
                continue
            if msg.ttl_class == "event" and msg.invalidated_at is not None:
                stale.append(StaleInfo(
                    turn_id=msg.turn_id,
                    ttl_class=msg.ttl_class,
                    source_id=msg.source_id,
                    content_preview=msg.content[:60],
                    age=now - msg.created_at,
                ))
            elif msg.ttl_class == "ephemeral":
                age = now - msg.created_at
                if age > EPHEMERAL_TTL:
                    stale.append(StaleInfo(
                        turn_id=msg.turn_id,
                        ttl_class=msg.ttl_class,
                        source_id=msg.source_id,
                        content_preview=msg.content[:60],
                        age=age,
                    ))
        return stale


def _row_to_message(row: sqlite3.Row) -> Message:
    inv = row["invalidated_at"]
    return Message(
        session_id=row["session_id"],
        turn_id=row["turn_id"],
        role=row["role"],
        content=row["content"],
        created_at=datetime.datetime.fromisoformat(row["created_at"]),
        timezone=row["timezone"],
        ttl_class=row["ttl_class"],
        source_id=row["source_id"],
        invalidated_at=datetime.datetime.fromisoformat(inv) if inv else None,
    )
