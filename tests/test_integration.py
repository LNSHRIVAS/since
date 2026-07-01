import datetime
import tempfile
from pathlib import Path

from since import Message, Store, with_time


def test_end_to_end():
    now = datetime.datetime(2026, 6, 30, 15, 30, 0)
    db_path = Path(tempfile.mktemp(suffix=".db"))
    store = Store(db_path)

    messages = [
        Message("session_1", 1, "user", "hello", now - datetime.timedelta(hours=2)),
        Message("session_1", 2, "assistant", "hi there!", now - datetime.timedelta(hours=1, minutes=55)),
        Message("session_1", 3, "user", "remember our plan", now - datetime.timedelta(minutes=30)),
    ]
    store.insert_many(messages)

    loaded = store.load_session("session_1")
    assert len(loaded) == 3

    info = store.session_info("session_1")
    assert info is not None
    assert info["count"] == 3

    loaded_from_store = store.load_session("session_1")
    prompt = with_time(loaded_from_store, now=now)

    assert len(prompt) == 5
    assert prompt[0]["role"] == "system"
    assert "timestamp" in prompt[0]["content"]
    assert prompt[1]["role"] == "user"
    assert "hello" in prompt[1]["content"]
    assert prompt[2]["role"] == "assistant"
    assert "hi there!" in prompt[2]["content"]
    assert prompt[3]["role"] == "system"
    assert "Now:" in prompt[3]["content"]
    assert prompt[4]["role"] == "user"
    assert prompt[4]["content"] == "remember our plan"

    results = store.load_range("session_1", now - datetime.timedelta(hours=2), now - datetime.timedelta(hours=1))
    assert len(results) >= 1

    store.close()
    db_path.unlink()
