"""
Agent-to-Agent protocol over Luffa DMs.

Message format:
  {"p": "luffa-agent/1.0", "from": "did:luffa:...", "intent": "introduce", "payload": {...}, "ts": 1710000000}

Detection: any message containing "luffa-agent/" is a protocol message.
Everything else is natural language.

Intents:
  introduce          payload: {name, capabilities, owner_did}
  capability_query   payload: {query: "what can you do?"}
  capability_response payload: {capabilities: [...]}
  request            payload: {task: "...", data: "..."}
  response           payload: {result: "...", status: "success"|"error"}
"""
from __future__ import annotations
import json
import time
from typing import Any, Dict, Optional


PROTOCOL_VERSION = "luffa-agent/1.0"
PROTOCOL_MARKER = "luffa-agent/"


class AgentMessage:
    def __init__(self, intent: str, payload: Dict[str, Any], sender_did: str, ts: Optional[float] = None):
        self.intent = intent
        self.payload = payload
        self.sender_did = sender_did
        self.ts = ts or time.time()

    def to_json(self, own_did: str) -> str:
        return json.dumps({
            "p": PROTOCOL_VERSION,
            "from": own_did,
            "intent": self.intent,
            "payload": self.payload,
            "ts": self.ts,
        })

    @classmethod
    def from_text(cls, text: str) -> Optional["AgentMessage"]:
        """Parse a protocol message from raw text. Returns None if not a protocol message."""
        if PROTOCOL_MARKER not in text:
            return None
        try:
            data = json.loads(text.strip())
            if not isinstance(data, dict) or PROTOCOL_MARKER not in data.get("p", ""):
                return None
            return cls(
                intent=data.get("intent", "unknown"),
                payload=data.get("payload", {}),
                sender_did=data.get("from", "unknown"),
                ts=data.get("ts"),
            )
        except (json.JSONDecodeError, Exception):
            return None

    def __repr__(self) -> str:
        return f"<AgentMessage intent={self.intent} from={self.sender_did}>"


# ── Helpers to build each intent ──────────────────────────────────────────────

def make_introduce(name: str, capabilities: list, owner_did: Optional[str] = None) -> AgentMessage:
    payload = {"name": name, "capabilities": capabilities}
    if owner_did:
        payload["owner_did"] = owner_did
    return AgentMessage("introduce", payload, sender_did="")


def make_capability_query(query: str = "what can you do?") -> AgentMessage:
    return AgentMessage("capability_query", {"query": query}, sender_did="")


def make_capability_response(capabilities: list) -> AgentMessage:
    return AgentMessage("capability_response", {"capabilities": capabilities}, sender_did="")


def make_request(task: str, data: str = "") -> AgentMessage:
    return AgentMessage("request", {"task": task, "data": data}, sender_did="")


def make_response(result: str, status: str = "success") -> AgentMessage:
    return AgentMessage("response", {"result": result, "status": status}, sender_did="")
