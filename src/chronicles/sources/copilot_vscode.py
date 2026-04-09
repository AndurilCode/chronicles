"""Copilot VS Code source adapter stub."""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from chronicles.models import Transcript
from chronicles.sources.base import BaseSource


class CopilotVSCodeSource(BaseSource):
    @property
    def name(self) -> str:
        return "GitHub Copilot VS Code"

    @property
    def key(self) -> str:
        return "copilot-vscode"

    def available(self) -> bool:
        raise NotImplementedError

    def parse_session(self, session_path: Path) -> Transcript:
        raise NotImplementedError

    def discover_sessions(self, since: Optional[datetime] = None) -> list[Path]:
        raise NotImplementedError

    def sniff(self, session_path: Path) -> bool:
        try:
            with session_path.open() as f:
                data = json.load(f)
            return isinstance(data, dict) and isinstance(data.get("sessions"), list)
        except Exception:
            return False
