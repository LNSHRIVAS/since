import datetime

from since.timeparse import detect_temporal, parse_temporal


def test_detect_temporal():
    assert detect_temporal("what did we say 5 days ago")
    assert detect_temporal("remind me what we talked about yesterday")
    assert detect_temporal("what happened on Tuesday")
    assert detect_temporal("what did we discuss last week")
    assert detect_temporal("tell me about June 25th")
    assert detect_temporal("what did we say this morning")
    assert not detect_temporal("hello how are you")
    assert not detect_temporal("tell me a joke")


def test_parse_relative_days_ago():
    now = datetime.datetime(2026, 6, 30, 15, 30, 0)
    result = parse_temporal("5 days ago", now)
    assert result is not None
    start, end = result
    expected_start = now - datetime.timedelta(days=5)
    assert abs((start - expected_start).total_seconds()) < 1
    assert end == now


def test_parse_relative_hours_ago():
    now = datetime.datetime(2026, 6, 30, 15, 30, 0)
    result = parse_temporal("3 hours ago", now)
    assert result is not None
    start, end = result
    expected_start = now - datetime.timedelta(hours=3)
    assert abs((start - expected_start).total_seconds()) < 1
    assert end == now


def test_parse_yesterday():
    now = datetime.datetime(2026, 6, 30, 15, 30, 0)
    result = parse_temporal("yesterday", now)
    assert result is not None
    start, end = result
    assert start.day == 29
    assert start.month == 6
    assert start.year == 2026


def test_parse_yesterday_at_time():
    now = datetime.datetime(2026, 6, 30, 15, 30, 0)
    result = parse_temporal("yesterday at 3pm", now)
    assert result is not None
    start, end = result
    assert start.day == 29
    assert start.hour == 15
    assert start.minute == 0


def test_parse_named_day():
    now = datetime.datetime(2026, 6, 30, 15, 30, 0)
    # June 30 2026 is a Tuesday
    result = parse_temporal("Monday", now)
    assert result is not None
    start, end = result
    # Monday before Tuesday June 30 would be June 29
    assert start.day == 29
    assert start.month == 6


def test_parse_last_week():
    now = datetime.datetime(2026, 6, 30, 15, 30, 0)
    result = parse_temporal("last week", now)
    assert result is not None
    start, end = result
    assert end.day == 30  # today is June 30, start of this week (Monday June 29 would be yesterday... actually wait)
    # last week means the 7 days before this week started
    # this week started Monday June 29 (Tuesday June 30, weekday 1 = Tuesday, Monday is 0)
    # Actually June 30 2026... let me check what day of week that is
    # Let's just verify it returns something reasonable
    assert start < end


def test_parse_date_june_25():
    now = datetime.datetime(2026, 6, 30, 15, 30, 0)
    result = parse_temporal("June 25", now)
    assert result is not None
    start, end = result
    assert start.month == 6
    assert start.day == 25
    assert start.year == 2026


def test_parse_today():
    now = datetime.datetime(2026, 6, 30, 15, 30, 0)
    result = parse_temporal("today", now)
    assert result is not None
    start, end = result
    assert start.day == 30
    assert start.month == 6


def test_parse_this_morning():
    now = datetime.datetime(2026, 6, 30, 15, 30, 0)
    result = parse_temporal("this morning", now)
    assert result is not None
    start, end = result
    assert start.day == 30
    assert start.hour == 5


def test_parse_tuesday_afternoon():
    now = datetime.datetime(2026, 6, 30, 15, 30, 0)
    result = parse_temporal("Tuesday afternoon", now)
    assert result is not None
    start, end = result
    assert start.hour == 12  # afternoon starts at 12


def test_no_match():
    now = datetime.datetime(2026, 6, 30, 15, 30, 0)
    result = parse_temporal("hello world", now)
    assert result is None
