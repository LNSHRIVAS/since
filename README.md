# since

**Your agent already read the file. `since` tells it when the file changed.**

[![CI](https://github.com/LNSHRIVAS/since/actions/workflows/ci.yml/badge.svg)](https://github.com/LNSHRIVAS/since/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/tests-45%20passing-brightgreen)]()
[![PyPI](https://img.shields.io/pypi/v/pysince)](https://pypi.org/project/pysince/)

Coding agents act on files they read minutes ago. Those files change: a formatter runs, a teammate pushes, another agent edits, a git pull lands. The agent never sees it, and acts on the stale version with full confidence. `since` tells it, on every tool call, exactly what changed.

```bash
pip install pysince
```

Zero dependencies. Works in Claude Code, Cursor, Copilot, and Antigravity. Any MCP client.

[▶ Watch demo](docs/demo.mp4)

## The problem is real and filed

This is not hypothetical. It is an open, reported failure in production agent tools:

- [claude-code #3032](https://github.com/anthropics/claude-code/issues/3032): subagents read stale versions of files. The main agent sees the update, the subagent keeps acting on the old content.
- [claude-code #51214](https://github.com/anthropics/claude-code/issues/51214): the tool's file cache diverges from disk. Read, Edit, and Grep all return the cached copy, so the agent cannot detect the divergence from inside its own loop. The reporter's conclusion is that only an out-of-band check against disk catches it.

That out-of-band, disk-truth check is exactly what `since` does.

## What it does

Every MCP tool response surfaces all files that changed since the agent last read them. The agent does not have to remember to check. `since` volunteers it:

```text
Files changed since last read:
  config.json (content changed, mtime changed) - read 4m ago
  alerts.py   (content changed, mtime changed) - read 3m ago
```
The agent re-reads those files before acting, instead of writing from a stale copy.

## When you need this

Strongest when files change outside the agent's view: another process, a teammate on the same repo, a formatter, a pre-commit hook, a parallel agent, or context that drifted over a long session.

Less useful for quick single-file edits an agent already re-reads on its own. Skip it for throwaway scripts. Reach for it when agents share files, sessions run long, or more than one actor touches the tree.

## Setup

`since` runs as a local MCP server. Add it to your client's MCP config.

**VS Code:**

```json
{
  "servers": {
    "pysince": {
      "type": "stdio",
      "command": "pysince-mcp",
      "args": [],
      "cwd": "${workspaceFolder}"
    }
  }
}
```

**Antigravity:**

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

Then add this line to your agent's system instructions so it knows when to call the tools:

> On the first read of any file, call `stamp_file_read`. Before editing a file, call `check_staleness`. When the response lists changed files, re-read them before acting on their contents.

## Tools

| Tool | When to call it | What it does |
|---|---|---|
| `stamp_file_read` | After reading any file | Records mtime and content hash |
| `check_staleness` | Before editing a file | Reports if it changed, and lists every other tracked file that changed too |
| `session_duration` | Anytime | How long the session has been tracked |
| `invalidate_source` | Manually | Marks a source stale on demand |

`check_staleness` is the core. It never answers only about the one file you asked about. It reports the full set of tracked files that have drifted, so the agent cannot stay blind to a change it did not think to check.

## How it works

`since` stamps every file read with its mtime and a SHA-256 hash. On any later call it compares stored fingerprints against the current file: mtime first because it is fast, full hash only if mtime moved. No daemon, no polling, no background process. Just a comparison against disk at the next turn, which is why it catches changes the agent's own cached view cannot.

---

## Also: temporal context for chat apps

The same primitive, aimed at conversations instead of files. Wrap your chat function and the model sees a timeline: when each message happened, how long the gaps were, and what context has gone stale.

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

The model receives a compact time block before each turn:
```yaml
Now:      Wed Jul 01, 02:36 AM (night)
Session:  9h 2m total, 4m active across 3 sittings, 8 messages
Gap:      6h since the last message
```
So instead of "I don't have information about previous conversations," it can say "welcome back, it has been about 6 hours since we last spoke."

The decorator reads the OpenAI response shape by default. For other providers, pass an `extract_reply` function that returns the reply text from your provider's response object.

## Requirements

- Python 3.10+
- Zero dependencies

## Install

```bash
pip install pysince
```

The PyPI name is `pysince` because `since` was already taken. You import it, and the repo is named, `since`.
