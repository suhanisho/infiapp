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
pyproject.toml               Repo-wide pinned Python dependency manifest
repo_tools/
  python_dependencies.py     Resolves pinned Python dependencies from pyproject.toml
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

Agents are Python Lambda functions defined by folder-level specs. Each agent owns its code, tests, and any DynamoDB tables declared for it. Agents can be `internal` or `external`; external agents get generated WebUI clients.

See [agents/README.md](agents/README.md) for the required folder structure, `spec.json` fields, framework defaults, shared utilities, and test expectations.

## DynamoDB

DynamoDB tables are declared as JSON specs under `dynamodb/<agent_name>/`. Each table belongs to the agent named by its parent folder, and repo tools generate shared Python helpers from these specs.

See [dynamodb/README.md](dynamodb/README.md) for the table spec format, supported attribute types, defaults, and key compatibility rules.

## WebUI

`webUI/` is a single Next.js App Router application. It is the user-facing web app for the repo.

Conventions:

- Use generated agent helpers from `webUI/src/lib/generated/agents.ts` when the WebUI calls external agents.
- Use generated mocks from `webUI/src/lib/generated/mockAgents.ts` for local development and tests.
- Keep API routes under `webUI/app/api/` thin; they should translate HTTP requests into generated agent-helper calls.
- Add WebUI package tests for generated-client behavior and other non-visual logic.
- Add curl smoke coverage for important API endpoints in `.github/workflows/test-webUI.yml`.
- Add Playwright screenshot coverage for important user workflows, including phone-sized viewports.

WebUI production agent access:

- External agent calls use generated AWS Lambda clients.
- Local development and tests use generated mocks.
- The deploy workflow configures Vercel production environment variables for OIDC access automatically.

## Repo Tools

Run repo tools from an activated Python virtual environment.

Run all repo checks:

```bash
source .venv/bin/activate
python -m repo_tools check
```

Generate code:

```bash
python -m repo_tools codegen
```

Validate generated files are current:

```bash
python -m repo_tools codegen-check
```

Validate specs:

```bash
python -m repo_tools validate
```

Install Python dependencies:

```bash
python -m repo_tools install-python
```

Run all tests:

```bash
python -m repo_tools test-agents
python -m repo_tools test-web
```

The generated files are:

- `agents/shared_utils/generated/dynamodb.py`
- `webUI/src/lib/generated/agents.ts`
- `webUI/src/lib/generated/mockAgents.ts`

## Local Setup

Required local tools:

- Python 3.11 is needed. On macOS:

  ```bash
  brew install python@3.11
  ```

- Node.js 22 is needed. On macOS:

  ```bash
  brew install node@22
  ```

- npm 10 is needed. `node@22` installs npm; if needed, pin npm with:

  ```bash
  npm install -g npm@10
  ```

Create a Python virtual environment:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

Install Python dependencies:

```bash
python -m repo_tools install-python
```

Python dependencies are pinned in root `pyproject.toml`. Agent specs list dependency names in `required_dependencies`, and validation fails if an agent names a dependency that is not pinned there.

Install Node dependencies:

```bash
npm --prefix webUI install
```

Generate framework helpers:

```bash
python -m repo_tools codegen
```

Run the WebUI:

```bash
npm --prefix webUI run dev
```

Run the starter agent test:

```bash
python -m repo_tools test-agents
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
- `VERCEL_TOKEN`
- `VERCEL_TEAM_ID`

Create the AWS secrets:

1. Use a dedicated AWS account for this app if possible.
2. In the AWS Console, go to **IAM > Users > Create user**.
3. Name the user `infiapp-control-plane`.
4. Choose **Attach policies directly** and attach the AWS managed policy `AdministratorAccess`.
5. Open the new user, go to **Security credentials > Create access key**.
6. Choose **Third-party service** as the use case.
7. Copy the **Access key ID** into GitHub as `AWS_ACCESS_KEY_ID`.
8. Copy the **Secret access key** into GitHub as `AWS_SECRET_ACCESS_KEY`.
9. Set `AWS_REGION` to the AWS region you want to deploy into, for example `us-east-1`.

For initial setup, the AWS keys are intentionally admin keys in an isolated account. The deploy workflow needs to create and update:

- DynamoDB tables.
- Lambda functions.
- IAM roles and inline role policies for generated agent roles.
- A Vercel OIDC IAM provider and project role for invoking external agents.
- CloudWatch Logs permissions attached to generated Lambda roles.

Create the Vercel secrets:

1. Create or choose the Vercel team that should own the WebUI project.
2. In Vercel, open **Settings > Tokens**.
3. Create a token for the account or team that owns the WebUI project. Copy the token immediately and add it to GitHub as `VERCEL_TOKEN`.
4. In Vercel, open the owning team's **Settings > General** page.
5. Copy the **Team ID**, which starts with `team_`, and add it to GitHub as `VERCEL_TEAM_ID`.

Do not install the Vercel GitHub app for this repo. Infiapp deploys the WebUI from the GitHub Actions deploy workflow.

Add all secrets in GitHub under **Repository > Settings > Secrets and variables > Actions > Repository secrets**. This repo does not require `AWS_ACCOUNT_ID`, `VERCEL_ORG_ID`, or `VERCEL_PROJECT_ID`; the AWS account id is read from the configured AWS credentials and Vercel is configured with `VERCEL_TOKEN` plus `VERCEL_TEAM_ID`.

The deploy workflow creates one IAM role per agent and grants that role full access to tables owned by the same agent. It also creates a Vercel OIDC role that can invoke external agents. Agent specs do not contain IAM policy JSON.

Deploy manually from GitHub Actions after changes land on `main`. Do not deploy from a local machine. The deploy workflow runs:

```bash
python -m repo_tools.deploy
```

The deploy tool is deliberately small and auditable. The GitHub Actions workflow uses it to create or update DynamoDB tables, package Lambda agents, configure Vercel OIDC access, and deploy the WebUI with Vercel.

The deploy workflow manages these Vercel production environment variables:

- `AWS_REGION`
- `AWS_ROLE_ARN`
- `INFIAPP_AGENT_BACKEND_MODE=aws_oidc`

## Deployed State Verification

`.github/workflows/verify-deployed-state.yml` is manually triggered and only runs from `main`. It compares the current deployed infrastructure against repo definitions:

```bash
python -m repo_tools.check_deployed_state
```

It verifies:

- DynamoDB tables exist with matching primary and sort keys.
- Lambda functions exist for every agent spec.
- Vercel OIDC access exists for invoking external agents.
