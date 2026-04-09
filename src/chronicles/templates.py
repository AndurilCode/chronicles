"""Jinja2 template loader and renderer."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

# Default templates ship with the package
_DEFAULT_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


class TemplateRenderer:
    """Renders chronicles artifacts from Jinja2 templates."""

    def __init__(self, template_dir: Path | None = None):
        self._dir = template_dir or _DEFAULT_TEMPLATE_DIR
        self._env = Environment(
            loader=FileSystemLoader(str(self._dir)),
            keep_trailing_newline=True,
            trim_blocks=True,
            lstrip_blocks=False,
        )

    def render(self, template_name: str, data: dict[str, Any]) -> str:
        """Render a template by name (without .md.j2 extension)."""
        tpl = self._env.get_template(f"{template_name}.md.j2")
        return tpl.render(**data)
