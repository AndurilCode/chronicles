"""Claude Code source adapter."""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from chronicles.models import Message, Transcript
from chronicles.sources.base import BaseSource

_CLAUDE_CODE_TYPES = {"human", "assistant", "summary"}

# Claude Code tool names are already canonical — no remapping needed
TOOL_NAME_MAP: dict[str, str] = {}


def _canonical_tool_name(name: str) -> str:
    return TOOL_NAME_MAP.get(name, name)


class ClaudeCodeSource(BaseSource):
    @property
    def name(self) -> str:
        return "Claude Code"

    @property
    def key(self) -> str:
        return "claude-code"

    def available(self) -> bool:
        return Path.home().joinpath(".claude", "projects").exists()

    def sniff(self, session_path: Path) -> bool:
        try:
            with session_path.open() as f:
                first_line = f.readline().strip()
            if not first_line:
                return False
            data = json.loads(first_line)
            return isinstance(data, dict) and data.get("type") in _CLAUDE_CODE_TYPES
        except Exception:
            return False

    def discover_sessions(self, since: Optional[datetime] = None) -> list[Path]:
        base = Path.home() / ".claude" / "projects"
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
        model = ""
        timestamp_start = ""
        timestamp_end = ""
        # Map tool_use_id -> tool_name for resolving tool_result tool_name
        tool_id_to_name: dict[str, str] = {}

        with session_path.open(encoding="utf-8") as f:
            for raw_line in f:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    event = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue

                # Skip sidechain events
                if event.get("isSidechain", False):
                    continue

                ts = event.get("timestamp", "")
                if ts:
                    if not timestamp_start:
                        timestamp_start = ts
                    timestamp_end = ts

                event_type = event.get("type", "")

                if event_type == "human":
                    # Capture cwd from first human event
                    if not cwd:
                        cwd = event.get("cwd", "")
                    msg_obj = event.get("message", {})
                    content_blocks = msg_obj.get("content", [])
                    text_parts = [
                        b.get("text", "")
                        for b in content_blocks
                        if b.get("type") == "text"
                    ]
                    text = "\n".join(text_parts).strip()
                    if text:
                        messages.append(Message(
                            role="user",
                            content=text,
                            timestamp=ts,
                        ))

                elif event_type == "assistant":
                    msg_obj = event.get("message", {})
                    # Capture model from first assistant event
                    if not model:
                        model = msg_obj.get("model", "")
                    content_blocks = msg_obj.get("content", [])

                    text_parts = []
                    for block in content_blocks:
                        btype = block.get("type")
                        if btype == "text":
                            text_parts.append(block.get("text", ""))
                        elif btype == "tool_use":
                            # Flush accumulated text as assistant message
                            combined_text = "\n".join(text_parts).strip()
                            if combined_text:
                                messages.append(Message(
                                    role="assistant",
                                    content=combined_text,
                                    timestamp=ts,
                                ))
                                text_parts = []
                            tool_id = block.get("id", "")
                            tool_name = _canonical_tool_name(block.get("name", ""))
                            tool_input = block.get("input", {})
                            if tool_id:
                                tool_id_to_name[tool_id] = tool_name
                            messages.append(Message(
                                role="tool_call",
                                content=json.dumps(tool_input),
                                timestamp=ts,
                                tool_name=tool_name,
                                tool_input=tool_input,
                            ))

                    # Flush any remaining text
                    combined_text = "\n".join(text_parts).strip()
                    if combined_text:
                        messages.append(Message(
                            role="assistant",
                            content=combined_text,
                            timestamp=ts,
                        ))

                elif event_type == "tool_result":
                    tool_use_id = event.get("tool_use_id", "")
                    tool_name = tool_id_to_name.get(tool_use_id, "")
                    content_blocks = event.get("content", [])
                    text_parts = [
                        b.get("text", "")
                        for b in content_blocks
                        if isinstance(b, dict) and b.get("type") == "text"
                    ]
                    # content may also be a plain string
                    if not content_blocks and isinstance(event.get("content"), str):
                        text_parts = [event["content"]]
                    text = "\n".join(text_parts).strip()
                    messages.append(Message(
                        role="tool_result",
                        content=text,
                        timestamp=ts,
                        tool_name=tool_name,
                    ))

        # Derive project from cwd (last path component)
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
            model=model,
            messages=messages,
        )
