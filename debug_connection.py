"""
Debug script — does a single receive() call and prints the raw result.
Run this to verify your secret is correct and the API is reachable.
"""
import asyncio
import os
from dotenv import load_dotenv
import luffa_bot
from luffa_bot.client import AsyncLuffaClient

load_dotenv()

secret = os.getenv("LUFFA_ROBOT_SECRET")
if not secret:
    raise EnvironmentError("Missing LUFFA_ROBOT_SECRET in .env")

print(f"Using secret: {secret[:6]}...{secret[-4:]} (first 6 / last 4 chars)")
print(f"Hitting: https://apibot.luffa.im/robot/receive")

async def main():
    import httpx
    # Raw HTTP call so we can see the actual response
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://apibot.luffa.im/robot/receive",
            json={"secret": secret},
            headers={"Content-Type": "application/json"},
        )
        print(f"\nStatus: {resp.status_code}")
        print(f"Response body: {resp.text}")

asyncio.run(main())
