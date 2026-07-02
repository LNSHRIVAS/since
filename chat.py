import datetime
import os
import time
from pathlib import Path

from openai import OpenAI
from since import Store, since_time

db_path = Path.home() / ".ticks" / "chat_test.db"
db_path.parent.mkdir(parents=True, exist_ok=True)
store = Store(db_path)
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

is_dst = time.localtime().tm_isdst
offset_sec = -time.altzone if is_dst else -time.timezone
hours = offset_sec // 3600
mins = (offset_sec % 3600) // 60
if hours == 0 and mins == 0:
    tz = "UTC"
else:
    sign = "+" if hours >= 0 else "-"
    tz = f"UTC{sign}{abs(hours):02d}:{mins:02d}"

@since_time(store=store, timezone=tz)
def chat(messages):
    return client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.7,
    )

print(f"Ticks Chat (detected timezone: {tz}) - type 'quit' to exit\n")

while True:
    user_input = input("You: ")
    if user_input.strip().lower() in ("quit", "exit"):
        break

    resp = chat(messages=[{"role": "user", "content": user_input}])
    reply = resp.choices[0].message.content
    print(f"Assistant: {reply}\n")
