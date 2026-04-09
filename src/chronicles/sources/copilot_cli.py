"""Copilot CLI source adapter."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from chronicles.models import Message, Transcript
from chronicles.sources.base import BaseSource

# Real Copilot CLI event types (from events.jsonl)
_COPILOT_CLI_TYPES = {
    "session.start", "user.message", "assistant.message",
    "assistant.turn_start", "assistant.turn_end",
    "tool.execution_start", "tool.execution_complete",
    "session.shutdown",
    # Legacy/fixture types
    "turn.start", "turn.end",
}

TOOL_NAME_MAP: dict[str, str] = {
    # Camel case (legacy/fixture)
    "readFile": "Read",
    "editFile": "Edit",
    "runCommand": "Bash",
    "listFiles": "Glob",
    "searchFiles": "Grep",
    "writeFile": "Write",
    # Snake case
    "read_file": "Read",
    "edit_file": "Edit",
    "run_command": "Bash",
    "list_files": "Glob",
    "search_files": "Grep",
    "write_file": "Write",
    # Lowercase (real Copilot CLI)
    "bash": "Bash",
    "read_bash": "Bash",
    "stop_bash": "Bash",
    "view": "Read",
    "edit": "Edit",
    "grep": "Grep",
    "create": "Write",
    # Internal — skip
    "report_intent": "_skip",
    "task_complete": "_skip",
    "ask_user": "_skip",
    "skill": "_skip",
}

# Internal tools to skip
_SKIP_TOOLS = frozenset({"_skip", "report_intent"})


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
                for i, line in enumerate(f):
                    if i >= 10:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    if isinstance(data, dict) and data.get("type") in _COPILOT_CLI_TYPES:
                        return True
            return False
        except Exception:
            return False

    def discover_sessions(self, since: Optional[datetime] = None) -> list[Path]:
        base = Path.home() / ".copilot" / "session-state"
        if not base.exists():
            return []
        paths = []
        for events_file in sorted(base.rglob("events.jsonl")):
            if since is not None:
                if datetime.fromtimestamp(events_file.stat().st_mtime, tz=timezone.utc) < since:
                    continue
            paths.append(events_file)
        return paths

    def parse_session(self, session_path: Path) -> Transcript:
        messages: list[Message] = []
        cwd = ""
        branch = ""
        model = ""
        timestamp_start = ""
        timestamp_end = ""

        # Try to load workspace metadata (cwd, branch)
        workspace_path = session_path.parent / "workspace.yaml"
        if workspace_path.exists():
            try:
                ws = yaml.safe_load(workspace_path.read_text())
                cwd = ws.get("cwd", "")
                branch = ws.get("branch", "")
            except yaml.YAMLError:
                pass

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
                data = event.get("data", {})

                # ── Session start ──
                if event_type == "session.start":
                    if not cwd:
                        # Real format: cwd in data; legacy: cwd at top level
                        cwd = (data.get("cwd", "") if isinstance(data, dict) else "") or event.get("cwd", "")

                # ── User message (real format) ──
                elif event_type == "user.message":
                    content = data.get("content", "") if isinstance(data, dict) else ""
                    text = content.strip() if isinstance(content, str) else ""
                    if text:
                        messages.append(Message(
                            role="user", content=text, timestamp=ts,
                        ))

                # ── User message (fixture/legacy format) ──
                elif event_type == "turn.start":
                    request = event.get("request", data if isinstance(data, dict) else {})
                    user_text = request.get("message", "").strip()
                    if user_text:
                        messages.append(Message(
                            role="user", content=user_text, timestamp=ts,
                        ))

                # ── Assistant message (real format) ──
                elif event_type == "assistant.message":
                    content = data.get("content", "") if isinstance(data, dict) else ""
                    text = content.strip() if isinstance(content, str) else ""

                    # Extract model from tool completion events instead
                    # (assistant.message doesn't have model)

                    if text:
                        messages.append(Message(
                            role="assistant", content=text, timestamp=ts,
                        ))

                    # Tool requests embedded in assistant message
                    tool_requests = data.get("toolRequests", []) if isinstance(data, dict) else []
                    for tr in tool_requests:
                        raw_name = tr.get("name", "")
                        canonical = _canonical_tool_name(raw_name)
                        if canonical in _SKIP_TOOLS:
                            continue
                        args = tr.get("arguments", {})
                        messages.append(Message(
                            role="tool_call", content="",
                            timestamp=ts, tool_name=canonical,
                            tool_input=args,
                        ))

                # ── Assistant message (fixture/legacy format) ──
                elif event_type == "message":
                    if event.get("role") == "assistant":
                        content = event.get("content", "").strip()
                        if content:
                            messages.append(Message(
                                role="assistant", content=content, timestamp=ts,
                            ))

                # ── Tool execution start (real format) ──
                elif event_type == "tool.execution_start":
                    raw_name = data.get("toolName", "") if isinstance(data, dict) else ""
                    canonical = _canonical_tool_name(raw_name)
                    if canonical in _SKIP_TOOLS:
                        continue
                    args = data.get("arguments", {}) if isinstance(data, dict) else {}
                    messages.append(Message(
                        role="tool_call", content="",
                        timestamp=ts, tool_name=canonical,
                        tool_input=args,
                    ))

                # ── Tool execution complete (real format) ──
                elif event_type == "tool.execution_complete":
                    if not model and isinstance(data, dict):
                        model = data.get("model", "")
                    raw_name = ""
                    result_text = ""
                    if isinstance(data, dict):
                        result_obj = data.get("result", {})
                        if isinstance(result_obj, dict):
                            result_text = result_obj.get("content", "")
                        elif isinstance(result_obj, str):
                            result_text = result_obj
                        # Find canonical name from most recent tool_call
                        tool_call_id = data.get("toolCallId", "")
                        for m in reversed(messages):
                            if m.role == "tool_call":
                                raw_name = m.tool_name
                                break
                    if raw_name and raw_name not in _SKIP_TOOLS:
                        messages.append(Message(
                            role="tool_result", content=result_text,
                            timestamp=ts, tool_name=raw_name,
                        ))

                # ── Tool call/result (fixture/legacy format) ──
                elif event_type == "tool.call":
                    tool = event.get("tool", {})
                    raw_name = tool.get("name", "")
                    canonical = _canonical_tool_name(raw_name)
                    if canonical not in _SKIP_TOOLS:
                        params = tool.get("parameters", {})
                        messages.append(Message(
                            role="tool_call", content="",
                            timestamp=ts, tool_name=canonical,
                            tool_input=params,
                        ))

                elif event_type == "tool.result":
                    tool = event.get("tool", {})
                    raw_name = tool.get("name", "")
                    canonical = _canonical_tool_name(raw_name)
                    result = event.get("result", "")
                    if not isinstance(result, str):
                        result = json.dumps(result)
                    if canonical not in _SKIP_TOOLS:
                        messages.append(Message(
                            role="tool_result", content=result,
                            timestamp=ts, tool_name=canonical,
                        ))

        project = Path(cwd).name if cwd else ""

        return Transcript(
            session_id=session_path.parent.name if session_path.name == "events.jsonl" else session_path.stem,
            source=self.key,
            project=project,
            repository="",
            branch=branch,
            cwd=cwd,
            timestamp_start=timestamp_start,
            timestamp_end=timestamp_end,
            model=model,
            messages=messages,
        )
