"""Tests for runner_mcp.runner."""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from runner_mcp.runner import (
    LOG_DIR,
    TRUNCATE_BYTES,
    TRUNCATE_LINES,
    RunResult,
    cleanup_stale_logs,
    run,
)


# ---------- truncation ----------

@pytest.mark.asyncio
async def test_short_output_not_truncated(tmp_path: Path) -> None:
    r = await run("echo hi", cwd=tmp_path, timeout_s=5, log_dir=tmp_path / "logs")
    assert r.exit_code == 0
    assert "hi" in r.stdout
    assert r.truncated is False
    assert r.log_file is None


@pytest.mark.asyncio
async def test_long_output_truncated_writes_log_file(tmp_path: Path) -> None:
    big = "x" * (TRUNCATE_BYTES + 1024)
    r = await run(
        f"python -c \"print('{big}')\"",
        cwd=tmp_path, timeout_s=10, log_dir=tmp_path / "logs",
    )
    assert r.exit_code == 0
    assert r.truncated is True
    assert r.log_file is not None
    assert r.log_file.exists()
    assert len(r.stdout.encode()) <= TRUNCATE_BYTES + 16


@pytest.mark.asyncio
async def test_truncated_logs_full_output(tmp_path: Path) -> None:
    big = "y" * (TRUNCATE_BYTES + 2048)
    r = await run(
        f"python -c \"print('{big}')\"",
        cwd=tmp_path, timeout_s=10, log_dir=tmp_path / "logs",
    )
    assert r.truncated is True
    assert r.log_file is not None
    full = r.log_file.read_text()
    assert len(full) >= TRUNCATE_BYTES + 1024


@pytest.mark.asyncio
async def test_many_lines_truncated_to_200(tmp_path: Path) -> None:
    r = await run(
        "python -c \"print('\\n'.join(['x'] * 500))\"",
        cwd=tmp_path, timeout_s=10, log_dir=tmp_path / "logs",
    )
    assert r.exit_code == 0
    assert r.truncated is True
    line_count = len(r.stdout.splitlines())
    assert line_count <= TRUNCATE_LINES


# ---------- exit code + stderr capture ----------

@pytest.mark.asyncio
async def test_nonzero_exit_returned_in_result(tmp_path: Path) -> None:
    r = await run("bash -c 'exit 7'", cwd=tmp_path, timeout_s=5, log_dir=tmp_path / "logs")
    assert r.exit_code == 7
    assert r.truncated is False


@pytest.mark.asyncio
async def test_stderr_captured(tmp_path: Path) -> None:
    r = await run("bash -c 'echo bad >&2; exit 1'", cwd=tmp_path, timeout_s=5, log_dir=tmp_path / "logs")
    assert r.exit_code == 1
    assert "bad" in r.stderr


# ---------- timeout ----------

@pytest.mark.asyncio
async def test_timeout_raises(tmp_path: Path) -> None:
    with pytest.raises(asyncio.TimeoutError):
        await run("sleep 10", cwd=tmp_path, timeout_s=1, log_dir=tmp_path / "logs")


# ---------- cleanup ----------

def test_cleanup_stale_logs_deletes_old_files(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    old = log_dir / "old.log"
    old.write_text("x")
    new = log_dir / "new.log"
    new.write_text("y")
    # Backdate old file to 8 days ago
    eight_days = time.time() - 8 * 86400
    import os
    os.utime(old, (eight_days, eight_days))

    deleted = cleanup_stale_logs(log_dir, max_age_days=7)
    assert deleted == 1
    assert not old.exists()
    assert new.exists()


def test_cleanup_stale_logs_no_old_files(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "fresh.log").write_text("z")
    assert cleanup_stale_logs(log_dir, max_age_days=7) == 0
