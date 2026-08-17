"""Shared fixtures for runtime-signals-mcp tests."""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def tmp_log_dir(tmp_path: Path) -> Path:
    """A temp dir with two log files for list_signals log discovery."""
    (tmp_path / "app.log").write_text("line 1\nline 2\n")
    (tmp_path / "debug.txt").write_text("debug entry\n")
    return tmp_path
