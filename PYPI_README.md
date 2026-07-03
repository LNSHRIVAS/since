# pysince

**MCP server for coding agents: detects stale file reads before your agent acts on outdated content. Zero dependencies.**

```bash
pip install pysince
```

## What it does

`pysince` is a local MCP server that stamps every file your agent reads with its mtime and SHA-256 hash. On any subsequent tool call, it compares stored fingerprints against the current file and surfaces all tracked files that have changed — unprompted. The agent does not need to remember to check anything.

```text
Files changed since last read:
  config.json (content changed, mtime changed) read 4m ago (+2 lines)
  alerts.py (content changed, mtime changed) read 3m ago
```

## How it works

Every file the agent reads gets stamped with its current mtime and content hash. On any later MCP call, `pysince` checks all tracked files: mtime first (fast `os.stat`), full hash only if mtime moved. No daemon, no polling, no background process. Just a comparison against disk at the next turn.

## Setup

Add to your MCP client config:

**VS Code** (`.vscode/mcp.json`):

```json
{
  "servers": {
    "pysince": {
      "type": "stdio",
      "command": "pysince-mcp"
    }
  }
}
```

**Claude Code / Cursor / Copilot** (`.cursor/mcp.json` or client settings):

```json
{
  "mcpServers": {
    "pysince": {
      "command": "pysince-mcp"
    }
  }
}
```

**Antigravity** (`mcp_config.json`):

```json
{
  "mcpServers": {
    "pysince": {
      "command": "python",
      "args": ["-m", "since.mcp"]
    }
  }
}
```

Then add this line to your agent's system instructions:

> On the first read of any file, call `stamp_file_read`. Before editing a file, call `check_staleness`. When the response lists changed files, re-read them before acting on their contents.

## Tools

| Tool | When to call it | Returns |
|---|---|---|
| `stamp_file_read` | After reading any file | Source ID confirmation |
| `check_staleness` | Before editing a stamped file | Stale status, change reasons (content vs mtime), line delta, read timestamp. Also lists all other tracked files that changed. |
| `session_duration` | Anytime | Session age and message count |
| `invalidate_source` | Manual override | Number of invalidated events |

`check_staleness` never answers only about the one file asked. It reports the full set of tracked files that have drifted, so the agent cannot stay blind to a change it did not think to check.

## When to use

Strongest when files change outside the agent's view: another process, a teammate on the same repo, a formatter, a pre-commit hook, a parallel agent, or context that drifted over a long session.

Less useful for quick single-file edits an agent already re-reads on its own. Skip it for throwaway scripts. Reach for it when agents share files, sessions run long, or more than one actor touches the tree.

## Chat apps

`pysince` also provides a `@since_time` decorator for wrapping LLM chat functions with temporal context: timestamps, session duration tracking, gap detection, and stale context surfacing.

```python
from since import Store, since_time
from openai import OpenAI

store = Store("~/.since/chat.db")
client = OpenAI()

@since_time(store=store, timezone="Asia/Kolkata")
def chat(messages):
    return client.chat.completions.create(model="gpt-4o-mini", messages=messages)

resp = chat(messages=[{"role": "user", "content": "hello"}])
print(resp.choices[0].message.content)
```

The model receives a time block before each turn:

```yaml
Now:      Wed Jul 01, 02:36 AM (night)
Session:  9h 2m total, 4m active across 3 sittings, 8 messages
Gap:      6h since the last message
```

Works with OpenAI, Anthropic, and Gemini response shapes automatically. Pass `extract_reply=` for other providers.

## CLI

```bash
pysince enrich <session_id>   # Enrich a session with temporal context
pysince search <session_id>   # Search messages by time range
pysince stats <session_id>    # Show session statistics
```

## Requirements

- Python 3.10+
- Zero dependencies

The PyPI name is `pysince` because `since` was already taken. The import name and repo name are `since`.

## Links

- [GitHub](https://github.com/LNSHRIVAS/since)
- [PyPI](https://pypi.org/project/pysince/)
