"""Env- and models.json-based configuration for delegate backends."""

from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
import json
import os

ROOT = Path(__file__).resolve().parent.parent

# Load .env from the project root regardless of the server's cwd, since
# Claude Code may launch the process with a different working directory.
load_dotenv(ROOT / ".env")

MODELS_JSON_PATH = ROOT / "models.json"


@dataclass(frozen=True)
class DelegateConfig:
    base_url: str
    api_key: str
    model: str


def _default_config() -> DelegateConfig:
    base_url = os.environ.get("DELEGATE_BASE_URL")
    model = os.environ.get("DELEGATE_MODEL")

    if not base_url:
        raise RuntimeError("DELEGATE_BASE_URL is not set (see .env.example)")
    if not model:
        raise RuntimeError("DELEGATE_MODEL is not set (see .env.example)")

    # Ollama's OpenAI-compatible endpoint doesn't check the key, but the
    # OpenAI client requires a non-empty string.
    api_key = os.environ.get("DELEGATE_API_KEY") or "unused"

    return DelegateConfig(base_url=base_url, api_key=api_key, model=model)


def _load_models() -> dict:
    if not MODELS_JSON_PATH.is_file():
        return {}
    return json.loads(MODELS_JSON_PATH.read_text(encoding="utf-8"))


def _resolve_api_key(backend: str, entry: dict) -> str:
    if "api_key_env" in entry:
        env_name = entry["api_key_env"]
        value = os.environ.get(env_name)
        if not value:
            raise RuntimeError(
                f"backend '{backend}' in models.json references env var "
                f"'{env_name}', which is not set"
            )
        return value
    return entry.get("api_key") or "unused"


def load_config(backend: str | None = None) -> DelegateConfig:
    """Resolve a backend to connect to.

    With no backend given, falls back to the DELEGATE_* env vars (Phase 1/2
    behavior). With a backend name, looks it up in models.json.
    """
    if backend is None:
        return _default_config()

    models = _load_models()
    if backend not in models:
        available = ", ".join(sorted(models)) or "(none configured - see models.json.example)"
        raise RuntimeError(f"unknown backend '{backend}'. Available: {available}")

    entry = models[backend]
    base_url = entry.get("base_url")
    model = entry.get("model")
    if not base_url or not model:
        raise RuntimeError(f"backend '{backend}' in models.json is missing 'base_url' or 'model'")

    return DelegateConfig(base_url=base_url, api_key=_resolve_api_key(backend, entry), model=model)
