"""
LuffaConnector — the main class that wires everything together.
Usage:
    connector = LuffaConnector(bot_secret="...", vllm_url="...", model="...", owner_uid="...")
    await connector.start()
"""
from __future__ import annotations
import asyncio
import hashlib
import os
from typing import Callable, Awaitable, List, Optional

import httpx
import luffa_bot

from .memory import ConversationMemory
from .brains import VLLMBrain, CustomBrain
from .safety import EscalationManager, needs_escalation, outbound_filter
from .owner import OwnerController
from .protocol import (
    AgentMessage, make_introduce, make_capability_response, make_response
)

HEARTBEAT_INTERVAL = 60  # seconds between heartbeats to discovery service


class LuffaConnector:
    """
    Standalone connector that joins Luffa as an AI agent.

    Parameters
    ----------
    bot_secret      : Luffa robot secret (or set LUFFA_ROBOT_SECRET env var)
    bot_luffa_uid   : The bot's own Luffa UID — so other agents can DM it.
                      Find it: message your bot from Luffa, note the UID shown
                      in robot.luffa.im dashboard, or ask a friend to DM it
                      and check what UID the reply arrives from.
                      Set LUFFA_BOT_UID in .env.
    owner_uid       : Luffa UID of the owner (enables slash commands)
    vllm_url        : Base URL for vLLM / OpenAI-compatible server
    model           : Model name served by vLLM
    system_prompt   : System prompt for the AI brain
    brain           : Optional custom async fn(message, context) -> str
    enable_safety   : Enable outbound filter + escalation (default True)
    poll_interval   : Polling interval in seconds (default 1.0)
    discovery_url   : Discovery service URL (default http://localhost:8002)
    agent_name      : Name to register in discovery (default "LuffaAgent")
    agent_did       : DID for this agent (auto-generated from secret if not set)
    capabilities    : List of capability strings to advertise
    """

    def __init__(
        self,
        bot_secret: Optional[str] = None,
        bot_luffa_uid: Optional[str] = None,
        owner_uid: Optional[str] = None,
        vllm_url: Optional[str] = None,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        brain: Optional[Callable[[str, dict], Awaitable[str]]] = None,
        enable_safety: bool = True,
        poll_interval: float = 1.0,
        discovery_url: Optional[str] = None,
        agent_name: Optional[str] = None,
        agent_did: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
    ):
        # Secrets can come from env vars as fallback
        self.bot_secret = bot_secret or os.getenv("LUFFA_ROBOT_SECRET")
        if not self.bot_secret:
            raise EnvironmentError("bot_secret or LUFFA_ROBOT_SECRET is required")

        # The bot's own Luffa UID — needed so other agents can DM it
        self.bot_luffa_uid = bot_luffa_uid or os.getenv("LUFFA_BOT_UID", "")
        self.owner_uid = owner_uid or os.getenv("OWNER_LUFFA_UID")
        self.enable_safety = enable_safety
        self.poll_interval = poll_interval

        # Discovery registration config
        self.discovery_url = (
            discovery_url
            or os.getenv("DISCOVERY_URL", "http://localhost:8002")
        ).rstrip("/")
        self.agent_name = agent_name or os.getenv("AGENT_NAME", "LuffaAgent")
        # Auto-generate a stable DID from the bot secret hash if not provided
        self.agent_did = agent_did or os.getenv("AGENT_DID") or (
            "did:luffa:" + hashlib.sha256(self.bot_secret.encode()).hexdigest()[:16]
        )
        self.capabilities = capabilities or []

        # Memory is shared between brain and owner controller
        self._memory = ConversationMemory()

        # Brain: custom function takes priority, otherwise use vLLM
        if brain is not None:
            self._brain = CustomBrain(brain, memory=self._memory)
            _model_label = "custom"
        else:
            _vllm_url = vllm_url or os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
            _model = model or os.getenv("VLLM_MODEL", "Qwen/Qwen2.5-7B-Instruct-AWQ")
            _system_prompt = system_prompt or self._default_system_prompt()
            self._brain = VLLMBrain(
                base_url=_vllm_url,
                model=_model,
                system_prompt=_system_prompt,
                memory=self._memory,
            )
            _model_label = _model

        self._escalations = EscalationManager()
        self._owner = OwnerController(
            owner_uid=self.owner_uid or "",
            model=_model_label,
        )
        self._model_label = _model_label
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._http: Optional[httpx.AsyncClient] = None  # set in start(), used by send_to_agent

    def _default_system_prompt(self) -> str:
        owner_ref = f"Your owner's Luffa UID is {self.owner_uid}." if self.owner_uid else ""
        return (
            f"You are {self.agent_name}, an AI agent on the Luffa messaging platform. "
            "You are helpful, concise, and friendly. Keep responses short — this is chat, not an essay. "
            f"You are transparent that you are an AI agent. {owner_ref}"
        )

    async def send_to_agent(self, target_did: str, message: AgentMessage) -> None:
        """
        Look up target_did in discovery, get their luffa_uid, send a protocol DM.
        This is how one agent proactively contacts another over Luffa.
        """
        if not self._http:
            raise RuntimeError("send_to_agent() can only be called after start() is running")

        # Look up the target agent's Luffa UID from discovery
        try:
            resp = await self._http.get(f"{self.discovery_url}/agents/{target_did}")
            if resp.status_code == 404:
                print(f"[LuffaConnector] Agent '{target_did}' not found in discovery")
                return
            target = resp.json()
        except Exception as e:
            print(f"[LuffaConnector] Discovery lookup failed: {e}")
            return

        target_uid = target.get("luffa_uid", "")
        if not target_uid:
            print(f"[LuffaConnector] Agent '{target_did}' has no luffa_uid registered — cannot DM")
            return

        # Send the protocol message as a Luffa DM
        luffa_client = luffa_bot._ensure_client()
        await luffa_client.send_to_user(target_uid, message.to_json(self.agent_did))
        print(f"[LuffaConnector] Sent '{message.intent}' to {target_did} (uid={target_uid})")

    async def _handle_protocol(self, agent_msg: AgentMessage, sender_uid: str, client) -> None:
        """Handle a structured agent-to-agent protocol message."""
        intent = agent_msg.intent
        print(f"[Protocol] {intent} from {agent_msg.sender_did} (uid={sender_uid})")

        if intent == "introduce":
            reply = make_introduce(
                name=self.agent_name,
                capabilities=self.capabilities,
                owner_did=self.owner_uid,
            )
            await client.send_to_user(sender_uid, reply.to_json(self.agent_did))

        elif intent == "capability_query":
            reply = make_capability_response(self.capabilities)
            await client.send_to_user(sender_uid, reply.to_json(self.agent_did))

        elif intent == "request":
            task = agent_msg.payload.get("task", "")
            data = agent_msg.payload.get("data", "")
            full_prompt = f"{task}\n{data}".strip() if data else task
            try:
                result = await self._brain.respond(agent_msg.sender_did, full_prompt)
                result = outbound_filter(result)
                reply = make_response(result, status="success")
            except Exception as e:
                reply = make_response(str(e), status="error")
            await client.send_to_user(sender_uid, reply.to_json(self.agent_did))

        elif intent in ("capability_response", "response"):
            print(f"[Protocol] Received {intent}: {agent_msg.payload}")

        else:
            print(f"[Protocol] Unknown intent '{intent}' — ignoring")

    async def _handler(self, msg, env, client) -> None:
        text = (msg.text or "").strip()
        if not text:
            return

        sender_uid = env.uid if env.type == 0 else (msg.uid or env.uid)
        is_owner = self._owner.is_owner(sender_uid)

        # Owner slash commands — always handled
        if is_owner and text.startswith("/"):
            reply = await self._owner.handle_command(
                text, client, self._escalations, self._memory, self._brain
            )
            await client.send_to_user(env.uid, reply)
            return

        # Protocol message detection — before any other logic
        agent_msg = AgentMessage.from_text(text)
        if agent_msg:
            await self._handle_protocol(agent_msg, sender_uid, client)
            return

        # Paused — only owner can chat
        if self._owner.paused and not is_owner:
            await client.send_to_user(env.uid, "I'm currently paused. My owner will resume me soon.")
            return

        # Escalation check
        if self.enable_safety and needs_escalation(text):
            esc_id = self._escalations.add(sender_uid, env.type, text)
            await client.send_to_user(env.uid, "This looks sensitive. Let me check with my owner first.")
            if self.owner_uid:
                await client.send_to_user(
                    self.owner_uid,
                    f"⚠️ Escalation #{esc_id}: User {sender_uid} asked:\n\"{text}\"\n\nReply /approve {esc_id} or /deny {esc_id}",
                )
            return

        # Normal AI response
        self._owner.messages_handled += 1
        reply = await self._brain.respond(sender_uid, text)

        if self.enable_safety:
            reply = outbound_filter(reply)

        if env.type == 0:
            await client.send_to_user(env.uid, reply)
        else:
            await client.send_to_group(env.uid, reply)

    async def _register(self, http: httpx.AsyncClient, status: str = "online") -> None:
        """POST agent info to the discovery service."""
        payload = {
            "did": self.agent_did,
            "name": self.agent_name,
            "luffa_uid": self.bot_luffa_uid,  # real UID so others can DM this agent
            "capabilities": self.capabilities,
            "brain_provider": self._model_label,
            "status": status,
        }
        if self.owner_uid:
            payload["owner_did"] = self.owner_uid
        try:
            resp = await http.post(f"{self.discovery_url}/agents/register", json=payload)
            if resp.status_code in (200, 201):
                print(f"[LuffaConnector] Registered '{self.agent_name}' luffa_uid={self.bot_luffa_uid or '(not set)'}")
            else:
                print(f"[LuffaConnector] Discovery register failed: {resp.status_code} {resp.text}")
        except Exception as e:
            print(f"[LuffaConnector] Discovery unreachable (continuing without it): {e}")

    async def _heartbeat_loop(self, http: httpx.AsyncClient) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                await http.post(
                    f"{self.discovery_url}/agents/{self.agent_did}/heartbeat",
                    json={"status": "online"},
                )
            except Exception as e:
                print(f"[LuffaConnector] Heartbeat failed: {e}")

    async def start(self) -> None:
        """Start the polling loop. Runs forever until interrupted."""
        luffa_bot.robot_key = self.bot_secret
        print(f"[LuffaConnector] Starting '{self.agent_name}'")
        print(f"  DID        : {self.agent_did}")
        print(f"  Luffa UID  : {self.bot_luffa_uid or '(not set — other agents cannot DM you)'}")
        print(f"  Owner      : {self.owner_uid or '(none)'}")
        print(f"  Discovery  : {self.discovery_url}")
        print(f"  Safety     : {self.enable_safety}")

        async with httpx.AsyncClient(timeout=10.0) as http:
            self._http = http
            await self._register(http)
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(http))
            try:
                await luffa_bot.run(self._handler, interval=self.poll_interval, concurrency=5)
            finally:
                self._heartbeat_task.cancel()
                await self._register(http, status="offline")
                self._http = None
                print("[LuffaConnector] Marked offline in discovery.")
