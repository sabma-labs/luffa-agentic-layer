"""
Full agent — all features enabled: vLLM brain, owner commands, safety layer.
All config via .env — no hardcoded secrets.
"""
import asyncio
import os
from dotenv import load_dotenv
from luffa_connector import LuffaConnector

load_dotenv()

connector = LuffaConnector(
    bot_secret=os.getenv("LUFFA_ROBOT_SECRET"),
    owner_uid=os.getenv("OWNER_LUFFA_UID"),
    vllm_url=os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1"),
    model=os.getenv("VLLM_MODEL", "Qwen/Qwen2.5-7B-Instruct-AWQ"),
    enable_safety=True,
)

asyncio.run(connector.start())
