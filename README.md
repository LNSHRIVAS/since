# since: temporal context for LLMs

LLMs have no sense of time. `since` fixes that.

```
pip install pysince
from since import Store, since_time
```

Zero dependencies. No AI calls. Works with any provider.

---

## The problem

Ask any LLM "what time is it?" and it guesses. Ask "what did we discuss 3 hours ago?" and it cannot answer. A message from five minutes ago looks identical to one from yesterday. Context is flat without a clock.

## What `since` does

`@since_time` wraps your chat function with a real clock. It timestamps every message, tracks session duration, detects gaps, and tells the model the current time so it never has to guess.

```python
from since import Store, since_time
from openai import OpenAI

store = Store("~/.since/chat.db")
client = OpenAI()

@since_time(store=store, timezone="Asia/Kolkata")
def chat(messages):
    return client.chat.completions.create(model="gpt-4o", messages=messages)

resp = chat(messages=[{"role": "user", "content": "hello"}])
```

The prompt sent to the model includes:

```
Now: Wed Jul 01, 02:36 AM (night)
Session: 4m . 3 messages
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

No daemon, no polling, no watcher. Just mtime and content hash at the next turn.

## MCP server (for Claude Code, Cursor, etc.)

```
pysince-mcp
```

Exposes 4 tools for agent integration:

- **`stamp_file_read`**: stamp a file after reading it
- **`check_staleness`**: check if a stamped file has changed
- **`session_duration`**: how long has this session been running
- **`invalidate_source`**: manually mark events stale

## TTL system

| Class | Decay | Use case |
|---|---|---|
| `permanent` | Never | Facts, identity |
| `slow` | Session age | Normal conversation |
| `event` | On `invalidate()` | File reads, tool outputs |
| `ephemeral` | 5 minutes | "ok", "thanks" |

Stale messages surface as `Stale:` in the prompt tail.

## Works with any provider

OpenAI, Anthropic, Gemini: `@since_time` detects the response shape automatically. Pass `extract_reply=` for anything else.

```python
@since_time(store=store, extract_reply=lambda r: r.content[0].text)
def chat(messages):
    return anthropic.messages.create(model="claude-3", messages=messages)
```

## Requirements

- Python 3.10+
- Zero dependencies

## Install

```bash
pip install pysince
```

Import as `since`.
