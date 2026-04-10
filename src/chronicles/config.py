"""Config loader — reads chronicles/config.yaml with defaults."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class OllamaConfig:
    """Ollama-specific settings."""
    base_url: str = "http://localhost:11434"
    timeout: int = 300
    temperature: float = 0.0
    num_ctx: int = 0       # 0 = use model default
    num_predict: int = 0   # 0 = use model default


@dataclass
class LLMStepConfig:
    """Per-step LLM override — empty strings mean 'inherit from global'."""
    provider: str = ""
    model: str = ""


@dataclass
class LLMConfig:
    provider: str = "copilot-cli"
    model: str = "gpt-5-mini"
    max_concurrent: int = 3
    ollama: OllamaConfig | None = None

    # Per-step overrides — each is optional and inherits from the global defaults.
    extract: LLMStepConfig | None = None
    enrich: LLMStepConfig | None = None
    signals: LLMStepConfig | None = None
    similarity: LLMStepConfig | None = None

    def for_step(self, step: str) -> LLMConfig:
        """Return an LLMConfig resolved for the given step.

        Step-level provider/model override the global values;
        max_concurrent and ollama settings are always inherited from the global config.
        """
        override: LLMStepConfig | None = getattr(self, step, None)
        if override is None:
            return self
        return LLMConfig(
            provider=override.provider or self.provider,
            model=override.model or self.model,
            max_concurrent=self.max_concurrent,
            ollama=self.ollama,
        )


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

    # Parse per-step overrides
    step_overrides: dict[str, LLMStepConfig | None] = {}
    for step_name in ("extract", "enrich", "signals", "similarity"):
        step_raw = llm_raw.get(step_name)
        if isinstance(step_raw, dict):
            step_overrides[step_name] = LLMStepConfig(
                provider=step_raw.get("provider", ""),
                model=step_raw.get("model", ""),
            )
        else:
            step_overrides[step_name] = None

    ollama_raw = raw.get("ollama", {})
    ollama = OllamaConfig(
        base_url=ollama_raw.get("base_url", "http://localhost:11434"),
        timeout=ollama_raw.get("timeout", 300),
        temperature=float(ollama_raw.get("temperature", 0.0)),
        num_ctx=ollama_raw.get("num_ctx", 0),
        num_predict=ollama_raw.get("num_predict", 0),
    )

    llm = LLMConfig(
        provider=llm_raw.get("provider", "copilot-cli"),
        model=llm_raw.get("model", "gpt-5-mini"),
        max_concurrent=llm_raw.get("max_concurrent", 3),
        ollama=ollama,
        extract=step_overrides["extract"],
        enrich=step_overrides["enrich"],
        signals=step_overrides["signals"],
        similarity=step_overrides["similarity"],
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
