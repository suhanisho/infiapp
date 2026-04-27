#!/usr/bin/env python3
"""Compare deployed AWS resources with repo specs."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from repo_tools.common import iter_agent_dirs, iter_table_paths, load_json


def run_json(command: list[str]) -> tuple[int, dict[str, Any]]:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return result.returncode, {}
    return 0, json.loads(result.stdout or "{}")


def check_tables() -> list[str]:
    errors: list[str] = []
    for path in iter_table_paths():
        table = load_json(path)
        code, data = run_json(["aws", "dynamodb", "describe-table", "--table-name", table["table_name"]])
        if code != 0:
            errors.append(f"DynamoDB table missing or inaccessible: {table['table_name']}")
            continue
        deployed_table = data.get("Table", {})
        key_schema = deployed_table.get("KeySchema", [])
        attr_defs = {
            item["AttributeName"]: item["AttributeType"]
            for item in deployed_table.get("AttributeDefinitions", [])
        }
        expected_pk = table["primary_key"]["partition_key"]
        expected_sk = table["primary_key"].get("sort_key")
        expected_schema = [{"AttributeName": expected_pk["name"], "KeyType": "HASH"}]
        if expected_sk:
            expected_schema.append({"AttributeName": expected_sk["name"], "KeyType": "RANGE"})
        if key_schema != expected_schema:
            errors.append(f"{table['table_name']}: key schema differs from repo definition")
        for key in (expected_pk, expected_sk):
            if key and attr_defs.get(key["name"]) != key["type"]:
                errors.append(f"{table['table_name']}: key attribute {key['name']} type differs")
    return errors


def check_agents() -> list[str]:
    errors: list[str] = []
    for agent_dir in iter_agent_dirs():
        spec = load_json(agent_dir / "spec.json")
        function_name = spec["name"]
        code, _ = run_json(["aws", "lambda", "get-function", "--function-name", function_name])
        if code != 0:
            errors.append(f"Lambda function missing or inaccessible: {function_name}")
            continue
        if spec["connectivity"] == "external":
            url_code, _ = run_json(
                ["aws", "lambda", "get-function-url-config", "--function-name", function_name]
            )
            if url_code != 0:
                errors.append(f"External Lambda has no Function URL: {function_name}")
    return errors


def main() -> int:
    errors = check_tables() + check_agents()
    if errors:
        print("Deployed state does not match repo definitions:\n")
        for error in errors:
            print(f"  ERROR: {error}")
        return 1
    print("Deployed infrastructure matches repo definitions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
