# Agent Development Notes

- Read `README.md` to learn the framework, concepts, setup, tests, and deployment flow. Read the README inside each framework folder, including `agents/`, `webUI/`, `repo_tools/`, and `dynamodb/`, to understand the conventions for developing those concepts and running tests/verifications.
- Never push directly to `main`; create a branch and open a pull request for every change.
- Always run Python commands, Python tests, repo tools, validators, codegen, and type checks through the repo venv. Prefer one-command invocations with `.venv/bin/python`, e.g. `.venv/bin/python -m repo_tools validate-agents`
- Some pointers:
  - Install Python dependencies with `.venv/bin/python -m pip install ".[dev]"`.
  - Validate changed specs with targeted commands such as `.venv/bin/python -m repo_tools validate-agents` or `.venv/bin/python -m repo_tools validate-db`.
  - Regenerate framework code with `.venv/bin/python -m repo_tools codegen`.
  - Run agent tests with `.venv/bin/python -m repo_tools test-agents`.
  - Type check agents with `.venv/bin/python -m repo_tools typecheck-agents`.
  - Run WebUI build and Playwright checks with `.venv/bin/python -m repo_tools build-web` and `.venv/bin/python -m repo_tools test-web-e2e`.
  - Run targeted repo tool commands for the files and behavior you changed before finalizing larger changes.
  - Python dependencies are pinned in root `pyproject.toml`. Agent specs list package names in `required_dependencies`; validation fails if a listed package is not pinned.
- Change conventions:
  - Agents: add `spec.json`, `code/handler.py`, tests under `test/`, owned DynamoDB specs when needed, and dependency names in `required_dependencies`.
  - DynamoDB: keep partition and sort key names and types stable; update tests around changed reads or writes.
  - WebUI: add Playwright coverage for visible workflows. Regenerate committed iPhone screenshot baselines with `npm --prefix webUI run test:e2e:update` after accepted visual changes.
  - Generated files: edit specs then run `.venv/bin/python -m repo_tools codegen`. Edit the specs or `repo_tools/codegen.py` instead of editing generated files by hand.
