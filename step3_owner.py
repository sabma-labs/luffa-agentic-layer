"""
Step 3: Owner detection + basic commands.
The bot recognizes its owner and responds to /commands.
Non-owners get normal AI replies. When paused, only the owner can interact.
"""
import asyncio
import os
import time
from collections import defaultdict
from dotenv import load_dotenv
import luffa_bot
from openai import AsyncOpenAI

load_dotenv()

secret = os.getenv("LUFFA_ROBOT_SECRET")
if not secret:
    raise EnvironmentError("Missing LUFFA_ROBOT_SECRET in .env")

owner_uid = os.getenv("OWNER_LUFFA_UID")
if not owner_uid:
    raise EnvironmentError("Missing OWNER_LUFFA_UID in .env — needed for owner commands")

vllm_url = os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
model = os.getenv("VLLM_MODEL", "Qwen/Qwen2.5-7B-Instruct-AWQ")

luffa_bot.robot_key = secret
ai = AsyncOpenAI(base_url=vllm_url, api_key="not-needed")

SYSTEM_PROMPT = (
    f"You are an AI agent living on the Luffa messaging platform. "
    f"You are helpful, concise, and friendly. "
    f"Keep responses short — this is chat, not an essay. "
    f"You are transparent that you are an AI agent. "
    f"If asked who owns you, say your owner's Luffa UID is {owner_uid}."
)

# State
history: dict = defaultdict(list)
MAX_HISTORY = 10
paused: bool = False
start_time: float = time.time()
messages_handled: int = 0


async def ask_llm(uid: str, user_text: str) -> str:
    history[uid].append({"role": "user", "content": user_text})
    if len(history[uid]) > MAX_HISTORY:
        history[uid] = history[uid][-MAX_HISTORY:]

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history[uid]
    resp = await ai.chat.completions.create(
        model=model, messages=messages, max_tokens=512, temperature=0.7,
    )
    reply = resp.choices[0].message.content.strip()
    history[uid].append({"role": "assistant", "content": reply})
    return reply


async def handle_owner_command(cmd: str, client) -> str:
    """Process slash commands from the owner. Returns the reply string."""
    global paused

    parts = cmd.strip().split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if command == "/status":
        uptime_secs = int(time.time() - start_time)
        hours, remainder = divmod(uptime_secs, 3600)
        mins, secs = divmod(remainder, 60)
        return (
            f"Status:\n"
            f"  Uptime : {hours}h {mins}m {secs}s\n"
            f"  Handled: {messages_handled} messages\n"
            f"  Model  : {model}\n"
            f"  Paused : {paused}"
        )

    elif command == "/pause":
        paused = True
        return "Paused. I'll tell non-owners I'm unavailable until you /resume."

    elif command == "/resume":
        paused = False
        return "Resumed. Back to normal operation."

    elif command == "/history":
        if not arg:
            return "Usage: /history <uid>"
        uid_to_check = arg.strip()
        msgs = history.get(uid_to_check, [])
        if not msgs:
            return f"No history found for uid: {uid_to_check}"
        # Show last 5 messages
        recent = msgs[-5:]
        lines = [f"Last {len(recent)} messages with {uid_to_check}:"]
        for m in recent:
            role = "You" if m["role"] == "user" else "Bot"
            preview = m["content"][:80] + ("..." if len(m["content"]) > 80 else "")
            lines.append(f"  [{role}] {preview}")
        return "\n".join(lines)

    else:
        return (
            f"Unknown command: {command}\n"
            f"Available: /status, /pause, /resume, /history <uid>"
        )


async def handler(msg, env, client):
    global messages_handled

    text = (msg.text or "").strip()
    if not text:
        return

    # In DMs, env.uid is the conversation partner. In groups, msg.uid is the sender.
    sender_uid = env.uid if env.type == 0 else (msg.uid or env.uid)
    is_owner = (sender_uid == owner_uid)

    print(f"[{'DM' if env.type == 0 else 'GROUP'}] {sender_uid} ({'owner' if is_owner else 'user'}): {text}")

    # Owner commands — always handled, even when paused
    if is_owner and text.startswith("/"):
        reply = await handle_owner_command(text, client)
        await client.send_to_user(env.uid, reply)
        return

    # Paused — only owner can interact (non-command messages from owner still go to AI)
    if paused and not is_owner:
        await client.send_to_user(env.uid, "I'm currently paused. My owner will resume me soon.")
        return

    # Normal AI reply
    messages_handled += 1
    reply = await ask_llm(sender_uid, text)
    print(f"[BOT] -> {reply[:80]}{'...' if len(reply) > 80 else ''}")

    if env.type == 0:
        await client.send_to_user(env.uid, reply)
    else:
        await client.send_to_group(env.uid, reply)


if __name__ == "__main__":
    print(f"Step 3 owner bot started.")
    print(f"  Model : {model}")
    print(f"  Owner : {owner_uid}")
    asyncio.run(luffa_bot.run(handler, interval=1.0, concurrency=5))
