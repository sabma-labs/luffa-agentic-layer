"""
Owner control layer — slash commands available to the bot owner.
OwnerController is stateful: holds paused flag, uptime, message count.
"""
from __future__ import annotations
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .safety import EscalationManager
    from .memory import ConversationMemory


class OwnerController:
    def __init__(self, owner_uid: str, model: str):
        self.owner_uid = owner_uid
        self.model = model
        self.paused: bool = False
        self._start_time: float = time.time()
        self.messages_handled: int = 0

    def is_owner(self, uid: str) -> bool:
        return uid == self.owner_uid

    async def handle_command(
        self,
        cmd: str,
        client,
        escalations: "EscalationManager",
        memory: "ConversationMemory",
        brain,
    ) -> str:
        parts = cmd.strip().split(maxsplit=1)
        command = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if command == "/status":
            uptime = int(time.time() - self._start_time)
            h, rem = divmod(uptime, 3600)
            m, s = divmod(rem, 60)
            return (
                f"Status:\n"
                f"  Uptime  : {h}h {m}m {s}s\n"
                f"  Handled : {self.messages_handled} messages\n"
                f"  Model   : {self.model}\n"
                f"  Paused  : {self.paused}\n"
                f"  Pending : {escalations.count()} escalation(s)"
            )

        elif command == "/pause":
            self.paused = True
            return "Paused."

        elif command == "/resume":
            self.paused = False
            return "Resumed."

        elif command == "/history":
            if not arg:
                return "Usage: /history <uid>"
            msgs = memory.get(arg)
            if not msgs:
                return f"No history for {arg}"
            recent = msgs[-5:]
            lines = [f"Last {len(recent)} messages with {arg}:"]
            for m in recent:
                role = "You" if m["role"] == "user" else "Bot"
                preview = m["content"][:80] + ("..." if len(m["content"]) > 80 else "")
                lines.append(f"  [{role}] {preview}")
            return "\n".join(lines)

        elif command == "/approve":
            if not arg:
                return "Usage: /approve <id>"
            esc = escalations.pop(arg)
            if not esc:
                return f"No pending escalation '{arg}'."
            # Process the held message through the brain now
            from .safety import outbound_filter
            reply = await brain.respond(esc["uid"], esc["text"])
            reply = outbound_filter(reply)
            if esc["env_type"] == 0:
                await client.send_to_user(esc["uid"], reply)
            else:
                await client.send_to_group(esc["uid"], reply)
            return f"Approved. Sent response to {esc['uid']}."

        elif command == "/deny":
            if not arg:
                return "Usage: /deny <id>"
            esc = escalations.pop(arg)
            if not esc:
                return f"No pending escalation '{arg}'."
            await client.send_to_user(esc["uid"], "My owner declined this request.")
            return f"Denied. Notified {esc['uid']}."

        else:
            return "Commands: /status /pause /resume /history <uid> /approve <id> /deny <id>"
