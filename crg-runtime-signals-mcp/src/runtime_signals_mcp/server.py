"""FastMCP server exposing 3 runtime-signal tools.

FastMCP 3.4.7 note: tools either:
- return the payload directly (``list`` for ``list_signals`` /
  ``profile_python``, ``dict`` for ``read_log``), letting FastMCP wrap it as
  the appropriate structured_content / text content; or
- return ``ToolResult(content=..., is_error=True)`` to flag a tool error.

Avoid wrapping payloads manually as content blocks ``[{"type":"text", ...}]``
- FastMCP would double-wrap them, breaking the JSON content stream.
"""
from __future__ import annotations

import asyncio
import logging

from fastmcp import FastMCP
from fastmcp.tools.tool import ToolResult

from runtime_signals_mcp import profiler, signals

logger = logging.getLogger(__name__)

mcp = FastMCP("crg-runtime-signals-mcp")


def _err(message: str) -> ToolResult:
    """Build an isError ToolResult carrying a single human-readable text block."""
    return ToolResult(content=f"ERROR: {message}", is_error=True)


def _to_dict(item) -> dict:
    return {
        "kind": item.kind,
        "path_or_pid": item.path_or_pid,
        "size_bytes": item.size_bytes,
        "mtime": item.mtime,
        "cmdline": item.cmdline,
        "rss_kb": item.rss_kb,
    }


@mcp.tool()
async def list_signals(kind: str | None = None) -> list[dict]:
    """Discover host runtime signals.

    Args:
        kind: "log" | "process" | None (both).

    Returns:
        JSON array of SignalItem dicts (kind, path_or_pid, size_bytes, mtime, cmdline, rss_kb).
    """
    try:
        items = await asyncio.to_thread(signals.list_signals, kind)
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        return _err(f"list_signals failed: {type(e).__name__}: {e}")
    return [_to_dict(it) for it in items]


@mcp.tool()
async def read_log(path: str, lines: int = 100) -> dict:
    """Read last `lines` lines of a file, truncated to 200 lines / 32 KB.

    Returns:
        JSON object {path, truncated, lines: [{line, text}]}.
    """
    try:
        result = await asyncio.to_thread(signals.read_log, path, lines)
    except FileNotFoundError:
        return _err(f"file not found: {path}")
    except IsADirectoryError:
        return _err(f"path is not a regular file: {path}")
    except PermissionError:
        return _err(f"permission denied: {path}")
    except Exception as e:
        return _err(f"read_log failed: {type(e).__name__}: {e}")
    return result


@mcp.tool()
async def profile_python(pid: int, duration_s: int = 5) -> list[dict]:
    """Profile a Python process via py-spy for `duration_s` seconds.

    Returns:
        JSON array of {function, self_pct, cum_pct} top-N entries.
    """
    try:
        result = await asyncio.to_thread(profiler.profile_python, pid, duration_s)
    except FileNotFoundError as e:
        return _err(str(e))
    except Exception as e:
        # Includes subprocess.CalledProcessError, OSError, etc.
        msg = str(e) if str(e) else f"{type(e).__name__}"
        return _err(f"profile_python failed: {msg}")
    return result
