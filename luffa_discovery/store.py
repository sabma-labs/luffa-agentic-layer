"""
Async SQLite storage for agent records.
DB file is created automatically on first run.
"""
from __future__ import annotations
import json
import time
from typing import List, Optional
import aiosqlite

DB_PATH = "agents.db"


async def init_db(db_path: str = DB_PATH) -> None:
    """Create the agents table if it doesn't exist."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                did             TEXT PRIMARY KEY,
                name            TEXT NOT NULL,
                owner_did       TEXT,
                capabilities    TEXT NOT NULL DEFAULT '[]',
                luffa_uid       TEXT NOT NULL,
                agent_type      TEXT,
                brain_provider  TEXT,
                status          TEXT NOT NULL DEFAULT 'online',
                registered_at   REAL NOT NULL,
                last_seen       REAL NOT NULL
            )
        """)
        await db.commit()


async def upsert_agent(reg: dict, db_path: str = DB_PATH) -> None:
    """Insert or update an agent record."""
    now = time.time()
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            INSERT INTO agents
                (did, name, owner_did, capabilities, luffa_uid, agent_type,
                 brain_provider, status, registered_at, last_seen)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(did) DO UPDATE SET
                name=excluded.name,
                owner_did=excluded.owner_did,
                capabilities=excluded.capabilities,
                luffa_uid=excluded.luffa_uid,
                agent_type=excluded.agent_type,
                brain_provider=excluded.brain_provider,
                status=excluded.status,
                last_seen=excluded.last_seen
        """, (
            reg["did"],
            reg["name"],
            reg.get("owner_did"),
            json.dumps(reg.get("capabilities", [])),
            reg["luffa_uid"],
            reg.get("agent_type"),
            reg.get("brain_provider"),
            reg.get("status", "online"),
            now,   # registered_at — ignored on conflict (kept original)
            now,   # last_seen — always updated
        ))
        await db.commit()


async def get_agent(did: str, db_path: str = DB_PATH) -> Optional[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM agents WHERE did=?", (did,)) as cur:
            row = await cur.fetchone()
            return _row_to_dict(row) if row else None


async def list_agents(
    capability: Optional[str] = None,
    status: Optional[str] = None,
    owner_did: Optional[str] = None,
    db_path: str = DB_PATH,
) -> List[dict]:
    clauses = []
    params = []

    if status:
        clauses.append("status = ?")
        params.append(status)
    if owner_did:
        clauses.append("owner_did = ?")
        params.append(owner_did)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    query = f"SELECT * FROM agents {where} ORDER BY last_seen DESC"

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cur:
            rows = await cur.fetchall()

    agents = [_row_to_dict(r) for r in rows]

    # capability filter — JSON array stored as text, filter in Python
    if capability:
        agents = [a for a in agents if capability in a["capabilities"]]

    return agents


async def update_status(did: str, status: str, db_path: str = DB_PATH) -> bool:
    """Update agent status and last_seen. Returns False if agent not found."""
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "UPDATE agents SET status=?, last_seen=? WHERE did=?",
            (status, time.time(), did),
        )
        await db.commit()
        return cur.rowcount > 0


async def delete_agent(did: str, db_path: str = DB_PATH) -> bool:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("DELETE FROM agents WHERE did=?", (did,))
        await db.commit()
        return cur.rowcount > 0


def _row_to_dict(row) -> dict:
    d = dict(row)
    # Deserialize capabilities from JSON string back to list
    d["capabilities"] = json.loads(d.get("capabilities", "[]"))
    return d
