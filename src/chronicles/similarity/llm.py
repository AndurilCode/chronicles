"""LLM-backed similarity engine."""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor

from chronicles.config import LLMConfig, SimilarityConfig
from chronicles.llm_utils import call_llm
from chronicles.similarity.base import BaseSimilarityEngine

log = logging.getLogger("chronicles")

_SIMILARITY_PROMPT = (
    "Rate the semantic similarity of these two texts on a scale of 0 to 10, "
    "where 0 means completely unrelated and 10 means identical in meaning. "
    "Return ONLY the number, nothing else.\n\n"
    "Text A: {text_a}\n\n"
    "Text B: {text_b}"
)


class LLMSimilarityEngine(BaseSimilarityEngine):
    """Similarity scoring via configured LLM backend."""

    def __init__(self, config: SimilarityConfig, llm_config: LLMConfig) -> None:
        super().__init__(config)
        self.llm_config = llm_config

    def score(self, text_a: str, text_b: str) -> float:
        prompt = _SIMILARITY_PROMPT.format(text_a=text_a, text_b=text_b)
        raw = self._call_llm(prompt)
        return self._parse_score(raw)

    def batch_score(
        self, items: list[str], threshold: float
    ) -> list[tuple[int, int, float]]:
        pairs = [(i, j) for i in range(len(items)) for j in range(i + 1, len(items))]
        if not pairs:
            return []

        def _score_pair(pair: tuple[int, int]) -> tuple[int, int, float]:
            i, j = pair
            return (i, j, self.score(items[i], items[j]))

        max_workers = self.llm_config.max_concurrent
        results: list[tuple[int, int, float]] = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for i, j, s in pool.map(_score_pair, pairs):
                if s >= threshold:
                    results.append((i, j, s))
        return results

    def _call_llm(self, prompt: str) -> str:
        try:
            return call_llm(prompt, self.llm_config).strip()
        except RuntimeError as e:
            log.warning("Similarity LLM call failed: %s", e)
            return ""

    @staticmethod
    def _parse_score(raw: str) -> float:
        if not raw:
            return 0.0
        match = re.search(r"(-?\d+(?:\.\d+)?)", raw)
        if not match:
            return 0.0
        value = float(match.group(1)) / 10.0
        return max(0.0, min(1.0, value))
