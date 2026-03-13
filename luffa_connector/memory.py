"""
In-memory conversation store.
Keeps per-user message history, capped at max_messages to avoid context bloat.
"""
from collections import defaultdict
from typing import List


class ConversationMemory:
    def __init__(self, max_messages: int = 10):
        self.max_messages = max_messages
        self._history: dict = defaultdict(list)  # uid -> [{role, content}]

    def append(self, uid: str, role: str, content: str) -> None:
        self._history[uid].append({"role": role, "content": content})
        # Trim oldest messages if over limit
        if len(self._history[uid]) > self.max_messages:
            self._history[uid] = self._history[uid][-self.max_messages:]

    def get(self, uid: str) -> List[dict]:
        return list(self._history[uid])

    def clear(self, uid: str) -> None:
        self._history.pop(uid, None)

    def all_uids(self) -> List[str]:
        return list(self._history.keys())
