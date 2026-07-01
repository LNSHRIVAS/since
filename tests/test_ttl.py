import datetime
import tempfile
from pathlib import Path

from since.models import Message
from since.store import Store


def _msg(session_id: str, turn_id: int, ttl_class: str = "slow",
         source_id: str | None = None, age_m: int = 0) -> Message:
    return Message(
        session_id=session_id,
        turn_id=turn_id,
        role="user",
        content=f"msg {turn_id}",
        created_at=datetime.datetime(2026, 6, 30, 15, 0, 0) - datetime.timedelta(minutes=age_m),
        ttl_class=ttl_class,
        source_id=source_id,
    )


def test_stale_ephemeral():
    db = Path(tempfile.mktemp(suffix=".db"))
    store = Store(db)
    now = datetime.datetime(2026, 6, 30, 15, 10, 0)  # 10 min later

    store.insert(_msg("s1", 1, ttl_class="permanent", age_m=8))
    store.insert(_msg("s1", 2, ttl_class="ephemeral", age_m=8))
    store.insert(_msg("s1", 3, ttl_class="slow", age_m=8))

    stale = store.stale_messages("s1", now)
    assert len(stale) == 1
    assert stale[0].turn_id == 2
    assert stale[0].ttl_class == "ephemeral"

    store.close()
    db.unlink()


def test_stale_event():
    db = Path(tempfile.mktemp(suffix=".db"))
    store = Store(db)
    now = datetime.datetime(2026, 6, 30, 15, 10, 0)

    store.insert(_msg("s1", 1, ttl_class="permanent", source_id="src_a", age_m=5))
    store.insert(_msg("s1", 2, ttl_class="event", source_id="src_a", age_m=5))
    store.insert(_msg("s1", 3, ttl_class="event", source_id="src_b", age_m=5))

    # Invalidate src_a
    count = store.invalidate("src_a")
    assert count == 1

    stale = store.stale_messages("s1", now)
    assert len(stale) == 1
    assert stale[0].turn_id == 2
    assert stale[0].source_id == "src_a"

    store.close()
    db.unlink()


def test_stale_permanent_never():
    db = Path(tempfile.mktemp(suffix=".db"))
    store = Store(db)
    now = datetime.datetime(2026, 6, 30, 16, 0, 0)

    store.insert(_msg("s1", 1, ttl_class="permanent", age_m=60))
    store.insert(_msg("s1", 2, ttl_class="ephemeral", age_m=60))

    stale = store.stale_messages("s1", now)
    # Only ephemeral is stale (60 min > 5 min)
    assert len(stale) == 1
    assert stale[0].turn_id == 2

    store.close()
    db.unlink()


def test_ephemeral_not_expired():
    db = Path(tempfile.mktemp(suffix=".db"))
    store = Store(db)
    now = datetime.datetime(2026, 6, 30, 15, 2, 0)  # only 2 min later

    store.insert(_msg("s1", 1, ttl_class="ephemeral", age_m=2))

    stale = store.stale_messages("s1", now)
    assert len(stale) == 0  # 2 min < 5 min EPHEMERAL_TTL

    store.close()
    db.unlink()


def test_stale_surfacing_in_tail():
    from since.format import build_prompt
    from since.models import StaleInfo

    now = datetime.datetime(2026, 6, 30, 15, 30, 0)

    msg = Message("s1", 1, "user", "hello", now - datetime.timedelta(minutes=10),
                  ttl_class="slow")

    stale_info = [StaleInfo(
        turn_id=2,
        ttl_class="event",
        source_id="read_file",
        content_preview="The file contents were...",
        age=datetime.timedelta(hours=2),
    )]

    prompt = build_prompt([msg], now, include_nudge=False, stale_info=stale_info)

    tail = [m for m in prompt if m["role"] == "system"][-1]["content"]
    assert "⚠" in tail
    assert "Stale:" in tail
    assert "read_file" in tail
    assert "2h" in tail


def test_empty_stale_info():
    from since.format import build_prompt
    now = datetime.datetime(2026, 6, 30, 15, 30, 0)
    msg = Message("s1", 1, "user", "hello", now)
    prompt = build_prompt([msg], now, include_nudge=False, stale_info=[])
    tail = [m for m in prompt if m["role"] == "system"][-1]["content"]
    assert "Stale" not in tail
    assert "⚠" not in tail


def test_migration_adds_columns():
    db = Path(tempfile.mktemp(suffix=".db"))
    conn = __import__("sqlite3").connect(str(db))
    conn.execute("CREATE TABLE messages (session_id TEXT, turn_id INTEGER, role TEXT, content TEXT, created_at TEXT, timezone TEXT, PRIMARY KEY (session_id, turn_id))")
    conn.commit()
    conn.close()

    store = Store(db)
    store.insert(Message("s1", 1, "user", "hello", datetime.datetime(2026, 6, 30, 15, 0, 0)))

    loaded = store.load_session("s1")
    assert len(loaded) == 1
    assert loaded[0].ttl_class == "slow"
    assert loaded[0].source_id is None

    store.close()
    db.unlink()


def test_invalidate_unknown_source():
    db = Path(tempfile.mktemp(suffix=".db"))
    store = Store(db)

    store.insert(_msg("s1", 1, ttl_class="event", source_id="src_a", age_m=0))
    count = store.invalidate("nonexistent")
    assert count == 0

    store.close()
    db.unlink()
