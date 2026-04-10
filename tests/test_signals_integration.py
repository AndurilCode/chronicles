"""Integration test: full signals pipeline from transcript to SIGNALS.md."""

from chronicles.models import Message, Transcript, Signal, SignalsResult
from chronicles.signals_cleaner import clean_transcript_for_signals
from chronicles.signals_writer import update_signals_file, load_active_signals


def test_full_signals_pipeline(tmp_path):
    """Transcript → clean → extract (mocked) → write → verify SIGNALS.md."""
    # 1. Create transcript with a realistic tool-mistake pattern
    transcript = Transcript(
        session_id="integration-test-001",
        source="claude-code",
        project="myproject",
        repository="myrepo",
        branch="feat/add-config",
        cwd="/home/user/myrepo",
        timestamp_start="2026-04-09T10:00:00Z",
        timestamp_end="2026-04-09T10:30:00Z",
        model="opus",
        messages=[
            Message(role="user", content="find the config file", timestamp="T0"),
            Message(role="assistant", content="Let me search for it.", timestamp="T1"),
            Message(role="tool_call", content="", timestamp="T2", tool_name="Bash",
                    tool_input={"command": "grep -r 'config' src/"}),
            Message(role="tool_result", content="lots of matches...", timestamp="T3",
                    tool_name="Bash"),
            Message(role="tool_call", content="", timestamp="T4", tool_name="Grep",
                    tool_input={"pattern": "config", "path": "src/"}),
            Message(role="tool_result", content="src/config.py:1:# config module",
                    timestamp="T5", tool_name="Grep"),
            Message(role="assistant", content="Found it at src/config.py", timestamp="T6"),
        ],
    )

    # 2. Clean
    cleaned = clean_transcript_for_signals(transcript)
    assert len(cleaned.chunks) >= 1
    # Verify tool_call parameters are preserved
    tool_calls = [m for chunk in cleaned.chunks for m in chunk if m.role == "tool_call"]
    assert any(m.tool_name == "Bash" and m.tool_input.get("command") for m in tool_calls)

    # 3. Mock extraction (LLM would detect Bash grep → Grep tool mistake)
    mock_result = SignalsResult(
        signals=[
            Signal(
                pattern="Agent used Bash with grep command before using the Grep tool",
                type="mistake",
                rule="Use the Grep tool directly instead of Bash with grep or rg commands",
                context=["tool:Bash", "tool:Grep", "area:search"],
                severity="high",
            ),
        ],
        demotions=[],
    )

    # 4. Write
    signals_path = tmp_path / "SIGNALS.md"
    update_signals_file(signals_path, mock_result, session_id="integration-test-001")

    # 5. Verify
    assert signals_path.exists()
    content = signals_path.read_text()
    assert "Use the Grep tool directly" in content
    assert "[tool:Bash,tool:Grep,area:search]" in content

    # 6. Verify load_active_signals returns the rule for injection
    active = load_active_signals(signals_path)
    assert "Use the Grep tool directly" in active


def test_demotion_lifecycle(tmp_path):
    """Signal is active → contradicted in next session → demoted."""
    signals_path = tmp_path / "SIGNALS.md"

    # Session 1: add a signal
    result1 = SignalsResult(
        signals=[
            Signal(
                pattern="Agent searched lib/ for modules",
                type="efficient",
                rule="Check lib/ first for utility modules",
                context=["area:navigation"],
                severity="low",
            ),
        ],
        demotions=[],
    )
    update_signals_file(signals_path, result1, session_id="session-001")
    assert "Check lib/ first" in load_active_signals(signals_path)

    # Session 2: contradicts — there is no lib/ directory
    result2 = SignalsResult(
        signals=[],
        demotions=["Check lib/ first for utility modules"],
    )
    update_signals_file(signals_path, result2, session_id="session-002")

    content = signals_path.read_text()
    active = content.split("## Active")[1].split("## Demoted")[0]
    assert "Check lib/" not in active

    demoted = content.split("## Demoted")[1]
    assert "Check lib/" in demoted
    assert "session-002" in demoted
