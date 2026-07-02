from __future__ import annotations

import datetime
import hashlib
import os
import re
from pathlib import Path

from .models import Message
from .store import Store


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()[:12]


def _parse_stored(content: str) -> tuple[float | None, str | None]:
    mtime_m = re.search(r"mtime=([\d.]+)", content)
    hash_m = re.search(r"hash=([a-f0-9]+)", content)
    mtime = float(mtime_m.group(1)) if mtime_m else None
    digest = hash_m.group(1) if hash_m else None
    return mtime, digest


def stamp_file_read(filepath: str, store: Store, session_id: str) -> str:
    path = Path(filepath).resolve()
    if not path.exists():
        raise FileNotFoundError(str(path))
    abs_path = str(path)
    mtime = os.path.getmtime(abs_path)
    digest = _file_hash(abs_path)
    source_id = f"read:{path}"
    store.invalidate(source_id, session_id)
    content = f"[FILE READ] {path} (mtime={mtime}, hash={digest})"
    msg = Message(session_id, 0, "user", content, _now(),
                  ttl_class="event", source_id=source_id)
    store.insert_next(msg)
    msg2 = Message(session_id, 0, "assistant",
                   f"I read {path.name} ({path}).",
                   _now(), ttl_class="event", source_id=source_id)
    store.insert_next(msg2)
    return source_id


def is_stale(filepath: str, store: Store, session_id: str) -> bool:
    path = Path(filepath).resolve()
    if not path.exists():
        return True
    abs_path = str(path)
    current_mtime = os.path.getmtime(abs_path)
    current_hash = _file_hash(abs_path)
    source_id = f"read:{path}"
    msgs = store.load_session(session_id)
    for m in reversed(msgs):
        if m.source_id == source_id and m.ttl_class == "event" and m.invalidated_at is None:
            stored_mtime, stored_hash = _parse_stored(m.content)
            if stored_hash is None and stored_mtime is None:
                continue
            if stored_hash is not None and current_hash != stored_hash:
                return True
            if stored_mtime is not None and current_mtime != stored_mtime:
                return True
            return False
    return False


def check_and_invalidate(filepath: str, store: Store, session_id: str) -> bool:
    """Returns True if the file was found stale and invalidated."""
    return check_and_invalidate_detail(filepath, store, session_id)["stale"]


def check_and_invalidate_detail(filepath: str, store: Store, session_id: str) -> dict:
    path = Path(filepath).resolve()
    abs_path = str(path)
    source_id = f"read:{abs_path}"
    try:
        current_mtime = os.path.getmtime(abs_path)
        current_hash = _file_hash(abs_path)
    except FileNotFoundError:
        return {"stale": False, "filepath": abs_path, "reasons": ["file not found"]}
    msgs = store.load_session(session_id)
    for m in reversed(msgs):
        if m.source_id == source_id and m.ttl_class == "event" and m.invalidated_at is None:
            stored_mtime, stored_hash = _parse_stored(m.content)
            if stored_hash is None and stored_mtime is None:
                continue
            reasons = []
            if stored_hash is not None and current_hash != stored_hash:
                reasons.append("content changed")
            if stored_mtime is not None and current_mtime != stored_mtime:
                reasons.append("mtime changed")
            if reasons:
                store.invalidate(source_id, session_id)
                return {"stale": True, "filepath": abs_path, "reasons": reasons,
                        "read_at": m.created_at.isoformat()}
            return {"stale": False, "filepath": abs_path, "reasons": []}
    return {"stale": False, "filepath": abs_path, "reasons": []}
