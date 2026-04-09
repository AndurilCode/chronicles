"""Base similarity engine ABC."""
from __future__ import annotations

from abc import ABC, abstractmethod

from chronicles.config import SimilarityConfig


class BaseSimilarityEngine(ABC):
    """Abstract base for all similarity engines."""

    def __init__(self, config: SimilarityConfig) -> None:
        self.config = config

    @abstractmethod
    def score(self, text_a: str, text_b: str) -> float:
        """Return 0.0-1.0 similarity score between two texts."""

    @abstractmethod
    def batch_score(
        self, items: list[str], threshold: float
    ) -> list[tuple[int, int, float]]:
        """Return (i, j, score) tuples for all pairs above threshold."""
