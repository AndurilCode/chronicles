"""Init command — scaffold chronicles directory and generate config.yaml."""
from __future__ import annotations

VALID_PROVIDERS = ("claude-code", "copilot-cli", "ollama")
VALID_SOURCES = ("claude-code", "copilot-cli", "copilot-vscode")

_COMMENTED_SECTIONS = """\

# confidence:
#   promotion_threshold: 3

# archive:
#   after_days: 90

# similarity:
#   engine: tfidf
#   threshold: 0.2
#   confirm_engine: ""
#   confirm_threshold: 0.7

# decay:
#   high_to_medium_days: 180
#   medium_to_low_days: 270
#   archive_after_days: 365

# signals:
#   max_active: 50
#   demoted_retention_days: 90
#   subagents: true

# enrich:
#   enabled: true

# gaps:
#   enabled: true
#   git_lookback_days: 90
"""

_PER_STEP_COMMENTS = """\

  # Per-step overrides (inherit from global if not set):
  # extract:
  #   provider: claude-code
  #   model: claude-sonnet-4-5-20250514
  # enrich:
  #   model: claude-haiku-4-5-20251001
  # signals:
  #   model: claude-haiku-4-5-20251001
  # similarity:
  #   model: claude-haiku-4-5-20251001
"""


def generate_config(
    provider: str,
    model: str,
    sources: list[str],
    ollama_base_url: str = "http://localhost:11434",
    ollama_timeout: int = 300,
) -> str:
    """Generate config.yaml content with active values and commented advanced options."""
    lines = [
        "llm:",
        f"  provider: {provider}",
        f"  model: {model}",
        "  max_concurrent: 3",
    ]
    lines.append(_PER_STEP_COMMENTS.rstrip("\n"))

    if provider == "ollama":
        lines.append("")
        lines.append("ollama:")
        lines.append(f"  base_url: {ollama_base_url}")
        lines.append(f"  timeout: {ollama_timeout}")
        lines.append("  # temperature: 0.0")
        lines.append("  # num_ctx: 0")
        lines.append("  # num_predict: 0")

    lines.append("")
    lines.append("sources:")
    for s in sources:
        lines.append(f"  - {s}")

    lines.append(_COMMENTED_SECTIONS.rstrip("\n"))
    lines.append("")

    return "\n".join(lines)
