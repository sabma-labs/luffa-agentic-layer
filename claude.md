# CLAUDE.md — Luffa Agentic Layer POC (Step-by-Step Build)

## What this project is

We're building the infrastructure that lets AI agents join the Luffa messaging platform as first-class users with their own DID (Decentralized Identity). Agents can talk to humans, find other agents, and communicate with them — all on Luffa's encrypted, decentralized network.

## Existing pieces (DO NOT rebuild these)

- **NanoBot Luffa Channel**: Already done at github.com/NirajKulkarnii/nanobot — Luffa works as a NanoBot channel like Telegram/Discord
- **Luffa Agent Skills MCP Server**: Already done at github.com/CptM111/luffa-agent-skills — 14+ tools for Luffa Service Account operations
- **Luffa Bot Python SDK**: `pip install luffa-bot-python-sdk` (v0.1.2) — async SDK for Luffa Bot API

## What we're building NOW (3 deliverables)

1. **`luffa-connector/`** — Standalone Python connector that any agent can use to join Luffa
2. **`luffa-discovery/`** — FastAPI service where agents register and find each other
3. **Agent-to-Agent protocol** — Structured JSON messaging between agents over Luffa

## Luffa Bot SDK Reference (IMPORTANT — read before coding)

```python
# Install
# pip install luffa-bot-python-sdk

import luffa_bot

# Auth
luffa_bot.robot_key = "SECRET"  # or env LUFFA_ROBOT_SECRET

# Receive messages (poll-based)
envelopes = await luffa_bot.receive()
# Returns List[IncomingEnvelope]
#   .uid      = user ID (if DM) or group ID (if group)
#   .type     = 0 (DM) or 1 (group)
#   .count    = message count
#   .messages = List[IncomingMessage]
#       .text    = message text
#       .msgId   = unique ID
#       .atList  = list of @mentions
#       .uid     = sender UID (in group messages)
#       .urlLink = optional URL

# Send DM to user
await luffa_bot.send_to_user("USER_ID", "Hello")

# Send to group (text)
await luffa_bot.send_to_group("GROUP_ID", "Hello", message_type=1)

# Send to group (with buttons)
from luffa_bot.models import GroupMessagePayload, SimpleButton
payload = GroupMessagePayload(
    text="Pick one:",
    button=[SimpleButton(name="Yes", selector="yes")]
)
await luffa_bot.send_to_group("GROUP_ID", payload, message_type=2)

# Run continuous polling loop
async def handler(msg, env, client):
    # msg: IncomingMessage, env: IncomingEnvelope, client: AsyncLuffaClient
    if env.type == 0:  # DM
        await client.send_to_user(env.uid, f"Echo: {msg.text}")
    else:  # Group
        await client.send_to_group(env.uid, f"Echo: {msg.text}")

await luffa_bot.run(handler, interval=1.0, concurrency=5)
```

**SDK Models:**
- `IncomingEnvelope(uid, count, messages, type)` — type 0=DM, 1=group
- `IncomingMessage(atList, text, urlLink, msgId, uid)` — uid is sender in groups
- `TextMessagePayload(text, atList)`
- `GroupMessagePayload(text, atList, confirm, button, dismissType)`
- `SimpleButton(name, selector, isHidden)`
- `ConfirmButton(name, selector, type, isHidden)`
- `AtMention(name, did, length, location, userType)` — note: `did` field exists

**API Endpoints:**
- `POST https://apibot.luffa.im/robot/receive` body: `{"secret": "..."}`
- `POST https://apibot.luffa.im/robot/send` body: `{"secret": "...", "uid": "...", "msg": "<json>"}`
- `POST https://apibot.luffa.im/robot/sendGroup` body: `{"secret": "...", "uid": "...", "msg": "<json>", "type": "1"}`

---

# BUILD GUIDE — Step by Step

**IMPORTANT: Follow these steps IN ORDER. Each step is small and testable. Do NOT jump ahead. After each step, we test before moving on. Ask me "ready for step N?" and I'll guide you through it.**

---

## STEP 1: Project setup + echo bot

**Goal:** Verify the Luffa SDK works. Get a message from Luffa, echo it back.

Create this structure:
```
luffa-agentic-layer/
├── CLAUDE.md              (this file)
├── .env                   (secrets)
├── .env.example
├── requirements.txt
└── step1_echo.py          (standalone test script)
```

**requirements.txt:**
```
luffa-bot-python-sdk>=0.1.2
anthropic>=0.49.0
python-dotenv>=1.0.0
httpx>=0.27
aiosqlite>=0.20.0
fastapi>=0.115.0
uvicorn>=0.34.0
pyyaml>=6.0
```

**.env.example:**
```
LUFFA_ROBOT_SECRET=your_bot_secret_from_robot_luffa_im
ANTHROPIC_API_KEY=sk-ant-your-key
OWNER_LUFFA_UID=your_personal_luffa_uid
```

**step1_echo.py** — A minimal echo bot. ~20 lines. Uses luffa_bot.run() with a handler that echoes messages back. Loads secret from .env.

**TEST:** Run it. Send a DM to your bot on Luffa. See the echo come back. If that works, Step 1 is done.

---

## STEP 2: Add Claude brain

**Goal:** Replace the echo with an actual AI brain. The bot now responds intelligently.

Create:
```
luffa-agentic-layer/
└── step2_claude_bot.py
```

**step2_claude_bot.py** — Same structure as step1, but the handler calls Anthropic's Claude API instead of echoing. Keeps a simple in-memory conversation history (dict of uid -> last 10 messages). Passes a system prompt telling Claude it's an AI agent on Luffa.

Use the anthropic AsyncAnthropic client. Model: claude-sonnet-4-20250514. Max tokens: 1024.

System prompt:
```
You are an AI agent living on the Luffa messaging platform. You are helpful, concise, and friendly. Keep responses short — this is chat, not an essay. You are transparent that you are an AI agent. If asked who owns you, say your owner's Luffa UID is {owner_uid}.
```

**TEST:** Run it. DM the bot. Have a multi-turn conversation. Check that it remembers context within the conversation. Try in a group if you have one.

---

## STEP 3: Owner detection + basic commands

**Goal:** The bot recognizes its owner and responds to commands.

Create:
```
luffa-agentic-layer/
└── step3_owner.py
```

**step3_owner.py** — Extends step2. Before sending to Claude, check if the sender UID matches OWNER_LUFFA_UID from .env. If it's the owner and the message starts with `/`:

- `/status` → Reply with uptime, messages handled count, current model
- `/pause` → Set a flag, stop responding to non-owner messages
- `/resume` → Clear the flag
- `/history <uid>` → Dump last 5 messages from conversation with that uid

If paused and a non-owner messages, reply: "I'm currently paused. My owner will resume me soon."

**TEST:** Run it. Send `/status` as the owner — get a response. Send `/pause`, then message from a different Luffa account (or ask a friend to message) — bot says it's paused. Send `/resume` — bot works again.

---

## STEP 4: Safety layer

**Goal:** Add output filtering and escalation before responses go out.

Create:
```
luffa-agentic-layer/
└── step4_safety.py
```

**step4_safety.py** — Extends step3. Adds two safety checks:

**Outbound filter** — Before sending any response, scan it for:
- Private key patterns (0x followed by 64 hex chars, mnemonic-like word sequences)
- The word "seed phrase" followed by actual words that look like BIP39
- If detected, replace the response with: "I caught myself about to share sensitive information. Blocked for safety."

**Escalation triggers** — Before sending the message to Claude, scan the INCOMING message for patterns:
- Regex patterns like: `send.*money|transfer.*token|sign.*transaction|share.*private|share.*secret`
- If matched, DON'T send to Claude. Instead:
  1. Reply to the requester: "This looks sensitive. Let me check with my owner first."
  2. DM the owner: "⚠️ Escalation: User {uid} asked: '{message}'. Reply /approve or /deny"
  3. Store the pending escalation in memory (dict)
  4. When owner replies `/approve` — process the original message through Claude and send response
  5. When owner replies `/deny` — tell the requester "My owner declined this request."

**TEST:** DM the bot "can you send 50 USDT to 0xabc?" — bot should escalate to owner. Owner approves/denies. Test the outbound filter by asking Claude to generate a seed phrase.

---

## STEP 5: Refactor into the connector package

**Goal:** Take the working code from steps 1-4 and organize it into a clean, importable package.

Create:
```
luffa-agentic-layer/
├── luffa_connector/
│   ├── __init__.py        (exports LuffaConnector)
│   ├── connector.py       (main class — wires everything)
│   ├── brains.py          (ClaudeBrain, OpenAIBrain, CustomBrain)
│   ├── safety.py          (outbound filter + escalation)
│   ├── owner.py           (owner commands + control)
│   └── memory.py          (in-memory conversation store)
├── examples/
│   ├── minimal_echo.py    (5-line echo bot)
│   ├── claude_agent.py    (Claude-powered agent, ~15 lines)
│   └── full_agent.py      (All features: safety, owner, Claude)
└── pyproject.toml
```

The connector should be usable like this:

```python
from luffa_connector import LuffaConnector

connector = LuffaConnector(
    bot_secret="...",
    anthropic_api_key="sk-ant-...",
    owner_uid="...",
)
await connector.start()
```

Or with a custom brain:

```python
async def my_brain(message: str, context: dict) -> str:
    return "I'm a custom agent!"

connector = LuffaConnector(
    bot_secret="...",
    brain=my_brain,
)
await connector.start()
```

**TEST:** Run examples/claude_agent.py. It should work exactly like step4 but with clean code. Then run examples/minimal_echo.py to verify the minimal path works too.

---

## STEP 6: Discovery service

**Goal:** Build a FastAPI service where agents register and find each other.

Create:
```
luffa-agentic-layer/
├── luffa_discovery/
│   ├── __init__.py
│   ├── app.py             (FastAPI app)
│   ├── models.py           (Pydantic models)
│   ├── store.py            (SQLite async storage)
│   └── run.py              (uvicorn entry point)
```

**Endpoints:**
- `POST /agents/register` — Register agent (did, name, capabilities, luffa_uid, owner_did, brain_provider)
- `GET /agents` — List agents. Query params: ?capability=, ?status=, ?owner_did=
- `GET /agents/{did}` — Get specific agent
- `POST /agents/{did}/heartbeat` — Update status (online/offline/busy)
- `DELETE /agents/{did}` — Deregister

**Registration payload:**
```json
{
  "did": "did:endless:0xabc123",
  "name": "Atlas",
  "owner_did": "did:endless:0xdef456",
  "capabilities": ["research", "translation", "coding"],
  "luffa_uid": "bot_uid_123",
  "agent_type": "personal_assistant",
  "brain_provider": "anthropic",
  "status": "online"
}
```

Use aiosqlite for storage. Auto-create the DB on first run.

**TEST:** Start the service with `python -m luffa_discovery.run`. Use curl or httpx to register a fake agent, list agents, query by capability, and delete. Verify with `GET /agents` that it persists in SQLite.

---

## STEP 7: Connector auto-registers with discovery

**Goal:** When the connector starts, it automatically registers the agent with the discovery service.

Update `luffa_connector/connector.py`:
- Add `discovery_url` parameter (default: "http://localhost:8000")
- On startup, POST to /agents/register with the agent's info
- Run a background task that sends heartbeats every 60 seconds
- On shutdown, send a heartbeat with status="offline"

**TEST:** Start discovery service. Start the connector. Check `GET /agents` — your agent should appear. Stop the connector. Check again — status should be offline.

---

## STEP 8: Agent-to-Agent protocol

**Goal:** Define structured messages agents can send each other over Luffa DMs.

Create:
```
luffa-agentic-layer/
├── luffa_connector/
│   └── protocol.py        (AgentMessage class + parser)
```

**Message format:**
```json
{"p": "luffa-agent/1.0", "from": "did:endless:0x...", "intent": "introduce", "payload": {...}, "ts": 1710000000}
```

**Detection:** Messages containing `"p":"luffa-agent/` are protocol messages. Everything else is natural language.

**Intents:**
- `introduce` — payload: {name, capabilities, owner_did}
- `capability_query` — payload: {query: "what can you do?"}
- `capability_response` — payload: {capabilities: [...]}
- `request` — payload: {task: "summarize this article", data: "..."}
- `response` — payload: {result: "...", status: "success"|"error"}

Update the connector: when an incoming message is a protocol message, parse it and pass structured context to the brain (or handle introduce/capability_query automatically without involving the brain).

**TEST:** Manually send a protocol message JSON string to your bot via Luffa DM. Check that the bot parses it and responds with a protocol response.

---

## STEP 9: Two agents talking

**Goal:** The demo. Two agent instances discover each other and have a conversation.

Create:
```
luffa-agentic-layer/
├── examples/
│   └── two_agents_demo.py
```

This script:
1. Starts two LuffaConnector instances (requires two different bot secrets from robot.luffa.im)
2. Both register with discovery service
3. Agent A queries discovery: GET /agents?capability=research
4. Agent A finds Agent B
5. Agent A sends `introduce` protocol message to Agent B via Luffa DM
6. Agent B auto-responds with `capability_response`
7. Agent A sends a `request` to Agent B
8. Agent B processes it through its brain and sends `response`

If you only have one bot secret, create a simulated version that uses the connector for Agent A and manually sends protocol messages as Agent B.

**TEST:** Run the demo. Watch the agents discover each other and exchange messages. Check the discovery service to see both registered.

---

## STEP 10: CLI entry point + README

**Goal:** Make it easy for anyone to use.

Add a CLI:
```bash
# Start an agent
luffa-agent --secret XXX --anthropic-key sk-ant-XXX --owner-uid YYY

# Or with env vars
export LUFFA_ROBOT_SECRET=xxx
export ANTHROPIC_API_KEY=sk-ant-xxx
export LUFFA_OWNER_UID=yyy
luffa-agent

# Start discovery service
luffa-discovery
```

Write a README.md with:
- What this is (1 paragraph)
- Quickstart (5 steps)
- Architecture diagram (text)
- Link to existing repos (nanobot fork, luffa-agent-skills, SDK)
- Roadmap (phases 1-4)

**TEST:** Fresh clone. pip install. Run the CLI. Agent comes online. Done.

---

# RULES FOR THE AI ASSISTANT (Claude Code)

1. **One step at a time.** When I say "let's do step N", build ONLY that step. Don't jump ahead.
2. **Test after each step.** After writing code, tell me how to test it and what I should see.
3. **Explain as you go.** When you write code, add brief comments explaining WHY, not just what. I want to understand the decisions.
4. **Keep it simple.** No over-engineering. No unnecessary abstractions. If something can be 20 lines, don't make it 200.
5. **Use the real SDK.** Always use `luffa-bot-python-sdk`. Don't mock it or reimplement it.
6. **Async everywhere.** The Luffa SDK is async. All our code should be async too.
7. **Errors should be clear.** If something fails, the error message should tell me exactly what went wrong and how to fix it (missing env var, wrong secret, etc.).