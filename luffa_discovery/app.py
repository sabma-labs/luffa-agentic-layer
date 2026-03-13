"""
FastAPI discovery service — agents register here and find each other.
"""
from __future__ import annotations
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager

from .models import AgentRegistration, AgentRecord, HeartbeatPayload
from . import store


@asynccontextmanager
async def lifespan(app: FastAPI):
    await store.init_db()  # create DB + table on startup
    yield

app = FastAPI(title="Luffa Agent Discovery", version="0.1.0", lifespan=lifespan)


@app.post("/agents/register", response_model=AgentRecord, status_code=201)
async def register_agent(body: AgentRegistration):
    """Register a new agent or update an existing one (upsert by DID)."""
    await store.upsert_agent(body.model_dump())
    record = await store.get_agent(body.did)
    return record


@app.get("/agents", response_model=List[AgentRecord])
async def list_agents(
    capability: Optional[str] = None,
    status: Optional[str] = None,
    owner_did: Optional[str] = None,
):
    """List agents. Filter with ?capability=research&status=online&owner_did=..."""
    return await store.list_agents(capability=capability, status=status, owner_did=owner_did)


@app.get("/agents/{did}", response_model=AgentRecord)
async def get_agent(did: str):
    """Get a specific agent by DID."""
    record = await store.get_agent(did)
    if not record:
        raise HTTPException(status_code=404, detail=f"Agent '{did}' not found")
    return record


@app.post("/agents/{did}/heartbeat", response_model=AgentRecord)
async def heartbeat(did: str, body: HeartbeatPayload):
    """Update agent status (online / offline / busy)."""
    updated = await store.update_status(did, body.status)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Agent '{did}' not found")
    return await store.get_agent(did)


@app.delete("/agents/{did}", status_code=204)
async def deregister_agent(did: str):
    """Remove an agent from the registry."""
    deleted = await store.delete_agent(did)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Agent '{did}' not found")
