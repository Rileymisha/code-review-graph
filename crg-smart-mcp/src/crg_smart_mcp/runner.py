"""Minimal subprocess runner: 200-line / 32KB truncation with log overflow."""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

MAX_LINES = 200
MAX_BYTES = 32 * 1024


@dataclass
class CmdResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    log_file: Path | None
    truncated: bool


def _truncate(text: str) -> tuple[str, bool]:
    truncated = False
    if len(text.encode("utf-8")) > MAX_BYTES:
        text = text.encode("utf-8")[:MAX_BYTES].decode("utf-8", errors="ignore")
        truncated = True
    lines = text.splitlines()
    if len(lines) > MAX_LINES:
        text = "\n".join(lines[:MAX_LINES])
        truncated = True
    return text, truncated


async def run_command(
    cmd: str,
    cwd: Path,
    *,
    timeout_s: int = 120,
    log_dir: Path | None = None,
) -> CmdResult:
    """Run `cmd` via `bash -lc` in `cwd`; truncate 200-line/32KB; overflow to log_dir."""
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        "bash", "-lc", cmd,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    duration_ms = int((time.monotonic() - started) * 1000)

    full_stdout = stdout_b.decode("utf-8", errors="replace")
    full_stderr = stderr_b.decode("utf-8", errors="replace")
    truncated_stdout, t1 = _truncate(full_stdout)
    truncated_stderr, t2 = _truncate(full_stderr)
    truncated = t1 or t2

    log_file: Path | None = None
    if truncated and log_dir is not None:
        log_file = log_dir / f"{uuid.uuid4().hex}.log"
        log_file.write_text(
            f"=== command ===\n{cwd}$ {cmd}\n\n"
            f"=== stdout ===\n{full_stdout}\n\n"
            f"=== stderr ===\n{full_stderr}\n\n"
            f"=== result ===\nexit_code: {proc.returncode}\nduration_ms: {duration_ms}\n",
            encoding="utf-8",
        )

    return CmdResult(
        exit_code=proc.returncode if proc.returncode is not None else -1,
        duration_ms=duration_ms,
        stdout=truncated_stdout,
        stderr=truncated_stderr,
        log_file=log_file,
        truncated=truncated,
    )