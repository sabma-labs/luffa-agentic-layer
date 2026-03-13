"""
NanoBot → Luffa adapter.

If you have an existing agent (NanoBot, LangChain, CrewAI, etc.) that already
has a function that takes a message and returns a reply, wrap it in 3 lines:

    from luffa_connector import LuffaConnector

    async def my_existing_agent(message: str, context: dict) -> str:
        return your_agent.respond(message)   # your existing logic here

    asyncio.run(LuffaConnector(brain=my_existing_agent).start())

This example shows a NanoBot-style agent connecting to Luffa.
"""
import asyncio
import os
from dotenv import load_dotenv
from luffa_connector import LuffaConnector

load_dotenv()

# ── Replace this with your actual agent logic ──────────────────────────────────

class NanoBotStub:
    """Stub that represents your existing NanoBot or any other agent."""
    def __init__(self):
        self.name = "NanoBot"

    def respond(self, message: str) -> str:
        # Your actual NanoBot/agent logic goes here.
        # Could call LangChain, CrewAI, your own model, etc.
        return f"[{self.name}] You said: '{message}'. I'm your NanoBot on Luffa!"

nanobot = NanoBotStub()

# ── Adapter: wrap NanoBot as a brain function ──────────────────────────────────

async def nanobot_brain(message: str, context: dict) -> str:
    """
    Bridge between LuffaConnector and NanoBot.
    context = {"uid": sender_uid, "history": [...]}
    """
    return nanobot.respond(message)

# ── Connect to Luffa ───────────────────────────────────────────────────────────

connector = LuffaConnector(
    brain=nanobot_brain,
    agent_name=os.getenv("AGENT_NAME", "NanoBot"),
    capabilities=["conversation", "general"],
    # All secrets come from .env
)

if __name__ == "__main__":
    print("NanoBot is now on Luffa. DM the bot to talk to it.")
    asyncio.run(connector.start())
