#!/usr/bin/env python3
"""Validate simplified Infiapp Lambda agent specs."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from repo_tools.common import iter_agent_dirs, load_json, repo_relative
from repo_tools.python_dependencies import (
    load_pinned_python_dependencies,
    validate_dependency_names,
)

VALID_CONNECTIVITY = {"internal", "external"}
AGENT_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
REQUIRED_FIELDS = {
    "name": str,
    "description": str,
    "connectivity": str,
    "required_dependencies": list,
}
REQUIRED_HANDLER_PATH = Path("code") / "handler.py"


def defines_lambda_handler(handler_path: Path) -> bool:
    try:
        tree = ast.parse(handler_path.read_text(encoding="utf-8"))
    except SyntaxError:
        return False
    return any(
        isinstance(node, ast.FunctionDef) and node.name == "lambda_handler"
        for node in tree.body
    )


def validate_spec(agent_dir: Path, pinned_dependencies: dict[str, str]) -> list[str]:
    errors: list[str] = []
    spec_path = agent_dir / "spec.json"

    if not spec_path.exists():
        return [f"{repo_relative(spec_path)} is missing"]

    try:
        spec = load_json(spec_path)
    except ValueError as exc:
        return [str(exc)]

    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in spec:
            errors.append(f"{repo_relative(spec_path)}: missing '{field}'")
            continue
        if not isinstance(spec[field], expected_type):
            errors.append(
                f"{repo_relative(spec_path)}: '{field}' must be {expected_type.__name__}"
            )

    extra_fields = sorted(set(spec) - set(REQUIRED_FIELDS))
    if extra_fields:
        errors.append(f"{repo_relative(spec_path)}: unexpected field(s): {extra_fields}")

    name = spec.get("name")
    if isinstance(name, str):
        if name != agent_dir.name:
            errors.append(f"{repo_relative(spec_path)}: name must match folder '{agent_dir.name}'")
        if not AGENT_NAME_RE.fullmatch(name):
            errors.append(f"{repo_relative(spec_path)}: name must be lowercase snake_case")

    description = spec.get("description")
    if isinstance(description, str) and not description.strip():
        errors.append(f"{repo_relative(spec_path)}: description must not be empty")

    connectivity = spec.get("connectivity")
    if isinstance(connectivity, str) and connectivity not in VALID_CONNECTIVITY:
        errors.append(
            f"{repo_relative(spec_path)}: connectivity must be one of {sorted(VALID_CONNECTIVITY)}"
        )

    handler_path = agent_dir / REQUIRED_HANDLER_PATH
    if not handler_path.exists():
        errors.append(
            f"{repo_relative(handler_path)} must exist and define lambda_handler"
        )
    elif not defines_lambda_handler(handler_path):
        errors.append(f"{repo_relative(handler_path)} must define lambda_handler")

    errors.extend(
        f"{repo_relative(spec_path)}: {error}"
        for error in validate_dependency_names(
            spec.get("required_dependencies"),
            pinned_dependencies=pinned_dependencies,
            label="required_dependencies",
        )
    )

    if not (agent_dir / "code").is_dir():
        errors.append(f"{repo_relative(agent_dir / 'code')} must exist")
    if not (agent_dir / "test").is_dir():
        errors.append(f"{repo_relative(agent_dir / 'test')} must exist")

    return errors


def load_external_agents() -> list[dict[str, Any]]:
    agents: list[dict[str, Any]] = []
    for agent_dir in iter_agent_dirs():
        spec = load_json(agent_dir / "spec.json")
        if spec["connectivity"] == "external":
            agents.append(spec)
    return agents


def main() -> int:
    errors: list[str] = []
    try:
        pinned_dependencies = load_pinned_python_dependencies()
    except ValueError as exc:
        pinned_dependencies = {}
        errors.append(str(exc))

    agent_dirs = iter_agent_dirs()
    if not agent_dirs:
        errors.append("agents/: at least one agent is required")

    for agent_dir in agent_dirs:
        errors.extend(validate_spec(agent_dir, pinned_dependencies))

    if errors:
        print("Agent spec validation failed:\n")
        for error in errors:
            print(f"  ERROR: {error}")
        return 1

    print(f"Validated {len(agent_dirs)} agent spec(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
