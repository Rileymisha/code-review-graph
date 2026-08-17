"""Tests for crg_smart_mcp.runner."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from unittest import mock

import pytest

from crg_smart_mcp.runner import CmdResult, run_command, MAX_LINES, MAX_BYTES


@pytest.mark.asyncio
async def test_short_output_not_truncated(tmp_path: Path) -> None:
    r = await run_command("echo hi", cwd=tmp_path, log_dir=tmp_path / "logs")
    assert r.exit_code == 0
    assert "hi" in r.stdout
    assert r.truncated is False
    assert r.log_file is None


@pytest.mark.asyncio
async def test_long_output_truncated_writes_log(tmp_path: Path) -> None:
    big = "x" * (MAX_BYTES + 1024)
    r = await run_command(
        f"python -c \"print('{big}')\"",
        cwd=tmp_path, timeout_s=10, log_dir=tmp_path / "logs",
    )
    assert r.exit_code == 0
    assert r.truncated is True
    assert r.log_file is not None
    assert r.log_file.exists()
    assert r.log_file.read_text().count("x") >= MAX_BYTES + 1024  # full output preserved


@pytest.mark.asyncio
async def test_too_many_lines_truncated_to_200(tmp_path: Path) -> None:
    r = await run_command(
        "python -c \"print('\\n'.join(['x']*500))\"",
        cwd=tmp_path, timeout_s=10, log_dir=tmp_path / "logs",
    )
    assert r.truncated is True
    assert r.stdout.count("\n") <= MAX_LINES


@pytest.mark.asyncio
async def test_timeout_raises(tmp_path: Path) -> None:
    with pytest.raises(asyncio.TimeoutError):
        await run_command("sleep 10", cwd=tmp_path, timeout_s=1, log_dir=tmp_path / "logs")


@pytest.mark.asyncio
async def test_nonzero_exit_returns_result(tmp_path: Path) -> None:
    r = await run_command("bash -c 'exit 7'", cwd=tmp_path, log_dir=tmp_path / "logs")
    assert r.exit_code == 7
    assert r.truncated is False