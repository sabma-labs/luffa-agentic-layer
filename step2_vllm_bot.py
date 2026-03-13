"""
Step 2: AI brain via vLLM (Qwen2.5-7B-AWQ or any OpenAI-compatible model).
The bot now responds intelligently instead of just echoing.
Keeps last 10 messages per user for multi-turn context.
"""
import asyncio
import os
from collections import defaultdict
from dotenv import load_dotenv
import luffa_bot
from openai import AsyncOpenAI

load_dotenv()

secret = os.getenv("LUFFA_ROBOT_SECRET")
if not secret:
    raise EnvironmentError("Missing LUFFA_ROBOT_SECRET in .env")

owner_uid = os.getenv("OWNER_LUFFA_UID", "unknown")
vllm_url = os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
model = os.getenv("VLLM_MODEL", "Qwen/Qwen2.5-7B-Instruct-AWQ")

luffa_bot.robot_key = secret

# vLLM exposes an OpenAI-compatible API — api_key can be anything
ai = AsyncOpenAI(base_url=vllm_url, api_key="not-needed")

SYSTEM_PROMPT = (
    f"You are an AI agent living on the Luffa messaging platform. "
    f"You are helpful, concise, and friendly. "
    f"Keep responses short — this is chat, not an essay. "
    f"You are transparent that you are an AI agent. "
    f"If asked who owns you, say your owner's Luffa UID is {owner_uid}."
)

# Per-user conversation history: uid -> list of {"role": ..., "content": ...}
history: dict = defaultdict(list)
MAX_HISTORY = 10  # keep last N messages per user to avoid context bloat


async def ask_llm(uid: str, user_text: str) -> str:
    """Append user message to history, call vLLM, append assistant reply."""
    history[uid].append({"role": "user", "content": user_text})

    # Trim to last MAX_HISTORY messages so we don't blow up the context
    if len(history[uid]) > MAX_HISTORY:
        history[uid] = history[uid][-MAX_HISTORY:]

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history[uid]

    resp = await ai.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=512,
        temperature=0.7,
    )

    reply = resp.choices[0].message.content.strip()
    history[uid].append({"role": "assistant", "content": reply})
    return reply


async def handler(msg, env, client):
    text = msg.text or ""
    if not text:
        return  # ignore empty messages

    # sender key: in DMs use env.uid (the DM partner), in groups use msg.uid (actual sender)
    sender_uid = env.uid if env.type == 0 else (msg.uid or env.uid)
    print(f"[{'DM' if env.type == 0 else 'GROUP'}] {sender_uid}: {text}")

    reply = await ask_llm(sender_uid, text)
    print(f"[BOT] -> {reply[:80]}{'...' if len(reply) > 80 else ''}")

    if env.type == 0:
        await client.send_to_user(env.uid, reply)
    else:
        await client.send_to_group(env.uid, reply)


if __name__ == "__main__":
    print(f"Step 2 vLLM bot started.")
    print(f"  Model : {model}")
    print(f"  vLLM  : {vllm_url}")
    print(f"  Owner : {owner_uid}")
    asyncio.run(luffa_bot.run(handler, interval=1.0, concurrency=5))
