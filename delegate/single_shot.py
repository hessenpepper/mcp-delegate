"""Phase 1: forward a single prompt to a configured OpenAI-compatible endpoint."""

import datetime

from openai import OpenAI

from .concurrency import limit_concurrency
from .config import load_config
from .logging import format_usage_suffix, log_delegation


def run_single_shot(
    prompt: str,
    model: str | None = None,
    system_prompt: str | None = None,
    backend: str | None = None,
    capture_transcript: bool = False,
) -> str:
    started_at = datetime.datetime.now(datetime.timezone.utc)
    resolved_model = model
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        config = load_config(backend)
        resolved_model = model or config.model
        client = OpenAI(base_url=config.base_url, api_key=config.api_key)

        with limit_concurrency():
            response = client.chat.completions.create(
                model=resolved_model,
                messages=messages,
            )
    except Exception as exc:
        log_delegation(
            tool="delegate_task",
            backend=backend,
            model=resolved_model,
            task=prompt,
            started_at=started_at,
            ended_at=datetime.datetime.now(datetime.timezone.utc),
            iterations=None,
            success=False,
            result_preview=f"{type(exc).__name__}: {exc}",
            transcript=messages if capture_transcript else None,
        )
        raise

    result = response.choices[0].message.content or ""
    usage = response.usage.model_dump() if response.usage else None
    transcript = messages + [{"role": "assistant", "content": result}] if capture_transcript else None

    delegation_id = log_delegation(
        tool="delegate_task",
        backend=backend,
        model=resolved_model,
        task=prompt,
        started_at=started_at,
        ended_at=datetime.datetime.now(datetime.timezone.utc),
        iterations=None,
        success=True,
        result_preview=result,
        usage=usage,
        transcript=transcript,
    )

    suffix = format_usage_suffix(usage)
    if capture_transcript and delegation_id is not None:
        suffix += f"\n\n[delegation_id: {delegation_id}]"

    return result + suffix
