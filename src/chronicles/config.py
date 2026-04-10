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
class EnrichConfig:
    enabled: bool = True


@dataclass
class SimilarityConfig:
    engine: str = "tfidf"
    threshold: float = 0.2
    confirm_engine: str = ""
    confirm_threshold: float = 0.7


@dataclass
class DecayConfig:
    high_to_medium_days: int = 180
    medium_to_low_days: int = 270
    archive_after_days: int = 365


@dataclass
class GapsConfig:
    enabled: bool = True
    git_lookback_days: int = 90


@dataclass
class SignalsConfig:
    max_active: int = 50
    demoted_retention_days: int = 90
    subagents: bool = True


@dataclass
class ChroniclesConfig:
    llm: LLMConfig
    sources: list[str]
    confidence: ConfidenceConfig
    archive: ArchiveConfig
    enrich: EnrichConfig
    similarity: SimilarityConfig
    decay: DecayConfig
    gaps: GapsConfig
    signals: SignalsConfig
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

    enrich_raw = raw.get("enrich", {})
    enrich = EnrichConfig(
        enabled=enrich_raw.get("enabled", True),
    )

    sim_raw = raw.get("similarity", {})
    similarity = SimilarityConfig(
        engine=sim_raw.get("engine", "tfidf"),
        threshold=sim_raw.get("threshold", 0.2),
        confirm_engine=sim_raw.get("confirm_engine", ""),
        confirm_threshold=sim_raw.get("confirm_threshold", 0.7),
    )

    decay_raw = raw.get("decay", {})
    decay = DecayConfig(
        high_to_medium_days=decay_raw.get("high_to_medium_days", 180),
        medium_to_low_days=decay_raw.get("medium_to_low_days", 270),
        archive_after_days=decay_raw.get("archive_after_days", 365),
    )

    gaps_raw = raw.get("gaps", {})
    gaps = GapsConfig(
        enabled=gaps_raw.get("enabled", True),
        git_lookback_days=gaps_raw.get("git_lookback_days", 90),
    )

    signals_raw = raw.get("signals", {})
    signals = SignalsConfig(
        max_active=signals_raw.get("max_active", 50),
        demoted_retention_days=signals_raw.get("demoted_retention_days", 90),
        subagents=signals_raw.get("subagents", True),
    )

    return ChroniclesConfig(
        llm=llm,
        sources=sources,
        confidence=confidence,
        archive=archive,
        enrich=enrich,
        similarity=similarity,
        decay=decay,
        gaps=gaps,
        signals=signals,
        chronicles_dir=chronicles_dir,
    )
