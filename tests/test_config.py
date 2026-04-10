"""Tests for config loading."""
from chronicles.config import load_config, LLMConfig, LLMStepConfig


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


def test_signals_config_defaults(chronicles_dir):
    from chronicles.config import load_config
    config = load_config(chronicles_dir)
    assert config.signals.max_active == 50
    assert config.signals.demoted_retention_days == 90


def test_signals_config_custom(tmp_path):
    from chronicles.config import load_config
    for d in ["records", "archives", "wiki/articles", "wiki/categories", "wiki/queries"]:
        (tmp_path / d).mkdir(parents=True)
    (tmp_path / "config.yaml").write_text(
        "llm:\n"
        "  provider: claude-code\n"
        "  model: haiku\n"
        "signals:\n"
        "  max_active: 30\n"
        "  demoted_retention_days: 60\n"
    )
    config = load_config(tmp_path)
    assert config.signals.max_active == 30
    assert config.signals.demoted_retention_days == 60


def test_for_step_no_override():
    """for_step returns self when no override is set."""
    llm = LLMConfig(provider="claude-code", model="haiku")
    result = llm.for_step("extract")
    assert result is llm


def test_for_step_with_override():
    """for_step merges step override with global defaults."""
    llm = LLMConfig(
        provider="claude-code",
        model="haiku",
        max_concurrent=5,
        extract=LLMStepConfig(model="sonnet"),
    )
    result = llm.for_step("extract")
    assert result.provider == "claude-code"  # inherited
    assert result.model == "sonnet"  # overridden
    assert result.max_concurrent == 5  # inherited


def test_for_step_override_provider_only():
    """for_step can override just the provider."""
    llm = LLMConfig(
        provider="claude-code",
        model="haiku",
        signals=LLMStepConfig(provider="copilot-cli"),
    )
    result = llm.for_step("signals")
    assert result.provider == "copilot-cli"
    assert result.model == "haiku"  # inherited


def test_for_step_unknown_step():
    """for_step with unknown step name returns self."""
    llm = LLMConfig(provider="claude-code", model="haiku")
    result = llm.for_step("nonexistent")
    assert result is llm


def test_load_config_per_step_overrides(tmp_path):
    """Per-step LLM overrides are parsed from config.yaml."""
    (tmp_path / "config.yaml").write_text(
        "llm:\n"
        "  provider: claude-code\n"
        "  model: haiku\n"
        "  extract:\n"
        "    model: sonnet\n"
        "  signals:\n"
        "    provider: copilot-cli\n"
        "    model: gpt-5\n"
    )
    config = load_config(tmp_path)
    assert config.llm.provider == "claude-code"
    assert config.llm.model == "haiku"

    extract = config.llm.for_step("extract")
    assert extract.provider == "claude-code"  # inherited
    assert extract.model == "sonnet"

    signals = config.llm.for_step("signals")
    assert signals.provider == "copilot-cli"
    assert signals.model == "gpt-5"

    # Steps without overrides return global config
    enrich = config.llm.for_step("enrich")
    assert enrich.provider == "claude-code"
    assert enrich.model == "haiku"
