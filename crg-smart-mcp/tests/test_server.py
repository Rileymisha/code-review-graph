"""In-process FastMCP Client smoke for crg-smart-mcp."""
from __future__ import annotations

import json
from unittest import mock

import pytest
from fastmcp import Client

from crg_smart_mcp.server import mcp


pytestmark = pytest.mark.asyncio


def _payload_from_text(text: str) -> dict | str:
    """FastMCP 3.x wraps a list[dict] tool result as JSON of a content-block list.

    With fastmcp 3.4.7, content[0].text is the JSON-serialized content list
    (e.g. '[{"type":"text","text":"{...payload...}"}]'), so unwrap the inner
    text before parsing. If the text is already the payload JSON (older/newer
    fastmcp wrapping), return it as-is.
    """
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text
    if (
        isinstance(parsed, list)
        and len(parsed) == 1
        and isinstance(parsed[0], dict)
        and "text" in parsed[0]
    ):
        inner = parsed[0]["text"]
        try:
            return json.loads(inner)
        except json.JSONDecodeError:
            return inner
    return parsed


async def _call(tool: str, args: dict, monkeypatch: pytest.MonkeyPatch) -> tuple[bool, dict | str, str | None]:
    """Call a tool in-process; return (is_error, payload, subprocess cmd)."""
    monkeypatch.setenv("OPENWEBUI_SMART_KEY", "k")
    fake_resp = mock.Mock()
    fake_resp.status = 200
    fake_resp.read.return_value = json.dumps({"choices": [{"message": {"content": "summary-text"}}]}).encode()
    fake_resp.__enter__ = mock.Mock(return_value=fake_resp)
    fake_resp.__exit__ = mock.Mock(return_value=False)
    fake_proc = mock.AsyncMock(
        communicate=mock.AsyncMock(return_value=(b"stdout-bytes", b"stderr-bytes")),
        returncode=0,
    )
    with mock.patch("asyncio.create_subprocess_exec", return_value=fake_proc) as m_exec, mock.patch(
        "urllib.request.urlopen", return_value=fake_resp
    ):
        client = Client(mcp)
        async with client:
            result = await client.call_tool(tool, args, raise_on_error=False)
    # run_command calls create_subprocess_exec("bash", "-lc", cmd, ...) -> args[2] is the cmd
    cmd = m_exec.call_args.args[2] if m_exec.call_args else None
    is_err = getattr(result, "is_error", False) or getattr(result, "isError", False)
    text = result.content[0].text if result.content else ""
    if is_err:
        return True, text, cmd
    return False, _payload_from_text(text), cmd


async def test_smart_run_happy(monkeypatch: pytest.MonkeyPatch) -> None:
    is_err, payload, _cmd = await _call("smart_run", {"cmd": "echo hi", "timeout_s": 5}, monkeypatch)
    assert is_err is False
    assert payload["summary"] == "summary-text"
    assert "raw" in payload
    assert "model" in payload


async def test_smart_run_test_uses_pytest(monkeypatch: pytest.MonkeyPatch) -> None:
    is_err, payload, cmd = await _call("smart_run_test", {"timeout_s": 5}, monkeypatch)
    assert is_err is False
    # Verify the captured command was "pytest -q"
    # (We mocked create_subprocess_exec, so args[2] is whatever run_command was called with)
    assert cmd == "pytest -q"
    assert "summary" in payload


async def test_smart_list_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    is_err, payload, _cmd = await _call("smart_list_signals", {"kind": "process"}, monkeypatch)
    assert is_err is False
    assert "summary" in payload
