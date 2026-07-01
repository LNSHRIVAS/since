import concurrent.futures
import datetime
import tempfile
from pathlib import Path

from since import Message, Store


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def test_insert_next_atomic():
    db_path = Path(tempfile.mktemp(suffix=".db"))
    store = Store(db_path)

    n = 20
    def insert(i: int) -> int:
        msg = Message("s1", 0, "user", f"msg-{i}", _now())
        return store.insert_next(msg)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        pool.map(insert, range(n))

    msgs = store.load_session("s1")
    assert len(msgs) == n
    turn_ids = [m.turn_id for m in msgs]
    assert sorted(turn_ids) == list(range(1, n + 1))
    assert len(set(turn_ids)) == n
    contents = {m.content for m in msgs}
    assert contents == {f"msg-{i}" for i in range(n)}

    store.close()
    db_path.unlink()


def test_insert_next_empty_session():
    db_path = Path(tempfile.mktemp(suffix=".db"))
    store = Store(db_path)

    msg = Message("fresh", 0, "user", "first message", _now())
    turn_id = store.insert_next(msg)

    assert turn_id == 1

    msgs = store.load_session("fresh")
    assert len(msgs) == 1
    assert msgs[0].turn_id == 1
    assert msgs[0].content == "first message"

    store.close()
    db_path.unlink()


def test_insert_next_interleaved_sessions():
    db_path = Path(tempfile.mktemp(suffix=".db"))
    store = Store(db_path)

    def insert_pair(sid: str, content: str) -> tuple[int, int]:
        m1 = Message(sid, 0, "user", content, _now())
        t1 = store.insert_next(m1)
        m2 = Message(sid, 0, "assistant", f"reply to {content}", _now())
        t2 = store.insert_next(m2)
        return t1, t2

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            pool.submit(insert_pair, "a", "hi"),
            pool.submit(insert_pair, "b", "hello"),
            pool.submit(insert_pair, "a", "how are you"),
            pool.submit(insert_pair, "b", "fine thanks"),
        ]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    msgs_a = store.load_session("a")
    msgs_b = store.load_session("b")
    assert len(msgs_a) == 4
    assert len(msgs_b) == 4
    assert [m.turn_id for m in msgs_a] == [1, 2, 3, 4]
    assert [m.turn_id for m in msgs_b] == [1, 2, 3, 4]

    store.close()
    db_path.unlink()


def test_insert_next_does_not_break_existing_insert():
    db_path = Path(tempfile.mktemp(suffix=".db"))
    store = Store(db_path)

    msg = Message("legacy", 5, "user", "explicit turn", _now())
    store.insert(msg)

    msg2 = Message("legacy", 0, "assistant", "auto turn", _now())
    t = store.insert_next(msg2)

    assert t == 6

    store.close()
    db_path.unlink()
