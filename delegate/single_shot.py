"""Phase 1: forward a single prompt to a configured OpenAI-compatible endpoint."""

from openai import OpenAI

from .config import load_config


def run_single_shot(
    prompt: str,
    model: str | None = None,
    system_prompt: str | None = None,
) -> str:
    config = load_config()
    client = OpenAI(base_url=config.base_url, api_key=config.api_key)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=model or config.model,
        messages=messages,
    )

    return response.choices[0].message.content or ""
