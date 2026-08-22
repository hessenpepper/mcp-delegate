"""Per-model USD pricing, for cost tracking alongside token usage.

pricing.json is reference data (not a secret, not environment-specific),
so unlike .env/models.json it's committed directly rather than gitignored
with a .example counterpart. Prices drift - the shipped file was fetched
from OpenRouter's /api/v1/models on 2026-08-21; re-fetch to refresh.

A model with no entry isn't assumed free - compute_cost_usd returns None
(cost unknown) rather than 0, so a missing entry doesn't silently under-
report spend. Genuinely free models (e.g. OpenRouter's `:free` suffix, or
local Ollama models you choose to price at $0) should get an explicit
{"input_per_million": 0, "output_per_million": 0} entry instead of being
omitted.
"""

from __future__ import annotations

import json
from pathlib import Path

PRICING_PATH = Path(__file__).resolve().parent.parent / "pricing.json"


def _load_pricing() -> dict:
    if not PRICING_PATH.is_file():
        return {}
    return json.loads(PRICING_PATH.read_text(encoding="utf-8"))


def compute_cost_usd(model: str | None, usage: dict | None) -> float | None:
    """USD cost for one call's token usage, or None if `model` has no
    pricing.json entry (unknown pricing - not the same as free)."""
    if not model or not usage:
        return None

    entry = _load_pricing().get(model)
    if entry is None:
        return None

    prompt_tokens = usage.get("prompt_tokens") or 0
    completion_tokens = usage.get("completion_tokens") or 0

    return (
        prompt_tokens / 1_000_000 * entry.get("input_per_million", 0)
        + completion_tokens / 1_000_000 * entry.get("output_per_million", 0)
    )
