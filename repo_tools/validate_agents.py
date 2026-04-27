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
    "description": str,
    "connectivity": str,
    "memory_mb": int,
    "timeout_seconds": int,
    "ephemeral_storage_mb": int,
    "api_context": list,
    "required_dependencies": list,
}
REQUIRED_HANDLER_PATH = Path("code") / "handler.py"
MEMORY_MB_RANGE = (128, 10_240)
TIMEOUT_SECONDS_RANGE = (1, 900)
EPHEMERAL_STORAGE_MB_RANGE = (512, 10_240)
CALL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
SCHEMA_TYPES = {"String", "Number", "Boolean", "Binary", "Map", "List", "Any", "Null"}


def defines_lambda_handler(handler_path: Path) -> bool:
    try:
        tree = ast.parse(handler_path.read_text(encoding="utf-8"))
    except SyntaxError:
        return False
    return any(
        isinstance(node, ast.FunctionDef) and node.name == "lambda_handler"
        for node in tree.body
    )


def validate_schema_type(path: Path, value: str, label: str) -> list[str]:
    errors: list[str] = []
    for part in [item.strip() for item in value.split("|")]:
        if not part:
            errors.append(f"{repo_relative(path)}: {label} has an empty union member")
        elif part.startswith("Literal[") and part.endswith("]"):
            if not part.removeprefix("Literal[").removesuffix("]"):
                errors.append(f"{repo_relative(path)}: {label} has an empty Literal[]")
        elif part not in SCHEMA_TYPES:
            errors.append(f"{repo_relative(path)}: {label} type must be one of {sorted(SCHEMA_TYPES)}")
    return errors


def validate_schema(path: Path, schema: object, label: str) -> list[str]:
    if isinstance(schema, str):
        return validate_schema_type(path, schema, label)

    if isinstance(schema, list):
        if len(schema) != 1:
            return [f"{repo_relative(path)}: {label} array schema must contain exactly one item schema"]
        return validate_schema(path, schema[0], f"{label}[0]")

    if isinstance(schema, dict):
        errors: list[str] = []
        for field_name, field_schema in schema.items():
            if not isinstance(field_name, str) or not field_name:
                errors.append(f"{repo_relative(path)}: {label} field names must be non-empty strings")
                continue
            clean_name = field_name[:-1] if field_name.endswith("?") else field_name
            if not clean_name:
                errors.append(f"{repo_relative(path)}: {label} field names must not be only '?'")
                continue
            errors.extend(validate_schema(path, field_schema, f"{label}.{clean_name}"))
        return errors

    return [f"{repo_relative(path)}: {label} must be a type string, object, or single-item array"]


def validate_api_context(path: Path, value: object) -> list[str]:
    if not isinstance(value, list):
        return [f"{repo_relative(path)}: api_context must be a list"]
    if not value:
        return [f"{repo_relative(path)}: api_context must contain at least one call"]

    errors: list[str] = []
    seen_calls: set[str] = set()
    for index, entry in enumerate(value):
        label = f"api_context[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{repo_relative(path)}: {label} must be an object")
            continue
        required_fields = {"call": str, "description": str, "input": dict, "output": dict}
        for field, expected_type in required_fields.items():
            if field not in entry:
                errors.append(f"{repo_relative(path)}: {label} missing '{field}'")
                continue
            if not isinstance(entry[field], expected_type):
                errors.append(f"{repo_relative(path)}: {label}.{field} must be {expected_type.__name__}")
        extra_fields = sorted(set(entry) - set(required_fields))
        if extra_fields:
            errors.append(f"{repo_relative(path)}: {label} has unexpected field(s): {extra_fields}")

        call = entry.get("call")
        if isinstance(call, str):
            if not CALL_NAME_RE.fullmatch(call):
                errors.append(f"{repo_relative(path)}: {label}.call must be lowercase snake_case")
            if call in seen_calls:
                errors.append(f"{repo_relative(path)}: duplicate api_context call '{call}'")
            seen_calls.add(call)

        description = entry.get("description")
        if isinstance(description, str) and not description.strip():
            errors.append(f"{repo_relative(path)}: {label}.description must not be empty")

        if isinstance(entry.get("input"), dict):
            errors.extend(validate_schema(path, entry["input"], f"{label}.input"))
        if isinstance(entry.get("output"), dict):
            errors.extend(validate_schema(path, entry["output"], f"{label}.output"))

    return errors


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

    if not AGENT_NAME_RE.fullmatch(agent_dir.name):
        errors.append(f"{repo_relative(agent_dir)}: folder name must be lowercase snake_case")

    description = spec.get("description")
    if isinstance(description, str) and not description.strip():
        errors.append(f"{repo_relative(spec_path)}: description must not be empty")

    connectivity = spec.get("connectivity")
    if isinstance(connectivity, str) and connectivity not in VALID_CONNECTIVITY:
        errors.append(
            f"{repo_relative(spec_path)}: connectivity must be one of {sorted(VALID_CONNECTIVITY)}"
        )

    errors.extend(validate_api_context(spec_path, spec.get("api_context")))

    ranged_fields = {
        "memory_mb": MEMORY_MB_RANGE,
        "timeout_seconds": TIMEOUT_SECONDS_RANGE,
        "ephemeral_storage_mb": EPHEMERAL_STORAGE_MB_RANGE,
    }
    for field, (minimum, maximum) in ranged_fields.items():
        value = spec.get(field)
        if isinstance(value, int) and not minimum <= value <= maximum:
            errors.append(
                f"{repo_relative(spec_path)}: {field} must be between {minimum} and {maximum}"
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
            spec["name"] = agent_dir.name
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
