"""
Safety layer — two protections:
  1. outbound_filter : scans AI replies before they're sent
  2. EscalationManager : holds suspicious requests until owner approves/denies
"""
from __future__ import annotations
import re
from typing import Dict, Optional


# ── Outbound filter ────────────────────────────────────────────────────────────

_OUTBOUND_PATTERNS = [
    re.compile(r'\b0x[0-9a-fA-F]{64}\b'),   # raw private key hex
    re.compile(r'(?i)seed\s+phrase\b'),       # "seed phrase"
    re.compile(r'(?i)private\s+key\b'),       # "private key"
]

BLOCKED_MESSAGE = "I caught myself about to share sensitive information. Blocked for safety."


def outbound_filter(text: str) -> str:
    """Return safe text, or a block message if sensitive data was detected."""
    for pattern in _OUTBOUND_PATTERNS:
        if pattern.search(text):
            return BLOCKED_MESSAGE
    return text


# ── Escalation patterns (inbound) ─────────────────────────────────────────────

_ESCALATION_RE = re.compile(
    r'(?i)(send.*money|transfer.*token|sign.*transaction|'
    r'share.*private|share.*secret|send.*crypto|send.*coin|'
    r'send.*usdt|send.*eth|send.*btc|wire.*transfer)',
)


def needs_escalation(text: str) -> bool:
    """Return True if the incoming message matches a sensitive pattern."""
    return bool(_ESCALATION_RE.search(text))


# ── Escalation manager ─────────────────────────────────────────────────────────

class EscalationManager:
    """
    Stores pending escalations and resolves them when the owner approves/denies.
    Each escalation gets a numeric id (str) used in /approve <id> and /deny <id>.
    """

    def __init__(self):
        self._counter: int = 0
        self._pending: Dict[str, dict] = {}  # id -> {uid, env_type, text}

    def add(self, uid: str, env_type: int, text: str) -> str:
        """Store a pending escalation and return its id."""
        self._counter += 1
        esc_id = str(self._counter)
        self._pending[esc_id] = {"uid": uid, "env_type": env_type, "text": text}
        return esc_id

    def pop(self, esc_id: str) -> Optional[dict]:
        """Remove and return the escalation, or None if not found."""
        return self._pending.pop(esc_id, None)

    def count(self) -> int:
        return len(self._pending)
