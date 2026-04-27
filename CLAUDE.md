# Agent Development Notes

Read `README.md` to learn the framework purpose, concepts, setup, tests, and deployment flow. Read the README inside each framework folder, including `agents/`, `webUI/`, `repo_tools/`, and `dynamodb/`, to understand the conventions for developing those concepts.

Hard rules:

- Never push directly to `main`; create a branch and open a pull request for every change.
- Always run Python commands, Python tests, repo tools, validators, codegen, and type checks through the repo venv. Prefer one-command invocations with `.venv/bin/python` instead of relying on shell activation:

  ```bash
  .venv/bin/python -m repo_tools validate-agents
  ```

Expected workflow:

1. Install Python dependencies with `.venv/bin/python -m pip install ".[dev]"`.
2. Validate changed specs with targeted commands such as `.venv/bin/python -m repo_tools validate-agents` or `.venv/bin/python -m repo_tools validate-db`.
3. Regenerate framework code with `.venv/bin/python -m repo_tools codegen`.
4. Run agent tests with `.venv/bin/python -m repo_tools test-agents`.
5. Type check agents with `.venv/bin/python -m repo_tools typecheck-agents`.
6. Run WebUI build and Playwright checks with `.venv/bin/python -m repo_tools build-web` and `.venv/bin/python -m repo_tools test-web-e2e`.
7. Run targeted repo tool commands for the files and behavior you changed before finalizing larger changes.

Python dependencies are pinned in root `pyproject.toml`. Agent specs list package names in `required_dependencies`; validation fails if a listed package is not pinned.

Change conventions:

- Agents: add `spec.json`, `code/handler.py`, tests under `test/`, owned DynamoDB specs when needed, and dependency names in `required_dependencies`.
- DynamoDB: keep partition and sort key names and types stable; update tests around changed reads or writes.
- WebUI: add Playwright coverage for visible workflows. Regenerate committed iPhone screenshot baselines with `npm --prefix webUI run test:e2e:update` after accepted visual changes.
- Generated files: edit specs or generator code, then run `.venv/bin/python -m repo_tools codegen`.

Generated files:

- `agents/shared_utils/generated/dynamodb.py`
- `webUI/src/lib/generated/agents.ts`
- `webUI/src/lib/generated/mockAgents.ts`

Edit the specs or `repo_tools/codegen.py` instead of editing generated files by hand.
