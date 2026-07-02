# Ticks TTL — Time-To-Live for LLM Context

## One-Line

> TTL for everything an LLM sees — four decay classes, auto-assigned, surfaced as staleness in the prompt.

---

## The Four TTL Classes

| Class | Example | Default TTL | Invalidates by | Display |
|-------|---------|-------------|----------------|---------|
| `permanent` | "This is a Python project" | None | Never | No decoration |
| `slow` | Chat turns, decisions, plans | Session | Time (session age) | No decoration (default) |
| `event` | File reads, tool outputs | None (clock) | `invalidate(source)` call | `⚠ filename` when stale |
| `ephemeral` | "Build running", "I'm hungry" | 5min | Time (wall clock) | `⚠ ephemeral` when expired |

### 1. Permanent
Facts that don't decay. Project conventions, user identity, architectural decisions.
- **Auto-assigned**: Never (developer must tag)
- **Surfacing**: None — always included in context
- **TTL**: Infinite

### 2. Slow
The default. Chat turns, decisions, stated context. Relevancy fades as the session grows.
- **Auto-assigned**: Every message unless otherwise tagged
- **TTL**: Session duration (effectively handled by context window limit + `last_n`)
- **Surfacing**: Never flagged individually. The tail block shows session age as context

### 3. Event-bound
External state that can change independently. File contents, API responses, tool outputs.
- **Auto-assigned**: When `source_id` is provided (e.g. file path, URL, resource name)
- **TTL**: No clock-based expiry. Invalidated explicitly by `store.invalidate(source_id)`
- **Surfacing**: `⚠ filename (modified — context stale)` in the tail block
- **Developer contract**: Call `store.invalidate("path/to/file.py")` when the file changes

### 4. Ephemeral
Momentary state that expires quickly. "I'm hungry", "build is running", temporary preferences.
- **Auto-assigned**: Never (developer tags explicitly, or content heuristics in future)
- **TTL**: 5 minutes (configurable)
- **Surfacing**: `⚠ "I'm hungry" (ephemeral, 8m old — expired)` in the tail block

---

## Storage Schema

```sql
-- Existing columns:
--   session_id, turn_id, role, content, created_at, timezone

-- New columns:
ALTER TABLE messages ADD COLUMN ttl_class TEXT DEFAULT 'slow';
ALTER TABLE messages ADD COLUMN source_id TEXT DEFAULT NULL;
ALTER TABLE messages ADD COLUMN invalidated_at TEXT DEFAULT NULL;  -- ISO UTC when invalidated
```

### Computed staleness (not stored)

```python
def is_stale(msg: Message, now, session_epoch) -> bool:
    if msg.ttl_class == "permanent":
        return False
    if msg.ttl_class == "ephemeral":
        return (now - msg.created_at) > msg.ttl_duration
    if msg.ttl_class == "event":
        return msg.invalidated_at is not None
    return False  # slow = not stale per se, just old
```

---

## API Surface

### Store (new methods)

```python
store.invalidate(source_id: str) -> int
    # Marks all event-bound messages with this source_id as invalidated
    # Returns count of messages affected

store.stale_summary(session_id: str, now: datetime) -> list[StaleInfo]
    # Returns list of stale items for surfacing in the tail block
```

### Message (new fields)

```python
@dataclass
class Message:
    ...
    ttl_class: str = "slow"        # "permanent" | "slow" | "event" | "ephemeral"
    source_id: str | None = None   # e.g. "src/main.py"
    invalidated_at: datetime | None = None  # when it was invalidated
```

---

## Surfacing in the Prompt

The tail block (`_build_tail`) will now include a stale summary section:

```
--- Current Time ---
Now: Tue Jun 30, 06:54 PM (evening)
Session: 5d · 47 messages

Stale context:
  ⚠ read_file.py — modified 1h ago, context may be stale
  ⚠ "build running" — ephemeral, expired 8m ago
```

If nothing is stale, the section is omitted entirely (no noise).

---

## Event-Bound Invalidation: The Developer Contract

Ticks does not watch files. It does not poll. When something changes, the developer calls:

```python
store.invalidate("src/main.py")
# or
store.invalidate("api_response_users")
```

This sets `invalidated_at = now` on all event-bound messages with that `source_id`. On the next LLM call, the tail block surfaces the staleness.

The developer owns the trigger. ticks owns the TTL arithmetic and surfacing.

---

## Agentic Coding Example

```python
from since import Store, since_time

store = Store("~/.ticks/coding.db")

@sense_time(store=store)
def agent(messages):
    return client.chat.completions.create(model="gpt-4o", messages=messages)

def read_file(path):
    content = open(path).read()
    agent(messages=[
        {"role": "user", "content": f"Read {path}:\n{content}", "source_id": path, "ttl_class": "event"}
    ])
    return content

def edit_file(path, new_content):
    open(path, "w").write(new_content)
    store.invalidate(path)  # ← TTL invalidation
```

When the agent later references `read_file.py`, the tail block flags it as stale — the agent re-reads before acting.

---

## Implementation Order

1. Add `ttl_class`, `source_id`, `invalidated_at` to `Message` model
2. Add columns to SQLite schema (migration)
3. Implement `invalidate(source_id)` and stale detection in Store
4. Update `_build_tail` to surface stale context
5. Wire through `sense_time` decorator (preserve `source_id` / `ttl_class` from caller metadata)
6. Update chat.py demo to accept per-message metadata
7. Write file-read demo for agentic use case

---

## Open Questions for Review

1. **Ephemeral TTL** — 5 minute default? Configurable per-call or globally?
2. **Stale flag format** — Single `⚠` line per stale item, or a count ("3 stale references")?
3. **Permanent auto-detection** — Should ticks auto-detect a fact as "permanent" (e.g., "I'm a Python project") or always require explicit tagging?
4. **Multiple invalidations** — Same file invalidated twice — keep all messages stale or only the ones before the latest invalidation?
