import datetime
import os
import tempfile
import time
from pathlib import Path

from since.models import Message
from since.store import Store
from since.stale_files import stamp_file_read, check_and_invalidate, is_stale


def test_stamp_read_creates_event():
    db = Path(tempfile.mktemp(suffix=".db"))
    store = Store(db)
    tmp = Path(tempfile.mktemp(suffix=".txt"))
    tmp.write_text("hello")

    src = stamp_file_read(str(tmp), store, "s1")
    assert src == f"read:{tmp.resolve()}"
    assert store.session_info("s1")["count"] == 2

    msgs = store.load_session("s1")
    assert msgs[0].ttl_class == "event"
    assert msgs[0].source_id == src
    assert msgs[1].ttl_class == "event"
    assert msgs[1].source_id == src

    store.close()
    db.unlink()
    tmp.unlink()


def test_check_unchanged():
    db = Path(tempfile.mktemp(suffix=".db"))
    store = Store(db)
    tmp = Path(tempfile.mktemp(suffix=".txt"))
    tmp.write_text("hello")

    stamp_file_read(str(tmp), store, "s1")
    assert check_and_invalidate(str(tmp), store, "s1") is False
    assert is_stale(str(tmp), store, "s1") is False

    store.close()
    db.unlink()
    tmp.unlink()


def test_check_changed_invalidates():
    db = Path(tempfile.mktemp(suffix=".db"))
    store = Store(db)
    tmp = Path(tempfile.mktemp(suffix=".txt"))
    tmp.write_text("hello")

    stamp_file_read(str(tmp), store, "s1")
    time.sleep(0.01)
    tmp.write_text("world")

    assert is_stale(str(tmp), store, "s1") is True
    assert check_and_invalidate(str(tmp), store, "s1") is True

    msgs = store.load_session("s1")
    invalidated = [m for m in msgs if m.invalidated_at is not None]
    assert len(invalidated) == 2

    store.close()
    db.unlink()
    tmp.unlink()


def test_no_stale_after_fresh_read():
    db = Path(tempfile.mktemp(suffix=".db"))
    store = Store(db)
    tmp = Path(tempfile.mktemp(suffix=".txt"))
    tmp.write_text("hello")

    stamp_file_read(str(tmp), store, "s1")
    time.sleep(0.01)
    tmp.write_text("world")
    check_and_invalidate(str(tmp), store, "s1")

    stale_before = len(store.stale_messages("s1", datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)))

    stamp_file_read(str(tmp), store, "s1")
    stale_after = len(store.stale_messages("s1", datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)))

    assert stale_after == stale_before

    store.close()
    db.unlink()
    tmp.unlink()


def test_file_not_found():
    db = Path(tempfile.mktemp(suffix=".db"))
    store = Store(db)
    try:
        stamp_file_read("nonexistent_file.txt", store, "s1")
        assert False, "Should have raised FileNotFoundError"
    except FileNotFoundError:
        pass
    store.close()
    if db.exists():
        db.unlink()
