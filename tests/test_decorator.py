import datetime
import tempfile
from pathlib import Path

from since import Store, since_time


class FakeResponse:
    def __init__(self, text: str):
        self.choices = [FakeChoice(FakeMessage(text))]


class FakeChoice:
    def __init__(self, msg):
        self.message = msg


class FakeMessage:
    def __init__(self, content: str):
        self.content = content


def test_sense_time_basic():
    db_path = Path(tempfile.mktemp(suffix=".db"))
    store = Store(db_path)
    calls = []

    @since_time(store=store, session_id="test_sesh")
    def chat(messages):
        calls.append(messages)
        return FakeResponse("hello back!")

    result = chat(messages=[{"role": "user", "content": "hello"}])

    assert result.choices[0].message.content == "hello back!"
    assert len(calls) == 1

    enriched = calls[0]
    assert len(enriched) >= 2
    assert enriched[-1]["role"] == "user"

    info = store.session_info("test_sesh")
    assert info is not None
    assert info["count"] == 2

    messages = store.load_session("test_sesh")
    assert messages[0].content == "hello"
    assert messages[1].content == "hello back!"

    store.close()
    db_path.unlink()


def test_sense_time_accumulates():
    db_path = Path(tempfile.mktemp(suffix=".db"))
    store = Store(db_path)

    @since_time(store=store, session_id="accum_test")
    def chat(messages):
        return FakeResponse("ok")

    chat(messages=[{"role": "user", "content": "first"}])
    chat(messages=[{"role": "user", "content": "second"}])
    chat(messages=[{"role": "user", "content": "third"}])

    info = store.session_info("accum_test")
    assert info is not None
    assert info["count"] == 6

    store.close()
    db_path.unlink()


def test_strips_timestamp_prefix():
    db_path = Path(tempfile.mktemp(suffix=".db"))
    store = Store(db_path)
    calls = []

    @since_time(store=store, session_id="strip_test")
    def chat(messages):
        calls.append(messages)
        return FakeResponse("[Tue Jun 30, 08:21PM]  Glad to hear that! How's it going?")

    chat(messages=[{"role": "user", "content": "hey"}])
    msgs = store.load_session("strip_test")
    stored = [m for m in msgs if m.role == "assistant"]
    assert len(stored) == 1
    assert stored[0].content == "Glad to hear that! How's it going?"
    assert "[Tue Jun 30" not in stored[0].content

    store.close()
    db_path.unlink()


def test_strips_double_prefix():
    db_path = Path(tempfile.mktemp(suffix=".db"))
    store = Store(db_path)
    calls = []

    @since_time(store=store, session_id="double_test")
    def chat(messages):
        calls.append(messages)
        return FakeResponse("[Tue Jun 30, 08:22PM]  [Tue Jun 30, 08:22PM]  Right, it hasn't been long!")

    chat(messages=[{"role": "user", "content": "hey"}])
    msgs = store.load_session("double_test")
    stored = [m for m in msgs if m.role == "assistant"]
    assert len(stored) == 1
    assert stored[0].content == "Right, it hasn't been long!"
    assert "[Tue Jun 30" not in stored[0].content

    store.close()
    db_path.unlink()


def test_does_not_strip_non_timestamp():
    db_path = Path(tempfile.mktemp(suffix=".db"))
    store = Store(db_path)
    calls = []

    @since_time(store=store, session_id="safe_test")
    def chat(messages):
        calls.append(messages)
        return FakeResponse("[1, 2, 3] this starts with brackets but not a timestamp")

    chat(messages=[{"role": "user", "content": "hey"}])
    msgs = store.load_session("safe_test")
    stored = [m for m in msgs if m.role == "assistant"]
    assert len(stored) == 1
    assert stored[0].content == "[1, 2, 3] this starts with brackets but not a timestamp"

    store.close()
    db_path.unlink()
