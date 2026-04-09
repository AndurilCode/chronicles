"""Similarity engine package."""
from __future__ import annotations

from chronicles.config import SimilarityConfig
from chronicles.similarity.base import BaseSimilarityEngine


def get_similarity_engine(config: SimilarityConfig, llm_config=None) -> BaseSimilarityEngine:
    """Factory: return the configured similarity engine."""
    if config.engine == "llm":
        from chronicles.similarity.llm import LLMSimilarityEngine
        if llm_config is None:
            raise ValueError("LLM similarity engine requires llm_config")
        return LLMSimilarityEngine(config, llm_config)
    raise ValueError(f"Unknown similarity engine: {config.engine}")
