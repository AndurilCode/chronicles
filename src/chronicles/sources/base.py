"""Base source adapter interface."""
from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional
from chronicles.models import Transcript


class BaseSource(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def key(self) -> str: ...

    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def parse_session(self, session_path: Path) -> Transcript: ...

    @abstractmethod
    def discover_sessions(self, since: Optional[datetime] = None) -> list[Path]: ...

    @abstractmethod
    def sniff(self, session_path: Path) -> bool: ...
