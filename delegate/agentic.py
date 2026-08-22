"""Phase 2 (built per Phase 5's approach): in-process agentic loop.

Gives the delegated model its own tool-use loop (file read/write, bash)
scoped to a caller-specified working directory, running to completion or a
stop condition (no tool call, max iterations, or timeout), and returning
only the final answer - not the full transcript.

Runs in-process rather than spawning agent-loop as a subprocess: agent-loop
only supports Linux/macOS/WSL, and this server needs to run natively on
Windows.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from openai import OpenAI

from .config import load_config
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
) -> str:
    resolved_dir = Path(working_dir).resolve()
    if not resolved_dir.is_dir():
        raise ValueError(f"working_dir does not exist or is not a directory: {working_dir}")

    config = load_config()
    client = OpenAI(base_url=config.base_url, api_key=config.api_key)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(working_dir=resolved_dir)},
        {"role": "user", "content": task},
    ]

    deadline = time.monotonic() + timeout_seconds

    for _ in range(max_iterations):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return f"Error: timed out after {timeout_seconds}s without completing the task"

        response = client.chat.completions.create(
            model=model or config.model,
            messages=messages,
            tools=TOOL_SCHEMAS,
            timeout=remaining,
        )
        message = response.choices[0].message

        if not message.tool_calls:
            return message.content or ""

        messages.append(message.model_dump(exclude_none=True))

        for tool_call in message.tool_calls:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return f"Error: timed out after {timeout_seconds}s without completing the task"

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

    return f"Error: hit max_iterations ({max_iterations}) without completing the task"
