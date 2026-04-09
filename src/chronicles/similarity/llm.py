"""LLM-backed similarity engine."""
from __future__ import annotations

import logging
import re
import subprocess

from chronicles.config import LLMConfig, SimilarityConfig
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
    """Similarity scoring via configured LLM CLI backend."""

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
        results: list[tuple[int, int, float]] = []
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                s = self.score(items[i], items[j])
                if s >= threshold:
                    results.append((i, j, s))
        return results

    def _call_llm(self, prompt: str) -> str:
        provider = self.llm_config.provider
        model = self.llm_config.model

        if provider == "copilot-cli":
            cmd = ["copilot", "-p", prompt, "--model", model]
        elif provider == "claude-code":
            cmd = ["claude", "--print", "--model", model, prompt]
        else:
            log.warning("Unknown LLM provider for similarity: %s", provider)
            return ""

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=False, timeout=60
            )
            if result.returncode != 0:
                log.warning("Similarity LLM call failed: %s", result.stderr[:200])
                return ""
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            log.warning("Similarity LLM call timed out")
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
