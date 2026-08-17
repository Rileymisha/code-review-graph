"""In-process FastMCP smoke test for runner-mcp.

Usage:
    CRG_PROJECT_ROOT=/home/riley/workspace/code-review-graph \
    PYTHONPATH=/home/riley/workspace/code-review-graph/runner-mcp/src \
        .venv/bin/python scripts/smoke.py

Exits non-zero on any assertion failure. Designed to be a sanity check
that the server is wired up correctly when an MCP-Inspector install is
not available.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# NOTE: src/ must be importable. Invoke this script with
#   PYTHONPATH=/home/riley/workspace/code-review-graph/runner-mcp/src \
# as documented in runner-mcp/README.md — no sys.path mutation here.

from fastmcp import Client

from runner_mcp.server import mcp


EXPECTED_TARGETS = {"test", "lint", "format", "type-check", "build"}


def _block_text(result) -> str:
    """Concatenate text blocks from a CallToolResult.content list."""
    parts = []
    for block in result.content:
        text = getattr(block, "text", None)
        if text is not None:
            parts.append(text)
    return "".join(parts)


def _is_error(result) -> bool:
    return bool(
        getattr(result, "isError", False) or getattr(result, "is_error", False)
    )


async def main() -> int:
    project_root = os.environ.get("CRG_PROJECT_ROOT")
    if not project_root:
        print("FAIL: CRG_PROJECT_ROOT is not set", file=sys.stderr)
        return 2
    cfg_path = Path(project_root) / "runner-config.json"
    if not cfg_path.exists():
        print(f"FAIL: runner-config.json missing at {cfg_path}", file=sys.stderr)
        return 2

    failures: list[str] = []

    async with Client(mcp) as client:
        # 1. list_targets -> 5 targets with expected names.
        result = await client.call_tool("list_targets", {}, raise_on_error=False)
        if _is_error(result):
            failures.append(f"list_targets returned isError: {_block_text(result)!r}")
        else:
            try:
                payload = json.loads(_block_text(result))
            except json.JSONDecodeError as e:
                failures.append(f"list_targets returned non-JSON payload: {e}")
            else:
                targets = payload.get("targets", [])
                names = {t["name"] for t in targets}
                if len(targets) != 5:
                    failures.append(
                        f"list_targets returned {len(targets)} targets, expected 5"
                    )
                if names != EXPECTED_TARGETS:
                    failures.append(
                        f"list_targets returned names {names}, expected {EXPECTED_TARGETS}"
                    )
                else:
                    print(f"OK  list_targets -> 5 targets: {sorted(names)}")

        # 2. run_command echo -> exit 0 + stdout contains the marker.
        result = await client.call_tool(
            "run_command",
            {"cmd": "echo hello-from-mcp", "timeout_s": 10},
            raise_on_error=False,
        )
        if _is_error(result):
            failures.append(f"run_command(echo) returned isError: {_block_text(result)!r}")
        else:
            try:
                payload = json.loads(_block_text(result))
            except json.JSONDecodeError as e:
                failures.append(f"run_command(echo) returned non-JSON: {e}")
            else:
                if payload.get("exit_code") != 0:
                    failures.append(
                        f"run_command(echo) exit_code={payload.get('exit_code')}, expected 0"
                    )
                elif "hello-from-mcp" not in payload.get("stdout", ""):
                    failures.append(
                        f"run_command(echo) stdout missing 'hello-from-mcp': {payload.get('stdout')!r}"
                    )
                else:
                    print(
                        f"OK  run_command(echo) -> exit_code=0, stdout contains 'hello-from-mcp'"
                    )

        # 3. run_command failing -> isError=True.
        result = await client.call_tool(
            "run_command",
            {"cmd": "bash -c 'exit 9'"},
            raise_on_error=False,
        )
        if not _is_error(result):
            failures.append("run_command(exit 9) returned isError=False, expected True")
        else:
            print("OK  run_command(bash -c 'exit 9') -> isError=True")

    if failures:
        print("\nFAIL:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("\nALL SMOKE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))