"""Shared frontmatter utilities — parsing, source normalization."""
from __future__ import annotations

import re
from typing import Any

import yaml


def parse_frontmatter(text: str) -> dict[str, Any] | None:
    """Extract and parse YAML frontmatter from markdown text. Returns None if absent."""
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return None
    try:
        return yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return None


def normalize_source(source) -> str:
    """Normalize a source entry to a string.

    Sources can be strings like '"[[record]]"' or nested lists like [['record']]
    when YAML parses unquoted [[...]] as a list. Normalize to 'record' stem.
    """
    if isinstance(source, list):
        while isinstance(source, list) and source:
            source = source[0]
    s = str(source).strip('"')
    match = re.search(r"\[\[([^\]]+)\]\]", s)
    if match:
        return match.group(1)
    return s
