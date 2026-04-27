# Claude Development Notes

Use `README.md` as the complete framework guide. This file only points coding assistants at the repo conventions.

Hard rule: never push directly to `main`. Work on a branch and open a pull request for every change.

Expected workflow:

1. Install Python dependencies with `python -m pip install ".[dev]"` after venv activation.
2. Validate specs with `python -m repo_tools validate`.
3. Regenerate framework code with `python -m repo_tools codegen`.
4. Run agent tests with `python -m repo_tools test-agents`.
5. Run WebUI tests and build with `python -m repo_tools test-web` and `python -m repo_tools build-web`.
6. Run `python -m repo_tools check` before finalizing larger changes.

Python dependencies are pinned in root `pyproject.toml`. Agent specs list package names in `required_dependencies`; validation fails if a listed package is not pinned.

Change conventions:

- Agents: add `spec.json`, `code/handler.py`, tests under `test/`, owned DynamoDB specs when needed, and dependency names in `required_dependencies`.
- DynamoDB: keep partition and sort key names and types stable; update tests around changed reads or writes.
- WebUI: add package tests for client logic and Playwright coverage for visible workflows.
- Generated files: edit specs or generator code, then run `python -m repo_tools codegen`.

Generated files:

- `agents/shared_utils/generated/dynamodb.py`
- `webUI/src/lib/generated/agents.ts`
- `webUI/src/lib/generated/mockAgents.ts`

Edit the specs or `repo_tools/codegen.py` instead of editing generated files by hand.
