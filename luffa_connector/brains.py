"""
Brain implementations — the AI layer that generates responses.

VLLMBrain   : OpenAI-compatible endpoint (vLLM, Ollama, LM Studio, etc.)
CustomBrain : Bring-your-own async function
"""
from __future__ import annotations
from typing import Callable, Awaitable, List
from openai import AsyncOpenAI

from .memory import ConversationMemory


class VLLMBrain:
    """
    Talks to any OpenAI-compatible server (vLLM, Ollama, etc.).
    Uses ConversationMemory to maintain per-user chat history.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        system_prompt: str,
        api_key: str = "not-needed",
        max_tokens: int = 512,
        temperature: float = 0.7,
        memory: ConversationMemory | None = None,
    ):
        self.model = model
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.memory = memory or ConversationMemory()
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)

    async def respond(self, uid: str, text: str) -> str:
        self.memory.append(uid, "user", text)

        messages: List[dict] = (
            [{"role": "system", "content": self.system_prompt}]
            + self.memory.get(uid)
        )

        resp = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

        reply = resp.choices[0].message.content.strip()
        self.memory.append(uid, "assistant", reply)
        return reply


class CustomBrain:
    """
    Wraps a plain async function as a brain.
    The function receives (message: str, context: dict) and returns a str.
    context contains: uid, history (list of {role, content})
    """

    def __init__(
        self,
        fn: Callable[[str, dict], Awaitable[str]],
        memory: ConversationMemory | None = None,
    ):
        self._fn = fn
        self.memory = memory or ConversationMemory()

    async def respond(self, uid: str, text: str) -> str:
        self.memory.append(uid, "user", text)
        context = {"uid": uid, "history": self.memory.get(uid)}
        reply = await self._fn(text, context)
        self.memory.append(uid, "assistant", reply)
        return reply
