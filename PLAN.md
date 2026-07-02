# Ticks — Temporal Context for LLMs

## One-Line Pitch

> Ticks pre-digests time so your LLM never has to do date arithmetic — and then nudges it to actually use what it's given.

---

## The Problem

LLMs are temporally blind. Without explicit time signals, agents perform near random guessing on temporal tasks. Even **with** timestamps in context, the best models align with human time judgment below 65%, and timestamps appear in fewer than 4% of model reasoning traces.

The failures are not about missing time data — they're about models being bad at using it:

- **Date arithmetic is unreliable.** LLMs struggle to subtract two timestamps and compute "3 days ago." Per-primitive accuracy ranges from near-zero to perfect depending on the model and format.
- **Format matters enormously.** How a date is formatted determines whether the model parses it correctly.
- **Time attached ≠ time used.** Injecting raw timestamps into context doesn't make the model consult them. Models need to be told time is available *and* when it matters.

Meanwhile, the "remember content across sessions" space is already well-served: Zep/Graphiti (bi-temporal modeling, 300ms P95 latency), Mem0 (47K+ GitHub stars), Letta (full agentic runtime). Competing on content recall across sessions is fighting on their turf.

The real gap is different.

---

## The Insight: Temporal Framing of the Live Thread

The conversation's own **temporal self-awareness** is underexplored:

- How long have we been talking?
- When did you last message me?
- How old is this specific turn?
- It's 2 AM — should responses adapt?

That's not content recall. It's **temporal framing of the live thread**. The memory players treat it as too trivial to package. It *is* trivial to build. But "trivial + nobody ships it cleanly + research proves it's done badly when done naively" is a legitimate niche.

There's one mechanical fact that collapses the design space: **there is no channel into an LLM except tokens.** A "Time Perception Block" and a plain timestamp in text are the same thing at the only layer that exists: text the model reads. The entire problem reduces to: **what temporal text do you put in, and when?**

---

## Core: The `withTime()` Function

Ticks is a pure function:

```
withTime(messages, store, now) → messages
```

It takes a list of conversation messages, optionally loads historical context from a store, and returns the same messages with temporal context folded in. Synchronous, sub-millisecond, no daemon, no background processes, no network.

### What `withTime()` does, in order:

#### 1. Injects a "Now" block (computed fresh every call)

```
Current time:   Tue Jun 30, 3:30 PM (afternoon)
Session age:    5 days, 5 hours
Last activity:  3 seconds ago
Day of week:    Tuesday
```

This is the only part that runs on every call. It's never stored — just computed from `now` and the session's `created_at`.

#### 2. Pre-computes per-message ages (this is the actual product)

Research shows models can't reliably subtract dates. So **you do the arithmetic and hand them the answer**. Every turn shows both the absolute anchor (for stable cross-session reasoning) and the pre-chewed relative delta (so the model never does math):

```
[Tue Jun 30, 3:30pm · 2 days 4h ago]  user: remind me about our plan
[Mon Jun 28, 11:15am · 4 days 8h ago] assistant: let's review the timeline
```

That pairing — absolute + relative, pre-computed, in formats the literature shows parse best — is the defensible cleverness. It directly attacks the failure modes the benchmarks exposed.

#### 3. Adds a prompting nudge (the most cost-effective piece)

Because models ignore timestamps in ~96% of reasoning traces, a short system instruction converts "time is present" into "time is used":

```
This conversation has temporal context attached. Use it to:
- Reference how long ago things were said
- Adapt tone/brevity to time of day
- Flag stale information
- Notice gaps in conversation
```

This is a two-line addition that probably moves the real metric more than anything in the storage layer.

#### 4. Optionally retrieves time-range history

For "what did we discuss Tuesday afternoon?" — parse to a range, run a SQL query, inject results as a block. No vector DB needed for time-addressed recall. That's just an index on a timestamp column.

---

## Storage

### Schema

```sql
CREATE TABLE messages (
  session_id  TEXT NOT NULL,
  turn_id     INTEGER NOT NULL,
  role        TEXT NOT NULL,       -- 'user' | 'assistant' | 'system'
  content     TEXT NOT NULL,
  created_at  TEXT NOT NULL,       -- ISO 8601 UTC, millisecond precision
  timezone    TEXT DEFAULT 'UTC',
  PRIMARY KEY (session_id, turn_id)
);

CREATE INDEX idx_messages_created_at ON messages(created_at);
```

### Why SQLite

- One file, zero infrastructure, ACID
- Every language has bindings (zero parsers to reimplement)
- Temporal queries are trivial: `SELECT * FROM messages WHERE created_at BETWEEN ? AND ?`
- The indexing is already done for you
- Debugging works: open the file with any SQLite browser

JSONL is also reasonable for simpler use cases. Either is strictly better than a custom binary format — faster to integrate, more portable, and the performance difference (microseconds vs nanoseconds) is invisible behind a 500-2000ms LLM call.

### What's NOT stored

Relative ages are never stored. `"2 days 4h ago"` is computed as `now − created_at` when you build the prompt. This is the only correct model: it's always fresh, no staleness, no background updates, no race conditions, no daemon.

---

## Integration

### Primary: Library

```python
from since import with_time

messages = load_messages(session_id)
enriched = with_time(messages, now=datetime.utcnow())

# Send enriched messages to OpenAI / Anthropic / whatever
response = client.chat.completions.create(
    messages=enriched,
    ...
)
```

Two lines. No proxy. No schema mutation. No daemon.

### Secondary: CLI

```
ticks enrich session_abc123          # Add temporal context to a session
ticks search session_abc123 --range "3 days ago"    # Time-range query
ticks stats session_abc123           # Session age, message count, gaps
```

### Optional: Proxy adapter

A transparent proxy for zero-code drop-in is feasible later, but it's not the foundation. Leading with the library avoids fragile provider schema tracking, auth, streaming, and payload mutation issues.

---

## The Bigger Play: Temporally-Aware Retrieval

The research reveals a genuine whitespace: **even Zep ignores time during memory retrieval**, leaving semantic × recency ranking underexplored.

Most retrieval systems rank by relevance only, then maybe filter by time. True **temporally-aware retrieval** — ranking by `relevance × recency` with learned weighting — is:

- Underserved in existing tools
- Harder to copy than a formatting library
- An actual step-function improvement for long-running agents

This is the direction where Ticks could grow beyond a utility into something defensible. But it starts with getting the temporal framing right first.

---

## Performance Budget (Honest Version)

| Operation | Target | Notes |
|-----------|--------|-------|
| `withTime()` execution | <1ms | Pure function, no I/O in hot path |
| Message INSERT | <1ms | SQLite single-row insert |
| Time-range SELECT | <5ms | Indexed by `created_at` |
| Conversation load (10K msgs) | <50ms | SQLite `SELECT * WHERE session_id = ?` |
| Relative age computation | <1ms per 10K msgs | `now - created_at`, trivial |
| Prompting nudge injection | 0 | Static text, no computation |

The LLM call dominates at 500-2000ms. There is nothing to optimize below that threshold. Any energy spent on microsecond savings is wasted.

---

## Implementation Roadmap

### Phase 1: Core Library (MVP)
- [ ] `withTime()` function (pure, synchronous)
- [ ] "Now" block generator
- [ ] Pre-computed relative age formatting for messages
- [ ] SQLite storage layer (insert, load, time-range query)
- [ ] Python package (`pip install ticks`)

### Phase 2: Temporal Search
- [ ] Natural language time range parser ("3 days ago", "Tuesday afternoon")
- [ ] Temporal query → SQL range → context injection
- [ ] Cross-session search (same time reference across multiple sessions)
- [ ] TypeScript/Node.js package (`npm install ticks`)

### Phase 3: Evaluation & Standardization
- [ ] Eval suite: measure model temporal reasoning with/without Ticks
- [ ] One-page spec for LLM temporal context formatting (the "standard")
- [ ] Published benchmark results (builds credibility, drives adoption)
- [ ] Reference implementations in 3+ languages

### Phase 4: Temporally-Aware Retrieval
- [ ] Recency × relevance ranking function
- [ ] Temporal weighting layer for retrieved context
- [ ] Integration with mem0 / existing memory systems
- [ ] Research publication on the approach

---

## Competitor Landscape

| Project | Focus | Where Ticks differs |
|---------|-------|---------------------|
| Zep/Graphiti | Bi-temporal memory, content recall | Ticks frames the **live thread**, not long-term recall |
| Mem0 | Pluggable memory layer, 47K+ stars | Ticks pre-digests time so models don't do arithmetic |
| Letta | Full agentic runtime | Ticks is a 1-function library, no runtime |
| Timestamps in prompts (ad hoc) | Everyone does this badly | Ticks formats in research-backed styles + pre-computes deltas + nudges usage |

Ticks doesn't compete with any of them for their core use case. It competes for the **temporal framing** layer they all skip.

---

## Quick Decisions (Settled by Feedback)

| Question | Decision | Why |
|----------|----------|-----|
| Language | TypeScript + Python first | Adoption beats raw speed; speed is not the constraint |
| Storage | SQLite | One file, ACID, every language has bindings |
| Integration | Library-first, proxy later | Fragile to track provider schemas |
| Timestamps | Absolute only, stored once | Relative computed lazily from `now - created_at` |
| Precision | Millisecond | Nanosecond is theater at this layer |
| Format | Absolute + relative, paired | Research: models need both for reliable reasoning |
| Auto-injection | Recent history always; time-range search gated by signals | Avoid spamming context |

---

## Open Questions

1. **Temporal signal detection** — How aggressively should the library detect "5 days ago" in user messages and trigger retrieval? Rule-based regex, LLM-classified, or always pre-fetch?
2. **Recency × relevance weighting** — Should temporal retrieval use exponential decay, linear decay, or learned weights? Underexplored in research.
3. **Cross-session linking** — How does the library associate "the same user" across separate sessions for temporal search? Identity is an unsolved problem.
4. **Privacy** — Temporal metadata (timezone, session patterns) can leak information. Should there be a "strip time" mode for sensitive conversations?

---

## Summary

Ticks is a library that takes a conversation and adds temporal context the LLM can actually use. It doesn't store time in a fancy format or run a background engine — it pre-computes age arithmetic (because models can't), formats it in a parse-friendly style (because format matters), and nudges the model to consult it (because it won't otherwise). The storage is SQLite. The core is one pure function. The moat is doing the formatting right and proving it with evals.

The long-term differentiator is temporally-aware retrieval — ranking by recency × relevance — which existing memory systems don't do.
