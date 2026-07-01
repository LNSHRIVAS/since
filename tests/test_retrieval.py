import datetime
import tempfile
from pathlib import Path

from since import Message, Store, with_time


def test_retrieve_by_days_ago():
    now = datetime.datetime(2026, 6, 30, 15, 30, 0)
    db_path = Path(tempfile.mktemp(suffix=".db"))
    store = Store(db_path)

    old = [
        Message("s1", 1, "user", "let's plan the project", now - datetime.timedelta(days=3, hours=2)),
        Message("s1", 2, "assistant", "sounds good, what are the goals?", now - datetime.timedelta(days=3, hours=1, minutes=55)),
    ]
    store.insert_many(old)

    recent = [
        Message("s1", 3, "user", "I'm back, where were we?", now - datetime.timedelta(minutes=5)),
        Message("s1", 4, "assistant", "you were planning the project", now - datetime.timedelta(minutes=4)),
    ]
    store.insert_many(recent)

    loaded = store.last_n("s1", 2)
    assert len(loaded) == 2

    prompt = with_time(loaded, now=now, store=store, user_input="what did we say 4 days ago")

    system_msgs = [m for m in prompt if m["role"] == "system"]
    user_msgs = [m for m in prompt if m["role"] == "user"]

    retrieved_headers = [m["content"] for m in system_msgs if "Retrieved from history" in m["content"]]
    assert len(retrieved_headers) == 1

    assert any("plan the project" in m["content"] for m in user_msgs)

    store.close()
    db_path.unlink()


def test_no_false_retrieval():
    now = datetime.datetime(2026, 6, 30, 15, 30, 0)
    db_path = Path(tempfile.mktemp(suffix=".db"))
    store = Store(db_path)

    msgs = [
        Message("s2", 1, "user", "hello", now - datetime.timedelta(minutes=10)),
        Message("s2", 2, "assistant", "hi", now - datetime.timedelta(minutes=9)),
    ]
    store.insert_many(msgs)
    loaded = store.load_session("s2")

    prompt = with_time(loaded, now=now, store=store, user_input="tell me a joke")

    system_msgs = [m for m in prompt if m["role"] == "system"]
    retrieved_headers = [m["content"] for m in system_msgs if "Retrieved from history" in m["content"]]
    assert len(retrieved_headers) == 0

    store.close()
    db_path.unlink()


def test_retrieve_yesterday():
    now = datetime.datetime(2026, 6, 30, 15, 30, 0)
    db_path = Path(tempfile.mktemp(suffix=".db"))
    store = Store(db_path)

    msgs = [
        Message("s3", 1, "user", "had lunch at the new place", now - datetime.timedelta(days=1, hours=3)),
        Message("s3", 2, "assistant", "how was it?", now - datetime.timedelta(days=1, hours=2, minutes=55)),
        Message("s3", 3, "user", "it was great!", now - datetime.timedelta(hours=1)),
    ]
    store.insert_many(msgs)

    loaded = store.last_n("s3", 1)
    assert len(loaded) == 1

    prompt = with_time(loaded, now=now, store=store, user_input="what did we talk about yesterday")

    system_msgs = [m for m in prompt if m["role"] == "system"]
    retrieved_headers = [m["content"] for m in system_msgs if "Retrieved from history" in m["content"]]
    assert len(retrieved_headers) == 1

    user_msgs = [m for m in prompt if m["role"] == "user"]
    assert any("lunch" in m["content"] for m in user_msgs)

    store.close()
    db_path.unlink()
