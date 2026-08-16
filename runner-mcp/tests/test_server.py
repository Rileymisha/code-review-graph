"""End-to-end tests via fastmcp.Client (in-process)."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path

import pytest
from fastmcp import Client

from runner_mcp.server import mcp


pytestmark = pytest.mark.asyncio


async def _call(tool: str, args: dict, project_env: dict) -> tuple[bool, dict]:
    """Invoke a tool via in-process FastMCP client. Return (isError, parsed_json_text)."""
    env = project_env
    # server.py reads CRG_PROJECT_ROOT from os.environ at call time.
    for k, v in env.items():
        os.environ[k] = v
    client = Client(mcp)
    async with client:
        # raise_on_error=False so isError is exposed on the CallToolResult
        # (default True would re-raise as ToolError before we can read it).
        result = await client.call_tool(tool, args, raise_on_error=False)
    is_error = getattr(result, "isError", False) or getattr(result, "is_error", False)
    if is_error:
        text = ""
        for block in result.content:
            text += block.text
        return True, {"raw": text}
    text = result.content[0].text
    return False, json.loads(text)


async def test_list_targets_returns_5(project_env):
    is_err, payload = await _call("list_targets", {}, project_env)
    assert is_err is False
    assert len(payload["targets"]) == 5
    names = {t["name"] for t in payload["targets"]}
    assert names == {"test", "lint", "format", "type-check", "build"}


async def test_run_command_echo(project_env):
    is_err, payload = await _call(
        "run_command", {"cmd": "echo hello-mcp"}, project_env,
    )
    assert is_err is False
    assert payload["exit_code"] == 0
    assert "hello-mcp" in payload["stdout"]


async def test_run_command_nonzero_iserror(project_env):
    is_err, payload = await _call(
        "run_command", {"cmd": "bash -c 'exit 9'"}, project_env,
    )
    assert is_err is True
    # The raw text must carry the structured exit_code=9 payload so LLM
    # agents can parse it consistently. Prefix is "ERROR: " per server._err_with_payload.
    assert "ERROR:" in payload["raw"]
    assert "exit_code=9" in payload["raw"]
    parsed = json.loads(payload["raw"].split("\n", 1)[1])
    assert parsed["exit_code"] == 9


async def test_run_command_timeout_iserror(project_env):
    is_err, payload = await _call(
        "run_command", {"cmd": "sleep 10", "timeout_s": 1}, project_env,
    )
    assert is_err is True
    assert "timed out" in payload["raw"].lower()


async def test_run_command_uses_project_root_as_default_cwd(project_env, project_root):
    is_err, payload = await _call(
        "run_command", {"cmd": "pwd"}, project_env,
    )
    assert is_err is False
    assert payload["exit_code"] == 0
    assert payload["stdout"].strip() == str(project_root)


async def test_run_command_truncates_and_writes_log(project_env, tmp_path: Path):
    big = "z" * (32 * 1024 + 4096)
    is_err, payload = await _call(
        "run_command",
        {"cmd": f"python -c \"import sys; sys.stdout.write('{big}')\""},
        project_env,
    )
    assert is_err is False
    assert payload["truncated"] is True
    assert payload["log_file"] is not None
    log_path = Path(payload["log_file"])
    assert log_path.exists()


async def test_list_targets_missing_cfg(project_env, monkeypatch):
    # Overwrite project_root fixture: nuke the cfg.
    root = Path(project_env["CRG_PROJECT_ROOT"])
    cfg = root / "runner-config.json"
    cfg.unlink()
    is_err, _ = await _call("list_targets", {}, project_env)
    assert is_err is True
