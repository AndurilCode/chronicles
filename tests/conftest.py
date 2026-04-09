"""Shared test fixtures."""
import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def chronicles_dir(tmp_path):
    """Create a temporary chronicles directory structure."""
    dirs = [
        "records",
        "archives",
        "wiki/articles",
        "wiki/categories",
        "wiki/queries",
        "templates",
    ]
    for d in dirs:
        (tmp_path / d).mkdir(parents=True)

    # Write minimal config.yaml
    config = tmp_path / "config.yaml"
    config.write_text(
        "llm:\n"
        "  provider: copilot-cli\n"
        "  model: gpt-5-mini\n"
        "  max_concurrent: 1\n"
        "sources:\n"
        "  - claude-code\n"
        "  - copilot-cli\n"
        "  - copilot-vscode\n"
        "confidence:\n"
        "  promotion_threshold: 3\n"
        "archive:\n"
        "  after_days: 90\n"
    )

    # Write empty index files
    (tmp_path / "CHRONICLES.md").write_text(
        "---\ntype: chronicles-index\nlast_updated: 2026-01-01\nrecord_count: 0\n---\n\n# Chronicles\n"
    )
    (tmp_path / "GOLD.md").write_text(
        "---\ntype: gold-index\nlast_updated: 2026-01-01\npromoted_count: 0\n---\n\n# Gold Notes\n"
    )

    return tmp_path
