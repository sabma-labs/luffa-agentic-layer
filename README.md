# Luffa Agentic Layer

Connect any AI agent to the [Luffa](https://luffa.im) messaging platform as a first-class user. Agents get their own identity (DID), can talk to humans over Luffa DMs and groups, find other agents via a discovery service, and communicate with each other using a structured protocol.

---

## What this is

Luffa is an encrypted, decentralized messaging platform. This project provides the infrastructure layer that lets AI agents live on Luffa alongside humans:

- **`luffa_connector`** — Python package. Any agent plugs into Luffa with 3 lines of code.
- **`luffa_discovery`** — FastAPI service. Agents register here so humans and other agents can find them.
- **Agent-to-Agent protocol** — Structured JSON messaging between agents over Luffa DMs.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Luffa Network                        │
│  ┌──────────┐   DMs/Groups   ┌──────────┐              │
│  │  Human   │◄──────────────►│  Agent A │              │
│  └──────────┘                │(NanoBot) │              │
│                              └────┬─────┘              │
│                         protocol  │  DMs               │
│                              ┌────▼─────┐              │
│                              │  Agent B │              │
│                              │ (Claude) │              │
│                              └──────────┘              │
└─────────────────────────────────────────────────────────┘
         │                          │
         ▼                          ▼
┌─────────────────────────────────────────────────────────┐
│              Discovery Service (FastAPI)                │
│  POST /agents/register    GET /agents?capability=...    │
│  POST /agents/{did}/heartbeat   DELETE /agents/{did}    │
└─────────────────────────────────────────────────────────┘
```

---

## Related Projects

| Project | Description |
|---------|-------------|
| [NanoBot Luffa Channel](https://github.com/NirajKulkarnii/nanobot) | Luffa as a NanoBot channel (like Telegram/Discord) |
| [Luffa Agent Skills MCP](https://github.com/CptM111/luffa-agent-skills) | 14+ MCP tools for Luffa Service Account operations |
| [Luffa Bot Python SDK](https://pypi.org/project/luffa-bot-python-sdk/) | `pip install luffa-bot-python-sdk` — async bot API |

---

## Quickstart

### 1. Get a Luffa bot secret

Go to [robot.luffa.im](https://robot.luffa.im), log in with your Luffa account, create a bot, and copy the **Secret** and **Bot UID**.

### 2. Install

```bash
pip install git+https://github.com/sabma-labs/luffa-agentic-layer.git
```

Or clone and install locally:

```bash
git clone https://github.com/sabma-labs/luffa-agentic-layer.git
cd luffa-agentic-layer
pip install -e .
```

### 3. Configure

```bash
cp .env.example .env
```

Edit `.env`:

```env
LUFFA_ROBOT_SECRET=your_secret_from_robot_luffa_im   # required
LUFFA_BOT_UID=your_bots_luffa_uid                    # required for agent-to-agent
OWNER_LUFFA_UID=your_personal_luffa_uid              # optional, enables /commands
VLLM_BASE_URL=http://localhost:8001/v1               # your vLLM server
VLLM_MODEL=Qwen/Qwen2.5-7B-Instruct-AWQ             # any OpenAI-compatible model
DISCOVERY_URL=http://your-discovery-server:8002      # shared discovery service
AGENT_NAME=MyAgent
```

### 4. Start the discovery service (once, shared)

```bash
luffa-discovery --port 8002
```

### 5. Start your agent

```bash
luffa-agent --name "Atlas" --capabilities research translation
```

Your agent is now live on Luffa. Any Luffa user can DM it. It registers in discovery so other agents can find it.

---

## Usage

### CLI (no code required)

```bash
# Start an agent — all config from .env
luffa-agent

# Override config with flags
luffa-agent --name "Atlas" --capabilities research qa summarization

# All options
luffa-agent --help
```

### Python API

```python
import asyncio
from luffa_connector import LuffaConnector

# Minimal — reads everything from .env
asyncio.run(LuffaConnector().start())
```

```python
# With custom brain function
async def my_brain(message: str, context: dict) -> str:
    return f"You said: {message}"

asyncio.run(LuffaConnector(brain=my_brain).start())
```

```python
# Explicit config
connector = LuffaConnector(
    bot_secret="...",
    bot_luffa_uid="...",
    owner_uid="...",
    agent_name="Atlas",
    capabilities=["research", "translation"],
    vllm_url="http://localhost:8001/v1",
    model="Qwen/Qwen2.5-7B-Instruct-AWQ",
    discovery_url="http://your-server:8002",
    enable_safety=True,
)
asyncio.run(connector.start())
```

### Channel plugin (for existing agents)

If you already have an agent running (NanoBot, LangChain, CrewAI, etc.), add Luffa as a channel without changing your existing code:

```python
from luffa_connector import LuffaChannel

# Your existing agent's response function (async or sync)
async def my_existing_agent(message: str, sender_id: str) -> str:
    return your_agent.respond(message)   # your logic here

# Async framework (asyncio)
luffa = LuffaChannel(respond_fn=my_existing_agent)
asyncio.create_task(luffa.start())       # non-blocking
await luffa.start()                      # blocking

# Sync / threaded framework
luffa = LuffaChannel(respond_fn=my_existing_agent)
luffa.start_background()                 # runs in background thread
```

### Agent-to-Agent communication

```python
from luffa_connector import LuffaConnector, make_request

connector = LuffaConnector(...)

# After connector.start() is running:
# Find agents in discovery
# GET http://your-discovery:8002/agents?capability=research

# Send a protocol message to another agent by DID
await connector.send_to_agent(
    "did:luffa:other-agent-did",
    make_request(task="Summarize this article", data="..."),
)
```

---

## Owner commands

If `OWNER_LUFFA_UID` is set, the owner can DM the bot with slash commands:

| Command | Description |
|---------|-------------|
| `/status` | Show uptime, message count, model, pending escalations |
| `/pause` | Stop responding to non-owner messages |
| `/resume` | Resume normal operation |
| `/history <uid>` | Show last 5 messages with a user |
| `/approve <id>` | Approve a pending escalation |
| `/deny <id>` | Deny a pending escalation |

---

## Safety features

**Outbound filter** — Before any AI reply is sent, it's scanned for:
- Raw private key patterns (`0x` followed by 64 hex chars)
- Seed phrase / private key language

If detected, the reply is replaced with a safe block message.

**Escalation** — Incoming messages matching sensitive patterns (e.g. "send 50 USDT", "sign transaction") are held and the owner is notified. The owner replies `/approve <id>` or `/deny <id>`.

---

## Agent-to-Agent protocol

Messages are standard Luffa DMs containing JSON:

```json
{
  "p": "luffa-agent/1.0",
  "from": "did:luffa:0xabc123",
  "intent": "request",
  "payload": {"task": "Summarize this", "data": "..."},
  "ts": 1710000000
}
```

| Intent | Payload | Auto-handled? |
|--------|---------|---------------|
| `introduce` | `{name, capabilities, owner_did}` | Yes — responds with own intro |
| `capability_query` | `{query}` | Yes — responds with capability list |
| `capability_response` | `{capabilities}` | Yes — logged |
| `request` | `{task, data}` | Yes — processed by brain |
| `response` | `{result, status}` | Yes — logged |

Any Luffa DM containing `"luffa-agent/"` is treated as a protocol message. All other messages are natural language.

---

## Discovery service API

Start: `luffa-discovery --port 8002`

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/agents/register` | Register or update an agent |
| `GET` | `/agents` | List agents (`?capability=`, `?status=`, `?owner_did=`) |
| `GET` | `/agents/{did}` | Get specific agent |
| `POST` | `/agents/{did}/heartbeat` | Update status (`online`/`offline`/`busy`) |
| `DELETE` | `/agents/{did}` | Deregister |

Interactive docs: `http://your-server:8002/docs`

---

## Configuration reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LUFFA_ROBOT_SECRET` | Yes | — | Bot secret from robot.luffa.im |
| `LUFFA_BOT_UID` | Recommended | `""` | Bot's own Luffa UID (needed for agent-to-agent) |
| `OWNER_LUFFA_UID` | No | `""` | Owner's UID — enables slash commands |
| `VLLM_BASE_URL` | No | `http://localhost:8000/v1` | vLLM / OpenAI-compatible server |
| `VLLM_MODEL` | No | `Qwen/Qwen2.5-7B-Instruct-AWQ` | Model name |
| `AGENT_NAME` | No | `LuffaAgent` | Name shown in discovery |
| `AGENT_DID` | No | auto-generated | Stable DID for this agent |
| `DISCOVERY_URL` | No | `http://localhost:8002` | Discovery service URL |

---

## Running vLLM

```bash
pip install vllm

vllm serve /path/to/Qwen2.5-7B-Instruct-AWQ \
  --quantization awq \
  --max-model-len 8192 \
  --port 8001
```

Any OpenAI-compatible server works (Ollama, LM Studio, OpenAI API, etc.).

---

## Project structure

```
luffa-agentic-layer/
├── luffa_connector/          # Core Python package
│   ├── __init__.py           # Public exports
│   ├── connector.py          # LuffaConnector — standalone agent
│   ├── channel.py            # LuffaChannel — plugin for existing agents
│   ├── brains.py             # VLLMBrain, CustomBrain
│   ├── safety.py             # Outbound filter, EscalationManager
│   ├── owner.py              # OwnerController + slash commands
│   ├── memory.py             # Per-user conversation memory
│   ├── protocol.py           # Agent-to-agent protocol messages
│   └── cli.py                # luffa-agent / luffa-discovery CLI
├── luffa_discovery/          # Discovery service
│   ├── app.py                # FastAPI app + endpoints
│   ├── models.py             # Pydantic models
│   ├── store.py              # Async SQLite storage
│   └── run.py                # uvicorn entry point
├── examples/
│   ├── minimal_echo.py       # 5-line echo bot
│   ├── vllm_agent.py         # vLLM agent from .env
│   ├── full_agent.py         # All features enabled
│   ├── nanobot_adapter.py    # Wrap an existing NanoBot agent
│   └── two_agents_demo.py    # Two agents discovering + talking
├── step1_echo.py             # Step-by-step build scripts
├── step2_vllm_bot.py
├── step3_owner.py
├── step4_safety.py
├── .env.example
├── requirements.txt
└── pyproject.toml
```

---

## Roadmap

**Phase 1 — Done (this repo)**
- Luffa connector package
- vLLM brain support
- Owner commands + safety layer
- Discovery service
- Agent-to-agent protocol
- CLI entry points

**Phase 2 — Planned**
- Claude / OpenAI brain adapters
- Persistent conversation history (SQLite)
- Group message support in protocol
- Web dashboard for discovery service

**Phase 3 — Future**
- DID verification using Endless blockchain
- End-to-end encrypted agent-to-agent channels
- Multi-agent orchestration (agent assigns tasks to discovered agents)
- Agent reputation / trust scoring

**Phase 4 — Vision**
- Agent marketplace on Luffa
- Autonomous agent economy (agents pay each other for services)
- Cross-platform agent identity (same DID on Telegram, Discord, Luffa)
