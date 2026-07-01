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
from .stale_files import stamp_file_read, check_and_invalidate

DB_PATH = Path.home() / ".since" / "mcp.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
_store = Store(DB_PATH)
_session = f"mcp_{uuid.uuid4().hex[:12]}"
_now = lambda: datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


TOOLS = [
    {
        "name": "stamp_file_read",
        "description": "Call this immediately after reading any file you intend to edit later, so you can detect if it changes underneath you. Records the file path and current mtime.",
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
        "description": "Check whether a previously-read file has changed since you last read it. If Stale=True, the file was modified — re-read it before acting on cached content.",
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
            "serverInfo": {"name": "pysince-mcp", "version": "0.1.0"},
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
            stale = check_and_invalidate(fp, _store, _session)
            now = _now()
            info = _store.session_info(_session)
            msgs = _store.load_session(_session)
            n_reads = sum(1 for m in msgs if m.source_id and fp in m.source_id)
            msg = f"Stale={stale}, prior_reads={n_reads}"
            if stale:
                msg += " — file changed since last read, re-read recommended"
            else:
                msg += " — file unchanged since last read"
            return _text_result(req, msg)

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
    return {
        "jsonrpc": "2.0",
        "id": req.get("id"),
        "result": {"content": [{"type": "text", "text": text}]},
    }


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
}


def main() -> None:
    while True:
        req = _read_request()
        if req is None:
            break
        method = req.get("method", "")
        handler = HANDLERS.get(method)
        if handler:
            _send(handler(req))
        else:
            _send(_error_result(req, f"Unknown method: {method}"))


if __name__ == "__main__":
    main()
