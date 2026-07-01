import datetime

from since.format import (
    build_prompt,
    format_absolute,
    _format_timedelta_short,
    _format_timedelta_compact,
    _time_of_day_band,
)
from since.models import Message


def test_format_timedelta_short():
    assert _format_timedelta_short(datetime.timedelta(seconds=5)) == "just now"
    assert _format_timedelta_short(datetime.timedelta(minutes=3)) == "3m ago"
    assert _format_timedelta_short(datetime.timedelta(hours=2, minutes=15)) == "2h 15m ago"
    assert _format_timedelta_short(datetime.timedelta(hours=3)) == "3h ago"
    assert _format_timedelta_short(datetime.timedelta(days=1, hours=4)) == "1d 4h ago"
    assert _format_timedelta_short(datetime.timedelta(days=5)) == "5d ago"
    assert _format_timedelta_short(datetime.timedelta(weeks=2, days=3)) == "2w 3d ago"
    assert _format_timedelta_short(datetime.timedelta(days=45)) == "1mo 15d ago"
    assert _format_timedelta_short(datetime.timedelta(days=400)) == "1y 35d ago"


def test_format_timedelta_compact():
    assert _format_timedelta_compact(datetime.timedelta(seconds=30)) == "30s"
    assert _format_timedelta_compact(datetime.timedelta(minutes=5)) == "5m"
    assert _format_timedelta_compact(datetime.timedelta(hours=3, minutes=45)) == "3h 45m"
    assert _format_timedelta_compact(datetime.timedelta(days=5, hours=2)) == "5d 2h"


def test_time_of_day_band():
    dt = datetime.datetime(2026, 6, 30, 3, 0, 0)
    assert _time_of_day_band(dt) == "night"
    dt = datetime.datetime(2026, 6, 30, 8, 0, 0)
    assert _time_of_day_band(dt) == "morning"
    dt = datetime.datetime(2026, 6, 30, 14, 0, 0)
    assert _time_of_day_band(dt) == "afternoon"
    dt = datetime.datetime(2026, 6, 30, 19, 0, 0)
    assert _time_of_day_band(dt) == "evening"


def test_format_absolute():
    now = datetime.datetime(2026, 6, 30, 15, 30, 0)
    msg = Message(
        session_id="s1",
        turn_id=1,
        role="user",
        content="hello",
        created_at=now - datetime.timedelta(hours=2),
    )
    result = format_absolute(msg)
    assert "hello" in result
    assert "Jun 30" in result
    assert "|" not in result


def test_build_prompt_simple():
    now = datetime.datetime(2026, 6, 30, 15, 30, 0)
    msg = Message("s1", 1, "user", "hello", now - datetime.timedelta(minutes=5))
    prompt = build_prompt([msg], now, include_nudge=True)
    assert len(prompt) == 3
    assert prompt[0]["role"] == "system"
    assert "timestamp" in prompt[0]["content"]
    assert prompt[1]["role"] == "system"
    assert "Now:" in prompt[1]["content"]
    assert prompt[2]["role"] == "user"
    assert prompt[2]["content"] == "hello"


def test_build_prompt_current_separated():
    now = datetime.datetime(2026, 6, 30, 15, 30, 0)
    msgs = [
        Message("s1", 1, "user", "old message", now - datetime.timedelta(hours=2)),
        Message("s1", 2, "assistant", "old reply", now - datetime.timedelta(hours=1, minutes=55)),
        Message("s1", 3, "user", "current turn", now),
    ]
    prompt = build_prompt(msgs, now, include_nudge=True)

    assert prompt[0]["role"] == "system"
    assert prompt[1]["role"] == "user"
    assert "old message" in prompt[1]["content"]
    assert "old reply" in prompt[2]["content"]
    assert prompt[3]["role"] == "system"
    assert "Now:" in prompt[3]["content"]
    assert prompt[4]["role"] == "user"
    assert prompt[4]["content"] == "current turn"


def test_build_prompt_with_extra_context():
    now = datetime.datetime(2026, 6, 30, 15, 30, 0)
    msg = Message("s1", 1, "user", "current", now)
    extra = [Message("s1", 0, "user", "retrieved", now - datetime.timedelta(days=3))]
    prompt = build_prompt([msg], now, include_nudge=False, extra_context=extra)

    assert any("Retrieved from history" in m["content"] for m in prompt if m["role"] == "system")
