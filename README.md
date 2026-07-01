# since: temporal context for LLMs

[![CI](https://github.com/LNSHRIVAS/since/actions/workflows/ci.yml/badge.svg)](https://github.com/LNSHRIVAS/since/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/tests-45%20passing-brightgreen)]()

LLMs have no sense of time. `since` fixes that.

```
pip install pysince
from since import Store, since_time
```

Zero dependencies. No AI calls. Works with any provider.

---

## Before and after

**Before** — ask a vanilla LLM about past conversation:

```
> What did we talk about last time?
I don't have information about previous conversations.
```

**After** — with `since`:

```
> What did we talk about last time?
Welcome back! It's been 2 days since we last spoke.
We were debugging your auth flow — specifically the JWT expiry issue.
```

The model sees a timeline, not a flat list.

## Quick start

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

The prompt sent to the model includes:

```
Now: Wed Jul 01, 02:36 AM (night)
Session: 4m · 3 messages
Gap: 2m between messages
Stale: "config.py" (read:config.py) invalidated, 14m old
```

The model sees *when* things happened, *how long ago* the last message was, and *what context is stale*.

## Stale-file detection (for coding agents)

Files change between agent turns. `since` catches that by stamping file reads with mtime and content hash, then surfacing staleness when the file changes.

```python
from since.stale_files import stamp_file_read, check_and_invalidate

# After reading a file
stamp_file_read("config.py", store, "session_1")

# Later, file changed externally
if check_and_invalidate("config.py", store, "session_1"):
    # Stale warning appears in the prompt tail automatically
    stamp_file_read("config.py", store, "session_1")
```

## MCP server (for Claude Code, Cursor, etc.)

```
pysince-mcp
```

Exposes 4 tools for agent integration:

- **`stamp_file_read`**: stamp a file after reading it
- **`check_staleness`**: check if a stamped file has changed
- **`session_duration`**: how long the MCP server has been tracking file stamps
- **`invalidate_source`**: manually mark events stale

Note: `session_duration` reflects the age of file-read stamps, not conversation length (the MCP protocol has no access to chat history).

## TTL system

| Class | Decay | Use case |
|---|---|---|
| `permanent` | Never | Facts, identity |
| `slow` | Session age | Normal conversation |
| `event` | On `invalidate()` | File reads, tool outputs |
| `ephemeral` | 5 minutes | "ok", "thanks" |

## Works with any provider

OpenAI, Anthropic, Gemini: `@since_time` detects the response shape automatically. Pass `extract_reply=` for anything else.

```python
@since_time(store=store, extract_reply=lambda r: r.content[0].text)
def chat(messages):
    return anthropic.messages.create(model="claude-3-5-sonnet-20241022", messages=messages)
```

## Requirements

- Python 3.10+
- Zero dependencies

## Install

```bash
pip install pysince
```

The PyPI name is `pysince` (the `since` name was taken on PyPI). Import and repo are `since`.

## Tests

```
pytest
```

45 tests, zero external services required.
