"""Shared helpers for repository tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENTS_DIR = REPO_ROOT / "agents"
DYNAMODB_DIR = REPO_ROOT / "dynamodb"
WEBUI_DIR = REPO_ROOT / "webUI"
GENERATED_DYNAMODB_PATH = AGENTS_DIR / "shared_utils" / "generated" / "dynamodb.py"
GENERATED_WEB_AGENTS_PATH = WEBUI_DIR / "src" / "lib" / "generated" / "agents.ts"
GENERATED_WEB_MOCKS_PATH = WEBUI_DIR / "src" / "lib" / "generated" / "mockAgents.ts"


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return data


def iter_agent_dirs() -> list[Path]:
    if not AGENTS_DIR.exists():
        return []
    return sorted(
        path
        for path in AGENTS_DIR.iterdir()
        if path.is_dir()
        and path.name not in {"shared_utils", "__pycache__"}
        and not path.name.startswith(".")
    )


def iter_table_paths() -> list[Path]:
    if not DYNAMODB_DIR.exists():
        return []
    return sorted(DYNAMODB_DIR.glob("*/*.json"))


def repo_relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()
