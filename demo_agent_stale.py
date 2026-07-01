"""
Scenario demo: Agent almost acts on stale file content.

Story: An agent reads a config file, the file changes (git pull),
the agent's next turn fires a stale warning and it re-reads.
"""

import datetime
import os
import tempfile
import time
from pathlib import Path

from since import Store
from since.stale_files import stamp_file_read, check_and_invalidate
from since.format import build_prompt
from since.models import Message

print("=" * 60)
print("  Demo: Agent catches stale file content")
print("=" * 60)

db = Path(tempfile.mktemp(suffix=".db"))
store = Store(db)
session = "agent_demo"
now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

# ── Step 1: Create a config file ──
config = Path(tempfile.mktemp(suffix=".py"))
config.write_text("API_URL = 'http://old-server.com'\nTIMEOUT = 30\n")
print(f"\n1. Config file created: {config.name}")
print(f"   Content:\n{config.read_text().strip()}")

# ── Step 2: Agent reads the file ──
print(f"\n2. Agent reads {config.name}...")
src = stamp_file_read(str(config), store, session)
print(f"   Stamped with source_id: {src}")

stale = store.stale_messages(session, now)
print(f"   Stale messages: {len(stale)} (none yet)")

# ── Step 3: Agent acts on the info (first turn) ──
prompt = build_prompt(
    [Message(session, 3, "assistant",
             "I'll use API_URL = 'http://old-server.com'", now)],
    now, include_nudge=True,
)
tail = [m for m in prompt if m["role"] == "system"][-1]["content"]
print(f"\n3. Agent's first turn — tail block:")
for line in tail.split("\n"):
    print(f"   {line}")
print("   (No stale warnings — file hasn't changed)")

# ── Step 4: Config file changes (simulating git pull) ──
time.sleep(0.01)
config.write_text("API_URL = 'http://new-server.com'\nTIMEOUT = 60\n")
print(f"\n4. Config CHANGED (simulating git pull / manual edit):")
print(f"   New content:\n{config.read_text().strip()}")

# ── Step 5: Agent's next turn — stale detection fires ──
changed = check_and_invalidate(str(config), store, session)
if changed:
    print(f"\n5. check_and_invalidate() → File changed! Invalidated old read.")

stale = store.stale_messages(session, now)
print(f"   Stale messages: {len(stale)}")

prompt2 = build_prompt(
    [Message(session, 4, "assistant",
             "Using API_URL from config...", now)],
    now, include_nudge=True, stale_info=stale,
)
tail2 = [m for m in prompt2 if m["role"] == "system"][-1]["content"]
print(f"\n6. Agent's second turn — tail block:")
for line in tail2.split("\n"):
    print(f"   {line}")

if "Stale:" in tail2:
    print("\n   >>> AGENT KNOWS THE FILE IS STALE <<<")
    print("   The agent sees the warning and re-reads the file.")
else:
    print("\n   !!! Stale warning MISSING — bug !!!")

# ── Step 7: Agent re-reads (fresh stamp) ──
print(f"\n7. Agent re-reads {config.name} (fresh stamp)...")
stamp_file_read(str(config), store, session)

stale3 = store.stale_messages(session, now)
print(f"   Now {len(stale3)} stale messages (the old reads still flagged,")
print(f"   but the new read is clean — agent has current content)")

print(f"\n{'=' * 60}")
print(f"  Status: {'PASS' if 'Stale:' in tail2 else 'FAIL'}")
print(f"{'=' * 60}")

store.close()
db.unlink()
config.unlink()
