from __future__ import annotations

import datetime

from .format import build_prompt, format_absolute
from .models import Message
from .store import Store
from .timeparse import detect_temporal, parse_temporal


def with_time(
    messages: list[Message],
    now: datetime.datetime | None = None,
    store: Store | None = None,
    include_nudge: bool = True,
    user_input: str | None = None,
    tz_name: str = "UTC",
) -> list[dict]:
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    extra_context = None
    session_id = messages[0].session_id if messages else None

    if store and session_id and user_input and detect_temporal(user_input):
        parsed = parse_temporal(user_input, now)
        if parsed:
            start, end = parsed
            retrieved = store.load_range(session_id, start, end)
            existing_ids = {(m.session_id, m.turn_id) for m in messages}
            extra_context = [m for m in retrieved if (m.session_id, m.turn_id) not in existing_ids]

    stale_info = None
    if store and session_id:
        stale_info = store.stale_messages(session_id, now)

    prompt = build_prompt(
        messages=messages,
        now=now,
        include_nudge=include_nudge,
        extra_context=extra_context,
        tz_name=tz_name,
        stale_info=stale_info,
    )

    return prompt


def enrich_message(msg: Message, tz_name: str = "UTC") -> str:
    return format_absolute(msg, tz_name)
