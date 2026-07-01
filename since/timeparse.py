from __future__ import annotations

import datetime
import re

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

TIME_BANDS = {
    "morning": (5, 12),
    "afternoon": (12, 17),
    "evening": (17, 21),
    "night": (21, 5),
    "dawn": (4, 6),
    "midday": (11, 13),
    "midnight": (23, 1),
}


def _last_weekday(day: int, now: datetime.datetime) -> datetime.datetime:
    today = now.weekday()
    days_ago = (today - day) % 7
    if days_ago == 0:
        days_ago = 7
    return (now - datetime.timedelta(days=days_ago)).replace(hour=0, minute=0, second=0, microsecond=0)


def _next_weekday(day: int, now: datetime.datetime) -> datetime.datetime:
    today = now.weekday()
    days_ahead = (day - today) % 7
    if days_ahead == 0:
        days_ahead = 7
    return (now + datetime.timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)


def _parse_time(s: str) -> int | None:
    s = s.strip().lower()

    m = re.match(r"(\d{1,2}):(\d{2})\s*(am|pm)?", s)
    if m:
        h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3)
        if ap == "pm" and h != 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        return h * 60 + mi

    m = re.match(r"(\d{1,2})\s*(am|pm)", s)
    if m:
        h, ap = int(m.group(1)), m.group(2)
        if ap == "pm" and h != 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        return h * 60

    band = TIME_BANDS.get(s)
    if band:
        return band[0] * 60

    return None


def parse_temporal(text: str, now: datetime.datetime | None = None) -> tuple[datetime.datetime, datetime.datetime] | None:
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    text = text.strip().lower()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    result = None

    # --- exact date: "June 25" or "25 June" or "Jun 25" ---
    m = re.search(r"(?:on\s+)?(\w+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s+(\d{4}))?", text)
    if m:
        maybe_month = m.group(1).lower()
        maybe_day = int(m.group(2))
        if maybe_month in MONTHS:
            year = int(m.group(3)) if m.group(3) else now.year
            month = MONTHS[maybe_month]
            try:
                dt = datetime.datetime(year, month, maybe_day, 0, 0, 0)
                time_match = re.search(r"\bat\b\s+(.+)", text)
                if time_match:
                    mins = _parse_time(time_match.group(1))
                    if mins is not None:
                        dt = dt.replace(hour=mins // 60, minute=mins % 60)
                    end_dt = dt + datetime.timedelta(hours=1)
                else:
                    end_dt = dt + datetime.timedelta(days=1)
                return (dt, end_dt)
            except ValueError:
                pass

    m = re.search(r"(?:on\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+(\w+)(?:\s+(\d{4}))?", text)
    if m:
        maybe_day = int(m.group(1))
        maybe_month = m.group(2).lower()
        if maybe_month in MONTHS:
            year = int(m.group(3)) if m.group(3) else now.year
            month = MONTHS[maybe_month]
            try:
                dt = datetime.datetime(year, month, maybe_day, 0, 0, 0)
                time_match = re.search(r"\bat\b\s+(.+)", text)
                if time_match:
                    mins = _parse_time(time_match.group(1))
                    if mins is not None:
                        dt = dt.replace(hour=mins // 60, minute=mins % 60)
                    end_dt = dt + datetime.timedelta(hours=1)
                else:
                    end_dt = dt + datetime.timedelta(days=1)
                return (dt, end_dt)
            except ValueError:
                pass

    # --- "today", "yesterday", "tomorrow" ---
    if re.search(r"\btoday\b", text):
        start = today_start
        time_match = re.search(r"\bat\b\s+(.+)", text)
        if time_match:
            mins = _parse_time(time_match.group(1))
            if mins is not None:
                start = start.replace(hour=mins // 60, minute=mins % 60)
            end = start + datetime.timedelta(hours=1)
        else:
            end = start + datetime.timedelta(days=1)
        result = (start, end)

    if re.search(r"\byesterday\b", text):
        start = today_start - datetime.timedelta(days=1)
        time_match = re.search(r"\bat\b\s+(.+)", text)
        if time_match:
            mins = _parse_time(time_match.group(1))
            if mins is not None:
                start = start.replace(hour=mins // 60, minute=mins % 60)
            end = start + datetime.timedelta(hours=1)
        else:
            end = start + datetime.timedelta(days=1)
        result = (start, end)

    if re.search(r"\btomorrow\b", text):
        start = today_start + datetime.timedelta(days=1)
        time_match = re.search(r"\bat\b\s+(.+)", text)
        if time_match:
            mins = _parse_time(time_match.group(1))
            if mins is not None:
                start = start.replace(hour=mins // 60, minute=mins % 60)
            end = start + datetime.timedelta(hours=1)
        else:
            end = start + datetime.timedelta(days=1)
        result = (start, end)

    # --- named days: "Monday", "last Tuesday", "this Friday" ---
    for day_name, day_num in WEEKDAYS.items():
        pattern = rf"(last|this|next)?\s*{day_name}\b"
        m = re.search(pattern, text)
        if m:
            qualifier = m.group(1)
            if qualifier == "last":
                dt = _last_weekday(day_num, now)
            elif qualifier == "next":
                dt = _next_weekday(day_num, now)
            else:
                dt = _last_weekday(day_num, now)
                if dt.date() == now.date():
                    pass
                elif (now - dt).days > 7:
                    dt = _next_weekday(day_num, now)

            time_match = re.search(r"\bat\b\s+(.+)", text)
            band_match = None
            for band_name, band_range in TIME_BANDS.items():
                if band_name in text and band_name not in ("midnight", "midday", "dawn"):
                    band_match = band_name
                    break

            if time_match:
                mins = _parse_time(time_match.group(1))
                if mins is not None:
                    dt = dt.replace(hour=mins // 60, minute=mins % 60)
                end = dt + datetime.timedelta(hours=1)
            elif band_match:
                band_range = TIME_BANDS[band_match]
                dt = dt.replace(hour=band_range[0], minute=0)
                end_hour = band_range[1] if band_range[1] > band_range[0] else 24
                end = (dt + datetime.timedelta(days=1)).replace(hour=0, minute=0) if end_hour == 24 else dt.replace(hour=end_hour, minute=0)
            else:
                end = dt + datetime.timedelta(days=1)

            result = (dt, end)
            break

    # --- relative offsets: "X days ago", "X hours ago", "last week", "last month" ---
    m = re.search(r"(\d+)\s+(second|seconds|minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)\s+ago", text)
    if m:
        amount = int(m.group(1))
        unit = m.group(2)
        unit_map = {
            "second": "seconds", "seconds": "seconds",
            "minute": "minutes", "minutes": "minutes",
            "hour": "hours", "hours": "hours",
            "day": "days", "days": "days",
            "week": "weeks", "weeks": "weeks",
            "month": "months", "months": "months",
            "year": "years", "years": "years",
        }
        kw = {unit_map[unit]: amount}
        start = now - datetime.timedelta(**kw)
        end = now
        result = (start, end)

    m = re.search(r"last\s+(week|month|year)", text)
    if m:
        unit = m.group(1)
        if unit == "week":
            start = today_start - datetime.timedelta(weeks=1)
            end = today_start
        elif unit == "month":
            start = (today_start.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
            end = today_start.replace(day=1)
        else:
            start = today_start.replace(year=now.year - 1, month=1, day=1)
            end = today_start.replace(year=now.year, month=1, day=1)
        result = (start, end)

    m = re.search(r"this\s+(week|month)", text)
    if m:
        unit = m.group(1)
        if unit == "week":
            start = today_start - datetime.timedelta(days=now.weekday())
            end = now
        else:
            start = today_start.replace(day=1)
            end = now
        result = (start, end)

    # --- simple "morning", "afternoon" etc (without a day reference) ---
    if result is None:
        for band_name, band_range in TIME_BANDS.items():
            if band_name in text and band_name not in ("midnight", "midday", "dawn"):
                start = today_start.replace(hour=band_range[0], minute=0)
                end_hour = band_range[1] if band_range[1] > band_range[0] else 24
                end = (today_start + datetime.timedelta(days=1)).replace(hour=0, minute=0) if end_hour == 24 else today_start.replace(hour=end_hour, minute=0)
                result = (start, end)
                break

    return result


def detect_temporal(text: str) -> bool:
    triggers = [
        r"\bago\b", r"\byesterday\b", r"\btoday\b", r"\btomorrow\b",
        r"\blasts?\b", r"\bnext\b", r"\bthis\s+(week|month|year|morning|afternoon|evening|night)\b",
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?\b",
        r"\b\d{1,2}(?:st|nd|rd|th)?\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b",
        r"\b(at\s+\d)",
        r"\b(morning|afternoon|evening|night)\b",
    ]
    text_lower = text.lower()
    return any(re.search(p, text_lower) for p in triggers)
