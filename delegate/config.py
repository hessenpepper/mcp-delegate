"""Env-based configuration for the delegated-agent backend."""

from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
import os

# Load .env from the project root regardless of the server's cwd, since
# Claude Code may launch the process with a different working directory.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@dataclass(frozen=True)
class DelegateConfig:
    base_url: str
    api_key: str
    model: str


def load_config() -> DelegateConfig:
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
