"""In-process FastMCP Client smoke tests for runtime-signals-mcp server."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastmcp import Client

from runtime_signals_mcp.server import mcp


pytestmark = pytest.mark.asyncio


async def _call(tool: str, args: dict) -> tuple[bool, dict | str]:
    """Call a tool via in-process FastMCP client. Returns (isError, parsed_json_or_raw)."""
    # No CRG_PROJECT_ROOT env binding for this server.
    client = Client(mcp)
    async with client:
        result = await client.call_tool(tool, args, raise_on_error=False)
    is_err = getattr(result, "is_error", False) or getattr(result, "isError", False)
    text = ""
    if result.content:
        text = result.content[0].text
    if is_err:
        return True, text
    try:
        return False, json.loads(text)
    except json.JSONDecodeError:
        return False, text


async def test_list_signals_returns_array(tmp_log_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "runtime_signals_mcp.signals.DEFAULT_LOG_PATHS", [str(tmp_log_dir)]
    )
    monkeypatch.setattr(
        "runtime_signals_mcp.signals.DEFAULT_LOG_GLOBS", ["*.log", "*.txt"]
    )
    is_err, payload = await _call("list_signals", {"kind": "log"})
    assert is_err is False
    assert isinstance(payload, list)
    paths = {item["path_or_pid"] for item in payload}
    assert any("app.log" in p for p in paths)


async def test_read_log_success(tmp_path: Path) -> None:
    log = tmp_path / "x.log"
    log.write_text("a\nb\nc\n")
    is_err, payload = await _call("read_log", {"path": str(log), "lines": 2})
    assert is_err is False
    assert payload["path"] == str(log.resolve())
    last = payload["lines"][-1]
    assert last["text"] in ("b", "c")


async def test_read_log_missing_file_iserror(tmp_path: Path) -> None:
    is_err, raw = await _call("read_log", {"path": str(tmp_path / "nope.log"), "lines": 10})
    assert is_err is True
    assert "not found" in raw.lower() or "No such file" in raw


async def test_profile_python_invalid_pid_iserror() -> None:
    is_err, raw = await _call("profile_python", {"pid": -1, "duration_s": 1})
    assert is_err is True
    assert "invalid" in raw.lower() or "py-spy" in raw.lower() or "pid" in raw.lower()
