"""Config loader — reads chronicles/config.yaml with defaults."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class LLMConfig:
    provider: str = "copilot-cli"
    model: str = "gpt-5-mini"
    max_concurrent: int = 3


@dataclass
class ConfidenceConfig:
    promotion_threshold: int = 3


@dataclass
class ArchiveConfig:
    after_days: int = 90


@dataclass
class ChroniclesConfig:
    llm: LLMConfig
    sources: list[str]
    confidence: ConfidenceConfig
    archive: ArchiveConfig
    chronicles_dir: Path


def load_config(chronicles_dir: Path) -> ChroniclesConfig:
    """Load config.yaml from chronicles_dir, falling back to defaults."""
    config_path = chronicles_dir / "config.yaml"

    raw: dict = {}
    if config_path.exists():
        raw = yaml.safe_load(config_path.read_text()) or {}

    llm_raw = raw.get("llm", {})
    llm = LLMConfig(
        provider=llm_raw.get("provider", "copilot-cli"),
        model=llm_raw.get("model", "gpt-5-mini"),
        max_concurrent=llm_raw.get("max_concurrent", 3),
    )

    sources = raw.get("sources", ["claude-code", "copilot-cli", "copilot-vscode"])

    conf_raw = raw.get("confidence", {})
    confidence = ConfidenceConfig(
        promotion_threshold=conf_raw.get("promotion_threshold", 3),
    )

    arch_raw = raw.get("archive", {})
    archive = ArchiveConfig(
        after_days=arch_raw.get("after_days", 90),
    )

    return ChroniclesConfig(
        llm=llm,
        sources=sources,
        confidence=confidence,
        archive=archive,
        chronicles_dir=chronicles_dir,
    )
