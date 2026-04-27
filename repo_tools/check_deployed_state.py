#!/usr/bin/env python3
"""Compare deployed AWS resources with repo specs."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from repo_tools.common import iter_agent_dirs, iter_table_paths, load_json
from repo_tools.deploy import (
    VERCEL_AGENT_POLICY_NAME,
    VERCEL_AGENT_ROLE_NAME,
    VERCEL_MANAGED_ENV_KEYS,
    build_vercel_invoke_policy,
    get_aws_account_id,
    list_vercel_project_envs,
    vercel_env_targets,
)

AWS_ATTRIBUTE_TYPES = {
    "String": "S",
    "Number": "N",
    "Binary": "B",
}


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
            if key and attr_defs.get(key["name"]) != AWS_ATTRIBUTE_TYPES[key["type"]]:
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
    return errors


def check_vercel_oidc_access() -> list[str]:
    errors: list[str] = []
    external_agents: list[str] = []
    for agent_dir in iter_agent_dirs():
        spec = load_json(agent_dir / "spec.json")
        if spec["connectivity"] == "external":
            external_agents.append(spec["name"])
    if not external_agents:
        return errors

    region = os.environ.get("AWS_REGION", "")
    vercel_token = os.environ.get("VERCEL_TOKEN", "")
    vercel_team_id = os.environ.get("VERCEL_TEAM_ID", "")
    if not region:
        errors.append("AWS_REGION is required to verify Vercel OIDC access")
    if not vercel_token:
        errors.append("VERCEL_TOKEN is required to verify Vercel OIDC access")
    if not vercel_team_id:
        errors.append("VERCEL_TEAM_ID is required to verify Vercel OIDC access")
    if errors:
        return errors

    account_id = get_aws_account_id()
    role_code, role_data = run_json(["aws", "iam", "get-role", "--role-name", VERCEL_AGENT_ROLE_NAME])
    if role_code != 0:
        errors.append(f"Vercel OIDC role missing or inaccessible: {VERCEL_AGENT_ROLE_NAME}")
        return errors

    policy_code, policy_data = run_json(
        [
            "aws",
            "iam",
            "get-role-policy",
            "--role-name",
            VERCEL_AGENT_ROLE_NAME,
            "--policy-name",
            VERCEL_AGENT_POLICY_NAME,
        ]
    )
    if policy_code != 0:
        errors.append(f"Vercel OIDC role policy missing: {VERCEL_AGENT_POLICY_NAME}")
    else:
        expected_policy = build_vercel_invoke_policy(account_id, region)
        if policy_data.get("PolicyDocument") != expected_policy:
            errors.append("Vercel OIDC invoke policy differs from repo definition")

    role_arn = role_data.get("Role", {}).get("Arn")
    expected_env = {
        "AWS_REGION": region,
        "AWS_ROLE_ARN": role_arn,
        "INFIAPP_AGENT_BACKEND_MODE": "aws_oidc",
    }
    envs = list_vercel_project_envs(vercel_token, vercel_team_id)
    for key, expected_value in expected_env.items():
        matching_envs = [
            env
            for env in envs
            if env.get("key") == key and "production" in vercel_env_targets(env)
        ]
        if not matching_envs:
            errors.append(f"Vercel production env var missing: {key}")
            continue
        if not any(env.get("value") == expected_value for env in matching_envs):
            errors.append(f"Vercel production env var differs: {key}")

    unexpected = sorted(
        {
            str(env.get("key"))
            for env in envs
            if env.get("key") in VERCEL_MANAGED_ENV_KEYS
            and "production" in vercel_env_targets(env)
            and env.get("key") not in expected_env
        }
    )
    if unexpected:
        errors.append(f"Unexpected managed Vercel env var(s): {unexpected}")

    return errors


def main() -> int:
    errors = check_tables() + check_agents() + check_vercel_oidc_access()
    if errors:
        print("Deployed state does not match repo definitions:\n")
        for error in errors:
            print(f"  ERROR: {error}")
        return 1
    print("Deployed infrastructure matches repo definitions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
