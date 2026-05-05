#!/usr/bin/env python3
"""Compare deployed AWS resources with repo specs."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from repo_tools.common import iter_agent_dirs, iter_table_paths, load_json, load_table_spec, repo_relative
from repo_tools.deploy import (
    LAMBDA_HANDLER,
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


@dataclass
class ResourceCheck:
    resource_type: str
    name: str
    found: bool
    discrepancies: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if not self.found:
            return "Missing"
        if self.discrepancies:
            return "Discrepancy"
        return "OK"


def log_section(message: str) -> None:
    print(f"\n==> {message}", flush=True)


def run_json(command: list[str]) -> tuple[int, dict[str, Any]]:
    if command and command[0] == "aws" and "--region" not in command:
        region = os.environ.get("AWS_REGION")
        if region:
            command = ["aws", "--region", region, *command[1:]]
    print("+", " ".join(command), flush=True)
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return result.returncode, {}
    return 0, json.loads(result.stdout or "{}")


def check_tables() -> tuple[list[str], list[ResourceCheck]]:
    table_paths = iter_table_paths()
    log_section(f"Verifying DynamoDB tables ({len(table_paths)} spec(s))")
    errors: list[str] = []
    resources: list[ResourceCheck] = []
    for path in table_paths:
        table = load_table_spec(path)
        table_errors: list[str] = []
        print(f"Checking DynamoDB table: {table['table_name']} ({path})", flush=True)
        code, data = run_json(["aws", "dynamodb", "describe-table", "--table-name", table["table_name"]])
        if code != 0:
            error = f"DynamoDB table missing or inaccessible: {table['table_name']}"
            errors.append(error)
            resources.append(
                ResourceCheck(
                    "DynamoDB table",
                    table["table_name"],
                    found=False,
                    discrepancies=[error],
                    details=[f"Spec: {repo_relative(path)}"],
                )
            )
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
            table_errors.append(f"{table['table_name']}: key schema differs from repo definition")
        for key in (expected_pk, expected_sk):
            if key and attr_defs.get(key["name"]) != AWS_ATTRIBUTE_TYPES[key["type"]]:
                table_errors.append(f"{table['table_name']}: key attribute {key['name']} type differs")
        resources.append(
            ResourceCheck(
                "DynamoDB table",
                table["table_name"],
                found=True,
                discrepancies=table_errors,
                details=[f"Spec: {repo_relative(path)}"],
            )
        )
        if table_errors:
            errors.extend(table_errors)
        else:
            print(f"DynamoDB table matches repo definition: {table['table_name']}", flush=True)
    return errors, resources


def check_agents() -> tuple[list[str], list[ResourceCheck]]:
    agent_dirs = iter_agent_dirs()
    log_section(f"Verifying Lambda agents ({len(agent_dirs)} spec(s))")
    errors: list[str] = []
    resources: list[ResourceCheck] = []
    for agent_dir in agent_dirs:
        spec = load_json(agent_dir / "spec.json")
        function_name = agent_dir.name
        agent_errors: list[str] = []
        print(f"Checking Lambda function: {function_name}", flush=True)
        code, data = run_json(["aws", "lambda", "get-function", "--function-name", function_name])
        if code != 0:
            error = f"Lambda function missing or inaccessible: {function_name}"
            errors.append(error)
            resources.append(
                ResourceCheck(
                    "Lambda function",
                    function_name,
                    found=False,
                    discrepancies=[error],
                    details=[f"Connectivity: {spec['connectivity']}"],
                )
            )
            continue
        config = data.get("Configuration", {})
        expected_values = {
            "Runtime": "python3.11",
            "Handler": LAMBDA_HANDLER,
            "MemorySize": spec["memory_mb"],
            "Timeout": spec["timeout_seconds"],
        }
        for field, expected in expected_values.items():
            if config.get(field) != expected:
                agent_errors.append(
                    f"{function_name}: {field} is {config.get(field)!r}, expected {expected!r}"
                )
        ephemeral_size = config.get("EphemeralStorage", {}).get("Size")
        if ephemeral_size != spec["ephemeral_storage_mb"]:
            agent_errors.append(
                f"{function_name}: ephemeral storage is {ephemeral_size!r}, "
                f"expected {spec['ephemeral_storage_mb']!r}"
            )
        resources.append(
            ResourceCheck(
                "Lambda function",
                function_name,
                found=True,
                discrepancies=agent_errors,
                details=[
                    f"Connectivity: {spec['connectivity']}",
                    f"Runtime: {config.get('Runtime', '<unknown>')}",
                ],
            )
        )
        if agent_errors:
            errors.extend(agent_errors)
        else:
            print(f"Lambda function matches repo definition: {function_name}", flush=True)
    return errors, resources


def check_vercel_oidc_access() -> tuple[list[str], list[ResourceCheck]]:
    log_section("Verifying Vercel OIDC access")
    errors: list[str] = []
    resources: list[ResourceCheck] = []
    external_agents: list[str] = []
    for agent_dir in iter_agent_dirs():
        spec = load_json(agent_dir / "spec.json")
        if spec["connectivity"] == "external":
            external_agents.append(agent_dir.name)
    if not external_agents:
        print("No external agents found; skipping Vercel OIDC verification.", flush=True)
        resources.append(
            ResourceCheck(
                "Vercel OIDC access",
                "external agent invocation",
                found=True,
                details=["Skipped: no external agents"],
            )
        )
        return errors, resources
    print(f"External agents requiring Vercel invoke access: {', '.join(sorted(external_agents))}", flush=True)

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
        resources.append(
            ResourceCheck(
                "Vercel OIDC access",
                "configuration",
                found=False,
                discrepancies=errors.copy(),
            )
        )
        return errors, resources

    account_id = get_aws_account_id()
    print(f"Checking Vercel IAM role: {VERCEL_AGENT_ROLE_NAME}", flush=True)
    role_code, role_data = run_json(["aws", "iam", "get-role", "--role-name", VERCEL_AGENT_ROLE_NAME])
    if role_code != 0:
        error = f"Vercel OIDC role missing or inaccessible: {VERCEL_AGENT_ROLE_NAME}"
        errors.append(error)
        resources.append(
            ResourceCheck(
                "IAM role",
                VERCEL_AGENT_ROLE_NAME,
                found=False,
                discrepancies=[error],
            )
        )
        return errors, resources
    resources.append(ResourceCheck("IAM role", VERCEL_AGENT_ROLE_NAME, found=True))

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
        error = f"Vercel OIDC role policy missing: {VERCEL_AGENT_POLICY_NAME}"
        errors.append(error)
        resources.append(
            ResourceCheck(
                "IAM role policy",
                VERCEL_AGENT_POLICY_NAME,
                found=False,
                discrepancies=[error],
            )
        )
    else:
        print(f"Checking Vercel invoke policy: {VERCEL_AGENT_POLICY_NAME}", flush=True)
        expected_policy = build_vercel_invoke_policy(account_id, region)
        policy_errors: list[str] = []
        if policy_data.get("PolicyDocument") != expected_policy:
            policy_errors.append("Vercel OIDC invoke policy differs from repo definition")
            errors.extend(policy_errors)
        resources.append(
            ResourceCheck(
                "IAM role policy",
                VERCEL_AGENT_POLICY_NAME,
                found=True,
                discrepancies=policy_errors,
                details=[f"External agents: {', '.join(sorted(external_agents))}"],
            )
        )

    role_arn = role_data.get("Role", {}).get("Arn")
    expected_env = {
        "AWS_REGION": region,
        "AWS_ROLE_ARN": role_arn,
        "SHALINI_CLINIC_AGENT_BACKEND_MODE": "aws_oidc",
    }
    envs = list_vercel_project_envs(vercel_token, vercel_team_id)
    for key, expected_value in expected_env.items():
        print(f"Checking Vercel production env var: {key}", flush=True)
        env_errors: list[str] = []
        matching_envs = [
            env
            for env in envs
            if env.get("key") == key and "production" in vercel_env_targets(env)
        ]
        if not matching_envs:
            env_errors.append(f"Vercel production env var missing: {key}")
            errors.extend(env_errors)
            resources.append(
                ResourceCheck(
                    "Vercel production env var",
                    key,
                    found=False,
                    discrepancies=env_errors,
                )
            )
            continue
        if not any(env.get("value") == expected_value for env in matching_envs):
            env_errors.append(f"Vercel production env var differs: {key}")
            errors.extend(env_errors)
        resources.append(
            ResourceCheck(
                "Vercel production env var",
                key,
                found=True,
                discrepancies=env_errors,
            )
        )

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
        error = f"Unexpected managed Vercel env var(s): {unexpected}"
        errors.append(error)
        for key in unexpected:
            resources.append(
                ResourceCheck(
                    "Vercel production env var",
                    key,
                    found=True,
                    discrepancies=["Unexpected managed env var"],
                )
            )
    if not errors:
        print("Vercel OIDC access matches repo definition.", flush=True)

    return errors, resources


def markdown_escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


def format_resource_summary(resources: list[ResourceCheck], errors: list[str]) -> str:
    ok_count = sum(1 for resource in resources if resource.status == "OK")
    discrepancy_count = sum(1 for resource in resources if resource.status == "Discrepancy")
    missing_count = sum(1 for resource in resources if resource.status == "Missing")
    lines = [
        "# Deployed State Verification",
        "",
        f"- Resources checked: {len(resources)}",
        f"- OK: {ok_count}",
        f"- Discrepancies: {discrepancy_count}",
        f"- Missing: {missing_count}",
        "",
        "## Resources",
        "",
        "| Type | Name | Status | Details |",
        "| --- | --- | --- | --- |",
    ]
    for resource in resources:
        detail_parts = resource.discrepancies or resource.details or ["Matches repo definition"]
        lines.append(
            "| "
            f"{markdown_escape(resource.resource_type)} | "
            f"`{markdown_escape(resource.name)}` | "
            f"{resource.status} | "
            f"{markdown_escape('; '.join(detail_parts))} |"
        )
    if errors:
        lines.extend(["", "## Discrepancies", ""])
        lines.extend(f"- {markdown_escape(error)}" for error in errors)
    return "\n".join(lines) + "\n"


def write_action_summary(resources: list[ResourceCheck], errors: list[str], summary_path: str | None) -> None:
    if not summary_path:
        return
    Path(summary_path).write_text(format_resource_summary(resources, errors))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare deployed infrastructure with repo specs")
    parser.add_argument(
        "--summary-out",
        default=os.environ.get("GITHUB_STEP_SUMMARY"),
        help="Optional path to write a GitHub Actions markdown summary to",
    )
    args = parser.parse_args(argv)

    table_errors, table_resources = check_tables()
    agent_errors, agent_resources = check_agents()
    vercel_errors, vercel_resources = check_vercel_oidc_access()
    errors = table_errors + agent_errors + vercel_errors
    resources = table_resources + agent_resources + vercel_resources
    write_action_summary(resources, errors, args.summary_out)
    if errors:
        print("Deployed state does not match repo definitions:\n")
        for error in errors:
            print(f"  ERROR: {error}")
        return 1
    print("Deployed infrastructure matches repo definitions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
