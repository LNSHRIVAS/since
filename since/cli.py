from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

from .core import with_time
from .store import Store


def cmd_enrich(args: argparse.Namespace) -> None:
    store = Store(args.db)
    messages = store.load_session(args.session_id)
    if not messages:
        print(f"Session '{args.session_id}' not found", file=sys.stderr)
        sys.exit(1)

    prompt = with_time(messages, store=store)
    for entry in prompt:
        print(f"[{entry['role']}]\n{entry['content']}\n")


def cmd_search(args: argparse.Namespace) -> None:
    store = Store(args.db)
    messages = store.load_session(args.session_id)
    if not messages:
        print(f"Session '{args.session_id}' not found", file=sys.stderr)
        sys.exit(1)

    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    if args.range:
        parts = args.range.split()
        if len(parts) == 2 and parts[1] in ("ago",):
            try:
                value = int(parts[0])
            except ValueError:
                print(f"Invalid range: {args.range}", file=sys.stderr)
                sys.exit(1)
            start = now - datetime.timedelta(days=value)
        else:
            try:
                start = datetime.datetime.fromisoformat(args.range)
            except ValueError:
                print(f"Invalid range: {args.range}", file=sys.stderr)
                sys.exit(1)
        end = now
        results = store.load_range(args.session_id, start, end)
    else:
        results = messages[-20:]

    from .format import format_absolute
    for m in results:
        print(format_absolute(m))


def cmd_stats(args: argparse.Namespace) -> None:
    store = Store(args.db)
    info = store.session_info(args.session_id)
    if not info:
        print(f"Session '{args.session_id}' not found", file=sys.stderr)
        sys.exit(1)

    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    from .format import _format_timedelta_compact
    print(f"Session:      {args.session_id}")
    print(f"Messages:     {info['count']}")
    print(f"Started:      {info['first'].isoformat()}")
    print(f"Last message: {info['last'].isoformat()}")
    print(f"Duration:     {_format_timedelta_compact(info['last'] - info['first'])}")
    print(f"Age:          {_format_timedelta_compact(now - info['first'])}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="since", description="Temporal context for LLM conversations")
    parser.add_argument("--db", default="~/.since/store.db", type=str, help="SQLite database path")

    sub = parser.add_subparsers(dest="command", required=True)

    p_enrich = sub.add_parser("enrich", help="Enrich a session with temporal context")
    p_enrich.add_argument("session_id", type=str)
    p_enrich.set_defaults(func=cmd_enrich)

    p_search = sub.add_parser("search", help="Search messages by time range")
    p_search.add_argument("session_id", type=str)
    p_search.add_argument("--range", type=str, default="", help="Time range (e.g. '3 days ago' or ISO 8601)")
    p_search.set_defaults(func=cmd_search)

    p_stats = sub.add_parser("stats", help="Show session statistics")
    p_stats.add_argument("session_id", type=str)
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    args.db = Path(Path.home() / ".since" / "store.db") if args.db == "~/.since/store.db" else Path(args.db)
    args.db.parent.mkdir(parents=True, exist_ok=True)
    args.func(args)


if __name__ == "__main__":
    main()
