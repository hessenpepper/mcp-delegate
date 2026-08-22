# mcp-delegate

An MCP server that gives Claude Code (as orchestrator) a tool to delegate a task to a
separate, full agentic loop running on a different model (local via Ollama, or remote via
OpenRouter), with its own tool access (files, bash, etc.), returning only a final result —
functionally equivalent to a native subagent, but model-agnostic.

See [mcp-subagent-delegation-plan.md](mcp-subagent-delegation-plan.md) for the full build
plan, phased as separate commits/checkpoints.

## Status

Phase 1 complete: bare MCP server with a single `delegate_task` tool that forwards a
prompt to a configured OpenAI-compatible endpoint (Ollama, LM Studio, vLLM, OpenRouter, ...)
and returns the text response. No tool-use loop yet — see the plan for later phases.

## Setup

```bash
uv sync
cp .env.example .env   # fill in DELEGATE_BASE_URL / DELEGATE_API_KEY / DELEGATE_MODEL
```

Run the server directly (mostly useful to check it starts without error — it then waits on
stdio for an MCP client):

```bash
uv run server.py
```

### Register with Claude Code

A project-scoped [.mcp.json](.mcp.json) is already checked in (`uv run server.py`). Restart
Claude Code in this directory, or run `claude mcp list` to confirm it picked up the `delegate`
server, then ask it to call `delegate_task` with a trivial prompt to confirm the round trip.

## Tools

- `delegate_task(prompt, model=None, system_prompt=None) -> str` — single-shot chat
  completion against the configured backend. Errors (bad config, unreachable endpoint) are
  returned as `"Error: ..."` strings rather than raising, so a calling agent can see what
  went wrong.
