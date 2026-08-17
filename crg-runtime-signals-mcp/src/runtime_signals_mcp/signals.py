"""Runtime signals: log discovery + tail + Python process list."""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

DEFAULT_LOG_PATHS: list[str] = ["/var/log", "/tmp", "$HOME/logs"]
DEFAULT_PROCESS_FILTERS: list[str] = [
    "python",
    "python3",
    "python3.10",
    "python3.11",
    "python3.12",
]
DEFAULT_LOG_GLOBS: list[str] = ["*.log", "*.txt", "*.out"]
DEFAULT_MAX_BYTES: int = 32 * 1024
DEFAULT_MAX_LINES: int = 200

# Rough average log line width, used only to approximate line numbers when the
# file is larger than max_bytes and we therefore never saw its beginning.
_AVG_LINE_WIDTH = 80


@dataclass
class SignalItem:
    kind: str                  # "log" | "process"
    path_or_pid: str           # absolute path for log; numeric pid for process
    size_bytes: int | None = None
    mtime: str | None = None   # ISO 8601, UTC
    cmdline: str | None = None
    rss_kb: int | None = None


def _expand(path: str) -> Path:
    """Expand ``$VAR``/``${VAR}`` and a leading ``~`` in a configured path."""
    return Path(os.path.expandvars(path)).expanduser()


def list_signals(kind: str | None = None, *, config: dict | None = None) -> list[SignalItem]:
    """Discover runtime signals.

    Args:
        kind: "log" | "process" | None (= both).
        config: optional override; if absent uses module defaults.

    Returns:
        List of SignalItem (unsorted).

    Raises:
        ValueError: unknown kind.
    """
    if kind not in (None, "log", "process"):
        raise ValueError(f"kind must be one of None, 'log', 'process'; got {kind!r}")

    cfg = config or {}
    log_paths = cfg.get("log_paths", DEFAULT_LOG_PATHS)
    log_globs = cfg.get("log_glob_patterns", DEFAULT_LOG_GLOBS)
    proc_filters = cfg.get("process_filters", DEFAULT_PROCESS_FILTERS)

    out: list[SignalItem] = []
    if kind in (None, "log"):
        out.extend(_list_logs(log_paths, log_globs))
    if kind in (None, "process"):
        out.extend(_list_python_processes(proc_filters))
    return out


def _list_logs(log_paths: Iterable[str], log_globs: Iterable[str]) -> list[SignalItem]:
    """Glob configured directories for log-ish files. Unreadable dirs are skipped."""
    out: list[SignalItem] = []
    seen: set[str] = set()
    globs = list(log_globs)
    for raw in log_paths:
        base = _expand(raw)
        try:
            if not base.is_dir():
                continue
        except OSError:
            continue
        for pat in globs:
            try:
                matches = list(base.glob(pat))
            except OSError:
                continue
            for f in matches:
                try:
                    if not f.is_file():
                        continue
                    st = f.stat()
                    resolved = str(f.resolve())
                except OSError:
                    continue
                if resolved in seen:
                    continue
                seen.add(resolved)
                out.append(
                    SignalItem(
                        kind="log",
                        path_or_pid=resolved,
                        size_bytes=st.st_size,
                        mtime=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                    )
                )
    return out


def _list_python_processes(filters: Iterable[str]) -> list[SignalItem]:
    """List Python-looking processes via ``ps``.

    Process discovery is best-effort: if ``ps`` is missing, fails, or is denied,
    we return an empty list rather than raising.
    """
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid=,comm=,rss=,args="],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, PermissionError, OSError):
        return []

    items: list[SignalItem] = []
    needles = tuple(filters)
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Format: "<pid> <comm> <rss> <args>"
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        pid_s, comm, rss_s, args = parts
        cmdline = args.strip()
        if needles and not any(n in cmdline or n in comm for n in needles):
            continue
        try:
            pid = int(pid_s)
            rss_kb = int(rss_s)
        except ValueError:
            continue
        items.append(
            SignalItem(
                kind="process",
                path_or_pid=str(pid),
                cmdline=cmdline,
                rss_kb=rss_kb,
            )
        )
    return items


def read_log(
    path: str,
    lines: int = 100,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_line_count: int = DEFAULT_MAX_LINES,
) -> dict:
    """Read the last ``lines`` lines of a file, capped by max_bytes / max_line_count.

    Returns a dict with keys ``path``, ``truncated`` and ``lines`` (a list of
    ``{"line": int, "text": str}``). ``truncated`` is True when anything was cut:
    either the byte tail did not cover the whole file, or lines were dropped from
    the front of the requested window.

    Line numbers are exact whenever the byte tail reached the start of the file.
    For larger files the leading line count is approximated from the skipped byte
    offset divided by an average line width — good enough for a log tail, and it
    avoids reading the whole file.

    Raises FileNotFoundError / IsADirectoryError / PermissionError / OSError for
    the caller to map to an MCP isError response.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"file not found: {path}")
    if p.is_dir():
        raise IsADirectoryError(f"path is a directory: {path}")
    if not p.is_file():
        raise OSError(f"path is not a regular file: {path}")

    # Read the tail (last max_bytes bytes), then split into lines.
    # PermissionError and other OSErrors propagate to the caller.
    size = p.stat().st_size
    offset = max(0, size - max_bytes)
    with p.open("rb") as fh:
        if offset:
            fh.seek(offset)
        raw_bytes = fh.read()

    text = raw_bytes.decode("utf-8", errors="replace")
    chunk_lines = text.splitlines()
    if offset and chunk_lines:
        # The first line of the chunk is very likely a partial line; drop it.
        chunk_lines = chunk_lines[1:]

    keep = min(lines, max_line_count)
    keep = max(keep, 0)
    kept = chunk_lines[-keep:] if keep else []
    dropped_from_chunk = len(chunk_lines) - len(kept)
    truncated = offset > 0 or dropped_from_chunk > 0

    if offset:
        base = max(1, offset // _AVG_LINE_WIDTH)
    else:
        base = 1
    start_no = base + dropped_from_chunk

    out_lines = [{"line": start_no + i, "text": ln} for i, ln in enumerate(kept)]
    return {"path": str(p.resolve()), "truncated": truncated, "lines": out_lines}
