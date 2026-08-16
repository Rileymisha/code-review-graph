"""Load and parse runner-config.json from a project root."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


CONFIG_FILENAME = "runner-config.json"


@dataclass(frozen=True)
class Target:
    """One runnable target defined in runner-config.json."""
    name: str
    description: str
    cmd: str


def load_targets(root: Path) -> dict[str, Target]:
    """Read $root/runner-config.json and return {name: Target}.

    Raises:
        FileNotFoundError: if runner-config.json does not exist.
        json.JSONDecodeError: if the file is not valid JSON.
        KeyError: if a required field is missing.
    """
    cfg_path = root / CONFIG_FILENAME
    with cfg_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    out: dict[str, Target] = {}
    for name, spec in raw["targets"].items():
        out[name] = Target(
            name=name,
            description=spec["description"],
            cmd=spec["cmd"],
        )
    return out
