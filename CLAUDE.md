# Claude Development Notes

Use `README.md` as the complete framework guide. This file only points coding assistants at the repo conventions.

Expected workflow:

1. Install Python dependencies with `python -m repo_tools install-python` after venv activation.
2. Validate specs with `python -m repo_tools validate`.
3. Regenerate framework code with `python -m repo_tools codegen`.
4. Run agent tests with `python -m repo_tools test-agents`.
5. Run WebUI tests and build with `python -m repo_tools test-web` and `python -m repo_tools build-web`.
6. Run `python -m repo_tools check` before finalizing larger changes.

Python dependencies are pinned in root `pyproject.toml`. Agent specs list package names in `required_dependencies`; validation fails if a listed package is not pinned.

Generated files:

- `agents/shared_utils/generated/dynamodb.py`
- `webUI/src/lib/generated/agents.ts`
- `webUI/src/lib/generated/mockAgents.ts`

Edit the specs or `repo_tools/codegen.py` instead of editing generated files by hand.
