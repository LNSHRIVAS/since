# since: temporal context for LLMs

[![CI](https://github.com/LNSHRIVAS/since/actions/workflows/ci.yml/badge.svg)](https://github.com/LNSHRIVAS/since/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/tests-45%20passing-brightgreen)]()

**`since` gives anything in an LLM's context a sense of how old it is — conversation turns, file reads, tool outputs. One library, zero dependencies.**

```
pip install pysince
from since import Store, since_time
```

---

## For chat apps

Wrap your chat function with `@since_time`. Every message gets a timestamp. The model sees a timeline instead of a flat list.

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

**Before:** ask a vanilla model about past conversations. It has no memory.

```
> What did we talk about last time?
I don't have information about previous conversations.
```

**After:** the model sees when each message happened and how long the gaps were.

```
> What did we talk about last time?
Welcome back! It's been 2 days since we last spoke.
We were debugging your auth flow — specifically the JWT expiry issue.
```

The prompt tail the model sees:

```
Now: Wed Jul 01, 02:36 AM (night)
Session: 9h 2m · 4m active · 3 sittings · 8 messages
Gap: 6h between messages
Stale: "config.py" (read:config.py) invalidated, 14m old
```

The model knows *when* things happened, *how long ago*, and *what context is stale*.

## For coding agents (MCP server)

Same primitive, aimed at files. Stamp a file when you read it. Check staleness before editing.

```
pysince-mcp
```

**`stamp_file_read`** — call after reading any file you intend to edit:
```
Stamped read: read:/path/to/config.json
```

**`check_staleness`** — call before editing a previously-read file:
```
Stale=True (content changed, mtime changed) read 4m ago
```

If the file changed, the agent re-reads it before acting on cached content. No daemon, no polling — just mtime and content hash comparison at the next turn.

**Setup:** your MCP client needs a trigger line telling the agent when to call the tools. For Claude Code or Cursor, add to your system instructions:

> For every file you read, call `stamp_file_read` immediately. Before any edit, call `check_staleness` on files involved in the change.

## TTL system

| Class | Decay | Use case |
|---|---|---|
| `permanent` | Never | Facts, identity |
| `slow` | Session age | Normal conversation |
| `event` | On `invalidate()` | File reads, tool outputs |
| `ephemeral` | 5 minutes | "ok", "thanks" |

## Works with any provider

OpenAI, Anthropic, Gemini — `@since_time` detects the response shape automatically. Pass `extract_reply=` for anything else.

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
