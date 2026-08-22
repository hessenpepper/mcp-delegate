"""MCP server entrypoint: delegate tasks to a locally- or remotely-hosted model."""

from mcp.server.mcpserver import MCPServer

from delegate.agentic import run_agentic_task
from delegate.logging import get_transcript, list_recent
from delegate.single_shot import run_single_shot

mcp = MCPServer("delegate")


@mcp.tool()
def delegate_task(
    prompt: str,
    model: str | None = None,
    system_prompt: str | None = None,
    backend: str | None = None,
    capture_transcript: bool = False,
) -> str:
    """Delegate a single-shot task to a configured OpenAI-compatible model
    (e.g. local Ollama or OpenRouter) and return its text response verbatim.

    Args:
        prompt: The task/question to send to the delegated model.
        model: Override just the model string for this call.
        system_prompt: Optional system prompt to steer the delegated model.
        backend: Named backend from models.json (base_url/model/api_key) to
            use instead of the default DELEGATE_* env vars. `model`, if also
            given, overrides the model within that backend.
        capture_transcript: Log the full message exchange for later retrieval
            via get_delegation_transcript. Off by default; useful when
            comparing models (e.g. a bake-off) rather than for routine use.
    """
    try:
        return run_single_shot(
            prompt,
            model=model,
            system_prompt=system_prompt,
            backend=backend,
            capture_transcript=capture_transcript,
        )
    except Exception as exc:
        return f"Error: {exc}"


@mcp.tool()
def delegate_agentic_task(
    task: str,
    working_dir: str,
    model: str | None = None,
    max_iterations: int = 20,
    timeout_seconds: int = 600,
    backend: str | None = None,
    capture_transcript: bool = False,
) -> str:
    """Delegate a multi-step task to a model with its own tool-use loop
    (read_file, write_file, run_bash) scoped to working_dir. Runs until the
    model stops calling tools, hits max_iterations, or exceeds
    timeout_seconds. Returns only the final answer, not the full transcript.

    The delegated model gets unattended file/bash access within working_dir
    for the duration of the call - point it at a directory you're comfortable
    it can read, write, and execute commands in.

    Args:
        task: The task instruction to give the delegated model.
        working_dir: Directory the model's tools are scoped to.
        model: Override just the model string for this call.
        max_iterations: Stop after this many tool-call rounds.
        timeout_seconds: Wall-clock budget for the whole task.
        backend: Named backend from models.json (base_url/model/api_key) to
            use instead of the default DELEGATE_* env vars. `model`, if also
            given, overrides the model within that backend.
        capture_transcript: Log every model message and tool call/result for
            later retrieval via get_delegation_transcript, instead of just
            the final answer. Off by default; useful when comparing models
            (e.g. a bake-off) rather than for routine use.
    """
    try:
        return run_agentic_task(
            task,
            working_dir,
            model=model,
            max_iterations=max_iterations,
            timeout_seconds=timeout_seconds,
            backend=backend,
            capture_transcript=capture_transcript,
        )
    except Exception as exc:
        return f"Error: {exc}"


@mcp.tool()
def list_recent_delegations(limit: int = 20) -> list[dict]:
    """List the most recent delegate_task / delegate_agentic_task calls
    (backend, model, task, duration, iterations, success, token usage,
    truncated result), most recent first. Answers "what did the delegated
    model actually do" without re-running anything.

    Args:
        limit: Max number of records to return (default 20).
    """
    return list_recent(limit=limit)


@mcp.tool()
def get_delegation_transcript(delegation_id: int) -> list[dict] | str:
    """Full message transcript (every model message and tool call/result)
    for one delegation, if it was run with capture_transcript=True. Get the
    id from list_recent_delegations. Returns an error string if no
    transcript was captured for that id.

    Args:
        delegation_id: The `id` field from a list_recent_delegations row.
    """
    transcript = get_transcript(delegation_id)
    if transcript is None:
        return f"Error: no transcript found for delegation_id {delegation_id} (was it run with capture_transcript=True?)"
    return transcript


if __name__ == "__main__":
    mcp.run(transport="stdio")
