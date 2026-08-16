"""Tests for runtime_signals_mcp.profiler."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path
from unittest import mock

import pytest

from runtime_signals_mcp.profiler import profile_python


def test_profile_python_py_spy_missing_raises(tmp_path: Path) -> None:
    # Pretend py-spy is not on PATH
    with mock.patch("shutil.which", return_value=None):
        with pytest.raises(FileNotFoundError) as exc_info:
            profile_python(1234, duration_s=1)
        assert "py-spy" in str(exc_info.value)


def test_profile_python_negative_pid_raises() -> None:
    if not shutil.which("py-spy"):
        pytest.skip("py-spy not installed")
    with pytest.raises(FileNotFoundError):
        profile_python(-1, duration_s=1)


def test_profile_python_nonexistent_pid_raises(tmp_path: Path) -> None:
    if not shutil.which("py-spy"):
        pytest.skip("py-spy not installed")
    # PID 999999 is almost certainly unused on any host
    with pytest.raises((FileNotFoundError, Exception)):
        profile_python(999999, duration_s=1)


def test_profile_python_returns_top_n(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock the subprocess.run call to return fake py-spy output and verify parsing."""
    from runtime_signals_mcp import profiler

    fake_output = (
        'main          30.0   30.0\n'
        'foo           20.0   50.0\n'
        'bar           10.0   60.0\n'
    )
    fake_completed = mock.Mock()
    fake_completed.stdout = fake_output
    fake_completed.returncode = 0

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/py-spy" if name == "py-spy" else None)

    with mock.patch("subprocess.run", return_value=fake_completed) as mocked:
        result = profiler.profile_python(1234, duration_s=2)

    assert len(result) == 3
    assert result[0] == {"function": "main", "self_pct": 30.0, "cum_pct": 30.0}
    assert result[1] == {"function": "foo", "self_pct": 20.0, "cum_pct": 50.0}
    assert result[2] == {"function": "bar", "self_pct": 10.0, "cum_pct": 60.0}

    # Verify py-spy invocation shape
    call_args = mocked.call_args
    assert call_args[0][0][0] == "py-spy"
    assert "dump" in call_args[0][0]
    assert "--pid" in call_args[0][0]
    assert call_args.kwargs.get("capture_output") is True
    assert call_args.kwargs.get("text") is True
    assert call_args.kwargs.get("check") is True
