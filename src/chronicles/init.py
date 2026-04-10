"""Init command — scaffold chronicles directory and generate config.yaml."""
from __future__ import annotations

from pathlib import Path

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


def run_init(
    chronicles_dir: Path,
    provider: str | None = None,
    model: str | None = None,
    sources: list[str] | None = None,
    ollama_base_url: str = "http://localhost:11434",
    ollama_timeout: int = 300,
) -> None:
    """Scaffold chronicles directory and generate config.yaml.

    If provider/model/sources are None, prompts interactively.
    """
    # Interactive prompts for missing values
    try:
        if provider is None:
            provider = prompt_provider()
        if model is None:
            model = prompt_model()
        if sources is None:
            sources = prompt_sources()
        if provider == "ollama" and _is_interactive():
            ollama_base_url, ollama_timeout = prompt_ollama()
    except KeyboardInterrupt:
        print("\nAborted.")
        raise SystemExit(130)

    # Scaffold directory structure
    _ensure_dir(chronicles_dir)

    # Generate config
    config_path = chronicles_dir / "config.yaml"
    if config_path.exists():
        print(f"{config_path} already exists, skipping config generation.")
        print(f"Verified chronicles directory structure in ./{chronicles_dir}")
        return

    config_text = generate_config(
        provider=provider,
        model=model,
        sources=sources,
        ollama_base_url=ollama_base_url,
        ollama_timeout=ollama_timeout,
    )
    config_path.write_text(config_text)

    print(f"Initialized chronicles in ./{chronicles_dir}\n")
    print(f"Config written to {config_path}\n")
    print("To enable automatic ingestion, install the chronicles plugin:")
    print("  Claude Code:")
    print("    claude plugin marketplace add AndurilCode/chronicles")
    print("    claude plugin install chronicles@chronicles")
    print("  Copilot CLI:")
    print("    copilot plugin install AndurilCode/chronicles:plugin")
    print()
    print("Run 'chronicles ingest' to process your first sessions.")


def _ensure_dir(chronicles_dir: Path) -> None:
    """Bootstrap chronicles directory structure if it doesn't exist."""
    from datetime import date

    for subdir in ["records", "archives", "wiki/articles", "wiki/categories", "wiki/queries"]:
        (chronicles_dir / subdir).mkdir(parents=True, exist_ok=True)

    chronicles_md = chronicles_dir / "CHRONICLES.md"
    if not chronicles_md.exists():
        chronicles_md.write_text(
            f"---\ntype: chronicles-index\nlast_updated: {date.today().isoformat()}\n"
            f"record_count: 0\n---\n\n# Chronicles\n"
        )

    gold_md = chronicles_dir / "GOLD.md"
    if not gold_md.exists():
        gold_md.write_text(
            f"---\ntype: gold-index\nlast_updated: {date.today().isoformat()}\n"
            f"promoted_count: 0\n---\n\n# Gold Notes\n\n"
            f"> High-confidence, validated knowledge for this repository. Read before acting.\n"
        )


def _is_interactive() -> bool:
    """Check if stdin is a terminal (interactive)."""
    import sys
    return sys.stdin.isatty()
