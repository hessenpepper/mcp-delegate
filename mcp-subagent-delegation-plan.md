# Plan: MCP Server for Delegating Subagent Tasks to Local/Other-Provider Models

**Goal:** Give Claude Code (as orchestrator) an MCP tool it can call to delegate a task to
a separate, full agentic loop running on a different model (local via Ollama, or remote via
OpenRouter), with its own tool access (files, bash, etc.), returning only a final result —
functionally equivalent to a native subagent, but model-agnostic.

Hand this whole file to Claude Code as the task brief. Sections are ordered as build phases;
each phase should be a separate commit/checkpoint.

---

## 0. Decisions to lock in before coding

Answer these (or let Claude Code assume the defaults in brackets) before starting:

1. **Backend for the delegated agent** — [default: OpenAI-compatible endpoint, config-driven]
   so it works with Ollama, LM Studio, vLLM, and OpenRouter without code changes.
2. **Delegated agent runtime** — [default: reuse `agent-loop`
   (github.com/AlessandroAnnini/agent-loop) as a subprocess rather than writing a harness
   from scratch]. Reasons: it already has the tool-use loop, iteration limits, and
   repetition detection built in. Caveat: AGPLv3 + no-commercial-use license — fine for
   personal/internal use, a blocker if this is ever part of a commercial product. If that's
   a concern, flag it now and Claude Code should instead build a minimal custom harness
   (Phase 5 below covers this as an alternative).
3. **Transport** — MCP server over stdio (simplest, matches how Claude Code loads local MCP
   servers via `.mcp.json` / `claude mcp add`).
4. **Language** — Python (matches agent-loop's own stack and has a mature `mcp` SDK) unless
   you have a strong preference for TypeScript.
5. **Where this runs relative to Claude Code** — if Claude Code is running natively on
   Windows, the MCP server and agent-loop subprocess should also run natively/cross-platform
   (see Phase 5 note on dropping the agent-loop dependency if WSL is not otherwise in use).
   If Claude Code is running inside WSL, everything can stay inside WSL and avoid path
   translation entirely.

---

## Phase 1 — Bare MCP server skeleton, single-shot delegation only

**Objective:** Prove the plumbing works before adding agentic-loop complexity.

- Scaffold an MCP server (Python `mcp` SDK, stdio transport) with one tool:
  - `delegate_task(prompt: str, model: str = None, system_prompt: str = None) -> str`
- Implementation: forward `prompt` as a single chat completion request to a configured
  OpenAI-compatible endpoint (env vars: `DELEGATE_BASE_URL`, `DELEGATE_API_KEY`,
  `DELEGATE_MODEL`). Return the text response verbatim.
- No tool-use loop yet — this just validates the MCP wiring and endpoint config.
- Add a `.env.example` documenting the vars needed for: local Ollama
  (`http://localhost:11434/v1`, no key), OpenRouter (`https://openrouter.ai/api/v1`, API key).
- Register the server with Claude Code (`claude mcp add` or `.mcp.json`) and manually test:
  ask Claude Code to delegate a trivial summarization task and confirm the round trip works.

**Exit criteria:** Claude Code can call `delegate_task` and get back a real response from a
local Ollama model and, separately, from OpenRouter, by swapping env vars only.

---

## Phase 2 — Full agentic loop via subprocess (agent-loop wrapper)

**Objective:** Upgrade `delegate_task` so the delegated model gets its own tool-use loop —
file access, bash, iteration, stopping conditions — not just single-shot text.

- Add a second tool: `delegate_agentic_task(task: str, working_dir: str, model: str = None,
  max_iterations: int = 20, timeout_seconds: int = 600) -> str`
- Implementation:
  - Spawn `agent-loop` as a subprocess (`--no-prompt-on-completion` so it doesn't block on
    stdin waiting for a human, `--model <configured model>`, `--max-iterations N`).
  - Pass `task` as the initial instruction (agent-loop supports piping the first prompt in
    non-interactively — confirm exact invocation flag; if it's REPL-only, wrap it with a
    small stdin-feeding shim).
  - Run with `cwd=working_dir` so file tools operate on the right project.
  - Capture stdout, strip Rich/ANSI formatting (agent-loop uses `Rich` for CLI output — use
    `--simple-text` flag to get plain output instead of parsing ANSI codes).
  - Enforce `timeout_seconds` at the subprocess level (`subprocess.run(..., timeout=...)`)
    as a hard backstop independent of agent-loop's own `MAX_ITERATIONS`.
  - Return only the final answer/summary — not the full transcript — mirroring how native
    subagents only surface their final output to the parent.
- Config for which local models map to which agent-loop invocation (env-driven or a small
  YAML/JSON config file, e.g. `models.json` mapping a friendly name → base_url/model/api_key).
- Error handling: if the subprocess exits non-zero, times out, or produces no parseable
  output, return a clear error string (not a stack trace) so Claude Code can decide whether
  to retry, fall back, or do the task itself.

**Exit criteria:** Claude Code delegates a real multi-step task ("refactor this file and run
the tests") to a local model via `delegate_agentic_task`, and gets back a coherent final
result after agent-loop runs its own loop to completion inside the given working directory.

---

## Phase 3 — Concurrency and multiple backends

**Objective:** Support Claude Code firing off several delegations in parallel, and picking
different backends per call (matching your "orchestrator on Claude, one subagent on local
Llama, another on OpenRouter" scenario).

- Make `model` (or a `backend` param) select from the `models.json` config at call time,
  rather than being fixed per server instance.
- Ensure the MCP server can handle concurrent tool calls — each `delegate_agentic_task`
  spawns its own isolated subprocess, so concurrency should be close to free; verify no
  shared mutable state (e.g. a single global subprocess handle) blocks parallel calls.
- Add basic concurrency limits (e.g. max N simultaneous subprocesses) to avoid resource
  exhaustion if Claude Code fans out many delegations at once.

**Exit criteria:** Two `delegate_agentic_task` calls issued in the same Claude Code turn,
pointed at two different backends (e.g. local Ollama + OpenRouter), complete concurrently
and both return correctly.

---

## Phase 4 — Observability and guardrails

**Objective:** Match the conveniences native subagents get for free (mentioned earlier):
telemetry, logging, safety limits.

- Log every delegation: task text, backend/model used, start/end time, iteration count,
  success/failure, to a local file or SQLite (not stdout, which is the MCP transport).
- Add a `list_recent_delegations` tool (optional) so Claude Code — or you — can inspect what
  happened without digging through logs manually.
- Cost/token tracking if using paid backends (OpenRouter) — log token usage per call if the
  API returns it, so you can see spend attributable to delegated work.
- Confirm agent-loop's own guardrails are active: iteration cap, repetition detection,
  `--safe` mode NOT used here (since there's no human in the loop for a delegated subagent —
  document this tradeoff explicitly: the delegated agent runs unattended, so keep its tool
  access scoped to a safe working directory, not your whole filesystem).

**Exit criteria:** You can answer "what did the local model actually do" after the fact
without re-running anything.

---

## Phase 5 — Optional: drop the agent-loop dependency

**Objective:** Only do this if the AGPL/no-commercial license is a blocker, or if native
Windows support (no WSL) turns out to be required and agent-loop's Linux/macOS/WSL-only
support is a hard blocker.

- Replace the agent-loop subprocess with a small custom loop (~150–250 lines) implementing
  the same core cycle described earlier: assemble context → call model with tool schema →
  parse tool call → execute (file read/write, bash, in a scoped sandbox dir) → append result
  → repeat → stop on completion phrase / no tool call / max iterations.
- This can run in-process in the MCP server (no subprocess needed) since you own the code,
  simplifying Phase 2's subprocess/timeout/ANSI-stripping complexity.
- Same tool interface (`delegate_agentic_task`) so Claude Code's usage doesn't change —
  this is purely a backend swap.

**Exit criteria:** Same behavior as Phase 2, MIT/permissive-licensed, no external agent
runtime dependency, and running natively on Windows if that's required.

---

## Open questions Claude Code should surface back to you, not guess on

- Exact non-interactive invocation syntax for agent-loop (confirm via `agent-loop --help`
  and the `CREATING_TOOLS.md`/README once cloned — the plan assumes a flag exists or a stdin
  shim is needed).
- Whether "working_dir" should be a fixed sandboxed directory you control, or whatever
  directory Claude Code's own session is in — this is a real safety decision, since the
  delegated agent will have unattended file/bash access there.
- Whether you want a hard ceiling on concurrent delegations/cost before Phase 3 ships.

---

## Suggested repo layout

```
mcp-local-delegate/
  server.py              # MCP server entrypoint, tool definitions
  delegate/
    single_shot.py       # Phase 1 implementation
    agentic.py            # Phase 2/3 subprocess wrapper around agent-loop
    config.py             # models.json loading, env var resolution
    logging.py            # Phase 4 delegation logging
  models.json.example
  .env.example
  README.md
  pyproject.toml
```

Give this file to Claude Code with an instruction like: "Build Phase 1 first, stop, and let
me test it before moving to Phase 2." Each phase is independently testable, which keeps
Claude Code from building the whole stack blind before you've validated the plumbing works.
