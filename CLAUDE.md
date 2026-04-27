# Claude Development Notes

Use `README.md` as the complete framework guide. This file only points coding assistants at the repo conventions.

Expected workflow:

1. Validate specs with `npm run validate`.
2. Regenerate framework code with `npm run codegen`.
3. Run agent tests with `npm run test:agents`.
4. Run WebUI tests and build with `npm --prefix webUI test` and `npm --prefix webUI run build`.
5. Run `npm run check` before finalizing larger changes.

Generated files:

- `agents/shared_utils/generated/dynamodb.py`
- `webUI/src/lib/generated/agents.ts`
- `webUI/src/lib/generated/mockAgents.ts`

Edit the specs or `repo_tools/codegen.py` instead of editing generated files by hand.

