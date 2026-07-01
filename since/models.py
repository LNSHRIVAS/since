from __future__ import annotations

import datetime
from dataclasses import dataclass


@dataclass
class Message:
    session_id: str
    turn_id: int
    role: str
    content: str
    created_at: datetime.datetime
    timezone: str = "UTC"
    ttl_class: str = "slow"
    source_id: str | None = None
    invalidated_at: datetime.datetime | None = None


@dataclass
class StaleInfo:
    turn_id: int
    ttl_class: str
    source_id: str | None
    content_preview: str
    age: datetime.timedelta


TIME_OF_DAY_BANDS = {
    (0, 5): "night",
    (5, 12): "morning",
    (12, 17): "afternoon",
    (17, 21): "evening",
    (21, 24): "night",
}

EPHEMERAL_TTL = datetime.timedelta(minutes=5)
