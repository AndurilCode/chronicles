"""Tests for config loading."""
from chronicles.config import load_config


def test_load_config_from_file(chronicles_dir):
    config = load_config(chronicles_dir)
    assert config.llm.provider == "copilot-cli"
    assert config.llm.model == "gpt-5-mini"
    assert config.llm.max_concurrent == 1
    assert "claude-code" in config.sources
    assert config.confidence.promotion_threshold == 3
    assert config.archive.after_days == 90


def test_load_config_defaults(tmp_path):
    """Missing config.yaml uses defaults."""
    config = load_config(tmp_path)
    assert config.llm.provider == "copilot-cli"
    assert config.llm.model == "gpt-5-mini"
    assert config.llm.max_concurrent == 3
    assert config.confidence.promotion_threshold == 3
    assert config.archive.after_days == 90


def test_load_config_partial_override(tmp_path):
    """Partial config merges with defaults."""
    (tmp_path / "config.yaml").write_text(
        "llm:\n  provider: claude-code\n  model: claude-opus-4-6\n"
    )
    config = load_config(tmp_path)
    assert config.llm.provider == "claude-code"
    assert config.llm.model == "claude-opus-4-6"
    assert config.llm.max_concurrent == 3  # default
    assert config.confidence.promotion_threshold == 3  # default


def test_load_config_new_sections_defaults(tmp_path):
    """New config sections use defaults when absent."""
    config = load_config(tmp_path)
    assert config.similarity.engine == "tfidf"
    assert config.similarity.threshold == 0.2
    assert config.decay.high_to_medium_days == 180
    assert config.decay.medium_to_low_days == 270
    assert config.decay.archive_after_days == 365
    assert config.gaps.enabled is True
    assert config.gaps.git_lookback_days == 90


def test_load_config_new_sections_override(tmp_path):
    """New config sections can be overridden."""
    (tmp_path / "config.yaml").write_text(
        "similarity:\n"
        "  engine: tfidf\n"
        "  threshold: 0.8\n"
        "decay:\n"
        "  high_to_medium_days: 90\n"
        "gaps:\n"
        "  enabled: false\n"
    )
    config = load_config(tmp_path)
    assert config.similarity.engine == "tfidf"
    assert config.similarity.threshold == 0.8
    assert config.decay.high_to_medium_days == 90
    assert config.decay.medium_to_low_days == 270  # default
    assert config.gaps.enabled is False
