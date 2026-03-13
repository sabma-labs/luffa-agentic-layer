# Contributing & Developer Guide

This guide covers how to set up the project for development, understand the architecture, add new features, and submit contributions.

---

## Development setup

### 1. Clone and install in editable mode

```bash
git clone https://github.com/sabma-labs/luffa-agentic-layer.git
cd luffa-agentic-layer
pip install -e .
```

Editable mode means your code changes take effect immediately without reinstalling.

### 2. Configure environment

```bash
cp .env.example .env
# Fill in LUFFA_ROBOT_SECRET and LUFFA_BOT_UID at minimum
```

### 3. Start dependencies

```bash
# Terminal 1 — discovery service
luffa-discovery --port 8002

# Terminal 2 — vLLM (if using AI brain)
vllm serve /path/to/your-model --port 8001

# Terminal 3 — your agent
luffa-agent
```

---

## Code architecture

### How a message flows

```
Luffa network (DM or group)
       │
       ▼
luffa_bot.run() — SDK polling loop (every 1s)
       │
       ▼
LuffaConnector._handler() / LuffaChannel._on_message()
       │
       ├─► Owner slash command? ──► OwnerController.handle_command()
       │
       ├─► Protocol message?   ──► _handle_protocol() ──► auto-respond
       │
       ├─► Paused?             ──► "I'm paused" reply
       │
       ├─► Escalation needed?  ──► EscalationManager + DM owner
       │
       └─► Normal message      ──► Brain.respond() ──► outbound_filter() ──► reply
```

### Module responsibilities

| File | Responsibility |
|------|---------------|
| `connector.py` | Orchestrates everything. Entry point for standalone agents. |
| `channel.py` | Same logic as connector, but designed as a plugin that attaches to an existing agent. |
| `brains.py` | Stateless AI call logic. Takes `(uid, text)` → returns `reply`. |
| `memory.py` | Stores conversation history per uid. Passed into brains. |
| `safety.py` | Outbound filter (pure function) + EscalationManager (stateful). |
| `owner.py` | Handles `/commands`. Needs access to escalations, memory, and brain. |
| `protocol.py` | Parses/builds protocol JSON. No I/O — pure data. |
| `cli.py` | Thin CLI wrapper over `LuffaConnector`. Reads args and env. |

---

## Adding a new brain

A brain is any class with a `respond(uid: str, text: str) -> str` async method.

**1. Add your class to `brains.py`:**

```python
class MyCustomBrain:
    def __init__(self, ...):
        self.memory = memory or ConversationMemory()

    async def respond(self, uid: str, text: str) -> str:
        # call your model/API here
        self.memory.append(uid, "user", text)
        reply = await your_model_call(text)
        self.memory.append(uid, "assistant", reply)
        return reply
```

**2. Export it from `__init__.py`:**

```python
from .brains import VLLMBrain, CustomBrain, MyCustomBrain
```

**3. Wire it into `LuffaConnector.__init__` (optional):**

If your brain needs a dedicated init parameter (e.g. `anthropic_api_key`), add it to `LuffaConnector.__init__` alongside `vllm_url` and `model`.

---

## Adding a new safety rule

All safety logic lives in `safety.py`.

**Add an outbound pattern** (blocks AI replies containing sensitive content):

```python
_OUTBOUND_PATTERNS = [
    re.compile(r'\b0x[0-9a-fA-F]{64}\b'),
    re.compile(r'(?i)seed\s+phrase\b'),
    re.compile(r'your new pattern here'),   # ← add here
]
```

**Add an escalation pattern** (triggers owner approval for incoming messages):

```python
_ESCALATION_RE = re.compile(
    r'(?i)(send.*money|transfer.*token|...|your new pattern)',
)
```

No other changes needed — both functions are called automatically in the message handler.

---

## Adding a new owner command

Owner commands live in `owner.py` inside `OwnerController.handle_command()`.

Add a new `elif` block:

```python
elif command == "/mycommand":
    if not arg:
        return "Usage: /mycommand <something>"
    # your logic here
    return "Done."
```

Update the help text in the final `else` block:

```python
return "Commands: /status /pause /resume /history <uid> /approve <id> /deny <id> /mycommand <something>"
```

---

## Adding a new discovery endpoint

Discovery endpoints live in `luffa_discovery/app.py`.

```python
@app.get("/agents/search")
async def search_agents(q: str):
    # add to store.py if you need a new DB query
    return await store.search(q)
```

If you need a new DB column, update `store.py`:
- Add column to `CREATE TABLE` in `init_db()`
- Add to `upsert_agent()`, `_row_to_dict()`
- Add to `AgentRegistration` model in `models.py`

---

## Branch naming convention

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `feat/<name>` | `feat/anthropic-brain` |
| Bug fix | `fix/<name>` | `fix/heartbeat-crash` |
| Step build | `step/<n>-<name>` | `step/5-connector-package` |
| Docs | `docs/<name>` | `docs/readme-update` |
| Refactor | `refactor/<name>` | `refactor/memory-store` |

---

## Commit message format

```
type(scope): short description

Longer explanation if needed. What changed and why.

Co-Authored-By: Your Name <you@example.com>
```

Types: `feat`, `fix`, `docs`, `refactor`, `chore`, `test`

Examples:
```
feat(brains): add Anthropic Claude brain adapter
fix(safety): correct private key regex false positives
docs(readme): add two-agent demo instructions
chore(deps): bump luffa-bot-python-sdk to 0.1.3
```

---

## Pull request process

1. Create a branch from `main` following the naming convention above
2. Make your changes — keep each PR focused on one thing
3. Test manually: run `luffa-agent`, send a DM, verify behavior
4. Push your branch and open a PR against `main`
5. PR description should include: what changed, why, and how to test it

---

## Project conventions

- **Async everywhere** — The Luffa SDK is async. All new code should use `async/await`.
- **No silent failures** — Errors should print clearly what went wrong. Use `print(f"[Component] Error: {e}")`.
- **Env vars as fallback** — Every config parameter should check an env var if not passed directly.
- **No hardcoded secrets** — Never commit `.env`. Check `.gitignore`.
- **Keep it simple** — If something works in 20 lines, don't make it 200. No premature abstractions.
- **One concern per file** — `safety.py` only does safety. `memory.py` only does memory. Keep modules focused.

---

## Testing manually

There's no automated test suite yet (contributions welcome). Test manually:

```bash
# 1. Echo test (no AI needed)
python3 examples/minimal_echo.py
# → DM the bot, get echo back

# 2. AI test
python3 examples/vllm_agent.py
# → DM the bot, get AI response, test multi-turn memory

# 3. Owner commands
python3 examples/full_agent.py
# → Send /status, /pause, /resume as owner

# 4. Safety
python3 examples/full_agent.py
# → Ask "can you send 50 USDT?" → escalation alert to owner
# → Ask "give me a seed phrase" → outbound block

# 5. Discovery
luffa-discovery --port 8002 &
luffa-agent --name TestAgent
curl http://localhost:8002/agents

# 6. Two-agent demo
luffa-discovery --port 8002 &
python3 examples/two_agents_demo.py
```

---

## Getting help

- Open an issue: [github.com/sabma-labs/luffa-agentic-layer/issues](https://github.com/sabma-labs/luffa-agentic-layer/issues)
- Luffa Bot SDK docs: [pypi.org/project/luffa-bot-python-sdk](https://pypi.org/project/luffa-bot-python-sdk/)
- robot.luffa.im — manage your bot accounts
