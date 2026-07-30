#!/usr/bin/env python3
"""Generate framework bindings from Nora specs."""

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
    load_table_spec,
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


def type_prefix(agent_name: str, call_name: str) -> str:
    return f"{pascal_name(agent_name)}{pascal_name(call_name)}"


def ts_property_name(name: str) -> str:
    if re.fullmatch(r"[A-Za-z_$][0-9A-Za-z_$]*", name):
        return name
    return json.dumps(name)


def ts_type_atom(type_name: str) -> str:
    if type_name.startswith("Literal[") and type_name.endswith("]"):
        value = type_name.removeprefix("Literal[").removesuffix("]")
        return json.dumps(value)
    return {
        "String": "string",
        "Number": "number",
        "Boolean": "boolean",
        "Binary": "Uint8Array",
        "Map": "Record<string, unknown>",
        "List": "unknown[]",
        "Any": "unknown",
        "Null": "null",
    }.get(type_name, "unknown")


def ts_type_from_schema(schema: Any) -> str:
    if isinstance(schema, str):
        return " | ".join(ts_type_atom(part.strip()) for part in schema.split("|"))

    if isinstance(schema, list):
        if len(schema) != 1:
            return "unknown[]"
        return f"{ts_type_from_schema(schema[0])}[]"

    if isinstance(schema, dict):
        fields = []
        for name, value in sorted(schema.items()):
            optional = "?" if name.endswith("?") else ""
            clean_name = name[:-1] if optional else name
            fields.append(f"{ts_property_name(clean_name)}{optional}: {ts_type_from_schema(value)};")
        return "{ " + " ".join(fields) + " }"

    return "unknown"


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
        "List": "list[Any]",
        "Map": "dict[str, Any]",
    }.get(attribute_type, "Any")


def load_tables() -> list[dict[str, Any]]:
    return [load_table_spec(path) for path in iter_table_paths()]


def load_agents() -> list[dict[str, Any]]:
    agents: list[dict[str, Any]] = []
    for agent_dir in iter_agent_dirs():
        spec = load_json(agent_dir / "spec.json")
        spec["name"] = agent_dir.name
        agents.append(spec)
    return agents


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
                f"def put_{table_identifier}_if_absent(",
                f"    item: {item_type_name},",
                "    *,",
                "    dynamodb_resource: Any | None = None,",
                ") -> bool:",
                '    expression_attribute_names = {"#partition_key": '
                + json.dumps(partition_key)
                + "}",
                '    condition_expression = "attribute_not_exists(#partition_key)"',
            ]
        )
        if sort_key_name:
            lines.extend(
                [
                    f'    expression_attribute_names["#sort_key"] = {json.dumps(sort_key_name)}',
                    '    condition_expression += " AND attribute_not_exists(#sort_key)"',
                ]
            )
        lines.extend(
            [
                "    try:",
                f"        _table({table_constant}, dynamodb_resource).put_item(",
                "            Item=dict(item),",
                "            ConditionExpression=condition_expression,",
                "            ExpressionAttributeNames=expression_attribute_names,",
                "        )",
                "    except Exception as exc:",
                '        response = getattr(exc, "response", None)',
                "        error = response.get(\"Error\") if isinstance(response, dict) else None",
                "        if isinstance(error, dict) and error.get(\"Code\") == \"ConditionalCheckFailedException\":",
                "            return False",
                "        raise",
                "    return True",
                "",
                "",
                f"def put_{table_identifier}_if_newer(",
                f"    item: {item_type_name},",
                "    *,",
                "    ordering_attribute: str,",
                "    dynamodb_resource: Any | None = None,",
                ") -> bool:",
                "    item_dict = dict(item)",
                "    if ordering_attribute not in item_dict:",
                f'        raise ValueError(f"{table_name} item does not contain {{ordering_attribute}}.")',
                "    try:",
                f"        _table({table_constant}, dynamodb_resource).put_item(",
                "            Item=item_dict,",
                '            ConditionExpression="attribute_not_exists(#ordering) OR #ordering < :ordering",',
                '            ExpressionAttributeNames={"#ordering": ordering_attribute},',
                '            ExpressionAttributeValues={":ordering": item_dict[ordering_attribute]},',
                "        )",
                "    except Exception as exc:",
                '        response = getattr(exc, "response", None)',
                '        error = response.get("Error") if isinstance(response, dict) else None',
                '        if isinstance(error, dict) and error.get("Code") == "ConditionalCheckFailedException":',
                "            return False",
                "        raise",
                "    return True",
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
        'import { callMockAgent } from "../mocks/agentMocks";',
        "",
    ]

    request_types: list[str] = []
    response_types: list[str] = []
    for agent in sorted(external_agents, key=lambda item: item["name"]):
        calls = sorted(agent["api_context"], key=lambda item: item["call"])
        agent_request_types: list[str] = []
        agent_response_types: list[str] = []
        for call in calls:
            prefix = type_prefix(agent["name"], call["call"])
            lines.append(f"export type {prefix}Input = {ts_type_from_schema(call['input'])};")
            lines.append(f"export type {prefix}Output = {ts_type_from_schema(call['output'])};")
            lines.append("")
            agent_request_types.append(f"({{ action: {json.dumps(call['call'])} }} & {prefix}Input)")
            agent_response_types.append(f"{prefix}Output")

        agent_pascal = pascal_name(agent["name"])
        agent_request = f"{agent_pascal}Request"
        agent_response = f"{agent_pascal}Response"
        lines.append(f"export type {agent_request} = {' | '.join(agent_request_types)};")
        lines.append(f"export type {agent_response} = {' | '.join(agent_response_types)};")
        lines.append("")
        request_types.append(agent_request)
        response_types.append(agent_response)

    lines.append(f"export type AgentRequest = {' | '.join(request_types) if request_types else 'never'};")
    lines.append(f"export type AgentResponse = {' | '.join(response_types) if response_types else 'never'};")
    lines.append("")

    for agent in sorted(external_agents, key=lambda item: item["name"]):
        agent_pascal = pascal_name(agent["name"])
        function_name = f"mockCall{pascal_name(agent['name'])}"
        request_name = f"{agent_pascal}Request"
        response_name = f"{agent_pascal}Response"
        lines.extend(
            [
                f"export async function {function_name}(payload: {request_name}): Promise<{response_name}> {{",
                f'  return callMockAgent("{agent["name"]}", payload) as Promise<{response_name}>;',
                "}",
                "",
            ]
        )
    return "\n".join(lines)


def render_agents_ts(agents: list[dict[str, Any]]) -> str:
    external_agents = [agent for agent in agents if agent["connectivity"] == "external"]
    mock_imports: list[str] = []
    type_imports: list[str] = []
    for agent in sorted(external_agents, key=lambda item: item["name"]):
        mock_imports.append(f"mockCall{pascal_name(agent['name'])}")
        for call in sorted(agent["api_context"], key=lambda item: item["call"]):
            prefix = type_prefix(agent["name"], call["call"])
            type_imports.extend([f"type {prefix}Input", f"type {prefix}Output"])
    import_clause = ", ".join([*mock_imports, *type_imports])
    lines = [
        "// Generated by repo_tools/codegen.py. Do not edit by hand.",
        "",
        'import { InvokeCommand, LambdaClient } from "@aws-sdk/client-lambda";',
        'import { awsCredentialsProvider } from "@vercel/oidc-aws-credentials-provider";',
        'import crypto from "node:crypto";',
        "",
        f'import {{ {import_clause} }} from "./mockAgents";',
        "",
        'type AgentBackendMode = "mock" | "aws_oidc";',
        "",
        "type LambdaEnvelope<T> = {",
        "  errorMessage?: string;",
        "  errorType?: string;",
        "  statusCode?: number;",
        "  body?: string | T;",
        "};",
        "",
        "let lambdaClient: LambdaClient | undefined;",
        "",
        "function getBackendMode(): AgentBackendMode {",
        "  const mode = process.env.SHALINI_CLINIC_AGENT_BACKEND_MODE;",
        '  if (mode === "mock" || mode === "aws_oidc") {',
        "    return mode;",
        "  }",
        "",
        '  if (!mode && process.env.NODE_ENV !== "production") {',
        '    return "mock";',
        "  }",
        "",
        '  throw new Error("SHALINI_CLINIC_AGENT_BACKEND_MODE must be set to mock or aws_oidc.");',
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
        "function parseLambdaPayload<T>(functionName: string, payloadText: string): T {",
        "  if (!payloadText) {",
        "    throw new Error(`${functionName} returned an empty payload.`);",
        "  }",
        "",
        "  const envelope = JSON.parse(payloadText) as LambdaEnvelope<T>;",
        "  if (typeof envelope.statusCode === \"number\" && envelope.statusCode >= 400) {",
        "    let detail = `${functionName} failed with status ${envelope.statusCode}`;",
        "    const body = typeof envelope.body === \"string\" ? JSON.parse(envelope.body) as unknown : envelope.body;",
        "    if (body && typeof body === \"object\" && \"error\" in body && typeof body.error === \"string\") {",
        "      detail = body.error;",
        "    }",
        "    throw new Error(detail);",
        "  }",
        "",
        '  if (typeof envelope.body === "string") {',
        "    return JSON.parse(envelope.body) as T;",
        "  }",
        "  if (envelope.body && typeof envelope.body === \"object\") {",
        "    return envelope.body;",
        "  }",
        "",
        "  return envelope as T;",
        "}",
        "",
        "function internalAgentSecret(): string {",
        "  const secret = process.env.CLINIC_AGENT_INTERNAL_SECRET || process.env.NEXTAUTH_SECRET || process.env.AUTH_SECRET;",
        "  if (!secret) {",
        '    throw new Error("CLINIC_AGENT_INTERNAL_SECRET or NEXTAUTH_SECRET is required for trusted agent calls.");',
        "  }",
        "  return secret;",
        "}",
        "",
        "function actorEmailFromPayload(payload: Record<string, unknown>): string {",
        '  const value = typeof payload.actorEmail === "string" && payload.actorEmail.trim()',
        "    ? payload.actorEmail",
        '    : typeof payload.accountEmail === "string"',
        "      ? payload.accountEmail",
        '      : "";',
        "  return value.trim().toLowerCase();",
        "}",
        "",
        "function withTrustedActorAssertion(payload: object): object {",
        "  const payloadRecord = payload as Record<string, unknown>;",
        "  const actorEmail = actorEmailFromPayload(payloadRecord);",
        "  if (!actorEmail) {",
        "    return payload;",
        "  }",
        "  const actorIssuedAt = Math.floor(Date.now() / 1000).toString();",
        "  const actorSignature = crypto",
        '    .createHmac("sha256", internalAgentSecret())',
        '    .update(`${actorEmail}:${actorIssuedAt}`)',
        '    .digest("hex");',
        "  return {",
        "    ...payloadRecord,",
        "    actorEmail,",
        "    actorIssuedAt,",
        "    actorSignature,",
        "  };",
        "}",
        "",
        "async function invokeLambda<T>(functionName: string, payload: object): Promise<T> {",
        "  const trustedPayload = withTrustedActorAssertion({ ...payload, source: \"webUI\" });",
        "  const response = await getLambdaClient().send(",
        "    new InvokeCommand({",
        "      FunctionName: functionName,",
        '      InvocationType: "RequestResponse",',
        "      Payload: new TextEncoder().encode(JSON.stringify(trustedPayload)),",
        "    }),",
        "  );",
        "",
        "  const payloadText = response.Payload ? new TextDecoder().decode(response.Payload) : \"\";",
        "  if (response.FunctionError) {",
        "    let detail = `${functionName} failed: ${response.FunctionError}`;",
        "    if (payloadText) {",
        "      try {",
        "        const errorPayload = JSON.parse(payloadText) as LambdaEnvelope<unknown>;",
        "        if (typeof errorPayload.errorMessage === \"string\" && errorPayload.errorMessage) {",
        "          detail = errorPayload.errorMessage;",
        "        }",
        "      } catch {",
        "        detail = payloadText;",
        "      }",
        "    }",
        "    throw new Error(detail);",
        "  }",
        "  return parseLambdaPayload<T>(functionName, payloadText);",
        "}",
        "",
    ]

    for agent in sorted(external_agents, key=lambda item: item["name"]):
        pascal = pascal_name(agent["name"])
        mock_fn = f"mockCall{pascal}"
        call_fn = f"call{pascal}"
        for call in sorted(agent["api_context"], key=lambda item: item["call"]):
            prefix = type_prefix(agent["name"], call["call"])
            wrapper_name = f"{call_fn}{pascal_name(call['call'])}"
            lines.extend(
                [
                    f"export async function {wrapper_name}(input: {prefix}Input): Promise<{prefix}Output> {{",
                    f'  const payload: {{ action: "{call["call"]}" }} & {prefix}Input = {{ action: "{call["call"]}", ...input }};',
                    '  if (getBackendMode() === "mock") {',
                    f"    return {mock_fn}(payload) as Promise<{prefix}Output>;",
                    "  }",
                    f'  return invokeLambda<{prefix}Output>("{agent["name"]}", payload);',
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
