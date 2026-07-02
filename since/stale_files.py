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


def _file_hash(path: str) -> tuple[str, int]:
    h = hashlib.sha256()
    lines = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
            lines += chunk.count(b"\n")
    return h.hexdigest()[:12], lines


def _parse_stored(content: str) -> tuple[float | None, str | None, int | None]:
    mtime_m = re.search(r"mtime=([\d.]+)", content)
    hash_m = re.search(r"hash=([a-f0-9]+)", content)
    lines_m = re.search(r"lines=(\d+)", content)
    mtime = float(mtime_m.group(1)) if mtime_m else None
    digest = hash_m.group(1) if hash_m else None
    lines = int(lines_m.group(1)) if lines_m else None
    return mtime, digest, lines


def stamp_file_read(filepath: str, store: Store, session_id: str) -> str:
    path = Path(filepath).resolve()
    if not path.exists():
        raise FileNotFoundError(str(path))
    abs_path = str(path)
    mtime = os.path.getmtime(abs_path)
    digest, lines = _file_hash(abs_path)
    source_id = f"read:{path}"
    store.invalidate(source_id, session_id)
    content = f"[FILE READ] {path} (mtime={mtime}, hash={digest}, lines={lines})"
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
    current_hash, _ = _file_hash(abs_path)
    source_id = f"read:{path}"
    msgs = store.load_session(session_id)
    for m in reversed(msgs):
        if m.source_id == source_id and m.ttl_class == "event" and m.invalidated_at is None:
            stored_mtime, stored_hash, _ = _parse_stored(m.content)
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


def drifted_files(store: Store, session_id: str) -> list[dict]:
    """Return all tracked files that have drifted since last stamped."""
    msgs = store.load_session(session_id)
    seen = {}
    for m in msgs:
        if m.source_id and m.ttl_class == "event" and m.invalidated_at is None:
            if m.source_id not in seen:
                stored_mtime, stored_hash, stored_lines = _parse_stored(m.content)
                if stored_hash is not None or stored_mtime is not None:
                    seen[m.source_id] = (stored_mtime, stored_hash, stored_lines, m.created_at)

    drifted = []
    for source_id, (stored_mtime, stored_hash, stored_lines, created_at) in seen.items():
        filepath = source_id[len("read:"):]
        try:
            current_mtime = os.path.getmtime(filepath)
        except FileNotFoundError:
            continue

        if stored_mtime is not None and current_mtime == stored_mtime:
            continue

        current_hash, current_lines = _file_hash(filepath)
        reasons = []
        if stored_hash is not None and current_hash != stored_hash:
            reasons.append("content changed")
        if stored_mtime is not None and current_mtime != stored_mtime:
            reasons.append("mtime changed")

        if reasons:
            d = {"filepath": filepath, "reasons": reasons,
                 "read_at": created_at.isoformat(), "has_record": True}
            if stored_lines is not None and current_lines is not None:
                delta = current_lines - stored_lines
                if delta != 0:
                    d["line_delta"] = f"{'+' if delta > 0 else ''}{delta}"
            drifted.append(d)

    return drifted


def check_and_invalidate_detail(filepath: str, store: Store, session_id: str) -> dict:
    path = Path(filepath).resolve()
    abs_path = str(path)
    source_id = f"read:{abs_path}"
    try:
        current_mtime = os.path.getmtime(abs_path)
        current_hash, current_lines = _file_hash(abs_path)
    except FileNotFoundError:
        return {"stale": False, "filepath": abs_path, "reasons": ["file not found"], "has_record": False}
    msgs = store.load_session(session_id)
    for m in reversed(msgs):
        if m.source_id == source_id and m.ttl_class == "event" and m.invalidated_at is None:
            stored_mtime, stored_hash, stored_lines = _parse_stored(m.content)
            if stored_hash is None and stored_mtime is None:
                continue
            reasons = []
            if stored_hash is not None and current_hash != stored_hash:
                reasons.append("content changed")
            if stored_mtime is not None and current_mtime != stored_mtime:
                reasons.append("mtime changed")
            if reasons:
                store.invalidate(source_id, session_id)
                result = {"stale": True, "filepath": abs_path, "reasons": reasons,
                          "read_at": m.created_at.isoformat(), "has_record": True}
                if stored_lines is not None and current_lines is not None:
                    delta = current_lines - stored_lines
                    if delta != 0:
                        result["line_delta"] = f"{'+' if delta > 0 else ''}{delta}"
                return result
            return {"stale": False, "filepath": abs_path, "reasons": [], "has_record": True}
    return {"stale": False, "filepath": abs_path, "reasons": [], "has_record": False}
