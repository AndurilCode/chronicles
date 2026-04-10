"""Tests for chronicles init command."""
from chronicles.init import generate_config, prompt_provider, prompt_model, prompt_sources, prompt_ollama


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
