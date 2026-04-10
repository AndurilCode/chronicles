"""Tests for LLM-backed similarity engine."""
from unittest.mock import patch

from chronicles.config import SimilarityConfig, LLMConfig
from chronicles.similarity.llm import LLMSimilarityEngine


def _make_engine():
    sim_config = SimilarityConfig(engine="llm", threshold=0.7)
    llm_config = LLMConfig(provider="claude-code", model="claude-haiku-4-5")
    return LLMSimilarityEngine(sim_config, llm_config)


@patch("chronicles.llm_utils._call_cli")
def test_score_parses_llm_response(mock_cli):
    mock_cli.return_value = "7\n"
    engine = _make_engine()
    result = engine.score("OAuth token refresh", "Token refresh mechanism")
    assert result == 0.7
    mock_cli.assert_called_once()


@patch("chronicles.llm_utils._call_cli")
def test_score_clamps_to_range(mock_cli):
    mock_cli.return_value = "12\n"
    engine = _make_engine()
    assert engine.score("a", "b") == 1.0

    mock_cli.return_value = "-3\n"
    assert engine.score("a", "b") == 0.0


@patch("chronicles.llm_utils._call_cli")
def test_score_returns_zero_on_llm_failure(mock_cli):
    mock_cli.side_effect = RuntimeError("CLI failed")
    engine = _make_engine()
    assert engine.score("a", "b") == 0.0


@patch("chronicles.llm_utils._call_cli")
def test_score_returns_zero_on_non_numeric(mock_cli):
    mock_cli.return_value = "these are similar\n"
    engine = _make_engine()
    assert engine.score("a", "b") == 0.0


@patch("chronicles.llm_utils._call_cli")
def test_batch_score_filters_by_threshold(mock_cli):
    # 3 items = 3 pairs: (0,1), (0,2), (1,2)
    mock_cli.side_effect = ["8\n", "3\n", "9\n"]
    engine = _make_engine()
    results = engine.batch_score(["A", "B", "C"], threshold=0.7)
    assert len(results) == 2
    assert (0, 1, 0.8) in results
    assert (1, 2, 0.9) in results


@patch("chronicles.llm_utils._call_cli")
def test_batch_score_empty_list(mock_cli):
    engine = _make_engine()
    assert engine.batch_score([], threshold=0.5) == []


@patch("chronicles.llm_utils._call_cli")
def test_batch_score_single_item(mock_cli):
    engine = _make_engine()
    assert engine.batch_score(["A"], threshold=0.5) == []


def test_factory_returns_llm_engine():
    from chronicles.similarity import get_similarity_engine
    sim_config = SimilarityConfig(engine="llm", threshold=0.7)
    llm_config = LLMConfig(provider="claude-code", model="claude-haiku-4-5")
    engine = get_similarity_engine(sim_config, llm_config=llm_config)
    assert isinstance(engine, LLMSimilarityEngine)


def test_factory_raises_on_unknown():
    from chronicles.similarity import get_similarity_engine
    import pytest
    sim_config = SimilarityConfig(engine="unknown", threshold=0.7)
    with pytest.raises(ValueError, match="Unknown similarity engine"):
        get_similarity_engine(sim_config)
