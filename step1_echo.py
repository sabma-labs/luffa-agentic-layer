"""
Step 1: Echo bot — verifies the Luffa SDK is working.
Send a DM to your bot and it echoes it back.
"""
import asyncio
import os
from dotenv import load_dotenv
import luffa_bot

load_dotenv()

# The SDK reads LUFFA_ROBOT_SECRET from env automatically,
# but we set it explicitly so a missing var gives a clear error.
secret = os.getenv("LUFFA_ROBOT_SECRET")
if not secret:
    raise EnvironmentError("Missing LUFFA_ROBOT_SECRET in .env — get it from robot.luffa.im")

luffa_bot.robot_key = secret


async def handler(msg, env, client):
    """
    Called for every incoming message.
    env.type 0 = DM, 1 = group.
    We echo back to whichever context the message came from.
    """
    text = msg.text or ""
    print(f"[{'DM' if env.type == 0 else 'GROUP'}] from {env.uid}: {text}")

    reply = f"Echo: {text}"

    if env.type == 0:
        # DM: reply to the sender's uid
        await client.send_to_user(env.uid, reply)
    else:
        # Group: reply to the group
        await client.send_to_group(env.uid, reply)


if __name__ == "__main__":
    print("Step 1 echo bot started. Send a DM to your bot on Luffa...")
    asyncio.run(luffa_bot.run(handler, interval=1.0, concurrency=5))
