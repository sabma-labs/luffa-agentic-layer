"""
Step 9: Two agents talking demo.

Since we have one bot secret, Agent B is simulated in-process.
Both agents register with the discovery service, then Agent A
discovers Agent B and they exchange protocol messages directly.

Flow:
  1. Both agents register with discovery
  2. Agent A queries discovery for a "research" agent
  3. Agent A finds Agent B
  4. Agent A sends `introduce` to Agent B
  5. Agent B auto-responds with `introduce`
  6. Agent A sends a `request` to Agent B
  7. Agent B processes it through its brain and sends `response`
  8. Agent A receives and prints the result
"""
import asyncio
import os
import httpx
from dotenv import load_dotenv

from luffa_connector.brains import VLLMBrain
from luffa_connector.memory import ConversationMemory
from luffa_connector.protocol import (
    AgentMessage,
    make_introduce, make_capability_query,
    make_capability_response, make_request, make_response,
)

load_dotenv()

DISCOVERY_URL = os.getenv("DISCOVERY_URL", "http://localhost:8002")
VLLM_URL      = os.getenv("VLLM_BASE_URL", "http://localhost:8001/v1")
MODEL         = os.getenv("VLLM_MODEL", "Qwen/Qwen2.5-7B-Instruct-AWQ")

# ── Agent definitions ──────────────────────────────────────────────────────────

AGENT_A = {
    "did": "did:luffa:agent-alpha-001",
    "name": "Alpha",
    "luffa_uid": "alpha_bot_uid",
    "capabilities": ["conversation", "general"],
    "brain_provider": "vllm",
    "status": "online",
}

AGENT_B = {
    "did": "did:luffa:agent-beta-001",
    "name": "Beta",
    "luffa_uid": "beta_bot_uid",
    "capabilities": ["research", "summarization", "qa"],
    "brain_provider": "vllm",
    "status": "online",
}


# ── In-process message bus ─────────────────────────────────────────────────────

class InProcessChannel:
    """
    Simulates Luffa DMs between two in-process agents.
    Instead of going through the Luffa network, messages are queued directly.
    """
    def __init__(self):
        self._queues: dict = {}

    def get_queue(self, uid: str) -> asyncio.Queue:
        if uid not in self._queues:
            self._queues[uid] = asyncio.Queue()
        return self._queues[uid]

    async def send(self, to_uid: str, message: str) -> None:
        await self.get_queue(to_uid).put(message)

    async def receive(self, uid: str) -> str:
        return await asyncio.wait_for(self.get_queue(uid).get(), timeout=30.0)


# ── Simulated agent handler ────────────────────────────────────────────────────

class SimulatedAgent:
    """Lightweight agent that handles protocol messages using a real vLLM brain."""

    def __init__(self, info: dict, brain: VLLMBrain, channel: InProcessChannel):
        self.info = info
        self.brain = brain
        self.channel = channel

    async def handle(self, raw: str, from_uid: str) -> None:
        msg = AgentMessage.from_text(raw)
        if not msg:
            print(f"  [{self.info['name']}] Got non-protocol message: {raw[:60]}")
            return

        intent = msg.intent
        print(f"  [{self.info['name']}] Received intent='{intent}' from {msg.sender_did}")

        if intent == "introduce":
            reply = make_introduce(
                name=self.info["name"],
                capabilities=self.info["capabilities"],
            )
            await self.channel.send(from_uid, reply.to_json(self.info["did"]))

        elif intent == "capability_query":
            reply = make_capability_response(self.info["capabilities"])
            await self.channel.send(from_uid, reply.to_json(self.info["did"]))

        elif intent == "request":
            task = msg.payload.get("task", "")
            data = msg.payload.get("data", "")
            prompt = f"{task}\n{data}".strip() if data else task
            print(f"  [{self.info['name']}] Processing task via brain: '{prompt[:60]}'")
            result = await self.brain.respond(msg.sender_did, prompt)
            reply = make_response(result, status="success")
            await self.channel.send(from_uid, reply.to_json(self.info["did"]))

        elif intent in ("capability_response", "response", "introduce"):
            pass  # handled by the caller


# ── Main demo ──────────────────────────────────────────────────────────────────

async def register_agent(http: httpx.AsyncClient, agent: dict) -> None:
    resp = await http.post(f"{DISCOVERY_URL}/agents/register", json=agent)
    if resp.status_code in (200, 201):
        print(f"  Registered '{agent['name']}' ({agent['did']})")
    else:
        print(f"  Failed to register '{agent['name']}': {resp.status_code} {resp.text}")


async def main():
    print("=" * 60)
    print("Two-Agent Demo — Luffa Agent Protocol")
    print("=" * 60)

    brain_a = VLLMBrain(
        base_url=VLLM_URL, model=MODEL,
        system_prompt="You are Alpha, a helpful AI agent on Luffa.",
        memory=ConversationMemory(),
    )
    brain_b = VLLMBrain(
        base_url=VLLM_URL, model=MODEL,
        system_prompt="You are Beta, a research-focused AI agent on Luffa. Answer clearly and concisely.",
        memory=ConversationMemory(),
    )

    channel = InProcessChannel()
    agent_b = SimulatedAgent(AGENT_B, brain_b, channel)

    # ── Step 1: Register both agents with discovery ────────────────────────────
    print("\n[Step 1] Registering agents with discovery...")
    async with httpx.AsyncClient(timeout=10.0) as http:

        await register_agent(http, AGENT_A)
        await register_agent(http, AGENT_B)

        # ── Step 2: Agent A queries discovery for a "research" agent ──────────
        print("\n[Step 2] Agent A queries discovery for capability='research'...")
        resp = await http.get(f"{DISCOVERY_URL}/agents", params={"capability": "research"})
        agents = resp.json()
        print(f"  Found {len(agents)} agent(s) with 'research' capability:")
        for a in agents:
            print(f"    - {a['name']} ({a['did']}) status={a['status']}")

        # Find Agent B
        found = next((a for a in agents if a["did"] == AGENT_B["did"]), None)
        if not found:
            print("  Agent B not found — is the discovery service running?")
            return

        b_uid = found["luffa_uid"]
        a_uid = AGENT_A["luffa_uid"]

        # ── Step 3: Agent A introduces itself to Agent B ───────────────────────
        print(f"\n[Step 3] Agent A sends 'introduce' to Agent B...")
        intro_msg = make_introduce(
            name=AGENT_A["name"],
            capabilities=AGENT_A["capabilities"],
        )
        raw = intro_msg.to_json(AGENT_A["did"])
        print(f"  Sending: {raw}")

        # Agent B handles it (simulated in-process)
        await agent_b.handle(raw, from_uid=a_uid)

        # Agent A reads B's response
        b_reply_raw = await channel.receive(a_uid)
        b_reply = AgentMessage.from_text(b_reply_raw)
        print(f"  Agent A received from B: intent='{b_reply.intent}' payload={b_reply.payload}")

        # ── Step 4: Agent A sends a request to Agent B ────────────────────────
        task = "Summarize what a DID (Decentralized Identifier) is in 2 sentences."
        print(f"\n[Step 4] Agent A sends 'request' to Agent B...")
        print(f"  Task: {task}")
        req_msg = make_request(task=task)
        await agent_b.handle(req_msg.to_json(AGENT_A["did"]), from_uid=a_uid)

        # Agent A reads the response
        response_raw = await channel.receive(a_uid)
        response = AgentMessage.from_text(response_raw)
        print(f"\n[Step 5] Agent A received response from Agent B:")
        print(f"  Status : {response.payload.get('status')}")
        print(f"  Result : {response.payload.get('result')}")

        # ── Mark both offline ──────────────────────────────────────────────────
        print("\n[Cleanup] Marking agents offline...")
        for agent in [AGENT_A, AGENT_B]:
            await http.post(
                f"{DISCOVERY_URL}/agents/{agent['did']}/heartbeat",
                json={"status": "offline"},
            )
            print(f"  {agent['name']} -> offline")

    print("\n" + "=" * 60)
    print("Demo complete.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
