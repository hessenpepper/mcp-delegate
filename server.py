"""MCP server entrypoint: delegate tasks to a locally- or remotely-hosted model."""

from mcp.server.mcpserver import MCPServer

from delegate.single_shot import run_single_shot

mcp = MCPServer("delegate")


@mcp.tool()
def delegate_task(
    prompt: str,
    model: str | None = None,
    system_prompt: str | None = None,
) -> str:
    """Delegate a single-shot task to a configured OpenAI-compatible model
    (e.g. local Ollama or OpenRouter) and return its text response verbatim.

    Args:
        prompt: The task/question to send to the delegated model.
        model: Override the model configured via DELEGATE_MODEL.
        system_prompt: Optional system prompt to steer the delegated model.
    """
    try:
        return run_single_shot(prompt, model=model, system_prompt=system_prompt)
    except Exception as exc:
        return f"Error: {exc}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
