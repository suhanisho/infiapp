#!/usr/bin/env python3
"""Deploy DynamoDB tables, Lambda agents, and the Vercel WebUI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from repo_tools.common import AGENTS_DIR, REPO_ROOT, WEBUI_DIR, iter_agent_dirs, iter_table_paths, load_json

AWS_ATTRIBUTE_TYPES = {
    "String": "S",
    "Number": "N",
    "Binary": "B",
}


def run(
    command: list[str],
    *,
    cwd: Path = REPO_ROOT,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(command))
    return subprocess.run(command, cwd=cwd, text=True, check=check, env=env)


def aws_json(command: list[str]) -> tuple[int, dict[str, Any]]:
    result = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return result.returncode, {}
    return 0, json.loads(result.stdout or "{}")


def get_aws_account_id() -> str:
    code, data = aws_json(["aws", "sts", "get-caller-identity"])
    if code != 0 or not isinstance(data.get("Account"), str):
        raise RuntimeError("Unable to determine AWS account id from configured credentials")
    return data["Account"]


def deploy_tables() -> None:
    for path in iter_table_paths():
        table = load_json(path)
        table_name = table["table_name"]
        code, _ = aws_json(["aws", "dynamodb", "describe-table", "--table-name", table_name])
        if code == 0:
            print(f"DynamoDB table exists: {table_name}")
            continue

        pk = table["primary_key"]["partition_key"]
        sk = table["primary_key"].get("sort_key")
        attr_defs = [
            {"AttributeName": pk["name"], "AttributeType": AWS_ATTRIBUTE_TYPES[pk["type"]]},
        ]
        key_schema = [{"AttributeName": pk["name"], "KeyType": "HASH"}]
        if sk:
            attr_defs.append(
                {"AttributeName": sk["name"], "AttributeType": AWS_ATTRIBUTE_TYPES[sk["type"]]}
            )
            key_schema.append({"AttributeName": sk["name"], "KeyType": "RANGE"})

        run(
            [
                "aws",
                "dynamodb",
                "create-table",
                "--table-name",
                table_name,
                "--billing-mode",
                "PAY_PER_REQUEST",
                "--attribute-definitions",
                json.dumps(attr_defs),
                "--key-schema",
                json.dumps(key_schema),
            ]
        )


def tables_for_agent(agent_name: str) -> list[dict[str, Any]]:
    return [load_json(path) for path in iter_table_paths() if path.parent.name == agent_name]


def ensure_agent_role(agent_name: str) -> str:
    account_id = get_aws_account_id()
    role_name = f"infiapp-{agent_name}-lambda-role"
    role_code, role_data = aws_json(["aws", "iam", "get-role", "--role-name", role_name])
    if role_code != 0:
        assume_role_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
        run(
            [
                "aws",
                "iam",
                "create-role",
                "--role-name",
                role_name,
                "--assume-role-policy-document",
                json.dumps(assume_role_policy),
            ]
        )
        role_code, role_data = aws_json(["aws", "iam", "get-role", "--role-name", role_name])
        if role_code != 0:
            raise RuntimeError(f"Unable to create or load IAM role {role_name}")
        time.sleep(8)

    owned_tables = tables_for_agent(agent_name)
    table_arns = [
        f"arn:aws:dynamodb:{os.environ['AWS_REGION']}:{account_id}:table/{table['table_name']}"
        for table in owned_tables
    ]
    statements: list[dict[str, Any]] = [
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents",
            ],
            "Resource": "arn:aws:logs:*:*:*",
        }
    ]
    if table_arns:
        statements.append(
            {
                "Effect": "Allow",
                "Action": "dynamodb:*",
                "Resource": table_arns,
            }
        )
    policy = {
        "Version": "2012-10-17",
        "Statement": statements,
    }
    run(
        [
            "aws",
            "iam",
            "put-role-policy",
            "--role-name",
            role_name,
            "--policy-name",
            "infiapp-agent-owned-tables",
            "--policy-document",
            json.dumps(policy),
        ]
    )
    return role_data["Role"]["Arn"]


def zip_agent(agent_dir: Path, output_path: Path) -> None:
    shared_utils = AGENTS_DIR / "shared_utils"
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for source_root in (agent_dir / "code", shared_utils):
            for file_path in source_root.rglob("*"):
                if file_path.is_file() and "__pycache__" not in file_path.parts:
                    archive.write(file_path, file_path.relative_to(source_root))


def deploy_agents() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for agent_dir in iter_agent_dirs():
            spec = load_json(agent_dir / "spec.json")
            function_name = spec["name"]
            role_arn = ensure_agent_role(function_name)
            zip_path = tmp_dir / f"{function_name}.zip"
            zip_agent(agent_dir, zip_path)
            code, _ = aws_json(["aws", "lambda", "get-function", "--function-name", function_name])
            if code == 0:
                run(
                    [
                        "aws",
                        "lambda",
                        "update-function-code",
                        "--function-name",
                        function_name,
                        "--zip-file",
                        f"fileb://{zip_path}",
                    ]
                )
            else:
                run(
                    [
                        "aws",
                        "lambda",
                        "create-function",
                        "--function-name",
                        function_name,
                        "--runtime",
                        "python3.11",
                        "--role",
                        role_arn,
                        "--handler",
                        spec["handler"],
                        "--zip-file",
                        f"fileb://{zip_path}",
                    ]
                )
            if spec["connectivity"] == "external":
                url_code, _ = aws_json(
                    ["aws", "lambda", "get-function-url-config", "--function-name", function_name]
                )
                if url_code != 0:
                    run(
                        [
                            "aws",
                            "lambda",
                            "create-function-url-config",
                            "--function-name",
                            function_name,
                            "--auth-type",
                            "NONE",
                        ]
                    )
                    run(
                        [
                            "aws",
                            "lambda",
                            "add-permission",
                            "--function-name",
                            function_name,
                            "--statement-id",
                            "infiapp-public-function-url",
                            "--action",
                            "lambda:InvokeFunctionUrl",
                            "--principal",
                            "*",
                            "--function-url-auth-type",
                            "NONE",
                        ],
                        check=False,
                    )


def deploy_webui() -> None:
    if not shutil.which("npx"):
        raise RuntimeError("npx is required to deploy the WebUI to Vercel")
    vercel_token = os.environ.get("VERCEL_TOKEN")
    vercel_team_id = os.environ.get("VERCEL_TEAM_ID")
    if not vercel_token:
        raise RuntimeError("VERCEL_TOKEN must be set for WebUI deployment")
    if not vercel_team_id:
        raise RuntimeError("VERCEL_TEAM_ID must be set for WebUI deployment")
    vercel_env = {
        **os.environ,
        "VERCEL_TOKEN": vercel_token,
        "VERCEL_TEAM_ID": vercel_team_id,
    }
    run(["npm", "ci"], cwd=WEBUI_DIR)
    run(["npx", "vercel", "deploy", "--prod", "--yes"], cwd=WEBUI_DIR, env=vercel_env)


def main() -> int:
    run([sys.executable, "-m", "repo_tools", "validate"])
    run([sys.executable, "-m", "repo_tools", "codegen-check"])
    deploy_tables()
    deploy_agents()
    deploy_webui()
    print("Deployment finished.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
