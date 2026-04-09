"""Copilot CLI source adapter."""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from chronicles.models import Message, Transcript
from chronicles.sources.base import BaseSource

_COPILOT_CLI_TYPES = {"session.start", "turn.start", "turn.end"}

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


class CopilotCLISource(BaseSource):
    @property
    def name(self) -> str:
        return "GitHub Copilot CLI"

    @property
    def key(self) -> str:
        return "copilot-cli"

    def available(self) -> bool:
        return Path.home().joinpath(".copilot", "session-state").exists()

    def sniff(self, session_path: Path) -> bool:
        try:
            with session_path.open() as f:
                first_line = f.readline().strip()
            if not first_line:
                return False
            data = json.loads(first_line)
            return isinstance(data, dict) and data.get("type") in _COPILOT_CLI_TYPES
        except Exception:
            return False

    def discover_sessions(self, since: Optional[datetime] = None) -> list[Path]:
        base = Path.home() / ".copilot" / "session-state"
        if not base.exists():
            return []
        paths = sorted(base.rglob("*.jsonl"))
        if since is not None:
            paths = [
                p for p in paths
                if datetime.fromtimestamp(p.stat().st_mtime) >= since
            ]
        return paths

    def parse_session(self, session_path: Path) -> Transcript:
        messages: list[Message] = []
        cwd = ""
        timestamp_start = ""
        timestamp_end = ""

        with session_path.open(encoding="utf-8") as f:
            for raw_line in f:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    event = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue

                ts = event.get("timestamp", "")
                if ts:
                    if not timestamp_start:
                        timestamp_start = ts
                    timestamp_end = ts

                event_type = event.get("type", "")

                if event_type == "session.start":
                    cwd = event.get("cwd", "")

                elif event_type == "turn.start":
                    request = event.get("request", {})
                    if request.get("type") == "user-text":
                        text = request.get("message", "").strip()
                        if text:
                            messages.append(Message(
                                role="user",
                                content=text,
                                timestamp=ts,
                            ))

                elif event_type == "message":
                    if event.get("role") == "assistant":
                        content = event.get("content", "").strip()
                        if content:
                            messages.append(Message(
                                role="assistant",
                                content=content,
                                timestamp=ts,
                            ))

                elif event_type == "tool.call":
                    tool = event.get("tool", {})
                    raw_name = tool.get("name", "")
                    canonical_name = _canonical_tool_name(raw_name)
                    parameters = tool.get("parameters", {})
                    messages.append(Message(
                        role="tool_call",
                        content=json.dumps(parameters),
                        timestamp=ts,
                        tool_name=canonical_name,
                        tool_input=parameters,
                    ))

                elif event_type == "tool.result":
                    tool = event.get("tool", {})
                    raw_name = tool.get("name", "")
                    canonical_name = _canonical_tool_name(raw_name)
                    result = event.get("result", "")
                    if not isinstance(result, str):
                        result = json.dumps(result)
                    messages.append(Message(
                        role="tool_result",
                        content=result,
                        timestamp=ts,
                        tool_name=canonical_name,
                    ))

        project = Path(cwd).name if cwd else ""

        return Transcript(
            session_id=session_path.stem,
            source=self.key,
            project=project,
            repository="",
            branch="",
            cwd=cwd,
            timestamp_start=timestamp_start,
            timestamp_end=timestamp_end,
            model="",
            messages=messages,
        )
