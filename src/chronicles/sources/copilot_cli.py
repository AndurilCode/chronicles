"""Copilot CLI source adapter stub."""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from chronicles.models import Transcript
from chronicles.sources.base import BaseSource

_COPILOT_CLI_TYPES = {"session.start", "turn.start", "turn.end"}


class CopilotCLISource(BaseSource):
    @property
    def name(self) -> str:
        return "GitHub Copilot CLI"

    @property
    def key(self) -> str:
        return "copilot-cli"

    def available(self) -> bool:
        raise NotImplementedError

    def parse_session(self, session_path: Path) -> Transcript:
        raise NotImplementedError

    def discover_sessions(self, since: Optional[datetime] = None) -> list[Path]:
        raise NotImplementedError

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
