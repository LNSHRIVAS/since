# since: your agent already read it. since tells it when it changed.

[![CI](https://github.com/LNSHRIVAS/since/actions/workflows/ci.yml/badge.svg)](https://github.com/LNSHRIVAS/since/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/tests-45%20passing-brightgreen)]()

**Coding agents act on files they read minutes ago. Those files change - a formatter, a git pull, another agent. The agent never knows. `since` tells it, on every tool call, what changed.**

```
pip install pysince
```

Zero dependencies. Works in Claude Code, Cursor, Copilot, Antigravity — any MCP client.

---

## What it does

Every MCP tool call surfaces *all* files that changed since the agent last read them. The agent doesn't need to remember to check — `since` volunteers it.

```
Files changed since last read:
C:\project\config.json (content changed, mtime changed) read 4m ago (+2 lines)
C:\project\alerts.py (content changed, mtime changed) read 3m ago
```

---

## When you need this

**Strongest when files change outside the agent's view** — another process, a teammate editing the same repo, a formatter, a pre-commit hook, or context that drifted across a long session.

**Less needed for quick single-file edits** where the agent already re-reads the file. Skip it for trivial scripts; add it when agents share files or sessions run long.

---

## This is a real, filed problem

Agents acting on stale file contents isn't theoretical — it's filed across production tools:

- [Aider #3032](https://github.com/Aider-AI/aider/issues/3032) — agent edits stale file content
- [Aider #51214](https://github.com/Aider-AI/aider/issues/51214) — compaction loses context between turns
- P1 context-rot issues in agent frameworks where no mechanism checks file freshness between read and edit

`since` closes the gap with a single install.

---

## Quick start — MCP server

Add to your client's MCP config:

```json
{
  "mcpServers": {
    "pysince": {
      "command": "pysince-mcp"
    }
  }
}
```

Then, in your agent's system instructions, add this line:

> On every file you read for the first time, call `stamp_file_read`. Before editing a file you previously stamped, call `check_staleness` — if stale, re-read it. When the drift report lists changed files, re-read them before acting on their content.

**Tools exposed:**

- **`stamp_file_read`** — call after reading any file. Records mtime and content hash.
- **`check_staleness`** — returns whether the file is current. Also lists all other tracked files that have changed, unprompted.
- **`session_duration`** — how long the MCP server has been tracking.
- **`invalidate_source`** — manually mark events stale.

---

## For chat apps

Wrap your chat function with `@since_time`. Every message gets a timestamp. The model sees a timeline, not a flat list.

```python
from since import Store, since_time
from openai import OpenAI

store = Store("~/.since/chat.db")
client = OpenAI()

@since_time(store=store, timezone="Asia/Kolkata")
def chat(messages):
    return client.chat.completions.create(model="gpt-4o", messages=messages)

resp = chat(messages=[{"role": "user", "content": "hello"}])
print(resp.choices[0].message.content)
```

**Before:** ask a vanilla model about past conversations — it can't recall.

**After:** the prompt tail gives the model facts:

```
Now: Wed Jul 01, 02:36 AM (night)
Session: 9h 2m · 4m active · 3 sittings · 8 messages
Gap: 6h between messages
```

The model sees *when* things happened, how long ago, and what context is stale.

## Works with any provider

OpenAI, Anthropic, Gemini — detected automatically. Pass `extract_reply=` for anything else:

```python
@since_time(store=store, extract_reply=lambda r: r.content[0].text)
def chat(messages):
    return anthropic.messages.create(
        model="claude-3-5-sonnet-latest",
        messages=messages
    )
```

## How it works

`since` stamps every file read with its mtime and SHA-256 hash. On any subsequent MCP call, it compares stored fingerprints against current state — mtime first (fast), full hash only if mtime changed. Results are surfaced as a drift report, unprompted, on every response.

**TTL system** (for chat context):

| Class | Decay | Use case |
|---|---|---|
| `permanent` | Never | Facts, identity |
| `slow` | Session age | Normal conversation |
| `event` | On `invalidate()` | File reads, tool outputs |
| `ephemeral` | 5 minutes | Short-lived messages |

## Requirements

- Python 3.10+
- Zero dependencies

## Install

```bash
pip install pysince
```

Import as `since`.

The PyPI name is `pysince` — the `since` name was taken. Import and repo are `since`.
