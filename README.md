# mcp-delegate

An MCP server that gives Claude Code (as orchestrator) a tool to delegate a task to a
separate, full agentic loop running on a different model (local via Ollama, or remote via
OpenRouter), with its own tool access (files, bash, etc.), returning only a final result —
functionally equivalent to a native subagent, but model-agnostic.

See [mcp-subagent-delegation-plan.md](mcp-subagent-delegation-plan.md) for the full build
plan, phased as separate commits/checkpoints.

## Status

Phase 1, 2, and 3 complete.

- `delegate_task` — single-shot chat completion against a configured OpenAI-compatible
  endpoint (Ollama, LM Studio, vLLM, OpenRouter, ...).
- `delegate_agentic_task` — gives the delegated model its own tool-use loop (`read_file`,
  `write_file`, `run_bash`) scoped to a caller-specified working directory, running until it
  stops calling tools, hits `max_iterations`, or exceeds `timeout_seconds`.

**Deviation from the original plan:** Phase 2 called for wrapping
[agent-loop](https://github.com/AlessandroAnnini/agent-loop) as a subprocess. agent-loop only
supports Linux/macOS/WSL, and this server needs to run natively on Windows, so we built the
in-process loop described as Phase 5's alternative instead — same tool interface, no
subprocess/ANSI-stripping complexity, and it sidesteps agent-loop's AGPL/no-commercial license
entirely. See [delegate/agentic.py](delegate/agentic.py).

**Safety note:** `working_dir` is caller-specified, not a fixed sandbox — the delegated model
gets unattended file/bash access to whatever directory it's pointed at. File tools
(`read_file`/`write_file`) are scoped to stay within `working_dir`; `run_bash` runs with that
directory as `cwd` but shell commands are not fully sandboxed and could escape it (e.g. `cd ..`).
Point this at a directory you're comfortable an unattended model can read, write, and execute
commands in.

## Setup

```bash
uv sync
cp .env.example .env             # fill in DELEGATE_BASE_URL / DELEGATE_API_KEY / DELEGATE_MODEL
cp models.json.example models.json   # optional: named backends, see below
```

### Multiple backends

Both tools take an optional `backend` param that looks up `base_url`/`model`/`api_key` from
`models.json` instead of the default `DELEGATE_*` env vars — e.g. `backend="ollama-local"` for
one call and `backend="openrouter-free"` for another in the same turn, each running
concurrently. `model`, if also given, overrides just the model string within that backend.

Reference an env var for a key instead of writing it into `models.json` directly:

```json
{
  "openrouter-free": {
    "base_url": "https://openrouter.ai/api/v1",
    "model": "nvidia/nemotron-nano-9b-v2:free",
    "api_key_env": "OPENROUTER_API_KEY"
  }
}
```

`models.json` is gitignored, same as `.env`.

### Concurrency

MCP tool calls already run on separate worker threads, so concurrent delegations run in
parallel with no extra plumbing. `DELEGATE_MAX_CONCURRENCY` (default 4, see `.env.example`)
caps how many delegations — across both tools, any backend — run at once, to avoid a large
fan-out overwhelming a local model server or a paid API's rate limits.

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

- `delegate_task(prompt, model=None, system_prompt=None, backend=None) -> str` — single-shot
  chat completion against the configured backend.
- `delegate_agentic_task(task, working_dir, model=None, max_iterations=20, timeout_seconds=600, backend=None) -> str` —
  multi-step delegation with `read_file`/`write_file`/`run_bash` tools scoped to `working_dir`.
  Returns only the final answer, not the full transcript.

Both tools return errors (bad config, unreachable endpoint, timeout, iteration cap) as
`"Error: ..."` strings rather than raising, so a calling agent can see what went wrong.
