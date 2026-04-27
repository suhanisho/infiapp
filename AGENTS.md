# Agent Development Notes

Read `README.md` to learn the framework purpose, concepts, setup, tests, and deployment flow. Read the README inside each framework folder, including `agents/`, `webUI/`, `repo_tools/`, and `dynamodb/`, to understand the conventions for developing those concepts.

Conventions for coding agents:

- Never push directly to `main`; create a branch and open a pull request for every change.
- Keep Lambda agents under `agents/<agent_name>/`.
- Keep shared Python code in `agents/shared_utils/`.
- Keep DynamoDB table definitions under `dynamodb/<agent_name>/`; ownership is inferred from the folder name.
- Keep Python dependency pins in root `pyproject.toml`; agent specs should list package names in `required_dependencies`.
- Run `python -m pip install ".[dev]"` after changing Python dependencies.
- Do not manually edit files under generated folders; run `python -m repo_tools codegen`.
- Run `python -m repo_tools typecheck-agents` when changing Python agents or shared utilities.
- Run targeted repo tool commands for the files and behavior you changed before considering the work complete.

When adding an agent:

- Create `agents/<agent_name>/spec.json`, `agents/<agent_name>/code/handler.py`, and focused tests under `agents/<agent_name>/test/`.
- Add DynamoDB specs under `dynamodb/<agent_name>/` when the agent owns data.
- Add imported external Python packages to `required_dependencies` and pin them in `pyproject.toml`.
- Run `python -m repo_tools codegen` after adding external agents or DynamoDB specs.

When changing DynamoDB:

- Keep partition and sort key names and types stable.
- Update tests for code that reads or writes changed attributes.

When changing WebUI:

- Add or update Playwright coverage for visible workflows.
- Keep the committed iPhone screenshot baseline current by running `npm --prefix webUI run test:e2e:update` after accepted visual changes.
- Keep generated files generated; edit specs or generator code instead.
