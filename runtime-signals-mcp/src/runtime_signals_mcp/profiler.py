"""Python process profiler via py-spy."""
from __future__ import annotations

import shutil
import subprocess
from typing import Any


def _find_py_spy(py_spy_path: str | None) -> str:
    if py_spy_path:
        return py_spy_path
    found = shutil.which("py-spy")
    if not found:
        raise FileNotFoundError(
            "py-spy not found on PATH; install via `pip install py-spy` "
            "or your system package manager"
        )
    return found


def _pid_alive(pid: int) -> None:
    if pid <= 0:
        raise FileNotFoundError(f"invalid pid: {pid}")
    try:
        subprocess.run(["kill", "-0", str(pid)], capture_output=True, check=True)
    except subprocess.CalledProcessError as e:
        raise FileNotFoundError(f"pid {pid} not found or not accessible") from e


def _parse_py_spy_output(raw: str) -> list[dict[str, Any]]:
    """Parse `py-spy dump` output. Format per line: <name> <self%> <cum%>."""
    out: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        name, self_pct_s, cum_pct_s = parts[0], parts[1], parts[2]
        try:
            self_pct = float(self_pct_s.rstrip("%"))
            cum_pct = float(cum_pct_s.rstrip("%"))
        except ValueError:
            continue
        out.append({"function": name, "self_pct": self_pct, "cum_pct": cum_pct})
    return out


def profile_python(
    pid: int,
    duration_s: int = 5,
    *,
    py_spy_path: str | None = None,
) -> list[dict[str, Any]]:
    """Profile a Python process via py-spy dump.

    Args:
        pid: Target process id (must be a Python process for meaningful output).
        duration_s: Sampling duration in seconds.
        py_spy_path: Override py-spy binary location (defaults to shutil.which).

    Returns:
        List of {function, self_pct, cum_pct} dicts.

    Raises:
        FileNotFoundError: pid invalid / not found, or py-spy not installed.
        subprocess.CalledProcessError: py-spy failed (e.g. ptrace denied).
    """
    py_spy = _find_py_spy(py_spy_path)
    _pid_alive(pid)

    # Invoke by the bare name (or explicit override) so callers' PATH resolution
    # is honored; ``_find_py_spy`` only validates presence.
    binary = py_spy_path if py_spy_path else "py-spy"
    result = subprocess.run(
        [binary, "dump", "--pid", str(pid), "--duration", str(duration_s)],
        capture_output=True,
        text=True,
        check=True,
    )
    return _parse_py_spy_output(result.stdout)
