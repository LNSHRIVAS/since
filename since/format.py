from __future__ import annotations

import datetime
import re
import zoneinfo

from .models import Message, StaleInfo, TIME_OF_DAY_BANDS

PROMPTING_NUDGE = (
    "Every message has a UTC timestamp. The 'Now:' line below is the "
    "current time — use it for all time references. Never guess the time."
)

GAP_THRESHOLD = datetime.timedelta(minutes=30)


def _utc_to_local(dt: datetime.datetime, tz_name: str) -> datetime.datetime:
    if tz_name == "UTC":
        return dt
    if tz_name.startswith("UTC") and len(tz_name) > 3:
        sign = 1 if tz_name[3] == "+" else -1
        parts = tz_name[4:].split(":")
        h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
        offset = datetime.timedelta(hours=sign * h, minutes=sign * m)
        tz = datetime.timezone(offset)
        return dt.replace(tzinfo=datetime.timezone.utc).astimezone(tz).replace(tzinfo=None)
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
        return dt.replace(tzinfo=datetime.timezone.utc).astimezone(tz).replace(tzinfo=None)
    except zoneinfo.ZoneInfoNotFoundError:
        return dt


def _time_of_day_band(dt: datetime.datetime) -> str:
    hour = dt.hour
    for (start, end), label in TIME_OF_DAY_BANDS.items():
        if start <= hour < end:
            return label
    return "night"


def _format_timedelta_short(td: datetime.timedelta) -> str:
    total_seconds = int(td.total_seconds())
    if total_seconds < 0:
        return "in the future"
    if total_seconds < 60:
        return "just now"
    if total_seconds < 3600:
        m = total_seconds // 60
        return f"{m}m ago"
    if total_seconds < 86400:
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        return f"{h}h {m}m ago" if m else f"{h}h ago"
    if total_seconds < 604800:
        d = total_seconds // 86400
        h = (total_seconds % 86400) // 3600
        return f"{d}d {h}h ago" if h else f"{d}d ago"
    days = total_seconds // 86400
    if days < 30:
        w = days // 7
        d = days % 7
        return f"{w}w {d}d ago" if d else f"{w}w ago"
    if days < 365:
        mo = days // 30
        d = days % 30
        return f"{mo}mo {d}d ago" if d else f"{mo}mo ago"
    y = days // 365
    d = days % 365
    return f"{y}y {d}d ago" if d else f"{y}y ago"


def _format_timedelta_compact(td: datetime.timedelta) -> str:
    total_seconds = int(td.total_seconds())
    if total_seconds < 0:
        return "0s"
    if total_seconds < 60:
        return f"{total_seconds}s"
    if total_seconds < 3600:
        return f"{total_seconds // 60}m"
    if total_seconds < 86400:
        return f"{total_seconds // 3600}h {(total_seconds % 3600) // 60}m"
    days = total_seconds // 86400
    h = (total_seconds % 86400) // 3600
    return f"{days}d {h}h"


def _format_absolute_label(dt: datetime.datetime) -> str:
    return dt.strftime("%a %b %d, %I:%M%p").lstrip("0").replace("  ", " ")


_TS_PREFIX = re.compile(
    r'^\[[A-Z][a-z]{2} [A-Z][a-z]{2} \d{1,2}, \d{1,2}:\d{2} ?(?:AM|PM)\]\s*'
)


def format_absolute(msg: Message, tz_name: str = "UTC") -> str:
    ts = _utc_to_local(msg.created_at, tz_name)
    clean = _TS_PREFIX.sub("", msg.content)
    return f"[{_format_absolute_label(ts)}]  {clean}"


def _build_tail(
    history: list[Message],
    now: datetime.datetime,
    tz_name: str = "UTC",
    stale_info: list[StaleInfo] | None = None,
) -> str:
    lines = []

    local_now = _utc_to_local(now, tz_name) if tz_name != "UTC" else now
    now_str = local_now.strftime("%a %b %d, %I:%M %p").lstrip("0").replace("  ", " ")
    band = _time_of_day_band(local_now)
    lines.append(f"Now: {now_str} ({band})")

    if history:
        span = now - history[0].created_at
        last_gap = now - history[-1].created_at

        active = datetime.timedelta()
        sittings = 1
        for i in range(1, len(history)):
            gap = history[i].created_at - history[i - 1].created_at
            if gap > GAP_THRESHOLD:
                sittings += 1
            else:
                active += gap

        parts = [f"Session: {_format_timedelta_compact(span)}"]
        if active.total_seconds() > 0:
            parts.append(f"{_format_timedelta_compact(active)} active")
        if sittings > 1:
            parts.append(f"{sittings} sittings")
        parts.append(f"{len(history) + 1} messages")
        lines.append(" · ".join(parts))

        if last_gap > GAP_THRESHOLD:
            lines.append(f"Gap: {_format_timedelta_short(last_gap)} — welcome back!")
        elif last_gap.total_seconds() > 60:
            lines.append(f"Last message: {_format_timedelta_short(last_gap)}")
    else:
        lines.append(f"Session: just started · 1 message")

    if stale_info:
        for s in stale_info:
            kind = {"event": "invalidated", "ephemeral": "expired"}.get(s.ttl_class, s.ttl_class)
            src = f" ({s.source_id})" if s.source_id else ""
            lines.append(f"⚠ Stale: \"{s.content_preview}\"{src} — {kind}, {_format_timedelta_compact(s.age)} old")

    return "\n".join(lines)


def build_prompt(
    messages: list[Message],
    now: datetime.datetime,
    include_nudge: bool = True,
    extra_context: list[Message] | None = None,
    tz_name: str = "UTC",
    stale_info: list[StaleInfo] | None = None,
) -> list[dict]:
    result = []

    if include_nudge:
        result.append({"role": "system", "content": PROMPTING_NUDGE})

    if extra_context:
        result.append({"role": "system", "content": f"--- Retrieved from history ({len(extra_context)} messages) ---"})
        for msg in extra_context:
            result.append({"role": msg.role, "content": format_absolute(msg, tz_name)})
        result.append({"role": "system", "content": "--- End of retrieved history ---"})

    history_msgs = messages
    current_content = None

    if messages and messages[-1].role == "user":
        history_msgs = messages[:-1]
        current_content = messages[-1].content

    for msg in history_msgs:
        result.append({"role": msg.role, "content": format_absolute(msg, tz_name)})

    tail = _build_tail(history_msgs, now, tz_name, stale_info)
    result.append({"role": "system", "content": tail})

    if current_content:
        result.append({"role": "user", "content": current_content})

    return result
