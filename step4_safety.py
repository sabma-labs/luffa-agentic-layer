"""
Step 4: Safety layer — outbound filter + escalation to owner.
Two protections:
  1. Outbound filter: scans AI replies for sensitive data before sending
  2. Escalation: suspicious incoming messages go to owner for approve/deny
"""
import asyncio
import os
import re
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
    raise EnvironmentError("Missing OWNER_LUFFA_UID in .env")

vllm_url = os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
model = os.getenv("VLLM_MODEL", "Qwen/Qwen2.5-7B-Instruct-AWQ")

luffa_bot.robot_key = secret
ai = AsyncOpenAI(base_url=vllm_url, api_key="not-needed")

SYSTEM_PROMPT = (
    f"You are an AI agent living on the Luffa messaging platform. "
    f"You are helpful, concise, and friendly. Keep responses short. "
    f"You are transparent that you are an AI agent. "
    f"If asked who owns you, say your owner's Luffa UID is {owner_uid}."
)

# ── State ──────────────────────────────────────────────────────────────────────
history: dict = defaultdict(list)
MAX_HISTORY = 10
paused: bool = False
start_time: float = time.time()
messages_handled: int = 0

# Pending escalations: maps escalation_id -> {uid, env_type, original_text}
# When owner replies /approve <id> or /deny <id> we look up this dict.
pending_escalations: dict = {}
_escalation_counter: int = 0

# ── Safety patterns ────────────────────────────────────────────────────────────

# Outbound: things the bot should NEVER send
OUTBOUND_BLOCKED = [
    re.compile(r'\b0x[0-9a-fA-F]{64}\b'),                         # private key hex
    re.compile(r'(?i)seed\s+phrase\b'),                            # "seed phrase"
    re.compile(r'(?i)\b(?:abandon|ability|able|about|above|absent|absorb|abstract|'
               r'absurd|abuse|access|accident|account|accuse|achieve|acid|acoustic|'
               r'acquire|across|act|action|actor|actress|actual)\b.*'
               r'\b(?:abandon|ability|able|about|above|absent|absorb|abstract)\b'),  # BIP39-like sequence
]

# Inbound: messages that need owner approval before processing
ESCALATION_PATTERNS = re.compile(
    r'(?i)(send.*money|transfer.*token|sign.*transaction|'
    r'share.*private|share.*secret|send.*crypto|send.*coin|'
    r'send.*usdt|send.*eth|send.*btc|wire.*transfer)',
    re.IGNORECASE,
)


def outbound_filter(text: str) -> str:
    """Block responses that contain sensitive data. Returns safe text or a block message."""
    for pattern in OUTBOUND_BLOCKED:
        if pattern.search(text):
            print(f"[SAFETY] Outbound blocked — matched pattern: {pattern.pattern[:40]}")
            return "I caught myself about to share sensitive information. Blocked for safety."
    return text


def is_escalation_needed(text: str) -> bool:
    """Return True if the incoming message matches a sensitive pattern."""
    return bool(ESCALATION_PATTERNS.search(text))


# ── LLM ───────────────────────────────────────────────────────────────────────

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


# ── Owner commands ─────────────────────────────────────────────────────────────

async def handle_owner_command(cmd: str, client) -> str:
    global paused, pending_escalations

    parts = cmd.strip().split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if command == "/status":
        uptime_secs = int(time.time() - start_time)
        h, rem = divmod(uptime_secs, 3600)
        m, s = divmod(rem, 60)
        return (
            f"Status:\n"
            f"  Uptime  : {h}h {m}m {s}s\n"
            f"  Handled : {messages_handled} messages\n"
            f"  Model   : {model}\n"
            f"  Paused  : {paused}\n"
            f"  Pending : {len(pending_escalations)} escalation(s)"
        )

    elif command == "/pause":
        paused = True
        return "Paused."

    elif command == "/resume":
        paused = False
        return "Resumed."

    elif command == "/history":
        if not arg:
            return "Usage: /history <uid>"
        msgs = history.get(arg, [])
        if not msgs:
            return f"No history for {arg}"
        recent = msgs[-5:]
        lines = [f"Last {len(recent)} messages with {arg}:"]
        for m in recent:
            role = "You" if m["role"] == "user" else "Bot"
            preview = m["content"][:80] + ("..." if len(m["content"]) > 80 else "")
            lines.append(f"  [{role}] {preview}")
        return "\n".join(lines)

    elif command == "/approve":
        if not arg:
            return "Usage: /approve <id>  (see escalation alert for the id)"
        esc = pending_escalations.pop(arg, None)
        if not esc:
            return f"No pending escalation with id '{arg}'."
        # Process the original message through the AI now
        reply = await ask_llm(esc["uid"], esc["text"])
        reply = outbound_filter(reply)
        if esc["env_type"] == 0:
            await client.send_to_user(esc["uid"], reply)
        else:
            await client.send_to_group(esc["uid"], reply)
        return f"Approved. Sent response to {esc['uid']}."

    elif command == "/deny":
        if not arg:
            return "Usage: /deny <id>"
        esc = pending_escalations.pop(arg, None)
        if not esc:
            return f"No pending escalation with id '{arg}'."
        await client.send_to_user(esc["uid"], "My owner declined this request.")
        return f"Denied. Notified {esc['uid']}."

    else:
        return "Commands: /status /pause /resume /history <uid> /approve <id> /deny <id>"


# ── Main handler ───────────────────────────────────────────────────────────────

async def handler(msg, env, client):
    global messages_handled, _escalation_counter

    text = (msg.text or "").strip()
    if not text:
        return

    sender_uid = env.uid if env.type == 0 else (msg.uid or env.uid)
    is_owner = (sender_uid == owner_uid)

    print(f"[{'DM' if env.type == 0 else 'GROUP'}] {sender_uid} ({'owner' if is_owner else 'user'}): {text}")

    # Owner slash commands — always handled
    if is_owner and text.startswith("/"):
        reply = await handle_owner_command(text, client)
        await client.send_to_user(env.uid, reply)
        return

    # Paused check
    if paused and not is_owner:
        await client.send_to_user(env.uid, "I'm currently paused. My owner will resume me soon.")
        return

    # Escalation check — sensitive request goes to owner for approval
    if is_escalation_needed(text):
        _escalation_counter += 1
        esc_id = str(_escalation_counter)
        pending_escalations[esc_id] = {
            "uid": sender_uid,
            "env_type": env.type,
            "text": text,
        }
        print(f"[SAFETY] Escalating message from {sender_uid} (id={esc_id}): {text[:60]}")

        # Tell the requester we're checking with the owner
        await client.send_to_user(env.uid, "This looks sensitive. Let me check with my owner first.")

        # Alert the owner
        await client.send_to_user(
            owner_uid,
            f"⚠️ Escalation #{esc_id}: User {sender_uid} asked:\n\"{text}\"\n\nReply /approve {esc_id} or /deny {esc_id}",
        )
        return

    # Normal flow — ask LLM, then filter output before sending
    messages_handled += 1
    reply = await ask_llm(sender_uid, text)
    reply = outbound_filter(reply)  # safety check on the way out
    print(f"[BOT] -> {reply[:80]}{'...' if len(reply) > 80 else ''}")

    if env.type == 0:
        await client.send_to_user(env.uid, reply)
    else:
        await client.send_to_group(env.uid, reply)


if __name__ == "__main__":
    print(f"Step 4 safety bot started.")
    print(f"  Model : {model}")
    print(f"  Owner : {owner_uid}")
    asyncio.run(luffa_bot.run(handler, interval=1.0, concurrency=5))
