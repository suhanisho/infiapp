#!/usr/bin/env python3
"""Validate DynamoDB table specs and key backwards compatibility."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from repo_tools.common import (
    REPO_ROOT,
    TABLE_KEY_BASELINE_PATH,
    iter_table_paths,
    load_json,
    repo_relative,
)

VALID_ATTRIBUTE_TYPES = {"String", "Number", "Binary", "Boolean"}
VALID_KEY_TYPES = {"String", "Number", "Binary"}
INFERRED_OR_DEFAULTED_FIELDS = {"owner_agent", "billing_mode"}


def key_signature(table: dict[str, Any]) -> dict[str, Any]:
    primary_key = table["primary_key"]
    return {
        "table_name": table["table_name"],
        "partition_key": primary_key["partition_key"],
        "sort_key": primary_key.get("sort_key"),
    }


def validate_key(path: Path, key: object, label: str, *, required: bool = True) -> list[str]:
    if key is None and not required:
        return []
    if not isinstance(key, dict):
        return [f"{repo_relative(path)}: {label} must be an object"]

    errors: list[str] = []
    name = key.get("name")
    key_type = key.get("type")
    if not isinstance(name, str) or not name:
        errors.append(f"{repo_relative(path)}: {label}.name must be a non-empty string")
    if key_type not in VALID_KEY_TYPES:
        errors.append(
            f"{repo_relative(path)}: {label}.type must be one of {sorted(VALID_KEY_TYPES)}"
        )
    return errors


def validate_table(path: Path) -> list[str]:
    try:
        table = load_json(path)
    except ValueError as exc:
        return [str(exc)]

    errors: list[str] = []
    required_fields = {
        "table_name": str,
        "primary_key": dict,
        "attributes": dict,
    }
    for field, expected_type in required_fields.items():
        if field not in table:
            errors.append(f"{repo_relative(path)}: missing '{field}'")
            continue
        if not isinstance(table[field], expected_type):
            errors.append(f"{repo_relative(path)}: '{field}' must be {expected_type.__name__}")

    if errors:
        return errors

    extra_fields = sorted(set(table) - set(required_fields))
    inferred_fields = sorted(set(extra_fields) & INFERRED_OR_DEFAULTED_FIELDS)
    for field in inferred_fields:
        errors.append(f"{repo_relative(path)}: '{field}' is inferred/defaulted and must be omitted")
    for field in sorted(set(extra_fields) - INFERRED_OR_DEFAULTED_FIELDS):
        errors.append(f"{repo_relative(path)}: unexpected field '{field}'")

    primary_key = table["primary_key"]
    errors.extend(validate_key(path, primary_key.get("partition_key"), "partition_key"))
    errors.extend(validate_key(path, primary_key.get("sort_key"), "sort_key", required=False))

    attributes = table["attributes"]
    for attr_name, attr_type in attributes.items():
        if not isinstance(attr_name, str) or not attr_name:
            errors.append(f"{repo_relative(path)}: attribute names must be non-empty strings")
        if attr_type not in VALID_ATTRIBUTE_TYPES:
            errors.append(
                f"{repo_relative(path)}: attribute '{attr_name}' type must be one of "
                f"{sorted(VALID_ATTRIBUTE_TYPES)}"
            )

    for label in ("partition_key", "sort_key"):
        key = primary_key.get(label)
        if key is None:
            continue
        key_name = key.get("name")
        key_type = key.get("type")
        if attributes.get(key_name) != key_type:
            errors.append(
                f"{repo_relative(path)}: {label} '{key_name}' must be present in attributes "
                f"with type '{key_type}'"
            )

    return errors


def load_baseline() -> dict[str, dict[str, Any]]:
    if TABLE_KEY_BASELINE_PATH.exists():
        data = json.loads(TABLE_KEY_BASELINE_PATH.read_text())
        if isinstance(data, dict):
            return data
    return {}


def load_git_base_table(path: Path, base_ref: str) -> dict[str, Any] | None:
    rel_path = repo_relative(path)
    result = subprocess.run(
        ["git", "show", f"{base_ref}:{rel_path}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def check_compatibility(path: Path, base_ref: str) -> list[str]:
    current = load_json(path)
    baseline = load_baseline()
    base_signature = baseline.get(repo_relative(path))

    if base_signature is None:
        base_table = load_git_base_table(path, base_ref)
        if base_table is None:
            return []
        base_signature = key_signature(base_table)

    current_signature = key_signature(current)
    if base_signature != current_signature:
        return [
            f"{repo_relative(path)}: primary/sort key changed from "
            f"{json.dumps(base_signature, sort_keys=True)} to "
            f"{json.dumps(current_signature, sort_keys=True)}"
        ]
    return []


def main() -> int:
    base_ref = "origin/main"
    table_paths = iter_table_paths()
    errors: list[str] = []
    if not table_paths:
        errors.append("dynamodb/: at least one table spec is required")

    for path in table_paths:
        errors.extend(validate_table(path))
        if not errors:
            errors.extend(check_compatibility(path, base_ref))

    if errors:
        print("DynamoDB validation failed:\n")
        for error in errors:
            print(f"  ERROR: {error}")
        return 1

    print(f"Validated {len(table_paths)} DynamoDB table spec(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
