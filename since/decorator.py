from __future__ import annotations

import datetime
import functools
import re
import warnings
from typing import Any, Callable

_TS_PREFIX = re.compile(
    r'^\[[A-Z][a-z]{2} [A-Z][a-z]{2} \d{1,2}, \d{1,2}:\d{2} ?(?:AM|PM)\]\s*'
)

from .core import with_time
from .models import Message
from .store import Store


def _try_extract(result: Any) -> str | None:
    if isinstance(result, dict):
        try:
            return result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            pass
        try:
            return result["content"][0]["text"]
        except (KeyError, IndexError, TypeError):
            pass
        try:
            return result["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            pass
        return None

    if hasattr(result, "choices") and result.choices:
        choice = result.choices[0]
        if hasattr(choice, "message") and hasattr(choice.message, "content"):
            return choice.message.content
        if isinstance(choice, dict):
            try:
                return choice["message"]["content"]
            except (KeyError, TypeError):
                pass

    if hasattr(result, "content"):
        content = result.content
        if isinstance(content, list) and content:
            first = content[0]
            if hasattr(first, "text"):
                return first.text
            if isinstance(first, dict):
                return first.get("text")
        if isinstance(content, str):
            return content

    if hasattr(result, "candidates") and result.candidates:
        candidate = result.candidates[0]
        if hasattr(candidate, "content") and hasattr(candidate.content, "parts"):
            parts = candidate.content.parts
            if parts and hasattr(parts[0], "text"):
                return parts[0].text

    return None


def since_time(
    store: Store,
    session_id: str | None = None,
    timezone: str = "UTC",
    extract_reply: Callable[[Any], str | None] | None = None,
) -> Callable:
    def decorator(func: Callable) -> Callable:
        sid = session_id or func.__name__

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

            ttl_class = kwargs.pop("__ttl_class__", "slow")
            source_id = kwargs.pop("__source_id__", None)

            messages = kwargs.get("messages")
            if messages is None and args:
                messages = args[0]

            if not messages or not isinstance(messages, list):
                return func(*args, **kwargs)

            last_user = None
            for m in reversed(messages):
                if m.get("role") == "user":
                    last_user = m
                    break

            user_text = last_user.get("content", "") if last_user else ""

            if last_user:
                msg = Message(sid, 0, "user", user_text, now,
                              timezone=timezone, ttl_class=ttl_class, source_id=source_id)
                store.insert_next(msg)

            history = store.load_session(sid)
            enriched = with_time(history, now=now, store=store, user_input=user_text, tz_name=timezone)

            new_kwargs = dict(kwargs)
            new_kwargs["messages"] = enriched
            result = func(*args, **new_kwargs)

            reply = extract_reply(result) if extract_reply is not None else None
            if reply is None:
                reply = _try_extract(result)

            if reply:
                clean = reply
                while _TS_PREFIX.match(clean):
                    clean = _TS_PREFIX.sub("", clean)
                msg = Message(sid, 0, "assistant", clean, now,
                              timezone=timezone, ttl_class=ttl_class, source_id=source_id)
                store.insert_next(msg)
            else:
                warnings.warn(
                    "since: couldn't extract reply from response; "
                    "the assistant message was not stored. "
                    "Pass extract_reply= to @since_time with a callable "
                    "that returns the text from your provider's response shape."
                )

            return result

        return wrapper

    return decorator
