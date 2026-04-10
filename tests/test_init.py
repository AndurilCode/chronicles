"""Tests for chronicles init command."""
from chronicles.init import generate_config


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
