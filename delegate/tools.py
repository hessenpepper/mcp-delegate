"""Tool implementations and schemas for the agentic delegation loop.

File tools are scoped to stay within the working directory. `run_bash` runs
with that directory as cwd but cannot be fully sandboxed from escaping it -
see README for the documented tradeoff.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class ToolError(Exception):
    """Raised when a tool call is invalid or unsafe."""


def _resolve_within(working_dir: Path, relative_path: str) -> Path:
    candidate = (working_dir / relative_path).resolve()
    if candidate != working_dir and working_dir not in candidate.parents:
        raise ToolError(f"path '{relative_path}' escapes the working directory")
    return candidate


def read_file(working_dir: Path, path: str) -> str:
    target = _resolve_within(working_dir, path)
    if not target.is_file():
        raise ToolError(f"no such file: {path}")
    return target.read_text(encoding="utf-8", errors="replace")


def write_file(working_dir: Path, path: str, content: str) -> str:
    target = _resolve_within(working_dir, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"wrote {len(content)} bytes to {path}"


def run_bash(working_dir: Path, command: str, timeout: float) -> str:
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=max(timeout, 1.0),
        )
    except subprocess.TimeoutExpired:
        raise ToolError(f"command timed out after {timeout:.0f}s")

    output = result.stdout
    if result.stderr:
        output += f"\n[stderr]\n{result.stderr}"
    output += f"\n[exit code: {result.returncode}]"
    return output.strip()


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a text file's contents, relative to the working directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to the working directory."}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write (create or overwrite) a text file, relative to the working directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to the working directory."},
                    "content": {"type": "string", "description": "Full contents to write."},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "Run a shell command in the working directory and return its stdout, stderr, and exit code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute."}
                },
                "required": ["command"],
            },
        },
    },
]
