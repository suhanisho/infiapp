# Agents

Each folder in `agents/` except `shared_utils/` is one AWS Lambda agent.

An agent must contain:

```text
agents/<agent_name>/
  code/
    handler.py
  test/
    test_*.py
  spec.json
```

## Spec

`spec.json` is the deployment contract for the agent:

```json
{
  "name": "sample_agent",
  "description": "Stores and echoes sample messages for the starter app.",
  "connectivity": "external",
  "handler": "handler.lambda_handler",
  "required_dependencies": [
    "boto3",
    "python-slugify"
  ]
}
```

Fields:

- `name`: must match the agent folder name.
- `description`: non-empty human-readable purpose.
- `connectivity`: `internal` or `external`.
- `handler`: Python module and function under `code/`, using `module.function` format.
- `required_dependencies`: package names used by the agent. Each name must resolve to an exact pinned requirement in root `pyproject.toml`.

Framework defaults:

- Runtime is always Python 3.11.
- Lambda type is always code.
- Agents are manually triggered by default.
- Agent specs do not declare IAM policy JSON.
- Agent specs do not declare environment variables or event triggers yet.
- Each agent automatically receives full access to DynamoDB tables declared under `dynamodb/<agent_name>/`.
- External agents get generated WebUI clients and are invoked by the deployed WebUI through Vercel OIDC IAM access.

## Code

Put Lambda implementation files under `code/`. The handler named in `spec.json` must exist there.

Shared Python utilities belong in `agents/shared_utils/`. Agent tests and deployment packaging make this folder importable for every agent.

Generated shared utilities live under `agents/shared_utils/generated/`. DynamoDB table specs generate a typed item object for every table plus helpers to put an item, query one item by key, and query a sort-key range. Agent code should use those helpers instead of hand-building table clients. Do not edit generated files by hand; update specs or `repo_tools/codegen.py`, then run:

```bash
python -m repo_tools codegen
```

## Dependencies

Declare Python package needs in `required_dependencies` as package names only, such as `python-slugify`. Add the exact pinned version once in root `pyproject.toml` under `project.dependencies`.

Install Python dependencies from an activated venv with:

```bash
python -m pip install ".[dev]"
```

Deployment packages only the pinned dependencies named by each agent.

## Tests

Put agent tests under `agents/<agent_name>/test/` with names matching `test_*.py`. Put shared utility tests under `agents/shared_utils/test/`; the same test command and CI workflow run them.

Agent unit tests must mock every external dependency. Do not call live AWS services, DynamoDB tables, Lambda functions, HTTP APIs, Vercel, databases, queues, or other networked systems from unit tests. Use fakes, stubs, dependency injection, or `unittest.mock` so tests only verify the agent's code and generated helper contracts.

Run all agent checks:

```bash
python -m repo_tools validate-agents
python -m repo_tools test-agents
python -m repo_tools typecheck-agents
```

The GitHub workflow `.github/workflows/test-agents.yml` runs these checks on pull requests and pushes to `main`.
