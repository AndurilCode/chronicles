"""Tests for TF-IDF similarity engine."""
from chronicles.config import SimilarityConfig
from chronicles.similarity.tfidf import TfidfSimilarityEngine


def _make_engine(threshold=0.3):
    return TfidfSimilarityEngine(SimilarityConfig(engine="tfidf", threshold=threshold))


def test_score_identical_texts():
    engine = _make_engine()
    assert engine.score("OAuth token refresh pattern", "OAuth token refresh pattern") == 1.0


def test_score_similar_texts():
    engine = _make_engine()
    score = engine.score(
        "OAuth token refresh pattern for API connections",
        "Token refresh mechanism for OAuth API endpoints",
    )
    assert score > 0.3


def test_score_unrelated_texts():
    engine = _make_engine()
    score = engine.score(
        "OAuth token refresh pattern",
        "Database migration rollback strategy",
    )
    assert score < 0.2


def test_batch_score_filters_by_threshold():
    engine = _make_engine(threshold=0.3)
    items = [
        "OAuth token refresh for API connections",
        "Token refresh mechanism for OAuth endpoints",
        "Database migration rollback strategy",
    ]
    results = engine.batch_score(items, threshold=0.3)
    # First two should be similar, third unrelated
    similar_pair = [(i, j) for i, j, s in results]
    assert (0, 1) in similar_pair
    assert (0, 2) not in similar_pair


def test_batch_score_empty():
    engine = _make_engine()
    assert engine.batch_score([], threshold=0.3) == []


def test_batch_score_single_item():
    engine = _make_engine()
    assert engine.batch_score(["one item"], threshold=0.3) == []


def test_factory_returns_tfidf_engine():
    from chronicles.similarity import get_similarity_engine
    config = SimilarityConfig(engine="tfidf", threshold=0.3)
    engine = get_similarity_engine(config)
    assert isinstance(engine, TfidfSimilarityEngine)
