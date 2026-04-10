"""Signals writer — maintains SIGNALS.md with active rules and demotions."""
from __future__ import annotations

import logging
from pathlib import Path

from chronicles.models import SignalsResult

log = logging.getLogger("chronicles")

_TEMPLATE = """\
# Signals

## Steers

{steers}

## Active

{active}

## Demoted

{demoted}
"""


def load_active_signals(signals_path: Path) -> str:
    """Load Steers + Active sections for injection into future sessions."""
    if not signals_path.exists():
        return ""
    content = signals_path.read_text()
    parts = []
    for section in ("## Steers", "## Active"):
        if section not in content:
            continue
        text = content.split(section)[1]
        # Stop at next ## header
        if "## " in text:
            text = text.split("## ", 1)[0]
        text = text.strip()
        if text:
            parts.append(text)
    return "\n".join(parts)


def update_signals_file(
    signals_path: Path,
    result: SignalsResult,
    session_id: str,
    max_active: int = 50,
) -> None:
    steers_lines: list[str] = []
    active_lines: list[str] = []
    demoted_lines: list[str] = []

    if signals_path.exists():
        content = signals_path.read_text()
        steers_lines = _parse_section(content, "## Steers")
        active_lines = _parse_section(content, "## Active")
        demoted_lines = _parse_section(content, "## Demoted")

    # Separate new signals into steers vs agent signals
    new_steers = [s for s in result.signals if s.type == "steer"]
    new_agent = [s for s in result.signals if s.type != "steer"]

    # Apply demotions to active signals only (steers are never auto-demoted)
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

    # Dedup steers
    existing_steer_rules = {_extract_rule_text(line) for line in steers_lines}
    for signal in new_steers:
        if signal.rule not in existing_steer_rules:
            tags = ",".join(signal.context)
            steers_lines.append(f"- {signal.rule} [{tags}]")

    # Dedup agent signals
    existing_rules = {_extract_rule_text(line) for line in active_lines}
    new_high: list[str] = []
    new_low: list[str] = []
    for signal in new_agent:
        if signal.rule in existing_rules:
            continue
        tags = ",".join(signal.context)
        formatted = f"- {signal.rule} [{tags}]"
        if signal.severity == "high":
            new_high.append(formatted)
        else:
            new_low.append(formatted)

    active_lines = new_high + active_lines + new_low

    # Enforce cap on active only (steers are uncapped)
    while len(active_lines) > max_active:
        active_lines.pop()

    steers_text = "\n".join(steers_lines) if steers_lines else ""
    active_text = "\n".join(active_lines) if active_lines else ""
    demoted_text = "\n".join(demoted_lines) if demoted_lines else ""

    signals_path.write_text(_TEMPLATE.format(
        steers=steers_text,
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
