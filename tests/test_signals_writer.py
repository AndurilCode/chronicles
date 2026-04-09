"""Tests for signals writer — maintains SIGNALS.md."""
from pathlib import Path

from chronicles.models import Signal, SignalsResult
from chronicles.signals_writer import update_signals_file, load_active_signals


def test_creates_signals_file_if_missing(tmp_path):
    signals_path = tmp_path / "SIGNALS.md"
    result = SignalsResult(
        signals=[
            Signal(
                pattern="Agent used Bash grep",
                type="mistake",
                rule="Use the Grep tool instead of Bash with grep",
                context=["tool:Bash", "tool:Grep"],
                severity="high",
            ),
        ],
        demotions=[],
    )
    update_signals_file(signals_path, result, session_id="abc123")
    assert signals_path.exists()
    content = signals_path.read_text()
    assert "## Active" in content
    assert "Use the Grep tool instead of Bash with grep" in content
    assert "[tool:Bash,tool:Grep]" in content


def test_appends_to_existing_signals(tmp_path):
    signals_path = tmp_path / "SIGNALS.md"
    signals_path.write_text(
        "# Signals\n\n## Active\n\n"
        "- Existing rule here [tool:Read] [area:nav]\n\n"
        "## Demoted\n"
    )
    result = SignalsResult(
        signals=[
            Signal(
                pattern="new pattern",
                type="efficient",
                rule="New rule for agents",
                context=["area:testing"],
                severity="low",
            ),
        ],
        demotions=[],
    )
    update_signals_file(signals_path, result, session_id="def456")
    content = signals_path.read_text()
    assert "Existing rule here" in content
    assert "New rule for agents" in content


def test_high_severity_at_top(tmp_path):
    signals_path = tmp_path / "SIGNALS.md"
    signals_path.write_text(
        "# Signals\n\n## Active\n\n"
        "- Low severity rule [area:nav]\n\n"
        "## Demoted\n"
    )
    result = SignalsResult(
        signals=[
            Signal(
                pattern="critical mistake",
                type="mistake",
                rule="High severity rule",
                context=["tool:Bash"],
                severity="high",
            ),
        ],
        demotions=[],
    )
    update_signals_file(signals_path, result, session_id="ghi789")
    content = signals_path.read_text()
    active_section = content.split("## Active")[1].split("## Demoted")[0]
    lines = [l for l in active_section.strip().split("\n") if l.startswith("- ")]
    assert "High severity rule" in lines[0]


def test_demotes_contradicted_signals(tmp_path):
    signals_path = tmp_path / "SIGNALS.md"
    signals_path.write_text(
        "# Signals\n\n## Active\n\n"
        "- Check lib/ for utility modules [area:navigation]\n"
        "- Use Grep instead of Bash grep [tool:Bash,Grep]\n\n"
        "## Demoted\n"
    )
    result = SignalsResult(
        signals=[],
        demotions=["Check lib/ for utility modules"],
    )
    update_signals_file(signals_path, result, session_id="xyz999")
    content = signals_path.read_text()
    active = content.split("## Active")[1].split("## Demoted")[0]
    assert "Check lib/" not in active
    demoted = content.split("## Demoted")[1]
    assert "Check lib/" in demoted
    assert "xyz999" in demoted


def test_does_not_add_duplicate_rules(tmp_path):
    signals_path = tmp_path / "SIGNALS.md"
    signals_path.write_text(
        "# Signals\n\n## Active\n\n"
        "- Use the Grep tool instead of Bash with grep [tool:Bash,Grep]\n\n"
        "## Demoted\n"
    )
    result = SignalsResult(
        signals=[
            Signal(
                pattern="same mistake again",
                type="mistake",
                rule="Use the Grep tool instead of Bash with grep",
                context=["tool:Bash", "tool:Grep"],
                severity="high",
            ),
        ],
        demotions=[],
    )
    update_signals_file(signals_path, result, session_id="dup123")
    content = signals_path.read_text()
    active = content.split("## Active")[1].split("## Demoted")[0]
    count = active.count("Use the Grep tool instead of Bash with grep")
    assert count == 1


def test_caps_at_max_signals(tmp_path):
    signals_path = tmp_path / "SIGNALS.md"
    existing = "# Signals\n\n## Active\n\n"
    for i in range(50):
        existing += f"- Existing rule {i} [area:test]\n"
    existing += "\n## Demoted\n"
    signals_path.write_text(existing)

    result = SignalsResult(
        signals=[
            Signal(
                pattern="new important signal",
                type="mistake",
                rule="Brand new rule",
                context=["tool:X"],
                severity="high",
            ),
        ],
        demotions=[],
    )
    update_signals_file(signals_path, result, session_id="cap123", max_active=50)
    content = signals_path.read_text()
    active = content.split("## Active")[1].split("## Demoted")[0]
    lines = [l for l in active.strip().split("\n") if l.startswith("- ")]
    assert len(lines) <= 50
    assert any("Brand new rule" in l for l in lines)


def test_load_active_signals(tmp_path):
    signals_path = tmp_path / "SIGNALS.md"
    signals_path.write_text(
        "# Signals\n\n## Active\n\n"
        "- Rule one [tool:X]\n"
        "- Rule two [area:Y]\n\n"
        "## Demoted\n\n"
        "- ~~Old rule~~ (contradicted: session abc)\n"
    )
    active = load_active_signals(signals_path)
    assert "Rule one" in active
    assert "Rule two" in active
    assert "Old rule" not in active


def test_load_active_signals_missing_file(tmp_path):
    signals_path = tmp_path / "SIGNALS.md"
    active = load_active_signals(signals_path)
    assert active == ""
