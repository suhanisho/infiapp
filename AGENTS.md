# Agent Development Notes

This repo uses README.md as the source of truth for framework concepts, setup, tests, and deployment.

Conventions for coding agents:

- Read `README.md` before changing framework structure.
- Keep Lambda agents under `agents/<agent_name>/`.
- Keep shared Python code in `agents/shared_utils/`.
- Keep DynamoDB table definitions under `dynamodb/<owner_agent>/`.
- Do not manually edit files under generated folders; run `npm run codegen`.
- Add or update agent tests for Lambda behavior.
- Add or update WebUI tests for visible UI or generated-client behavior.
- Run `npm run check` before considering the work complete.

