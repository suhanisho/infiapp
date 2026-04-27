# Infiapp

Infiapp is a minimal, opinionated framework for building web applications. It abstracts infrastructure deployment and management into maintainable, secure repo conventions so builders can vibe code applications with a practical level of production readiness.

The framework keeps four concepts small and explicit:

- **Agents** are AWS Lambda functions. Each agent owns its runtime code, tests, and `spec.json`.
- **DynamoDB** tables are declared in repo specs. Tables are owned by agents and generated into typed helper APIs.
- **WebUI** is one Next.js application. External agents are exposed to it through generated API clients and mocks.
- **Repo Tools** validate specs, generate code, run tests and manage infrastructure.

## Repository Layout

```text
agents/
  README.md                  Agent folder contract and spec reference
  shared_utils/              Shared Python utilities copied onto every Lambda path
  sample_agent/
    code/                    Lambda handler and implementation
    test/                    Agent unit tests
    spec.json                Agent definition
dynamodb/
  README.md                  DynamoDB table spec
  sample_agent/
    sample_messages.json     Demo message table owned by sample_agent
repo_tools/
  codegen.py                 Generates DynamoDB helpers and WebUI agent clients
  validate_agents.py         Validates Lambda agent specs
  validate_dynamodb.py       Validates table specs and key compatibility
  check_deployed_state.py    Compares deployed infra with repo definitions
  deploy.py                  Deploys DynamoDB, Lambda agents, and Vercel WebUI
webUI/
  app/                       Next.js App Router application
  src/lib/generated/         Generated external agent clients and mocks
.github/workflows/
  test-agents.yml            Agent spec validation, agent tests, Python compile checks
  test-db.yml                DynamoDB spec validation and generated-code checks
  test-webUI.yml             WebUI package tests, build, curl, screenshot checks
  deploy.yml                 Main-only deploy workflow
  verify-deployed-state.yml  Main-only deployed-state verification
```

## Agents

Each folder in `agents/` except `shared_utils/` is a Lambda agent.

Agent folders must contain:

```text
agents/<agent_name>/
  code/
    handler.py
  test/
    test_*.py
  spec.json
```

`spec.json` is intentionally small:

```json
{
  "name": "sample_agent",
  "description": "Stores and echoes sample messages for the starter app.",
  "connectivity": "external",
  "handler": "handler.lambda_handler"
}
```

Rules:

- `name` must match the folder name.
- `connectivity` must be `internal` or `external`.
- Runtime is always Python 3.11.
- Lambda type is always code.
- Agents are manually triggered by default.
- Environment variables and custom triggers are not part of the initial framework.
- Each agent automatically receives full permissions to its own DynamoDB tables.
- Shared code belongs in `agents/shared_utils/` and is importable by every agent test and Lambda package.
- External agents are generated into `webUI/src/lib/generated/agents.ts` and can be called from the WebUI.

## DynamoDB

DynamoDB definitions live under `dynamodb/`. Each agent owns one folder, and every JSON file inside that folder defines one table.

Example:

```json
{
  "table_name": "sample_messages",
  "owner_agent": "sample_agent",
  "billing_mode": "PAY_PER_REQUEST",
  "primary_key": {
    "partition_key": {
      "name": "app_name",
      "type": "S"
    },
    "sort_key": {
      "name": "message_id",
      "type": "S"
    }
  },
  "attributes": {
    "app_name": "S",
    "message_id": "S",
    "created_at": "S",
    "message": "S"
  }
}
```

Compatibility rules:

- The table file path owns the table identity.
- `table_name` and `owner_agent` are required.
- `owner_agent` must match the parent folder.
- Partition key and sort key names and types are backwards compatible and must not change after deployment.
- Non-key attributes may be added, changed, or removed.
- The validator compares against `.infiapp/table-key-baseline.json` when present. Generate or refresh the baseline intentionally after the first accepted table definition.

## WebUI

`webUI/` is a single Next.js App Router application. It has one starter page:

- Displays `Hi from infiapp`.
- Shows a message input and a button that calls `/api/sample`.
- `/api/sample` uses the generated external agent client.
- In local development the generated client uses the mock and echoes the submitted message.
- In production it calls the configured Lambda Function URL.
- `sample_agent` stores submitted messages in `sample_messages` and returns the latest submitted message as `lastMessage`.

Required WebUI secrets and environment variables:

- `NEXT_PUBLIC_APP_NAME`: optional display name, defaults to `Infiapp`.
- `SAMPLE_AGENT_URL`: production URL for the external `sample_agent` Lambda Function URL.

## Repo Tools

Run all repo checks:

```bash
npm run check
```

Generate code:

```bash
npm run codegen
```

Validate generated files are current:

```bash
npm run codegen:check
```

Validate specs:

```bash
npm run validate
```

Run all tests:

```bash
npm test
```

The generated files are:

- `agents/shared_utils/generated/dynamodb.py`
- `webUI/src/lib/generated/agents.ts`
- `webUI/src/lib/generated/mockAgents.ts`

## Local Setup

Required local tools:

- Python 3.11 for Lambda parity. Python 3.10 can run the current repo tools locally, but CI and Lambda use 3.11.
- Node.js 22.
- npm 10 or newer.
- AWS CLI v2 for deploy and deployed-state verification.
- Vercel CLI, invoked through `npx vercel`, for WebUI deployment.

Create a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

The current framework tools use only the Python standard library, so there are no Python packages to install yet. Keep the venv anyway so future agent dependencies have a predictable home.

Install Node dependencies:

```bash
npm --prefix webUI install
```

Generate framework helpers:

```bash
npm run codegen
```

Run the WebUI:

```bash
npm --prefix webUI run dev
```

Run the starter agent test:

```bash
python3 -m unittest discover -s agents -p 'test_*.py'
```

## CI

The test workflows run on pull requests and pushes to `main`:

- `.github/workflows/test-agents.yml` validates agent specs, runs all agent tests, and compiles Python tooling.
- `.github/workflows/test-db.yml` validates DynamoDB table specs and fails if generated files are stale.
- `.github/workflows/test-webUI.yml` installs and tests `webUI`, builds it, starts it, runs a curl smoke test, and runs Playwright screenshot tests.

## Operations

Production operations are manual and main-only.

Use `.github/workflows/deploy.yml` when you want to apply the repo definition to AWS and Vercel. The workflow has `workflow_dispatch` only, so it must be started manually from GitHub Actions after the desired commit is on `main`.

Use `.github/workflows/verify-deployed-state.yml` when you want to check whether deployed AWS resources still match this repo. This workflow is also `workflow_dispatch` only and only runs from `main`.

## Deployment

Deployment is intentionally centralized in `.github/workflows/deploy.yml`, is manually triggered, and only runs from `main`.

Required GitHub secrets:

- `AWS_REGION`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_ACCOUNT_ID`
- `VERCEL_TOKEN`
- `VERCEL_ORG_ID`
- `VERCEL_PROJECT_ID`

The AWS credentials must be allowed to manage:

- DynamoDB tables.
- Lambda functions and Lambda Function URLs.
- IAM roles and inline role policies for generated agent roles.
- CloudWatch Logs permissions attached to generated Lambda roles.

The deploy workflow creates one IAM role per agent and grants that role full access to tables owned by the same agent. Agent specs do not contain IAM policy JSON.

Deploy manually from GitHub Actions after changes land on `main`. The deploy workflow runs:

```bash
python3 repo_tools/deploy.py
```

The deploy tool is deliberately small and auditable. It creates or updates DynamoDB tables, packages Lambda agents, and deploys the WebUI with Vercel.

Required runtime environment variables:

- `SAMPLE_AGENT_URL`: set in Vercel production once the external Lambda Function URL exists. If this is missing, the WebUI uses its generated local mock.
- `NEXT_PUBLIC_APP_NAME`: optional display name, defaults to `Infiapp`.

## Deployed State Verification

`.github/workflows/verify-deployed-state.yml` is manually triggered and only runs from `main`. It compares the current deployed infrastructure against repo definitions:

```bash
python3 repo_tools/check_deployed_state.py
```

It verifies:

- DynamoDB tables exist with matching primary and sort keys.
- Lambda functions exist for every agent spec.
- External agents have a Lambda Function URL configured.

## Development Conventions

When adding an agent:

- Create `agents/<agent_name>/spec.json`.
- Add `agents/<agent_name>/code/handler.py`.
- Add focused unit tests in `agents/<agent_name>/test/`.
- Add DynamoDB table specs under `dynamodb/<agent_name>/` when the agent owns data.
- Run `npm run codegen` after adding external agents or DynamoDB specs.

When changing DynamoDB:

- Keep primary and sort key names and types stable.
- Prefer additive table changes.
- Update tests around code that reads or writes new attributes.

When changing WebUI:

- Add package tests for client logic.
- Add or update Playwright tests for visible workflows.
- Keep generated files generated; edit specs or generator code instead.

Before opening a PR:

```bash
npm run check
```
