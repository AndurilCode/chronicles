"""Similarity engine package."""
from __future__ import annotations

from chronicles.config import SimilarityConfig
from chronicles.similarity.base import BaseSimilarityEngine


def get_similarity_engine(config: SimilarityConfig, llm_config=None) -> BaseSimilarityEngine:
    """Factory: return the configured similarity engine.

    Falls back from tfidf to llm if scikit-learn is not installed.
    """
    if config.engine == "tfidf":
        try:
            import sklearn  # noqa: F401
            from chronicles.similarity.tfidf import TfidfSimilarityEngine
            return TfidfSimilarityEngine(config)
        except ImportError:
            import logging
            logging.getLogger("chronicles").warning(
                "scikit-learn not installed, falling back to LLM similarity engine. "
                "Install with: pip install chronicles[tfidf]"
            )
            if llm_config is None:
                raise ValueError(
                    "TF-IDF engine requires scikit-learn (pip install chronicles[tfidf]) "
                    "and LLM fallback requires llm_config"
                )
            from chronicles.similarity.llm import LLMSimilarityEngine
            return LLMSimilarityEngine(config, llm_config)
    if config.engine == "llm":
        from chronicles.similarity.llm import LLMSimilarityEngine
        if llm_config is None:
            raise ValueError("LLM similarity engine requires llm_config")
        return LLMSimilarityEngine(config, llm_config)
    raise ValueError(f"Unknown similarity engine: {config.engine}")
