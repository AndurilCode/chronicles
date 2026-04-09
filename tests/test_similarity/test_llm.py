"""Tests for LLM-backed similarity engine."""
from unittest.mock import patch, MagicMock

from chronicles.config import SimilarityConfig, LLMConfig
from chronicles.similarity.llm import LLMSimilarityEngine


def _make_engine():
    sim_config = SimilarityConfig(engine="llm", threshold=0.7)
    llm_config = LLMConfig(provider="claude-code", model="claude-haiku-4-5")
    return LLMSimilarityEngine(sim_config, llm_config)


@patch("chronicles.similarity.llm.subprocess.run")
def test_score_parses_llm_response(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="7\n", stderr="")
    engine = _make_engine()
    result = engine.score("OAuth token refresh", "Token refresh mechanism")
    assert result == 0.7
    mock_run.assert_called_once()


@patch("chronicles.similarity.llm.subprocess.run")
def test_score_clamps_to_range(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="12\n", stderr="")
    engine = _make_engine()
    assert engine.score("a", "b") == 1.0

    mock_run.return_value = MagicMock(returncode=0, stdout="-3\n", stderr="")
    assert engine.score("a", "b") == 0.0


@patch("chronicles.similarity.llm.subprocess.run")
def test_score_returns_zero_on_llm_failure(mock_run):
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
    engine = _make_engine()
    assert engine.score("a", "b") == 0.0


@patch("chronicles.similarity.llm.subprocess.run")
def test_score_returns_zero_on_non_numeric(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="these are similar\n", stderr="")
    engine = _make_engine()
    assert engine.score("a", "b") == 0.0


@patch("chronicles.similarity.llm.subprocess.run")
def test_batch_score_filters_by_threshold(mock_run):
    # 3 items = 3 pairs: (0,1), (0,2), (1,2)
    mock_run.side_effect = [
        MagicMock(returncode=0, stdout="8\n", stderr=""),
        MagicMock(returncode=0, stdout="3\n", stderr=""),
        MagicMock(returncode=0, stdout="9\n", stderr=""),
    ]
    engine = _make_engine()
    results = engine.batch_score(["A", "B", "C"], threshold=0.7)
    assert len(results) == 2
    assert (0, 1, 0.8) in results
    assert (1, 2, 0.9) in results


@patch("chronicles.similarity.llm.subprocess.run")
def test_batch_score_empty_list(mock_run):
    engine = _make_engine()
    assert engine.batch_score([], threshold=0.5) == []


@patch("chronicles.similarity.llm.subprocess.run")
def test_batch_score_single_item(mock_run):
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
