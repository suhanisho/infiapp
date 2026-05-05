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
VERCEL_PROJECT_NAME = "shalini-clinic-webui"
VERCEL_AGENT_ROLE_NAME = f"vercel-{VERCEL_PROJECT_NAME}-agent-invoke"
VERCEL_AGENT_POLICY_NAME = "invoke-external-agents"
GOOGLE_AGENT_NAME = "clinic_agent"
GOOGLE_TOKEN_SECRET_DEFAULT_PREFIX = "shalini-clinic/clinic_agent/google"
VERCEL_MANAGED_ENV_KEYS = {
    "AWS_REGION",
    "AWS_ROLE_ARN",
    "CLINIC_ALLOWED_EMAILS",
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "NEXTAUTH_SECRET",
    "NEXTAUTH_URL",
    "SHALINI_CLINIC_AGENT_BACKEND_MODE",
}
GOOGLE_AGENT_ENV_KEYS = {
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "GOOGLE_TOKEN_SECRET_PREFIX",
}
VERCEL_CLI_OMITTED_ENV_KEYS = {
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "NEXTAUTH_SECRET",
}
VERCEL_ENCRYPTED_ENV_KEYS = {
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "NEXTAUTH_SECRET",
}
LAMBDA_HANDLER = "handler.lambda_handler"


def log_section(message: str) -> None:
    print(f"\n==> {message}", flush=True)


def vercel_project_path() -> str:
    return f"/v9/projects/{urllib.parse.quote(VERCEL_PROJECT_NAME)}"


def vercel_project_env_path() -> str:
    return f"/v10/projects/{urllib.parse.quote(VERCEL_PROJECT_NAME)}/env"


def run(
    command: list[str],
    *,
    cwd: Path = REPO_ROOT,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command = with_aws_region(command)
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


def with_aws_region(command: list[str]) -> list[str]:
    if command and command[0] == "aws" and "--region" not in command:
        region = os.environ.get("AWS_REGION")
        if region:
            return ["aws", "--region", region, *command[1:]]
    return command


def aws_json(command: list[str]) -> tuple[int, dict[str, Any]]:
    command = with_aws_region(command)
    print("+", " ".join(redact_command(command)), flush=True)
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
    print("Checking AWS caller identity.", flush=True)
    code, data = aws_json(["aws", "sts", "get-caller-identity"])
    account_id = data.get("Account")
    if code != 0 or not isinstance(account_id, str):
        raise RuntimeError("Unable to determine AWS account id from configured credentials")
    return account_id


def get_role_arn(role_data: dict[str, Any], role_name: str) -> str:
    role = role_data.get("Role")
    role_arn = role.get("Arn") if isinstance(role, dict) else None
    if not isinstance(role_arn, str):
        raise RuntimeError(f"Unable to determine ARN for IAM role {role_name}")
    return role_arn


def external_agent_names() -> list[str]:
    names: list[str] = []
    for agent_dir in iter_agent_dirs():
        spec = load_json(agent_dir / "spec.json")
        if spec["connectivity"] == "external":
            names.append(agent_dir.name)
    return sorted(names)


def deploy_tables() -> None:
    table_paths = iter_table_paths()
    log_section(f"Deploying DynamoDB tables ({len(table_paths)} spec(s))")
    for path in table_paths:
        table = load_table_spec(path)
        table_name = table["table_name"]
        print(f"Processing DynamoDB table: {table_name} ({path})", flush=True)
        code, _ = aws_json(["aws", "dynamodb", "describe-table", "--table-name", table_name])
        if code == 0:
            print(f"DynamoDB table exists: {table_name}", flush=True)
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
    role_name = f"shalini-clinic-{agent_name}-lambda-role"
    print(f"Ensuring Lambda IAM role for {agent_name}: {role_name}", flush=True)
    role_code, role_data = aws_json(["aws", "iam", "get-role", "--role-name", role_name])
    if role_code != 0:
        print(f"Creating Lambda IAM role: {role_name}", flush=True)
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
    print(
        f"Writing IAM policy for {role_name}; owned table count: {len(owned_tables)}",
        flush=True,
    )
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
    token_secret_prefix = google_token_secret_prefix(agent_name)
    if token_secret_prefix:
        statements.append(
            {
                "Effect": "Allow",
                "Action": [
                    "secretsmanager:CreateSecret",
                    "secretsmanager:DescribeSecret",
                    "secretsmanager:GetSecretValue",
                    "secretsmanager:PutSecretValue",
                    "secretsmanager:UpdateSecret",
                ],
                "Resource": (
                    f"arn:aws:secretsmanager:{os.environ['AWS_REGION']}:{account_id}:"
                    f"secret:{token_secret_prefix}/*"
                ),
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
            "shalini-clinic-agent-owned-tables",
            "--policy-document",
            json.dumps(policy),
        ]
    )
    return get_role_arn(role_data, role_name)


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
        print(f"Agent {agent_dir.name} has no external Python dependencies.", flush=True)
        return

    print(
        f"Installing Python dependencies for {agent_dir.name}: {', '.join(requirements)}",
        flush=True,
    )
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
    print(f"Packaging agent {agent_dir.name} into {output_path}", flush=True)
    shared_utils = AGENTS_DIR / "shared_utils"
    with tempfile.TemporaryDirectory() as tmp:
        build_dir = Path(tmp)
        install_agent_dependencies(agent_dir, build_dir)
        copy_tree_contents(agent_dir / "code", build_dir)
        copy_tree_contents(shared_utils, build_dir)
        zip_directory(build_dir, output_path)


def google_token_secret_prefix(agent_name: str) -> str:
    if agent_name != GOOGLE_AGENT_NAME:
        return ""
    configured = os.environ.get("GOOGLE_TOKEN_SECRET_PREFIX", GOOGLE_TOKEN_SECRET_DEFAULT_PREFIX)
    return configured.strip().strip("/") or GOOGLE_TOKEN_SECRET_DEFAULT_PREFIX


def agent_environment_args(agent_name: str) -> list[str]:
    if agent_name != GOOGLE_AGENT_NAME:
        return []
    variables = {
        key: value
        for key in sorted(GOOGLE_AGENT_ENV_KEYS)
        if (value := os.environ.get(key))
    }
    return ["--environment", json.dumps({"Variables": variables})] if variables else []


def deploy_agents() -> None:
    agent_dirs = iter_agent_dirs()
    log_section(f"Deploying Lambda agents ({len(agent_dirs)} spec(s))")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for agent_dir in agent_dirs:
            spec = load_json(agent_dir / "spec.json")
            function_name = agent_dir.name
            print(f"Processing Lambda agent: {function_name}", flush=True)
            role_arn = ensure_agent_role(function_name)
            zip_path = tmp_dir / f"{function_name}.zip"
            zip_agent(agent_dir, zip_path)
            code, _ = aws_json(["aws", "lambda", "get-function", "--function-name", function_name])
            if code == 0:
                print(f"Updating existing Lambda function: {function_name}", flush=True)
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
                        *agent_environment_args(function_name),
                    ]
                )
                run(["aws", "lambda", "wait", "function-updated-v2", "--function-name", function_name])
            else:
                print(f"Creating Lambda function: {function_name}", flush=True)
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
                        *agent_environment_args(function_name),
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
    print("Fetching Vercel team metadata.", flush=True)
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
    print(f"Ensuring Vercel OIDC provider for team: {team_slug}", flush=True)
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
            print(f"Vercel OIDC provider exists: {provider_arn}", flush=True)
            if audience not in detail.get("ClientIDList", []):
                print("Adding Vercel OIDC audience to existing provider.", flush=True)
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

    print(f"Creating Vercel OIDC provider: {provider_url}", flush=True)
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
    print(f"Ensuring Vercel agent invoke IAM role: {VERCEL_AGENT_ROLE_NAME}", flush=True)
    ensure_vercel_oidc_provider(account_id, team_slug)
    trust_policy = build_vercel_trust_policy(account_id, team_slug)
    role_code, role_data = aws_json(["aws", "iam", "get-role", "--role-name", VERCEL_AGENT_ROLE_NAME])
    if role_code == 0:
        print(f"Updating Vercel IAM role trust policy: {VERCEL_AGENT_ROLE_NAME}", flush=True)
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
        role_arn = get_role_arn(role_data, VERCEL_AGENT_ROLE_NAME)
    else:
        print(f"Creating Vercel IAM role: {VERCEL_AGENT_ROLE_NAME}", flush=True)
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
                f"OIDC role for Vercel project {VERCEL_PROJECT_NAME} to invoke external Dr. Shalini's Clinic agents.",
            ]
        )
        role_code, role_data = aws_json(["aws", "iam", "get-role", "--role-name", VERCEL_AGENT_ROLE_NAME])
        if role_code != 0:
            raise RuntimeError(f"Unable to create or load IAM role {VERCEL_AGENT_ROLE_NAME}")
        role_arn = get_role_arn(role_data, VERCEL_AGENT_ROLE_NAME)

    print(f"Writing Vercel invoke policy: {VERCEL_AGENT_POLICY_NAME}", flush=True)
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
    print(f"Ensuring Vercel project exists: {VERCEL_PROJECT_NAME}", flush=True)
    project = vercel_request_json(
        method="GET",
        path=vercel_project_path(),
        token=vercel_token,
        team_id=vercel_team_id,
        not_found_ok=True,
    )
    if project is not None:
        print(f"Vercel project exists: {VERCEL_PROJECT_NAME}", flush=True)
        return

    print(f"Creating Vercel project: {VERCEL_PROJECT_NAME}", flush=True)
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
    print(f"Listing Vercel project env vars for {VERCEL_PROJECT_NAME}.", flush=True)
    envs: list[dict[str, Any]] = []
    query: dict[str, str] | None = None
    while True:
        response = vercel_request_json(
            method="GET",
            path=vercel_project_env_path(),
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
    for key, value in sorted(values.items()):
        print(f"Syncing Vercel production env var: {key}", flush=True)
        vercel_request_json(
            method="POST",
            path=vercel_project_env_path(),
            token=vercel_token,
            team_id=vercel_team_id,
            query={"upsert": "true"},
            body={
                "key": key,
                "value": value,
                "type": "encrypted" if key in VERCEL_ENCRYPTED_ENV_KEYS else "plain",
                "target": ["production"],
            },
        )


def vercel_runtime_env(region: str, role_arn: str) -> dict[str, str]:
    values = {
        "AWS_REGION": region,
        "AWS_ROLE_ARN": role_arn,
        "SHALINI_CLINIC_AGENT_BACKEND_MODE": "aws_oidc",
    }
    for key in sorted(VERCEL_MANAGED_ENV_KEYS - values.keys()):
        value = os.environ.get(key, "").strip()
        if value:
            values[key] = value
    return values


def deploy_vercel_oidc_access(vercel_token: str, vercel_team_id: str) -> str:
    log_section("Configuring Vercel OIDC access")
    region = os.environ["AWS_REGION"]
    account_id = get_aws_account_id()
    team_slug = get_vercel_team_slug(vercel_token, vercel_team_id)
    ensure_vercel_project(vercel_token, vercel_team_id)
    role_arn = ensure_vercel_agent_role(account_id, region, team_slug)
    sync_vercel_oidc_env(vercel_token, vercel_team_id, vercel_runtime_env(region, role_arn))
    print(f"Synced Vercel OIDC agent access for {VERCEL_PROJECT_NAME} with role {role_arn}.")
    return team_slug


def deploy_webui() -> None:
    log_section("Deploying WebUI to Vercel")
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
    for key in VERCEL_CLI_OMITTED_ENV_KEYS:
        vercel_env.pop(key, None)
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
    log_section("Validating repo definitions before deploy")
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
