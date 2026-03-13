"""
LuffaChannel — a drop-in channel plugin for any existing agent framework.

Unlike LuffaConnector (which IS the agent), LuffaChannel is a component
you add to an agent that already exists. It plugs Luffa in as a messaging
channel alongside Telegram, Discord, Slack, etc.

Usage in any agent framework:
─────────────────────────────
    from luffa_connector import LuffaChannel

    # Your existing agent already has a respond function:
    async def my_agent_respond(message: str, sender_id: str) -> str:
        return agent.process(message)

    # Add Luffa as a channel — 3 lines:
    luffa = LuffaChannel(respond_fn=my_agent_respond)
    await luffa.start()          # async frameworks
    luffa.start_background()     # sync / threaded frameworks

Config (all from .env or passed directly):
    LUFFA_ROBOT_SECRET   — bot secret from robot.luffa.im
    LUFFA_BOT_UID        — your bot's Luffa UID
    AGENT_NAME           — name shown in discovery
    DISCOVERY_URL        — shared discovery server
"""
from __future__ import annotations
import asyncio
import hashlib
import os
import threading
from typing import Callable, Awaitable, List, Optional

import httpx
import luffa_bot

from .protocol import AgentMessage, make_introduce, make_capability_response, make_response
from .safety import needs_escalation, outbound_filter, EscalationManager

HEARTBEAT_INTERVAL = 60

# The respond function signature your agent must provide.
# Takes (message, sender_id) — returns reply string.
RespondFn = Callable[[str, str], Awaitable[str]]


class LuffaChannel:
    """
    A Luffa channel that can be bolted onto any existing agent.

    Parameters
    ----------
    respond_fn      : async fn(message: str, sender_id: str) -> str
                      Your agent's existing response function.
                      If your function is sync, wrap it:
                        async def fn(m, s): return your_sync_fn(m)
    name            : Agent name shown in discovery (env: AGENT_NAME)
    bot_secret      : Luffa robot secret (env: LUFFA_ROBOT_SECRET)
    bot_luffa_uid   : Your bot's Luffa UID (env: LUFFA_BOT_UID)
    agent_did       : Stable DID, auto-generated if not set (env: AGENT_DID)
    capabilities    : Capabilities to advertise in discovery
    discovery_url   : Shared discovery server URL (env: DISCOVERY_URL)
    owner_uid       : Owner's Luffa UID for /commands (env: OWNER_LUFFA_UID)
    enable_safety   : Filter outbound messages for sensitive data (default True)
    poll_interval   : Luffa polling interval in seconds (default 1.0)
    """

    def __init__(
        self,
        respond_fn: RespondFn,
        name: Optional[str] = None,
        bot_secret: Optional[str] = None,
        bot_luffa_uid: Optional[str] = None,
        agent_did: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        discovery_url: Optional[str] = None,
        owner_uid: Optional[str] = None,
        enable_safety: bool = True,
        poll_interval: float = 1.0,
    ):
        self._respond_fn = respond_fn
        self.name = name or os.getenv("AGENT_NAME", "LuffaAgent")
        self.bot_secret = bot_secret or os.getenv("LUFFA_ROBOT_SECRET")
        if not self.bot_secret:
            raise EnvironmentError("LUFFA_ROBOT_SECRET is required (set in .env or pass bot_secret=)")

        self.bot_luffa_uid = bot_luffa_uid or os.getenv("LUFFA_BOT_UID", "")
        self.owner_uid = owner_uid or os.getenv("OWNER_LUFFA_UID", "")
        self.enable_safety = enable_safety
        self.poll_interval = poll_interval
        self.discovery_url = (discovery_url or os.getenv("DISCOVERY_URL", "http://localhost:8002")).rstrip("/")
        self.capabilities = capabilities or []
        self.agent_did = (
            agent_did
            or os.getenv("AGENT_DID")
            or "did:luffa:" + hashlib.sha256(self.bot_secret.encode()).hexdigest()[:16]
        )
        self._escalations = EscalationManager()
        self._http: Optional[httpx.AsyncClient] = None

    # ── Internal: message handler ──────────────────────────────────────────────

    async def _on_message(self, msg, env, client) -> None:
        text = (msg.text or "").strip()
        if not text:
            return

        sender_uid = env.uid if env.type == 0 else (msg.uid or env.uid)

        # Protocol messages are handled automatically — no agent involvement needed
        agent_msg = AgentMessage.from_text(text)
        if agent_msg:
            await self._handle_protocol(agent_msg, sender_uid, client)
            return

        # Safety: escalate suspicious requests to owner
        if self.enable_safety and needs_escalation(text):
            esc_id = self._escalations.add(sender_uid, env.type, text)
            await client.send_to_user(sender_uid, "This looks sensitive. Let me check with my owner first.")
            if self.owner_uid:
                await client.send_to_user(
                    self.owner_uid,
                    f"⚠️ Escalation #{esc_id}: {sender_uid} asked: \"{text}\"\nReply /approve {esc_id} or /deny {esc_id}",
                )
            return

        # Pass message to the agent's brain
        try:
            reply = await self._respond_fn(text, sender_uid)
        except Exception as e:
            reply = f"Sorry, I encountered an error: {e}"

        if self.enable_safety:
            reply = outbound_filter(reply)

        if env.type == 0:
            await client.send_to_user(env.uid, reply)
        else:
            await client.send_to_group(env.uid, reply)

    async def _handle_protocol(self, agent_msg: AgentMessage, sender_uid: str, client) -> None:
        intent = agent_msg.intent
        print(f"[LuffaChannel:{self.name}] Protocol '{intent}' from {agent_msg.sender_did}")

        if intent == "introduce":
            reply = make_introduce(self.name, self.capabilities)
            await client.send_to_user(sender_uid, reply.to_json(self.agent_did))

        elif intent == "capability_query":
            reply = make_capability_response(self.capabilities)
            await client.send_to_user(sender_uid, reply.to_json(self.agent_did))

        elif intent == "request":
            task = agent_msg.payload.get("task", "")
            data = agent_msg.payload.get("data", "")
            prompt = f"{task}\n{data}".strip() if data else task
            try:
                result = await self._respond_fn(prompt, agent_msg.sender_did)
                result = outbound_filter(result) if self.enable_safety else result
                reply = make_response(result, "success")
            except Exception as e:
                reply = make_response(str(e), "error")
            await client.send_to_user(sender_uid, reply.to_json(self.agent_did))

        elif intent in ("capability_response", "response"):
            print(f"[LuffaChannel:{self.name}] Received {intent}: {agent_msg.payload}")

    # ── Internal: discovery registration ──────────────────────────────────────

    async def _register(self, http: httpx.AsyncClient, status: str = "online") -> None:
        payload = {
            "did": self.agent_did,
            "name": self.name,
            "luffa_uid": self.bot_luffa_uid,
            "capabilities": self.capabilities,
            "status": status,
        }
        if self.owner_uid:
            payload["owner_did"] = self.owner_uid
        try:
            resp = await http.post(f"{self.discovery_url}/agents/register", json=payload)
            if resp.status_code in (200, 201):
                print(f"[LuffaChannel:{self.name}] Registered in discovery ✓")
            else:
                print(f"[LuffaChannel:{self.name}] Discovery registration failed: {resp.status_code}")
        except Exception as e:
            print(f"[LuffaChannel:{self.name}] Discovery unreachable (continuing): {e}")

    async def _heartbeat_loop(self, http: httpx.AsyncClient) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                await http.post(
                    f"{self.discovery_url}/agents/{self.agent_did}/heartbeat",
                    json={"status": "online"},
                )
            except Exception:
                pass

    # ── Public: start the channel ──────────────────────────────────────────────

    async def start(self) -> None:
        """
        Start the Luffa channel. Awaitable — use with asyncio.

        In an async agent framework:
            await luffa_channel.start()            # blocking
            asyncio.create_task(luffa_channel.start())  # non-blocking background task
        """
        luffa_bot.robot_key = self.bot_secret
        print(f"[LuffaChannel:{self.name}] Starting on Luffa")
        print(f"  DID       : {self.agent_did}")
        print(f"  Bot UID   : {self.bot_luffa_uid or '(not set)'}")
        print(f"  Discovery : {self.discovery_url}")

        async with httpx.AsyncClient(timeout=10.0) as http:
            self._http = http
            await self._register(http)
            heartbeat = asyncio.create_task(self._heartbeat_loop(http))
            try:
                await luffa_bot.run(self._on_message, interval=self.poll_interval, concurrency=5)
            finally:
                heartbeat.cancel()
                await self._register(http, status="offline")
                self._http = None
                print(f"[LuffaChannel:{self.name}] Offline.")

    def start_background(self) -> threading.Thread:
        """
        Start the Luffa channel in a background thread.

        For sync / non-asyncio agent frameworks:
            luffa_channel.start_background()
            # your existing sync agent loop continues here
        """
        thread = threading.Thread(
            target=lambda: asyncio.run(self.start()),
            name=f"luffa-{self.name}",
            daemon=True,  # thread dies when main process exits
        )
        thread.start()
        print(f"[LuffaChannel:{self.name}] Running in background thread.")
        return thread
