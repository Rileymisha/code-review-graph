"""Tests for runtime_signals_mcp.signals."""
from __future__ import annotations

from pathlib import Path

import pytest

from runtime_signals_mcp.signals import (
    DEFAULT_LOG_GLOBS,
    DEFAULT_LOG_PATHS,
    DEFAULT_PROCESS_FILTERS,
    SignalItem,
    list_signals,
    read_log,
)


def test_read_log_returns_last_n_lines(tmp_path: Path) -> None:
    log = tmp_path / "test.log"
    log.write_text("\n".join(f"line {i}" for i in range(1, 101)))
    result = read_log(str(log), lines=10)
    assert result["truncated"] is True
    assert result["path"] == str(log)
    last = result["lines"][-1]
    assert last["line"] == 100
    assert last["text"] == "line 100"


def test_read_log_short_file_no_truncation(tmp_path: Path) -> None:
    log = tmp_path / "short.log"
    log.write_text("only line\n")
    result = read_log(str(log), lines=100)
    assert result["truncated"] is False
    assert len(result["lines"]) == 1
    assert result["lines"][0]["line"] == 1
    assert result["lines"][0]["text"] == "only line"


def test_read_log_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_log(str(tmp_path / "nope.log"), lines=10)


def test_read_log_directory_raises(tmp_path: Path) -> None:
    with pytest.raises(IsADirectoryError):
        read_log(str(tmp_path), lines=10)


def test_read_log_permission_denied(tmp_path: Path) -> None:
    log = tmp_path / "noperm.log"
    log.write_text("x")
    log.chmod(0o000)
    try:
        with pytest.raises(PermissionError):
            read_log(str(log), lines=10)
    finally:
        log.chmod(0o644)  # restore for cleanup


def test_list_signals_log_kind_finds_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log1 = tmp_path / "app.log"
    log1.write_text("hello")
    log2 = tmp_path / "other.txt"
    log2.write_text("world")
    monkeypatch.setattr(
        "runtime_signals_mcp.signals.DEFAULT_LOG_PATHS", [str(tmp_path)]
    )
    monkeypatch.setattr(
        "runtime_signals_mcp.signals.DEFAULT_LOG_GLOBS", ["*.log", "*.txt"]
    )
    items = list_signals(kind="log")
    paths = {item.path_or_pid for item in items if item.kind == "log"}
    assert str(log1) in paths
    assert str(log2) in paths


def test_list_signals_unknown_kind_raises() -> None:
    with pytest.raises(ValueError):
        list_signals(kind="bogus")


def test_signal_item_dataclass_shape() -> None:
    item = SignalItem(
        kind="log",
        path_or_pid="/tmp/x.log",
        size_bytes=123,
        mtime="2026-08-16T00:00:00",
        cmdline=None,
        rss_kb=None,
    )
    assert item.kind == "log"
    assert item.size_bytes == 123


def test_defaults_are_verbatim() -> None:
    assert DEFAULT_LOG_PATHS == ["/var/log", "/tmp", "$HOME/logs"]
    assert DEFAULT_LOG_GLOBS == ["*.log", "*.txt", "*.out"]
    assert DEFAULT_PROCESS_FILTERS == [
        "python",
        "python3",
        "python3.10",
        "python3.11",
        "python3.12",
    ]


def test_list_signals_process_kind_returns_process_items() -> None:
    items = list_signals(kind="process")
    assert all(item.kind == "process" for item in items)
    for item in items:
        assert item.path_or_pid.isdigit()
