"""
Minimal echo bot — 5 lines of logic.
No AI, no safety, just proves the connector plumbing works.
"""
import asyncio, os
from dotenv import load_dotenv
from luffa_connector import LuffaConnector

load_dotenv()

async def echo(message: str, context: dict) -> str:
    return f"Echo: {message}"

asyncio.run(LuffaConnector(brain=echo).start())
