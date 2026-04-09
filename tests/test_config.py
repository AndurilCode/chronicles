"""Tests for config loading."""
from pathlib import Path

from chronicles.config import load_config, ChroniclesConfig


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
