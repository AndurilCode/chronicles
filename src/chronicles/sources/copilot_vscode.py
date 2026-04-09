"""Copilot VS Code source adapter."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from chronicles.models import Message, Transcript
from chronicles.sources.base import BaseSource

TOOL_NAME_MAP: dict[str, str] = {
    "readFile": "Read",
    "editFile": "Edit",
    "runCommand": "Bash",
    "listFiles": "Glob",
    "searchFiles": "Grep",
    "writeFile": "Write",
}


def _canonical_tool_name(name: str) -> str:
    return TOOL_NAME_MAP.get(name, name)


def _ms_to_iso(ms: int) -> str:
    """Convert epoch milliseconds to ISO 8601 string."""
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat()


class CopilotVSCodeSource(BaseSource):
    @property
    def name(self) -> str:
        return "GitHub Copilot VS Code"

    @property
    def key(self) -> str:
        return "copilot-vscode"

    def available(self) -> bool:
        return Path.home().joinpath(".vscode", "extensions").exists()

    def sniff(self, session_path: Path) -> bool:
        try:
            with session_path.open() as f:
                data = json.load(f)
            return isinstance(data, dict) and isinstance(data.get("sessions"), list)
        except Exception:
            return False

    def discover_sessions(self, since: Optional[datetime] = None) -> list[Path]:
        base = Path.home() / ".vscode" / "copilot-sessions"
        if not base.exists():
            return []
        paths = sorted(base.rglob("*.json"))
        if since is not None:
            paths = [
                p for p in paths
                if datetime.fromtimestamp(p.stat().st_mtime) >= since
            ]
        return paths

    def parse_session(self, session_path: Path) -> Transcript:
        with session_path.open(encoding="utf-8") as f:
            data = json.load(f)

        sessions = data.get("sessions", [])
        # Use first session if available
        session = sessions[0] if sessions else {}

        session_id = session.get("sessionId", session_path.stem)
        messages: list[Message] = []
        timestamp_start = ""
        timestamp_end = ""

        for request in session.get("requests", []):
            # Extract timestamp
            ts_ms = request.get("timestamp")
            ts = _ms_to_iso(ts_ms) if ts_ms is not None else ""
            if ts:
                if not timestamp_start:
                    timestamp_start = ts
                timestamp_end = ts

            # User message
            message_obj = request.get("message", {})
            user_text = message_obj.get("text", "").strip()
            if user_text:
                messages.append(Message(
                    role="user",
                    content=user_text,
                    timestamp=ts,
                ))

            result = request.get("result", {})

            # Tool calls from metadata.toolCallRounds
            metadata = result.get("metadata", {})
            for round_ in metadata.get("toolCallRounds", []):
                for tool_call in round_.get("toolCalls", []):
                    raw_name = tool_call.get("name", "")
                    canonical_name = _canonical_tool_name(raw_name)
                    tool_input = tool_call.get("input", {})
                    messages.append(Message(
                        role="tool_call",
                        content=json.dumps(tool_input),
                        timestamp=ts,
                        tool_name=canonical_name,
                        tool_input=tool_input,
                    ))

            # Assistant text from result.value
            assistant_text = result.get("value", "").strip()
            if assistant_text:
                messages.append(Message(
                    role="assistant",
                    content=assistant_text,
                    timestamp=ts,
                ))

        return Transcript(
            session_id=session_id,
            source=self.key,
            project="",
            repository="",
            branch="",
            cwd="",
            timestamp_start=timestamp_start,
            timestamp_end=timestamp_end,
            model="",
            messages=messages,
        )
