# Infiapp

Infiapp is a minimal, opinionated framework for building web applications. It abstracts infrastructure deployment and management into maintainable, secure repo conventions so builders can vibe code applications with a practical level of production readiness.

The framework keeps four concepts small and explicit:

- **Agents** are AWS Lambda functions. Each agent owns its runtime code, tests, and `spec.json`.
- **DynamoDB** tables are declared in repo specs. Tables are owned by agents and generated into helper APIs for agent reads and writes.
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
  test-webUI.yml             WebUI build, Playwright E2E and screenshot checks
  deploy.yml                 Main-only deploy workflow
  verify-deployed-state.yml  Main-only deployed-state verification
```

## Agents

Agents are Python Lambda functions defined by folder-level specs. Each agent owns its code, tests, and any DynamoDB tables declared for it. Agents can be `internal` or `external`; external agents get generated WebUI clients.

See [agents/README.md](agents/README.md) for the required folder structure, `spec.json` fields, framework defaults, shared utilities, and test expectations.

## DynamoDB

DynamoDB tables are declared as JSON specs under `dynamodb/<agent_name>/`. Each table belongs to the agent named by its parent folder, and repo tools generate shared Python helpers from these specs, including typed item objects, single-item reads, sort-key range queries, and item puts.

See [dynamodb/README.md](dynamodb/README.md) for the table spec format, supported attribute types, defaults, and key compatibility rules.

## WebUI

`webUI/` is a single Next.js App Router application. It can call external Lambda agents through generated helpers, uses generated agent mocks for local development, and should be tested with build checks and Playwright E2E screenshots.

See [webUI/README.md](webUI/README.md) for WebUI conventions, generated helper usage, local mock behavior, and test expectations.

## Repo Tools

`repo_tools/` contains the Python command runner, validators, code generators, deploy tooling, and deployed-state verification. Run it from an activated Python virtual environment.

See [repo_tools/README.md](repo_tools/README.md) for the command reference and generated file list.

## Getting Started

Fork this repo into your own GitHub account or organization, then clone your fork.

Rename the starter app before building on it:

```bash
APP_NAME="my-app-name" APP_TITLE="My App Name" python3 - <<'PY'
from pathlib import Path
import subprocess
import os

app_name = os.environ["APP_NAME"]
app_title = os.environ["APP_TITLE"]

for rel_path in subprocess.check_output(["git", "ls-files"], text=True).splitlines():
    path = Path(rel_path)
    try:
        text = path.read_text()
    except UnicodeDecodeError:
        continue
    updated = text.replace("Infiapp", app_title).replace("infiapp", app_name)
    if updated != text:
        path.write_text(updated)
PY
```

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

Create a Python virtual environment:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

Install Python dependencies:

```bash
python -m pip install ".[dev]"
```

Python dependencies are pinned in root `pyproject.toml`. Agent specs list dependency names in `required_dependencies`, and validation fails if an agent names a dependency that is not pinned there.

Install Node dependencies:

```bash
npm --prefix webUI install
```

Run the WebUI against generated agent mocks:

```bash
INFIAPP_AGENT_BACKEND_MODE=mock npm --prefix webUI run dev
```

Open `http://localhost:3000` in a browser.

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

Create the Vercel secrets:

1. Create or choose the Vercel team that should own the WebUI project.
2. In Vercel, open **Settings > Tokens**.
3. Create a token for the account or team that owns the WebUI project. Copy the token immediately and add it to GitHub as `VERCEL_TOKEN`.
4. In Vercel, open the owning team's **Settings > General** page.
5. Copy the **Team ID**, which starts with `team_`, and add it to GitHub as `VERCEL_TEAM_ID`.

No need to install the Vercel GitHub app for this repo. Infiapp deploys the WebUI from the GitHub Actions deploy workflow.

Add all secrets in GitHub under **Repository > Settings > Secrets and variables > Actions > Repository secrets**.

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
