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
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from repo_tools.common import (
    AGENTS_DIR,
    REPO_ROOT,
    WEBUI_DIR,
    iter_agent_dirs,
    iter_table_paths,
    load_json,
    load_table_spec,
)
from repo_tools.python_dependencies import resolve_dependency_names

AWS_ATTRIBUTE_TYPES = {
    "String": "S",
    "Number": "N",
    "Binary": "B",
}
OIDC_PROVIDER_HOST = "oidc.vercel.com"
VERCEL_API_BASE = "https://api.vercel.com"
VERCEL_PROJECT_NAME = "infiapp-webui"
VERCEL_AGENT_ROLE_NAME = f"vercel-{VERCEL_PROJECT_NAME}-agent-invoke"
VERCEL_AGENT_POLICY_NAME = "invoke-external-agents"
VERCEL_MANAGED_ENV_KEYS = {
    "AWS_REGION",
    "AWS_ROLE_ARN",
    "INFIAPP_AGENT_BACKEND_MODE",
}
LAMBDA_HANDLER = "handler.lambda_handler"


def run(
    command: list[str],
    *,
    cwd: Path = REPO_ROOT,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(redact_command(command)), flush=True)
    return subprocess.run(command, cwd=cwd, text=True, check=check, env=env)


def redact_command(command: list[str]) -> list[str]:
    redacted: list[str] = []
    skip_next = False
    for part in command:
        if skip_next:
            redacted.append("<redacted>")
            skip_next = False
            continue
        redacted.append(part)
        if part == "--token":
            skip_next = True
    return redacted


def aws_json(command: list[str]) -> tuple[int, dict[str, Any]]:
    result = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return result.returncode, {}
    return 0, json.loads(result.stdout or "{}")


def vercel_request_json(
    *,
    method: str,
    path: str,
    token: str,
    team_id: str | None = None,
    body: dict[str, Any] | None = None,
    query: dict[str, str] | None = None,
    not_found_ok: bool = False,
) -> dict[str, Any] | None:
    params = dict(query or {})
    if team_id:
        params["teamId"] = team_id
    query_string = f"?{urllib.parse.urlencode(params)}" if params else ""
    url = f"{VERCEL_API_BASE}{path}{query_string}"
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request) as response:
            raw_body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw_body = exc.read().decode("utf-8", errors="replace")
        if not_found_ok and exc.code == 404:
            return None
        raise RuntimeError(
            f"Vercel API {method} {path} failed with HTTP {exc.code}: {raw_body or '<empty>'}"
        ) from exc

    return json.loads(raw_body) if raw_body else {}


def get_aws_account_id() -> str:
    code, data = aws_json(["aws", "sts", "get-caller-identity"])
    if code != 0 or not isinstance(data.get("Account"), str):
        raise RuntimeError("Unable to determine AWS account id from configured credentials")
    return data["Account"]


def external_agent_names() -> list[str]:
    names: list[str] = []
    for agent_dir in iter_agent_dirs():
        spec = load_json(agent_dir / "spec.json")
        if spec["connectivity"] == "external":
            names.append(agent_dir.name)
    return sorted(names)


def deploy_tables() -> None:
    for path in iter_table_paths():
        table = load_table_spec(path)
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
    return [load_table_spec(path) for path in iter_table_paths() if path.parent.name == agent_name]


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


def copy_tree_contents(source_root: Path, target_root: Path) -> None:
    for file_path in source_root.rglob("*"):
        if file_path.is_file() and "__pycache__" not in file_path.parts:
            relative_path = file_path.relative_to(source_root)
            target_path = target_root / relative_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, target_path)


def zip_directory(source_root: Path, output_path: Path) -> None:
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in source_root.rglob("*"):
            if file_path.is_file() and "__pycache__" not in file_path.parts:
                archive.write(file_path, file_path.relative_to(source_root))


def install_agent_dependencies(agent_dir: Path, build_dir: Path) -> None:
    spec = load_json(agent_dir / "spec.json")
    requirements = resolve_dependency_names(spec["required_dependencies"])
    if not requirements:
        return

    requirements_path = build_dir / "requirements.txt"
    requirements_path.write_text("\n".join(requirements) + "\n")
    run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--target",
            str(build_dir),
            "--requirement",
            str(requirements_path),
        ]
    )
    requirements_path.unlink()


def zip_agent(agent_dir: Path, output_path: Path) -> None:
    shared_utils = AGENTS_DIR / "shared_utils"
    with tempfile.TemporaryDirectory() as tmp:
        build_dir = Path(tmp)
        install_agent_dependencies(agent_dir, build_dir)
        copy_tree_contents(agent_dir / "code", build_dir)
        copy_tree_contents(shared_utils, build_dir)
        zip_directory(build_dir, output_path)


def deploy_agents() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for agent_dir in iter_agent_dirs():
            spec = load_json(agent_dir / "spec.json")
            function_name = agent_dir.name
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
                run(["aws", "lambda", "wait", "function-updated-v2", "--function-name", function_name])
                run(
                    [
                        "aws",
                        "lambda",
                        "update-function-configuration",
                        "--function-name",
                        function_name,
                        "--memory-size",
                        str(spec["memory_mb"]),
                        "--timeout",
                        str(spec["timeout_seconds"]),
                        "--ephemeral-storage",
                        f"Size={spec['ephemeral_storage_mb']}",
                    ]
                )
                run(["aws", "lambda", "wait", "function-updated-v2", "--function-name", function_name])
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
                        LAMBDA_HANDLER,
                        "--memory-size",
                        str(spec["memory_mb"]),
                        "--timeout",
                        str(spec["timeout_seconds"]),
                        "--ephemeral-storage",
                        f"Size={spec['ephemeral_storage_mb']}",
                        "--zip-file",
                        f"fileb://{zip_path}",
                    ]
                )
            if spec["connectivity"] == "external":
                url_code, _ = aws_json(
                    ["aws", "lambda", "get-function-url-config", "--function-name", function_name]
                )
                if url_code == 0:
                    run(
                        [
                            "aws",
                            "lambda",
                            "delete-function-url-config",
                            "--function-name",
                            function_name,
                        ]
                    )
                print(f"External agent deploy ready for IAM invocation: {function_name}")


def get_vercel_team_slug(vercel_token: str, vercel_team_id: str) -> str:
    team = vercel_request_json(
        method="GET",
        path=f"/v2/teams/{urllib.parse.quote(vercel_team_id)}",
        token=vercel_token,
        not_found_ok=True,
    )
    if not isinstance(team, dict):
        raise RuntimeError(f"Vercel team {vercel_team_id} could not be fetched")
    slug = team.get("slug")
    if not isinstance(slug, str) or not slug:
        raise RuntimeError(f"Vercel team {vercel_team_id} did not return a slug")
    return slug


def build_vercel_oidc_provider_url(team_slug: str) -> str:
    return f"https://{OIDC_PROVIDER_HOST}/{team_slug}"


def build_vercel_audience(team_slug: str) -> str:
    return f"https://vercel.com/{team_slug}"


def build_vercel_oidc_provider_arn(account_id: str, team_slug: str) -> str:
    return f"arn:aws:iam::{account_id}:oidc-provider/{OIDC_PROVIDER_HOST}/{team_slug}"


def ensure_vercel_oidc_provider(account_id: str, team_slug: str) -> str:
    provider_url = build_vercel_oidc_provider_url(team_slug)
    provider_host_path = provider_url.removeprefix("https://")
    audience = build_vercel_audience(team_slug)

    code, data = aws_json(["aws", "iam", "list-open-id-connect-providers"])
    if code != 0:
        raise RuntimeError("Unable to list AWS OIDC providers")

    for entry in data.get("OpenIDConnectProviderList", []):
        provider_arn = entry.get("Arn")
        if not isinstance(provider_arn, str):
            continue
        detail_code, detail = aws_json(
            ["aws", "iam", "get-open-id-connect-provider", "--open-id-connect-provider-arn", provider_arn]
        )
        if detail_code == 0 and detail.get("Url") == provider_host_path:
            if audience not in detail.get("ClientIDList", []):
                run(
                    [
                        "aws",
                        "iam",
                        "add-client-id-to-open-id-connect-provider",
                        "--open-id-connect-provider-arn",
                        provider_arn,
                        "--client-id",
                        audience,
                    ]
                )
            return provider_arn

    run(
        [
            "aws",
            "iam",
            "create-open-id-connect-provider",
            "--url",
            provider_url,
            "--client-id-list",
            audience,
        ]
    )
    return build_vercel_oidc_provider_arn(account_id, team_slug)


def build_vercel_trust_policy(account_id: str, team_slug: str) -> dict[str, Any]:
    claim_prefix = f"{OIDC_PROVIDER_HOST}/{team_slug}"
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Federated": build_vercel_oidc_provider_arn(account_id, team_slug),
                },
                "Action": "sts:AssumeRoleWithWebIdentity",
                "Condition": {
                    "StringEquals": {
                        f"{claim_prefix}:aud": build_vercel_audience(team_slug),
                        f"{claim_prefix}:sub": (
                            f"owner:{team_slug}:project:{VERCEL_PROJECT_NAME}:environment:production"
                        ),
                    },
                },
            },
        ],
    }


def build_vercel_invoke_policy(account_id: str, region: str) -> dict[str, Any]:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["lambda:InvokeFunction"],
                "Resource": [
                    f"arn:aws:lambda:{region}:{account_id}:function:{agent_name}"
                    for agent_name in external_agent_names()
                ],
            },
        ],
    }


def ensure_vercel_agent_role(account_id: str, region: str, team_slug: str) -> str:
    ensure_vercel_oidc_provider(account_id, team_slug)
    trust_policy = build_vercel_trust_policy(account_id, team_slug)
    role_code, role_data = aws_json(["aws", "iam", "get-role", "--role-name", VERCEL_AGENT_ROLE_NAME])
    if role_code == 0:
        run(
            [
                "aws",
                "iam",
                "update-assume-role-policy",
                "--role-name",
                VERCEL_AGENT_ROLE_NAME,
                "--policy-document",
                json.dumps(trust_policy),
            ]
        )
        role_arn = role_data["Role"]["Arn"]
    else:
        run(
            [
                "aws",
                "iam",
                "create-role",
                "--role-name",
                VERCEL_AGENT_ROLE_NAME,
                "--assume-role-policy-document",
                json.dumps(trust_policy),
                "--description",
                f"OIDC role for Vercel project {VERCEL_PROJECT_NAME} to invoke external Infiapp agents.",
            ]
        )
        role_code, role_data = aws_json(["aws", "iam", "get-role", "--role-name", VERCEL_AGENT_ROLE_NAME])
        if role_code != 0:
            raise RuntimeError(f"Unable to create or load IAM role {VERCEL_AGENT_ROLE_NAME}")
        role_arn = role_data["Role"]["Arn"]

    run(
        [
            "aws",
            "iam",
            "put-role-policy",
            "--role-name",
            VERCEL_AGENT_ROLE_NAME,
            "--policy-name",
            VERCEL_AGENT_POLICY_NAME,
            "--policy-document",
            json.dumps(build_vercel_invoke_policy(account_id, region)),
        ]
    )
    return role_arn


def ensure_vercel_project(vercel_token: str, vercel_team_id: str) -> None:
    project = vercel_request_json(
        method="GET",
        path=f"/v9/projects/{urllib.parse.quote(VERCEL_PROJECT_NAME)}",
        token=vercel_token,
        team_id=vercel_team_id,
        not_found_ok=True,
    )
    if project is not None:
        return

    vercel_request_json(
        method="POST",
        path="/v11/projects",
        token=vercel_token,
        team_id=vercel_team_id,
        body={
            "name": VERCEL_PROJECT_NAME,
            "framework": "nextjs",
        },
    )


def list_vercel_project_envs(vercel_token: str, vercel_team_id: str) -> list[dict[str, Any]]:
    envs: list[dict[str, Any]] = []
    query: dict[str, str] | None = None
    while True:
        response = vercel_request_json(
            method="GET",
            path=f"/v10/projects/{urllib.parse.quote(VERCEL_PROJECT_NAME)}/env",
            token=vercel_token,
            team_id=vercel_team_id,
            query=query,
        )
        if not isinstance(response, dict):
            return envs
        page_envs = response.get("envs")
        if isinstance(page_envs, list):
            envs.extend(entry for entry in page_envs if isinstance(entry, dict))
        pagination = response.get("pagination")
        next_cursor = pagination.get("next") if isinstance(pagination, dict) else None
        if not isinstance(next_cursor, (int, str)):
            return envs
        query = {"from": str(next_cursor)}


def vercel_env_targets(env_entry: dict[str, Any]) -> list[str]:
    raw_target = env_entry.get("target")
    if isinstance(raw_target, str):
        return [raw_target]
    if isinstance(raw_target, list):
        return [target for target in raw_target if isinstance(target, str)]
    return []


def sync_vercel_oidc_env(vercel_token: str, vercel_team_id: str, values: dict[str, str]) -> None:
    for env_entry in list_vercel_project_envs(vercel_token, vercel_team_id):
        key = env_entry.get("key")
        env_id = env_entry.get("id")
        if (
            isinstance(key, str)
            and key in VERCEL_MANAGED_ENV_KEYS
            and isinstance(env_id, str)
            and "production" in vercel_env_targets(env_entry)
        ):
            vercel_request_json(
                method="DELETE",
                path=f"/v9/projects/{urllib.parse.quote(VERCEL_PROJECT_NAME)}/env/{urllib.parse.quote(env_id)}",
                token=vercel_token,
                team_id=vercel_team_id,
            )

    for key, value in sorted(values.items()):
        vercel_request_json(
            method="POST",
            path=f"/v10/projects/{urllib.parse.quote(VERCEL_PROJECT_NAME)}/env",
            token=vercel_token,
            team_id=vercel_team_id,
            body={
                "key": key,
                "value": value,
                "type": "plain",
                "target": ["production"],
            },
        )


def deploy_vercel_oidc_access(vercel_token: str, vercel_team_id: str) -> str:
    region = os.environ["AWS_REGION"]
    account_id = get_aws_account_id()
    team_slug = get_vercel_team_slug(vercel_token, vercel_team_id)
    ensure_vercel_project(vercel_token, vercel_team_id)
    role_arn = ensure_vercel_agent_role(account_id, region, team_slug)
    sync_vercel_oidc_env(
        vercel_token,
        vercel_team_id,
        {
            "AWS_REGION": region,
            "AWS_ROLE_ARN": role_arn,
            "INFIAPP_AGENT_BACKEND_MODE": "aws_oidc",
        },
    )
    print(f"Synced Vercel OIDC agent access for {VERCEL_PROJECT_NAME} with role {role_arn}.")
    return team_slug


def deploy_webui() -> None:
    if not shutil.which("npx"):
        raise RuntimeError("npx is required to deploy the WebUI to Vercel")
    vercel_token = os.environ.get("VERCEL_TOKEN")
    vercel_team_id = os.environ.get("VERCEL_TEAM_ID")
    if not vercel_token:
        raise RuntimeError("VERCEL_TOKEN must be set for WebUI deployment")
    if not vercel_team_id:
        raise RuntimeError("VERCEL_TEAM_ID must be set for WebUI deployment")
    vercel_team_slug = deploy_vercel_oidc_access(vercel_token, vercel_team_id)
    vercel_env = {**os.environ, "VERCEL_TOKEN": vercel_token, "VERCEL_TEAM_ID": vercel_team_id}
    run(["npm", "ci"], cwd=WEBUI_DIR)
    run(
        [
            "npx",
            "vercel",
            "link",
            "--yes",
            "--project",
            VERCEL_PROJECT_NAME,
            "--scope",
            vercel_team_slug,
            "--token",
            vercel_token,
        ],
        cwd=WEBUI_DIR,
        env=vercel_env,
    )
    run(
        [
            "npx",
            "vercel",
            "deploy",
            "--prod",
            "--yes",
            "--scope",
            vercel_team_slug,
            "--token",
            vercel_token,
        ],
        cwd=WEBUI_DIR,
        env=vercel_env,
    )


def main() -> int:
    run([sys.executable, "-m", "repo_tools", "validate-agents"])
    run([sys.executable, "-m", "repo_tools", "validate-db"])
    run([sys.executable, "-m", "repo_tools", "codegen-check"])
    deploy_tables()
    deploy_agents()
    deploy_webui()
    print("Deployment finished.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
