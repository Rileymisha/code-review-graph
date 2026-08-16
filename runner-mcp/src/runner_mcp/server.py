"""FastMCP server exposing run_command and list_targets."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.tools.tool import ToolResult

from runner_mcp.config import load_targets
from runner_mcp.runner import cleanup_stale_logs, run

mcp = FastMCP("runner-mcp")


def get_project_root() -> Path:
    """Resolve the project root from CRG_PROJECT_ROOT env var."""
    raw = os.environ.get("CRG_PROJECT_ROOT")
    if not raw:
        raise RuntimeError(
            "CRG_PROJECT_ROOT env var is not set; runner-mcp requires it."
        )
    root = Path(raw).expanduser().resolve()
    return root


def _ok(payload: dict) -> str:
    """Success payload — plain JSON string; FastMCP wraps as TextContent."""
    return json.dumps(payload, ensure_ascii=False)


def _err(message: str) -> ToolResult:
    """Generic error result — sets is_error=True on the wire."""
    return ToolResult(content=f"ERROR: {message}", is_error=True)


def _err_with_payload(prefix: str, payload: dict) -> ToolResult:
    """Diagnostic error result carrying a JSON payload, is_error=True."""
    text = json.dumps(payload, ensure_ascii=False)
    return ToolResult(content=f"{prefix}\n{text}", is_error=True)


@mcp.tool()
async def run_command(
    cmd: str,
    cwd: str | None = None,
    timeout_s: int = 120,
) -> str | ToolResult:
    """Run a shell command inside the project root.

    Args:
        cmd: Shell command to execute (passed to `bash -lc`).
        cwd: Optional override; defaults to $CRG_PROJECT_ROOT.
        timeout_s: Max runtime in seconds (default 120, recommended ≤ 300).

    Returns:
        On success (exit_code == 0): JSON text content with
            exit_code, duration_ms, stdout, stderr, log_file, truncated.
        On non-zero exit: ToolResult with is_error=True, content
            "exit_code=N\\n<json>".
        On timeout or unexpected exception: ToolResult with is_error=True,
            content "ERROR: <message>".
        On missing CRG_PROJECT_ROOT: ToolResult with is_error=True.
    """
    try:
        project_root = get_project_root()
    except RuntimeError as e:
        return _err(str(e))

    workdir = Path(cwd).expanduser().resolve() if cwd else project_root
    # Per spec: artifact path defaults to runner.LOG_DIR (/tmp/runner-mcp/);
    # stale reaping happens at startup in __main__.py — see spec §"artifact 格式".

    try:
        result = await run(cmd, workdir, timeout_s=timeout_s)
    except asyncio.TimeoutError:
        return _err(f"Command timed out after {timeout_s}s")
    except Exception as e:
        return _err(f"Execution failed: {type(e).__name__}: {e}")

    payload = {
        "exit_code": result.exit_code,
        "duration_ms": result.duration_ms,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "log_file": str(result.log_file) if result.log_file else None,
        "truncated": result.truncated,
    }

    if result.exit_code != 0:
        return _err_with_payload(f"exit_code={result.exit_code}", payload)

    return _ok(payload)


@mcp.tool()
async def list_targets() -> str | ToolResult:
    """List the runnable targets declared in runner-config.json.

    Returns:
        JSON text content with: project_root, config_file, targets[]
        (each having name, description, cmd). On missing config or
        CRG_PROJECT_ROOT unset: ToolResult with is_error=True.
    """
    try:
        root = get_project_root()
    except RuntimeError as e:
        return _err(str(e))

    cfg_path = root / "runner-config.json"
    try:
        targets = load_targets(root)
    except FileNotFoundError:
        return _err(f"runner-config.json not found at {cfg_path}")
    except Exception as e:
        return _err(f"Failed to parse runner-config.json: {type(e).__name__}: {e}")

    payload = {
        "project_root": str(root),
        "config_file": str(cfg_path),
        "targets": [
            {"name": t.name, "description": t.description, "cmd": t.cmd}
            for t in targets.values()
        ],
    }
    return _ok(payload)
