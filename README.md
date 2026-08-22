# mcp-delegate

An MCP server that gives Claude Code (as orchestrator) a tool to delegate a task to a
separate, full agentic loop running on a different model (local via Ollama, or remote via
OpenRouter), with its own tool access (files, bash, etc.), returning only a final result —
functionally equivalent to a native subagent, but model-agnostic.

See [mcp-subagent-delegation-plan.md](mcp-subagent-delegation-plan.md) for the full build
plan, phased as separate commits/checkpoints.

## Status

Planning stage — no implementation yet.
