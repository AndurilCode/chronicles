"""Signals writer — maintains SIGNALS.md with active rules and demotions."""
from __future__ import annotations

import logging
from pathlib import Path

from chronicles.models import SignalsResult

log = logging.getLogger("chronicles")

_TEMPLATE = """\
# Signals

## Active

{active}

## Demoted

{demoted}
"""


def load_active_signals(signals_path: Path) -> str:
    if not signals_path.exists():
        return ""
    content = signals_path.read_text()
    if "## Active" not in content:
        return ""
    active_section = content.split("## Active")[1]
    if "## Demoted" in active_section:
        active_section = active_section.split("## Demoted")[0]
    return active_section.strip()


def update_signals_file(
    signals_path: Path,
    result: SignalsResult,
    session_id: str,
    max_active: int = 50,
) -> None:
    active_lines: list[str] = []
    demoted_lines: list[str] = []

    if signals_path.exists():
        content = signals_path.read_text()
        active_lines = _parse_section(content, "## Active")
        demoted_lines = _parse_section(content, "## Demoted")

    # Apply demotions
    for demotion_rule in result.demotions:
        remaining = []
        for line in active_lines:
            if demotion_rule in line:
                demoted_lines.append(
                    f"- ~~{_strip_bullet(line)}~~ "
                    f"(contradicted: session {session_id})"
                )
            else:
                remaining.append(line)
        active_lines = remaining

    # Collect existing rule texts for dedup
    existing_rules = {_extract_rule_text(line) for line in active_lines}

    # Add new signals (deduplicated)
    new_high: list[str] = []
    new_low: list[str] = []
    for signal in result.signals:
        if signal.rule in existing_rules:
            continue
        tags = ",".join(signal.context)
        formatted = f"- {signal.rule} [{tags}]"
        if signal.severity == "high":
            new_high.append(formatted)
        else:
            new_low.append(formatted)

    # High severity at top, then existing, then new low severity
    active_lines = new_high + active_lines + new_low

    # Enforce cap
    while len(active_lines) > max_active:
        active_lines.pop()

    active_text = "\n".join(active_lines) if active_lines else ""
    demoted_text = "\n".join(demoted_lines) if demoted_lines else ""

    signals_path.write_text(_TEMPLATE.format(
        active=active_text,
        demoted=demoted_text,
    ))


def _parse_section(content: str, header: str) -> list[str]:
    if header not in content:
        return []
    section = content.split(header)[1]
    for next_header in ["## "]:
        parts = section.split(next_header, 1)
        if len(parts) > 1:
            section = parts[0]
            break
    return [line for line in section.strip().split("\n") if line.startswith("- ")]


def _strip_bullet(line: str) -> str:
    return line[2:] if line.startswith("- ") else line


def _extract_rule_text(line: str) -> str:
    text = _strip_bullet(line)
    while text.rstrip().endswith("]"):
        bracket_start = text.rfind("[")
        if bracket_start == -1:
            break
        text = text[:bracket_start].rstrip()
    return text
