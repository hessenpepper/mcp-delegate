"""Phase 2 (built per Phase 5's approach): in-process agentic loop.

Gives the delegated model its own tool-use loop (file read/write, bash)
scoped to a caller-specified working directory, running to completion or a
stop condition (no tool call, max iterations, or timeout), and returning
only the final answer - not the full transcript, unless capture_transcript
is set (for evaluation/comparison runs - see delegate/logging.py).

Runs in-process rather than spawning agent-loop as a subprocess: agent-loop
only supports Linux/macOS/WSL, and this server needs to run natively on
Windows.
"""

from __future__ import annotations

import datetime
import json
import time
from pathlib import Path

from openai import OpenAI

from .concurrency import limit_concurrency
from .config import load_config
from .logging import format_usage_suffix, log_delegation
from .tools import TOOL_SCHEMAS, ToolError, read_file, run_bash, write_file

SYSTEM_PROMPT = """You are an autonomous coding agent working in: {working_dir}

Use the read_file, write_file, and run_bash tools to accomplish the task. \
When you are completely done, respond with your final answer as plain text \
and do not call any more tools - that response ends the session."""


def _dispatch_tool(working_dir: Path, name: str, arguments: dict, remaining_time: float) -> str:
    try:
        if name == "read_file":
            return read_file(working_dir, arguments["path"])
        if name == "write_file":
            return write_file(working_dir, arguments["path"], arguments["content"])
        if name == "run_bash":
            return run_bash(working_dir, arguments["command"], timeout=remaining_time)
        return f"error: unknown tool '{name}'"
    except ToolError as exc:
        return f"error: {exc}"
    except KeyError as exc:
        return f"error: missing required argument {exc}"


def run_agentic_task(
    task: str,
    working_dir: str,
    model: str | None = None,
    max_iterations: int = 20,
    timeout_seconds: int = 600,
    backend: str | None = None,
    capture_transcript: bool = False,
) -> str:
    started_at = datetime.datetime.now(datetime.timezone.utc)
    resolved_model = model
    iterations_used = 0
    usage_totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    usage_seen = False
    messages: list[dict] = []

    def _finish(success: bool, result_preview: str) -> str:
        """Log the delegation and return a suffix (usage + delegation_id)
        to append to whatever string the caller is about to return."""
        delegation_id = log_delegation(
            tool="delegate_agentic_task",
            backend=backend,
            model=resolved_model,
            task=task,
            started_at=started_at,
            ended_at=datetime.datetime.now(datetime.timezone.utc),
            iterations=iterations_used,
            success=success,
            result_preview=result_preview,
            usage=usage_totals if usage_seen else None,
            transcript=messages if capture_transcript else None,
        )
        suffix = format_usage_suffix(usage_totals if usage_seen else None)
        if capture_transcript and delegation_id is not None:
            suffix += f"\n\n[delegation_id: {delegation_id}]"
        return suffix

    try:
        resolved_dir = Path(working_dir).resolve()
        if not resolved_dir.is_dir():
            raise ValueError(f"working_dir does not exist or is not a directory: {working_dir}")

        config = load_config(backend)
        resolved_model = model or config.model
        client = OpenAI(base_url=config.base_url, api_key=config.api_key)

        messages.append({"role": "system", "content": SYSTEM_PROMPT.format(working_dir=resolved_dir)})
        messages.append({"role": "user", "content": task})

        deadline = time.monotonic() + timeout_seconds

        with limit_concurrency():
            for _ in range(max_iterations):
                iterations_used += 1
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    msg = f"Error: timed out after {timeout_seconds}s without completing the task"
                    return msg + _finish(False, msg)

                response = client.chat.completions.create(
                    model=resolved_model,
                    messages=messages,
                    tools=TOOL_SCHEMAS,
                    timeout=remaining,
                )

                if response.usage:
                    usage_seen = True
                    usage_dict = response.usage.model_dump()
                    for key in usage_totals:
                        usage_totals[key] += usage_dict.get(key) or 0

                message = response.choices[0].message
                messages.append(message.model_dump(exclude_none=True))

                if not message.tool_calls:
                    result = message.content or ""
                    return result + _finish(True, result)

                for tool_call in message.tool_calls:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        msg = f"Error: timed out after {timeout_seconds}s without completing the task"
                        return msg + _finish(False, msg)

                    try:
                        arguments = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        result = "error: could not parse tool arguments"
                    else:
                        result = _dispatch_tool(resolved_dir, tool_call.function.name, arguments, remaining)

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result,
                        }
                    )

            msg = f"Error: hit max_iterations ({max_iterations}) without completing the task"
            return msg + _finish(False, msg)
    except Exception as exc:
        _finish(False, f"{type(exc).__name__}: {exc}")
        raise
