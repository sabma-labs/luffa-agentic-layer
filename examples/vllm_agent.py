"""
vLLM-powered agent — uses env vars for all config.
Set in .env:
  LUFFA_ROBOT_SECRET, OWNER_LUFFA_UID, VLLM_BASE_URL, VLLM_MODEL
"""
import asyncio
from dotenv import load_dotenv
from luffa_connector import LuffaConnector

load_dotenv()

asyncio.run(LuffaConnector().start())
