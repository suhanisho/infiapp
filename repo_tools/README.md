# Repo Tools

Run repo tools from an activated Python virtual environment:

```bash
source .venv/bin/activate
```

## Commands

Run all repo checks:

```bash
python -m repo_tools check
```

Install Python dependencies from `pyproject.toml`, including the `dev` extra:

```bash
python -m pip install ".[dev]"
```

Validate specs:

```bash
python -m repo_tools validate
```

Generate code:

```bash
python -m repo_tools codegen
```

Validate generated files are current:

```bash
python -m repo_tools codegen-check
```

Run agent tests:

```bash
python -m repo_tools test-agents
```

Type check agents:

```bash
python -m repo_tools typecheck-agents
```

Run WebUI package tests:

```bash
python -m repo_tools test-web
```

Build WebUI:

```bash
python -m repo_tools build-web
```

Run WebUI screenshot tests:

```bash
python -m repo_tools test-web-e2e
```

Compile Python files:

```bash
python -m repo_tools compile-python
```

## Generated Files

Do not edit generated files by hand. Update specs or generator code, then run `python -m repo_tools codegen`.

Generated files:

- `agents/shared_utils/generated/dynamodb.py`: DynamoDB table metadata, typed item objects, and per-table helpers for item put, single-item query, and sort-key range query.
- `webUI/src/lib/generated/agents.ts`
- `webUI/src/lib/generated/mockAgents.ts`
