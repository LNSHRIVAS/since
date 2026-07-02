import datetime
import os

from openai import OpenAI
from since import Message, with_time

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

now = datetime.datetime(2026, 6, 30, 15, 30, 0)

messages = [
    Message("s1", 1, "user", "hey, i want to build a time-aware LLM project", now - datetime.timedelta(days=5, hours=2)),
    Message("s1", 2, "assistant", "sounds great! what's the idea?", now - datetime.timedelta(days=5, hours=1, minutes=55)),
    Message("s1", 3, "user", "i want the LLM to know when things were said", now - datetime.timedelta(days=5, hours=1, minutes=50)),
    Message("s1", 4, "assistant", "like temporal context awareness?", now - datetime.timedelta(days=5, hours=1, minutes=48)),
    Message("s1", 5, "user", "exactly! every message knows its time", now - datetime.timedelta(minutes=30)),
    Message("s1", 6, "assistant", "brilliant, let's call it Ticks", now - datetime.timedelta(minutes=28)),
]

prompt = with_time(messages, now=now)
model = "gpt-4o-mini"

print(f"Sending {len(prompt)} messages to {model}...\n")

resp = client.chat.completions.create(model=model, messages=prompt, temperature=0)

print("=== LLM Response ===")
print(resp.choices[0].message.content)
