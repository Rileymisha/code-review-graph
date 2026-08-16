"""Shared fixtures for runner-mcp tests."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """A temp project root with a 5-target runner-config.json written."""
    cfg = {
        "targets": {
            "test":        {"description": "Run pytest",          "cmd": "pytest -q"},
            "lint":        {"description": "Ruff check",          "cmd": "ruff check ."},
            "format":      {"description": "Ruff format --check", "cmd": "ruff format --check ."},
            "type-check":  {"description": "mypy",                "cmd": "mypy code_review_graph"},
            "build":       {"description": "hatch build",         "cmd": "hatch build"},
        }
    }
    (tmp_path / "runner-config.json").write_text(json.dumps(cfg))
    return tmp_path


@pytest.fixture
def project_env(project_root: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Set CRG_PROJECT_ROOT to the temp project root for the duration of the test."""
    monkeypatch.setenv("CRG_PROJECT_ROOT", str(project_root))
    return {"CRG_PROJECT_ROOT": str(project_root)}
