"""TF-IDF similarity engine — fast, local, no LLM calls."""
from __future__ import annotations

import logging

from chronicles.config import SimilarityConfig
from chronicles.similarity.base import BaseSimilarityEngine

log = logging.getLogger("chronicles")


class TfidfSimilarityEngine(BaseSimilarityEngine):
    """Similarity scoring via TF-IDF + cosine similarity. No external API calls."""

    def __init__(self, config: SimilarityConfig) -> None:
        super().__init__(config)

    def score(self, text_a: str, text_b: str) -> float:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        tfidf = TfidfVectorizer().fit_transform([text_a, text_b])
        sim = cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0]
        return float(max(0.0, min(1.0, sim)))

    def batch_score(
        self, items: list[str], threshold: float
    ) -> list[tuple[int, int, float]]:
        if len(items) < 2:
            return []

        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        tfidf = TfidfVectorizer().fit_transform(items)
        sim_matrix = cosine_similarity(tfidf)

        results: list[tuple[int, int, float]] = []
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                s = float(sim_matrix[i][j])
                if s >= threshold:
                    results.append((i, j, s))
        return results
