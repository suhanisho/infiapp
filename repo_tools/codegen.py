#!/usr/bin/env python3
"""Generate framework bindings from Infiapp specs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from repo_tools.common import (
    GENERATED_DYNAMODB_PATH,
    GENERATED_WEB_AGENTS_PATH,
    GENERATED_WEB_MOCKS_PATH,
    iter_agent_dirs,
    iter_table_paths,
    load_json,
)


def constant_name(table_name: str) -> str:
    return f"{table_name.upper()}_TABLE"


def snake_identifier(name: str) -> str:
    identifier = re.sub(r"[^0-9a-zA-Z_]+", "_", name).strip("_").lower()
    if not identifier:
        return "table"
    if identifier[0].isdigit():
        return f"table_{identifier}"
    return identifier


def pascal_name(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_") if part)


def typed_dict_name(table_name: str) -> str:
    return f"{pascal_name(snake_identifier(table_name))}Item"


def page_type_name(table_name: str) -> str:
    return f"{pascal_name(snake_identifier(table_name))}Page"


def python_type_name(attribute_type: str) -> str:
    return {
        "String": "str",
        "Number": "int | float",
        "Binary": "bytes",
        "Boolean": "bool",
    }.get(attribute_type, "Any")


def load_tables() -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    for path in iter_table_paths():
        table = load_json(path)
        table["owner_agent"] = path.parent.name
        tables.append(table)
    return tables


def load_agents() -> list[dict[str, Any]]:
    return [load_json(agent_dir / "spec.json") for agent_dir in iter_agent_dirs()]


def render_python_value(value: Any, indent: int = 0) -> str:
    prefix = "    " * indent
    child_prefix = "    " * (indent + 1)
    if isinstance(value, dict):
        if not value:
            return "{}"
        lines = ["{"]
        for key in sorted(value):
            lines.append(f"{child_prefix}{json.dumps(key)}: {render_python_value(value[key], indent + 1)},")
        lines.append(f"{prefix}}}")
        return "\n".join(lines)
    if isinstance(value, list):
        if not value:
            return "[]"
        lines = ["["]
        for item in value:
            lines.append(f"{child_prefix}{render_python_value(item, indent + 1)},")
        lines.append(f"{prefix}]")
        return "\n".join(lines)
    if isinstance(value, str):
        return json.dumps(value)
    return repr(value)


def render_dynamodb_py(tables: list[dict[str, Any]]) -> str:
    lines = [
        '"""Generated DynamoDB helpers. Run `python -m repo_tools codegen` to refresh."""',
        "",
        "from __future__ import annotations",
        "",
        "from collections.abc import Mapping",
        "from typing import Any, TypedDict, cast",
        "",
        "_DYNAMODB_RESOURCE: Any | None = None",
        "",
        "",
        "def _get_dynamodb_resource(dynamodb_resource: Any | None = None) -> Any:",
        "    if dynamodb_resource is not None:",
        "        return dynamodb_resource",
        "",
        "    global _DYNAMODB_RESOURCE",
        "    if _DYNAMODB_RESOURCE is None:",
        "        import boto3",
        "",
        '        _DYNAMODB_RESOURCE = boto3.resource("dynamodb")',
        "    return _DYNAMODB_RESOURCE",
        "",
        "",
        "def _table(table_definition: Mapping[str, Any], dynamodb_resource: Any | None = None) -> Any:",
        '    return _get_dynamodb_resource(dynamodb_resource).Table(str(table_definition["table_name"]))',
        "",
        "",
        "def _build_key(",
        "    table_definition: Mapping[str, Any],",
        "    partition_key_value: Any,",
        "    sort_key_value: Any | None = None,",
        ") -> dict[str, Any]:",
        '    partition_key = table_definition["partition_key"]',
        '    key = {str(partition_key["name"]): partition_key_value}',
        '    sort_key = table_definition.get("sort_key")',
        "    if sort_key:",
        "        if sort_key_value is None:",
        '            raise ValueError(f"{table_definition[\'table_name\']} requires a sort key value.")',
        '        key[str(sort_key["name"])] = sort_key_value',
        "    elif sort_key_value is not None:",
        '        raise ValueError(f"{table_definition[\'table_name\']} does not have a sort key.")',
        "    return key",
        "",
    ]

    for table in sorted(tables, key=lambda item: item["table_name"]):
        item_type_name = typed_dict_name(table["table_name"])
        table_page_type_name = page_type_name(table["table_name"])
        lines.append("")
        lines.append(f"class {item_type_name}(TypedDict):")
        lines.append(f'    """Typed representation of a row in the {table["table_name"]} table."""')
        lines.append("")
        for attribute_name, attribute_type in sorted(table["attributes"].items()):
            lines.append(f"    {snake_identifier(attribute_name)}: {python_type_name(attribute_type)}")
        lines.append("")
        lines.append("")
        lines.append(f"class {table_page_type_name}(TypedDict):")
        lines.append(f'    """Paginated query result for the {table["table_name"]} table."""')
        lines.append("")
        lines.append(f"    items: list[{item_type_name}]")
        lines.append("    next_key: dict[str, Any] | None")
        lines.append("")

    for table in sorted(tables, key=lambda item: item["table_name"]):
        table_value = {
            "table_name": table["table_name"],
            "partition_key": table["primary_key"]["partition_key"],
            "sort_key": table["primary_key"].get("sort_key"),
            "attributes": table["attributes"],
        }
        lines.append(f"{constant_name(table['table_name'])}: dict[str, Any] = {render_python_value(table_value)}")
        lines.append("")

    lines.append("TABLES: dict[str, dict[str, Any]] = {")
    for table in sorted(tables, key=lambda item: item["table_name"]):
        lines.append(f"    {json.dumps(table['table_name'])}: {constant_name(table['table_name'])},")
    lines.append("}")
    lines.append("")

    for table in sorted(tables, key=lambda item: item["table_name"]):
        table_name = table["table_name"]
        table_identifier = snake_identifier(table_name)
        table_constant = constant_name(table_name)
        item_type_name = typed_dict_name(table_name)
        table_page_type_name = page_type_name(table_name)
        partition_key = table["primary_key"]["partition_key"]["name"]
        partition_arg = snake_identifier(partition_key)
        sort_key = table["primary_key"].get("sort_key")
        sort_key_name = sort_key["name"] if sort_key else None
        sort_arg = snake_identifier(sort_key_name) if sort_key_name else None

        lines.extend(
            [
                "",
                f"def put_{table_identifier}(",
                f"    item: {item_type_name},",
                "    *,",
                "    dynamodb_resource: Any | None = None,",
                ") -> dict[str, Any]:",
                "    return cast(",
                "        dict[str, Any],",
                f"        _table({table_constant}, dynamodb_resource).put_item(Item=dict(item)),",
                "    )",
                "",
                "",
            ]
        )

        if sort_key_name and sort_arg:
            lines.extend(
                [
                    f"def get_{table_identifier}(",
                    f"    {partition_arg}: Any,",
                    f"    {sort_arg}: Any,",
                    "    *,",
                    "    dynamodb_resource: Any | None = None,",
                    f") -> {item_type_name} | None:",
                    "    response = _table(",
                    f"        {table_constant},",
                    "        dynamodb_resource,",
                    "    ).get_item(",
                    "        Key=_build_key(",
                    f"            {table_constant},",
                    f"            {partition_arg},",
                    f"            {sort_arg},",
                    "        )",
                    "    )",
                    '    item = response.get("Item")',
                    f"    return cast({item_type_name}, item) if isinstance(item, dict) else None",
                    "",
                    "",
                    f"def query_{table_identifier}_item(",
                    f"    {partition_arg}: Any,",
                    f"    {sort_arg}: Any,",
                    "    *,",
                    "    dynamodb_resource: Any | None = None,",
                    f") -> {item_type_name} | None:",
                    f"    return get_{table_identifier}(",
                    f"        {partition_arg},",
                    f"        {sort_arg},",
                    "        dynamodb_resource=dynamodb_resource,",
                    "    )",
                    "",
                    "",
                    f"def delete_{table_identifier}(",
                    f"    {partition_arg}: Any,",
                    f"    {sort_arg}: Any,",
                    "    *,",
                    "    dynamodb_resource: Any | None = None,",
                    ") -> dict[str, Any]:",
                    "    return cast(",
                    "        dict[str, Any],",
                    f"        _table({table_constant}, dynamodb_resource).delete_item(",
                    "            Key=_build_key(",
                    f"                {table_constant},",
                    f"                {partition_arg},",
                    f"                {sort_arg},",
                    "            )",
                    "        ),",
                    "    )",
                    "",
                    "",
                    f"def query_{table_identifier}_by_{sort_arg}_range_page(",
                    f"    {partition_arg}: Any,",
                    "    *,",
                    f"    start_{sort_arg}: Any | None = None,",
                    f"    end_{sort_arg}: Any | None = None,",
                    "    exclusive_start_key: Mapping[str, Any] | None = None,",
                    "    dynamodb_resource: Any | None = None,",
                    "    scan_index_forward: bool = True,",
                    "    consistent_read: bool = False,",
                    "    limit: int | None = None,",
                    f") -> {table_page_type_name}:",
                    "    from boto3.dynamodb.conditions import Key",
                    "",
                    f'    key_condition = Key("{partition_key}").eq({partition_arg})',
                    f"    if start_{sort_arg} is not None and end_{sort_arg} is not None:",
                    f'        key_condition = key_condition & Key("{sort_key_name}").between(start_{sort_arg}, end_{sort_arg})',
                    f"    elif start_{sort_arg} is not None:",
                    f'        key_condition = key_condition & Key("{sort_key_name}").gte(start_{sort_arg})',
                    f"    elif end_{sort_arg} is not None:",
                    f'        key_condition = key_condition & Key("{sort_key_name}").lte(end_{sort_arg})',
                    "    query_args: dict[str, Any] = {",
                    '        "KeyConditionExpression": key_condition,',
                    '        "ScanIndexForward": scan_index_forward,',
                    '        "ConsistentRead": consistent_read,',
                    "    }",
                    "    if exclusive_start_key is not None:",
                    '        query_args["ExclusiveStartKey"] = dict(exclusive_start_key)',
                    "    if limit is not None:",
                    '        query_args["Limit"] = limit',
                    f"    response = _table({table_constant}, dynamodb_resource).query(**query_args)",
                    '    next_key = response.get("LastEvaluatedKey")',
                    "    return {",
                    f'        "items": [cast({item_type_name}, item) for item in response.get("Items", [])],',
                    '        "next_key": dict(next_key) if isinstance(next_key, dict) else None,',
                    "    }",
                    "",
                    "",
                    f"def query_{table_identifier}_by_{sort_arg}_range(",
                    f"    {partition_arg}: Any,",
                    "    *,",
                    f"    start_{sort_arg}: Any | None = None,",
                    f"    end_{sort_arg}: Any | None = None,",
                    "    dynamodb_resource: Any | None = None,",
                    "    scan_index_forward: bool = True,",
                    "    consistent_read: bool = False,",
                    "    limit: int | None = None,",
                    f") -> list[{item_type_name}]:",
                    f"    return query_{table_identifier}_by_{sort_arg}_range_page(",
                    f"        {partition_arg},",
                    f"        start_{sort_arg}=start_{sort_arg},",
                    f"        end_{sort_arg}=end_{sort_arg},",
                    "        dynamodb_resource=dynamodb_resource,",
                    "        scan_index_forward=scan_index_forward,",
                    "        consistent_read=consistent_read,",
                    "        limit=limit,",
                    '    )["items"]',
                    "",
                    "",
                    f"def query_{table_identifier}(",
                    f"    {partition_arg}: Any,",
                    "    *,",
                    "    dynamodb_resource: Any | None = None,",
                    "    scan_index_forward: bool = True,",
                    "    consistent_read: bool = False,",
                    "    limit: int | None = None,",
                    f") -> list[{item_type_name}]:",
                    f"    return query_{table_identifier}_by_{sort_arg}_range(",
                    f"        {partition_arg},",
                    "        dynamodb_resource=dynamodb_resource,",
                    "        scan_index_forward=scan_index_forward,",
                    "        consistent_read=consistent_read,",
                    "        limit=limit,",
                    "    )",
                    "",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    f"def get_{table_identifier}(",
                    f"    {partition_arg}: Any,",
                    "    *,",
                    "    dynamodb_resource: Any | None = None,",
                    f") -> {item_type_name} | None:",
                    f"    response = _table({table_constant}, dynamodb_resource).get_item(",
                    f"        Key=_build_key({table_constant}, {partition_arg})",
                    "    )",
                    '    item = response.get("Item")',
                    f"    return cast({item_type_name}, item) if isinstance(item, dict) else None",
                    "",
                    "",
                    f"def query_{table_identifier}_item(",
                    f"    {partition_arg}: Any,",
                    "    *,",
                    "    dynamodb_resource: Any | None = None,",
                    f") -> {item_type_name} | None:",
                    f"    return get_{table_identifier}(",
                    f"        {partition_arg},",
                    "        dynamodb_resource=dynamodb_resource,",
                    "    )",
                    "",
                    "",
                    f"def delete_{table_identifier}(",
                    f"    {partition_arg}: Any,",
                    "    *,",
                    "    dynamodb_resource: Any | None = None,",
                    ") -> dict[str, Any]:",
                    "    return cast(",
                    "        dict[str, Any],",
                    f"        _table({table_constant}, dynamodb_resource).delete_item(",
                    f"            Key=_build_key({table_constant}, {partition_arg})",
                    "        ),",
                    "    )",
                    "",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def render_mock_agents_ts(agents: list[dict[str, Any]]) -> str:
    external_agents = [agent for agent in agents if agent["connectivity"] == "external"]
    lines = [
        "// Generated by repo_tools/codegen.py. Do not edit by hand.",
        "",
        "export type AgentRequest = Record<string, unknown>;",
        "",
        "export type AgentMessage = {",
        "  messageId: string;",
        "  createdAt: string;",
        "  message: string;",
        "};",
        "",
        "export type AgentResponse = {",
        "  action?: string;",
        "  message?: string;",
        "  lastMessage?: string;",
        "  item?: AgentMessage;",
        "  messages?: AgentMessage[];",
        "  nextKey?: Record<string, unknown> | null;",
        "  agent: string;",
        "  mocked: boolean;",
        "  stored?: boolean;",
        "};",
        "",
    ]
    for agent in sorted(external_agents, key=lambda item: item["name"]):
        function_name = f"mockCall{pascal_name(agent['name'])}"
        store_name = f"mock{pascal_name(agent['name'])}Messages"
        lines.extend(
            [
                f"const {store_name}: AgentMessage[] = [];",
                "",
                f"export async function {function_name}(payload: AgentRequest = {{}}): Promise<AgentResponse> {{",
                '  const action = typeof payload.action === "string" ? payload.action : "store_message";',
                '  if (action === "list_messages") {',
                '    const limit = typeof payload.limit === "number" ? Math.max(1, Math.min(payload.limit, 50)) : 10;',
                '    const nextKey = payload.nextKey && typeof payload.nextKey === "object" ? (payload.nextKey as Record<string, unknown>) : undefined;',
                '    const offset = typeof nextKey?.offset === "number" ? nextKey.offset : 0;',
                f"    const messages = {store_name}.slice(offset, offset + limit);",
                f"    const newOffset = offset + messages.length;",
                "    return {",
                '      action: "list_messages",',
                "      messages,",
                f"      nextKey: newOffset < {store_name}.length ? {{ offset: newOffset }} : null,",
                f'      agent: "{agent["name"]}",',
                "      mocked: true,",
                "    };",
                "  }",
                "",
                '  const message = typeof payload.message === "string" ? payload.message.trim() : "";',
                "  if (!message) {",
                '    throw new Error("message is required");',
                "  }",
                "  const createdAt = new Date().toISOString();",
                "  const item = {",
                '    messageId: `${createdAt}#mock`,',
                "    createdAt,",
                "    message,",
                "  };",
                f"  {store_name}.unshift(item);",
                "  return {",
                '    action: "store_message",',
                '    message: "message stored",',
                "    item,",
                f'    agent: "{agent["name"]}",',
                "    mocked: true,",
                "    stored: true,",
                "  };",
                "}",
                "",
            ]
        )
    return "\n".join(lines)


def render_agents_ts(agents: list[dict[str, Any]]) -> str:
    external_agents = [agent for agent in agents if agent["connectivity"] == "external"]
    mock_imports = [
        f"mockCall{pascal_name(agent['name'])}"
        for agent in sorted(external_agents, key=lambda item: item["name"])
    ]
    import_clause = ", ".join([*mock_imports, "type AgentResponse"])
    lines = [
        "// Generated by repo_tools/codegen.py. Do not edit by hand.",
        "",
        'import { InvokeCommand, LambdaClient } from "@aws-sdk/client-lambda";',
        'import { awsCredentialsProvider } from "@vercel/oidc-aws-credentials-provider";',
        "",
        f'import {{ {import_clause}, type AgentRequest }} from "./mockAgents";',
        "",
        'type AgentBackendMode = "mock" | "aws_oidc";',
        "",
        "type LambdaEnvelope = {",
        "  statusCode?: number;",
        "  body?: string | AgentResponse;",
        "};",
        "",
        "let lambdaClient: LambdaClient | undefined;",
        "",
        "function getBackendMode(): AgentBackendMode {",
        "  const mode = process.env.INFIAPP_AGENT_BACKEND_MODE;",
        '  if (mode === "mock" || mode === "aws_oidc") {',
        "    return mode;",
        "  }",
        "",
        '  if (!mode && process.env.NODE_ENV !== "production") {',
        '    return "mock";',
        "  }",
        "",
        '  throw new Error("INFIAPP_AGENT_BACKEND_MODE must be set to mock or aws_oidc.");',
        "}",
        "",
        "function getLambdaClient(): LambdaClient {",
        "  if (lambdaClient) {",
        "    return lambdaClient;",
        "  }",
        "",
        "  const region = process.env.AWS_REGION;",
        "  const roleArn = process.env.AWS_ROLE_ARN;",
        "  if (!region) {",
        '    throw new Error("AWS_REGION is required for aws_oidc agent access.");',
        "  }",
        "  if (!roleArn) {",
        '    throw new Error("AWS_ROLE_ARN is required for aws_oidc agent access.");',
        "  }",
        "",
        "  lambdaClient = new LambdaClient({",
        "    region,",
        "    credentials: awsCredentialsProvider({ roleArn }),",
        "  });",
        "  return lambdaClient;",
        "}",
        "",
        "function parseLambdaPayload(functionName: string, payloadText: string): AgentResponse {",
        "  if (!payloadText) {",
        "    throw new Error(`${functionName} returned an empty payload.`);",
        "  }",
        "",
        "  const envelope = JSON.parse(payloadText) as LambdaEnvelope;",
        "  if (typeof envelope.statusCode === \"number\" && envelope.statusCode >= 400) {",
        "    throw new Error(`${functionName} failed with status ${envelope.statusCode}`);",
        "  }",
        "",
        '  if (typeof envelope.body === "string") {',
        "    return JSON.parse(envelope.body) as AgentResponse;",
        "  }",
        "  if (envelope.body && typeof envelope.body === \"object\") {",
        "    return envelope.body;",
        "  }",
        "",
        "  return envelope as AgentResponse;",
        "}",
        "",
        "async function invokeAgent(functionName: string, payload: AgentRequest): Promise<AgentResponse> {",
        "  const response = await getLambdaClient().send(",
        "    new InvokeCommand({",
        "      FunctionName: functionName,",
        '      InvocationType: "RequestResponse",',
        '      Payload: new TextEncoder().encode(JSON.stringify({ ...payload, source: "webUI" })),',
        "    }),",
        "  );",
        "",
        "  const payloadText = response.Payload ? new TextDecoder().decode(response.Payload) : \"\";",
        "  return parseLambdaPayload(functionName, payloadText);",
        "}",
        "",
    ]

    for agent in sorted(external_agents, key=lambda item: item["name"]):
        pascal = pascal_name(agent["name"])
        mock_fn = f"mockCall{pascal}"
        call_fn = f"call{pascal}"
        lines.extend(
            [
                f"export async function {call_fn}(payload: AgentRequest = {{}}): Promise<AgentResponse> {{",
                '  if (getBackendMode() === "mock") {',
                f"    return {mock_fn}(payload);",
                "  }",
                f'  return invokeAgent("{agent["name"]}", payload);',
                "}",
                "",
            ]
        )

    return "\n".join(lines)


def write_or_check(path: Path, content: str, check: bool) -> bool:
    if check:
        existing = path.read_text() if path.exists() else ""
        if existing != content:
            print(f"Generated file is stale: {path}")
            return False
        return True

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    print(f"Wrote {path}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if generated files are stale")
    args = parser.parse_args()

    tables = load_tables()
    agents = load_agents()
    outputs = {
        GENERATED_DYNAMODB_PATH: render_dynamodb_py(tables),
        GENERATED_WEB_MOCKS_PATH: render_mock_agents_ts(agents),
        GENERATED_WEB_AGENTS_PATH: render_agents_ts(agents),
    }

    ok = True
    for path, content in outputs.items():
        ok = write_or_check(path, content, args.check) and ok

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
