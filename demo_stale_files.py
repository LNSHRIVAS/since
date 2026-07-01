"""
Stale-file detection demo.

Creates a temp file, reads it (stamps an event), modifies it,
then shows staleness surfacing in the prompt tail.
"""

import datetime
import os
import tempfile
import time
from pathlib import Path

from since import Store
from since.stale_files import stamp_file_read, check_and_invalidate
from since.format import build_prompt, format_absolute
from since.models import Message

print("=== Stale-File Detection Demo ===\n")

db = Path(tempfile.mktemp(suffix=".db"))
store = Store(db)
session_id = "demo"
now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

# ── Step 1: Create a temp file ──
tmp = Path(tempfile.mktemp(suffix=".txt"))
tmp.write_text("Hello, world!")
print(f"1. Created file: {tmp}")
print(f"   Content: '{tmp.read_text()}'")
print(f"   mtime:   {os.path.getmtime(str(tmp))}\n")

# ── Step 2: "Read" the file (stamp an event) ──
src = stamp_file_read(str(tmp), store, session_id)
print(f"2. Stamped file read (source_id={src})")
msgs = store.load_session(session_id)
print(f"   Messages in session: {len(msgs)}")

stale = store.stale_messages(session_id, now)
print(f"   Stale before modify: {len(stale)}\n")

# ── Step 3: Build a prompt with no staleness ──
prompt = build_prompt(
    [Message(session_id, 3, "user", "what does the file say?", now)],
    now,
    include_nudge=True,
)
tail = [m for m in prompt if m["role"] == "system"][-1]["content"]
print(f"3. Prompt tail (before modify):")
print(f"   {tail}\n")

# ── Step 4: Modify the file ──
time.sleep(0.01)
tmp.write_text("Hello, world! UPDATED")
print(f"4. Modified file: '{tmp.read_text()}'")
print(f"   new mtime: {os.path.getmtime(str(tmp))}\n")

# ── Step 5: Check staleness ──
changed = check_and_invalidate(str(tmp), store, session_id)
if changed:
    print(f"5. Staleness detected! File changed.")
else:
    print(f"5. No change detected (shouldn't happen).")

stale = store.stale_messages(session_id, now)
print(f"   Stale messages: {len(stale)}")
for s in stale:
    print(f"   - turn={s.turn_id} src={s.source_id} preview=\"{s.content_preview}\"")
print()

# ── Step 6: Build prompt with stale warning ──
prompt2 = build_prompt(
    [Message(session_id, 4, "user", "what does the file say now?", now)],
    now,
    include_nudge=True,
    stale_info=stale,
)
tail2 = [m for m in prompt2 if m["role"] == "system"][-1]["content"]
print(f"6. Prompt tail (AFTER modify):")
print(f"   {tail2}")
assert "Stale:" in tail2
print("\n   -> Stale warning visible in tail! The agent should re-read.\n")

# ── Step 7: Re-read the file (fresh stamp) ──
# Invalidating the old event doesn't remove it; we stamp a new read
# to show the cycle
src2 = stamp_file_read(str(tmp), store, session_id)
print(f"7. Re-stamped file read (source_id={src2})")

stale2 = store.stale_messages(session_id, now + datetime.timedelta(seconds=1))
print(f"   Stale after re-read: {len(stale2)} (only the old event, not the new one)\n")

store.close()
db.unlink()
tmp.unlink()
print("=== Demo complete ===")
