"""
MCP server for since — exposes staleness checks as tools
any MCP client (Claude Code, Cursor, etc.) can call.

Usage:
    python -m since.mcp
"""

from __future__ import annotations

import datetime
import json
import sys
import uuid
from pathlib import Path

from . import Store
from .stale_files import stamp_file_read, check_and_invalidate_detail, drifted_files

DB_PATH = Path.home() / ".since" / "mcp.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
_store = Store(DB_PATH)
_session = f"mcp_{uuid.uuid4().hex[:12]}"
_now = lambda: datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


TOOLS = [
    {
        "name": "stamp_file_read",
        "description": "Call this immediately after reading a file for the first time. Must be called BEFORE check_staleness can detect changes to that file. Records current mtime and content hash.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Path to the file"}
            },
            "required": ["filepath"],
        },
    },
    {
        "name": "check_staleness",
        "description": "Check whether a previously-stamped file has changed since you last read it. If no prior stamp exists it will tell you to stamp first. Call this before editing any file you stamped earlier — if stale, re-read it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Path to the file"}
            },
            "required": ["filepath"],
        },
    },
    {
        "name": "session_duration",
        "description": "How long has this session been running and how many messages have been exchanged. Useful for understanding context age.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "invalidate_source",
        "description": "Manually mark all events from a source as stale. Used when you know a resource has changed and want to ensure stale warnings fire.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_id": {"type": "string", "description": "Source ID to invalidate"}
            },
            "required": ["source_id"],
        },
    },
]


def _read_request() -> dict | None:
    line = sys.stdin.readline()
    if not line:
        return None
    return json.loads(line)


def _send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _now_iso() -> str:
    return _now().isoformat()


def handle_initialize(req: dict) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": req.get("id"),
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "pysince-mcp", "version": "0.2.9"},
        },
    }


def handle_list_tools(req: dict) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": req.get("id"),
        "result": {"tools": TOOLS},
    }


def handle_call_tool(req: dict) -> dict:
    params = req.get("params", {})
    name = params.get("name", "")
    args = params.get("arguments", {})

    try:
        if name == "stamp_file_read":
            fp = args["filepath"]
            src = stamp_file_read(fp, _store, _session)
            return _text_result(req, f"Stamped read: {src}")

        elif name == "check_staleness":
            fp = args["filepath"]
            detail = check_and_invalidate_detail(fp, _store, _session)
            stale = detail["stale"]
            reasons = detail.get("reasons", [])
            has_record = detail.get("has_record", False)
            read_at = detail.get("read_at", "")

            if not has_record:
                return _text_result(req, "No prior stamp — call stamp_file_read first")
            if not stale:
                return _text_result(req, "Stale=False (unchanged since last stamp)")

            parts = [f"Stale=True ({', '.join(reasons)})"]
            if read_at:
                try:
                    dt = datetime.datetime.fromisoformat(read_at)
                    age = _now() - dt
                    m = int(age.total_seconds() // 60)
                    ago = f"{m}m ago" if m < 60 else f"{m // 60}h {m % 60}m ago"
                    parts.append(f"read {ago}")
                except (ValueError, TypeError):
                    pass
            line_delta = detail.get("line_delta")
            if line_delta:
                parts.append(f"({line_delta} lines)")
            return _text_result(req, " ".join(parts))

        elif name == "session_duration":
            gap = "just started"
            count = 0
            info = _store.session_info(_session)
            if info:
                count = info["count"]
                td = _now() - info["first"]
                m = int(td.total_seconds() // 60)
                gap = f"{m} minutes" if m < 60 else f"{m // 60}h {m % 60}m"
            return _text_result(req, f"Session duration: {gap}, messages: {count}")

        elif name == "invalidate_source":
            src = args["source_id"]
            n = _store.invalidate(src)
            return _text_result(req, f"Invalidated {n} events for source: {src}")

        else:
            return _error_result(req, f"Unknown tool: {name}")

    except Exception as e:
        return _error_result(req, str(e))


def _text_result(req: dict, text: str) -> dict:
    drift = _drift_report()
    full = f"{text}\n\n{drift}" if drift else text
    return {
        "jsonrpc": "2.0",
        "id": req.get("id"),
        "result": {"content": [{"type": "text", "text": full}]},
    }


def _drift_report() -> str:
    drifted = drifted_files(_store, _session)
    if not drifted:
        return ""
    lines = []
    for d in drifted:
        parts = [f"• {d['filepath']} ({', '.join(d['reasons'])})"]
        try:
            dt = datetime.datetime.fromisoformat(d["read_at"])
            age = _now() - dt
            m = int(age.total_seconds() // 60)
            ago = f"{m}m ago" if m < 60 else f"{m // 60}h {m % 60}m ago"
            parts.append(f"read {ago}")
        except (ValueError, TypeError):
            pass
        ld = d.get("line_delta")
        if ld:
            parts.append(f"({ld} lines)")
        lines.append(" ".join(parts))
    return "Files changed since last read:\n" + "\n".join(lines)


def _error_result(req: dict, msg: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": req.get("id"),
        "error": {"code": -32000, "message": msg},
    }


HANDLERS = {
    "initialize": handle_initialize,
    "tools/list": handle_list_tools,
    "tools/call": handle_call_tool,
    "notifications/initialized": lambda _: None,
}


def main() -> None:
    while True:
        req = _read_request()
        if req is None:
            break
        method = req.get("method", "")
        handler = HANDLERS.get(method)
        if handler:
            result = handler(req)
            if result is not None:
                _send(result)
        elif "id" in req:
            _send(_error_result(req, f"Unknown method: {method}"))


if __name__ == "__main__":
    main()
