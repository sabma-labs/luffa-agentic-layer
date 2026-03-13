"""
Pydantic models for the discovery service API.
"""
from __future__ import annotations
from typing import List, Literal, Optional
from pydantic import BaseModel


AgentStatus = Literal["online", "offline", "busy"]


class AgentRegistration(BaseModel):
    did: str                          # e.g. "did:endless:0xabc123"
    name: str
    owner_did: Optional[str] = None
    capabilities: List[str] = []      # e.g. ["research", "translation"]
    luffa_uid: str                    # bot's Luffa UID for messaging
    agent_type: Optional[str] = None  # e.g. "personal_assistant"
    brain_provider: Optional[str] = None  # e.g. "vllm", "anthropic"
    status: AgentStatus = "online"


class AgentRecord(AgentRegistration):
    registered_at: float   # unix timestamp
    last_seen: float       # updated on heartbeat


class HeartbeatPayload(BaseModel):
    status: AgentStatus = "online"
