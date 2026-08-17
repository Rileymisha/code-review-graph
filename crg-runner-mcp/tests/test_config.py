"""Tests for runner_mcp.config.load_targets."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from runner_mcp.config import Target, load_targets


def _write_cfg(root: Path, payload: dict) -> Path:
    cfg_path = root / "runner-config.json"
    cfg_path.write_text(json.dumps(payload))
    return cfg_path


def test_load_targets_returns_targets(tmp_path: Path) -> None:
    _write_cfg(tmp_path, {
        "targets": {
            "test": {"description": "Run pytest", "cmd": "pytest -q"},
            "lint": {"description": "Ruff", "cmd": "ruff check ."},
        },
    })
    result = load_targets(tmp_path)
    assert result == {
        "test":  Target(name="test",  description="Run pytest", cmd="pytest -q"),
        "lint":  Target(name="lint",  description="Ruff",       cmd="ruff check ."),
    }


def test_load_targets_empty_targets(tmp_path: Path) -> None:
    _write_cfg(tmp_path, {"targets": {}})
    assert load_targets(tmp_path) == {}


def test_load_targets_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_targets(tmp_path)


def test_load_targets_missing_targets_key_raises(tmp_path: Path) -> None:
    _write_cfg(tmp_path, {"other": {}})
    with pytest.raises(KeyError):
        load_targets(tmp_path)


def test_load_targets_missing_description_raises(tmp_path: Path) -> None:
    _write_cfg(tmp_path, {"targets": {"foo": {"cmd": "echo"}}})
    with pytest.raises(KeyError):
        load_targets(tmp_path)
