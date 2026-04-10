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


def prompt_provider() -> str:
    """Prompt user to select an LLM provider. Returns provider string."""
    print("Select LLM provider:")
    for i, p in enumerate(VALID_PROVIDERS, 1):
        print(f"  [{i}] {p}")
    while True:
        choice = input("Choice [1]: ").strip()
        if choice == "":
            return VALID_PROVIDERS[0]
        if choice.isdigit() and 1 <= int(choice) <= len(VALID_PROVIDERS):
            return VALID_PROVIDERS[int(choice) - 1]
        print(f"Invalid choice. Enter 1-{len(VALID_PROVIDERS)}.")


def prompt_model() -> str:
    """Prompt user for a model name. Required — loops until non-empty."""
    value = input("Model: ").strip()
    while not value:
        value = input("Model is required. Enter a model name: ").strip()
    return value


def prompt_sources() -> list[str]:
    """Prompt user to select transcript sources. Returns list of source strings."""
    print("Select transcript sources (comma-separated):")
    for i, s in enumerate(VALID_SOURCES, 1):
        print(f"  [{i}] {s}")
    default_nums = ",".join(str(i) for i in range(1, len(VALID_SOURCES) + 1))
    while True:
        choice = input(f"Sources [{default_nums}]: ").strip()
        if choice == "":
            return list(VALID_SOURCES)
        parts = [p.strip() for p in choice.split(",")]
        if all(p.isdigit() and 1 <= int(p) <= len(VALID_SOURCES) for p in parts):
            return [VALID_SOURCES[int(p) - 1] for p in parts]
        print(f"Invalid choice. Enter numbers 1-{len(VALID_SOURCES)} separated by commas.")


def prompt_ollama() -> tuple[str, int]:
    """Prompt for Ollama-specific settings. Returns (base_url, timeout)."""
    base_url = input("Ollama base URL [http://localhost:11434]: ").strip()
    if not base_url:
        base_url = "http://localhost:11434"
    timeout_str = input("Ollama timeout in seconds [300]: ").strip()
    timeout = int(timeout_str) if timeout_str else 300
    return base_url, timeout
