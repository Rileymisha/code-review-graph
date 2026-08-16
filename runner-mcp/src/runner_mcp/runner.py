"""Execute shell commands with truncation + artifact logging."""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

LOG_DIR = Path("/tmp/runner-mcp")
TRUNCATE_LINES = 200
TRUNCATE_BYTES = 32 * 1024  # 32 KiB


@dataclass
class RunResult:
    """Outcome of a single command execution."""
    exit_code: int
    duration_ms: int
    stdout: str
    stderr: str
    log_file: Optional[Path]
    truncated: bool


def _truncate(text: str) -> tuple[str, bool]:
    """Truncate to TRUNCATE_LINES lines and TRUNCATE_BYTES bytes (whichever first).

    Returns (truncated_text, was_truncated).
    """
    truncated = False
    # Enforce byte cap first (cheap path).
    if len(text.encode("utf-8")) > TRUNCATE_BYTES:
        text = text.encode("utf-8")[:TRUNCATE_BYTES].decode("utf-8", errors="ignore")
        truncated = True
    # Then line cap.
    lines = text.splitlines()
    if len(lines) > TRUNCATE_LINES:
        text = "\n".join(lines[:TRUNCATE_LINES])
        truncated = True
    return text, truncated


async def run(cmd: str, cwd: Path, *, timeout_s: int, log_dir: Path = LOG_DIR) -> RunResult:
    """Execute `cmd` via `bash -lc` inside `cwd`.

    Args:
        cmd: The shell command to execute.
        cwd: Working directory for the subprocess.
        timeout_s: Maximum runtime in seconds. Raise asyncio.TimeoutError on hit.
        log_dir: Where to write overflow logs. Created if missing.

    Returns:
        RunResult capturing stdout/stderr (possibly truncated), exit_code, and the
        log_file path when truncation occurred.

    Raises:
        asyncio.TimeoutError: if the command exceeded timeout_s.
    """
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

    log_file: Optional[Path] = None
    if truncated:
        log_file = log_dir / f"{uuid.uuid4().hex}.log"
        log_file.write_text(
            f"=== command ===\n{cwd}$ {cmd}\n\n"
            f"=== stdout ===\n{full_stdout}\n\n"
            f"=== stderr ===\n{full_stderr}\n\n"
            f"=== result ===\nexit_code: {proc.returncode}\nduration_ms: {duration_ms}\n",
            encoding="utf-8",
        )

    return RunResult(
        exit_code=proc.returncode,
        duration_ms=duration_ms,
        stdout=truncated_stdout,
        stderr=truncated_stderr,
        log_file=log_file,
        truncated=truncated,
    )


def cleanup_stale_logs(log_dir: Path, *, max_age_days: int = 7) -> int:
    """Delete *.log under log_dir whose mtime is older than max_age_days. Returns count."""
    if not log_dir.exists():
        return 0
    cutoff = time.time() - max_age_days * 86400
    deleted = 0
    for path in log_dir.glob("*.log"):
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            continue
        if mtime < cutoff:
            try:
                path.unlink()
                deleted += 1
            except FileNotFoundError:
                pass
    return deleted
