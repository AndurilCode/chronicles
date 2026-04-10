"""Tests for chronicles init command."""
import pytest
from chronicles.init import generate_config, prompt_provider, prompt_model, prompt_sources, prompt_ollama
from chronicles.init import run_init
from chronicles.cli import main


def test_generate_config_claude_code():
    result = generate_config(
        provider="claude-code",
        model="claude-haiku-4-5-20251001",
        sources=["claude-code", "copilot-cli"],
    )
    assert "provider: claude-code" in result
    assert "model: claude-haiku-4-5-20251001" in result
    assert "- claude-code" in result
    assert "- copilot-cli" in result
    assert "- copilot-vscode" not in result
    # Commented advanced sections present
    assert "# confidence:" in result
    assert "# archive:" in result
    assert "# similarity:" in result
    assert "# decay:" in result
    assert "# signals:" in result
    assert "# enrich:" in result
    assert "# gaps:" in result
    # No ollama section for non-ollama provider
    assert "ollama:" not in result


def test_generate_config_ollama():
    result = generate_config(
        provider="ollama",
        model="gemma3:12b",
        sources=["claude-code"],
        ollama_base_url="http://myhost:11434",
        ollama_timeout=600,
    )
    assert "provider: ollama" in result
    assert "model: gemma3:12b" in result
    assert "ollama:" in result
    assert "base_url: http://myhost:11434" in result
    assert "timeout: 600" in result
    assert "# temperature: 0.0" in result
    assert "- claude-code" in result


def test_generate_config_all_sources():
    result = generate_config(
        provider="copilot-cli",
        model="gpt-5-mini",
        sources=["claude-code", "copilot-cli", "copilot-vscode"],
    )
    assert "- claude-code" in result
    assert "- copilot-cli" in result
    assert "- copilot-vscode" in result


def test_prompt_provider_default(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert prompt_provider() == "claude-code"


def test_prompt_provider_selection(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "3")
    assert prompt_provider() == "ollama"


def test_prompt_provider_invalid_then_valid(monkeypatch):
    responses = iter(["9", "2"])
    monkeypatch.setattr("builtins.input", lambda _: next(responses))
    assert prompt_provider() == "copilot-cli"


def test_prompt_model_value(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "claude-haiku-4-5-20251001")
    assert prompt_model() == "claude-haiku-4-5-20251001"


def test_prompt_model_required(monkeypatch):
    responses = iter(["", "", "my-model"])
    monkeypatch.setattr("builtins.input", lambda _: next(responses))
    assert prompt_model() == "my-model"


def test_prompt_sources_default(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert prompt_sources() == ["claude-code", "copilot-cli", "copilot-vscode"]


def test_prompt_sources_selection(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "1,3")
    assert prompt_sources() == ["claude-code", "copilot-vscode"]


def test_prompt_sources_invalid_then_valid(monkeypatch):
    responses = iter(["0,5", "2"])
    monkeypatch.setattr("builtins.input", lambda _: next(responses))
    assert prompt_sources() == ["copilot-cli"]


def test_prompt_ollama_defaults(monkeypatch):
    responses = iter(["", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(responses))
    base_url, timeout = prompt_ollama()
    assert base_url == "http://localhost:11434"
    assert timeout == 300


def test_prompt_ollama_custom(monkeypatch):
    responses = iter(["http://myhost:11434", "600"])
    monkeypatch.setattr("builtins.input", lambda _: next(responses))
    base_url, timeout = prompt_ollama()
    assert base_url == "http://myhost:11434"
    assert timeout == 600


def test_run_init_creates_structure(tmp_path):
    chronicles_dir = tmp_path / "chronicles"
    run_init(
        chronicles_dir=chronicles_dir,
        provider="claude-code",
        model="haiku",
        sources=["claude-code"],
    )
    assert (chronicles_dir / "config.yaml").exists()
    assert (chronicles_dir / "CHRONICLES.md").exists()
    assert (chronicles_dir / "GOLD.md").exists()
    assert (chronicles_dir / "records").is_dir()
    assert (chronicles_dir / "wiki" / "articles").is_dir()

    config_text = (chronicles_dir / "config.yaml").read_text()
    assert "provider: claude-code" in config_text
    assert "model: haiku" in config_text


def test_run_init_skips_existing_config(tmp_path, capsys):
    chronicles_dir = tmp_path / "chronicles"
    chronicles_dir.mkdir()
    (chronicles_dir / "config.yaml").write_text("llm:\n  provider: ollama\n")

    run_init(
        chronicles_dir=chronicles_dir,
        provider="claude-code",
        model="haiku",
        sources=["claude-code"],
    )

    # Config should NOT be overwritten
    assert "ollama" in (chronicles_dir / "config.yaml").read_text()
    captured = capsys.readouterr()
    assert "already exists" in captured.out


def test_run_init_creates_missing_dirs(tmp_path):
    chronicles_dir = tmp_path / "chronicles"
    chronicles_dir.mkdir()
    (chronicles_dir / "config.yaml").write_text("llm:\n  provider: claude-code\n")
    # records/ and wiki/ don't exist yet

    run_init(
        chronicles_dir=chronicles_dir,
        provider="claude-code",
        model="haiku",
        sources=["claude-code"],
    )

    assert (chronicles_dir / "records").is_dir()
    assert (chronicles_dir / "wiki" / "articles").is_dir()
    assert (chronicles_dir / "CHRONICLES.md").exists()
    assert (chronicles_dir / "GOLD.md").exists()


def test_run_init_interactive(tmp_path, monkeypatch):
    chronicles_dir = tmp_path / "chronicles"
    responses = iter(["2", "gpt-5-mini", "1,2"])
    monkeypatch.setattr("builtins.input", lambda _: next(responses))

    run_init(chronicles_dir=chronicles_dir)

    config_text = (chronicles_dir / "config.yaml").read_text()
    assert "provider: copilot-cli" in config_text
    assert "model: gpt-5-mini" in config_text
    assert "- claude-code" in config_text
    assert "- copilot-cli" in config_text
    assert "- copilot-vscode" not in config_text


def test_cli_init_with_flags(tmp_path):
    chronicles_dir = tmp_path / "chronicles"
    main([
        "init",
        "--chronicles-dir", str(chronicles_dir),
        "--provider", "claude-code",
        "--model", "haiku",
        "--source", "claude-code",
        "--source", "copilot-cli",
    ])
    assert (chronicles_dir / "config.yaml").exists()
    config_text = (chronicles_dir / "config.yaml").read_text()
    assert "provider: claude-code" in config_text
    assert "model: haiku" in config_text
    assert "- claude-code" in config_text
    assert "- copilot-cli" in config_text


def test_cli_init_interactive(tmp_path, monkeypatch):
    chronicles_dir = tmp_path / "chronicles"
    responses = iter(["1", "my-model", "1"])
    monkeypatch.setattr("builtins.input", lambda _: next(responses))

    main([
        "init",
        "--chronicles-dir", str(chronicles_dir),
    ])

    config_text = (chronicles_dir / "config.yaml").read_text()
    assert "provider: claude-code" in config_text
    assert "model: my-model" in config_text


def test_run_init_ctrl_c_exits_cleanly(tmp_path, monkeypatch):
    chronicles_dir = tmp_path / "chronicles"
    monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(KeyboardInterrupt))

    with pytest.raises(SystemExit) as exc_info:
        run_init(chronicles_dir=chronicles_dir)
    assert exc_info.value.code == 130
    # No config.yaml should exist
    assert not (chronicles_dir / "config.yaml").exists()


def test_cli_init_invalid_provider(tmp_path):
    with pytest.raises(SystemExit) as exc_info:
        main([
            "init",
            "--chronicles-dir", str(tmp_path / "chronicles"),
            "--provider", "invalid",
            "--model", "haiku",
        ])
    assert exc_info.value.code == 2  # argparse error
