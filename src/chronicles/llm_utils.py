"""Unified LLM provider abstraction and shared LLM response utilities.

All provider-specific logic lives here. Consumers call ``call_llm()``
and never need to know which backend is in use.
"""
from __future__ import annotations

import json
import logging
import subprocess
import urllib.request
import urllib.error

from json_repair import repair_json

from chronicles.config import LLMConfig, OllamaConfig

log = logging.getLogger("chronicles")


def call_llm(prompt: str, config: LLMConfig) -> str:
    """Call the configured LLM provider and return the raw response text.

    Raises RuntimeError on failure.
    """
    provider = config.provider
    model = config.model

    if provider == "ollama":
        return _call_ollama(model, prompt, config.ollama)
    if provider == "copilot-cli":
        return _call_cli(["copilot", "-p", prompt, "--model", model])
    if provider == "claude-code":
        return _call_cli(["claude", "--print", "--model", model, prompt])

    raise RuntimeError(f"Unknown LLM provider: {provider}")


def _call_cli(cmd: list[str], timeout: int = 120) -> str:
    """Run a CLI-based LLM provider as a subprocess."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"LLM CLI call timed out after {timeout}s")

    if result.returncode != 0:
        raise RuntimeError(
            f"LLM CLI failed (exit {result.returncode}): {result.stderr[:300]}"
        )
    return result.stdout


def _call_ollama(model: str, prompt: str, ollama_config: OllamaConfig | None = None) -> str:
    """Call the Ollama HTTP API."""
    cfg = ollama_config or OllamaConfig()

    url = f"{cfg.base_url}/api/generate"
    body: dict = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }

    options: dict = {}
    if cfg.temperature > 0:
        options["temperature"] = cfg.temperature
    if cfg.num_ctx > 0:
        options["num_ctx"] = cfg.num_ctx
    if cfg.num_predict > 0:
        options["num_predict"] = cfg.num_predict
    if options:
        body["options"] = options

    payload = json.dumps(body).encode()

    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=cfg.timeout) as resp:
            data = json.loads(resp.read())
            return data.get("response", "")
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Ollama API call failed (is ollama running at {cfg.base_url}?): {e}"
        ) from e
    except TimeoutError:
        raise RuntimeError(
            f"Ollama API call timed out after {cfg.timeout}s"
        )


def parse_llm_json(raw: str) -> dict:
    """Strip markdown fences, locate JSON object, parse with repair fallback.

    Raises RuntimeError on empty input or unparseable response.
    """
    text = raw.strip()
    if not text:
        raise RuntimeError("LLM returned empty response")
    # Strip markdown fences if present
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
    if text.endswith("```"):
        text = "\n".join(text.split("\n")[:-1])
    text = text.strip()
    # Find JSON object in response
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise RuntimeError(f"No JSON object found in LLM response: {text[:200]}")
    text = text[start:end]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            return json.loads(repair_json(text))
        except (json.JSONDecodeError, ValueError) as e:
            raise RuntimeError(
                f"Failed to parse LLM JSON: {e}\nResponse: {text[:500]}"
            ) from e


def normalize_enum(value: str, valid: set[str], default: str) -> str:
    """Normalize an enum value: lowercase, strip, fuzzy match."""
    if not isinstance(value, str):
        return default
    v = value.strip().lower()
    if v in valid:
        return v
    for candidate in valid:
        if v.startswith(candidate) or candidate.startswith(v):
            return candidate
    return default
