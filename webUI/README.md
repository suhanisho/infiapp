# WebUI

`webUI/` is the single Next.js App Router application for this repo.

## Agent Calls

Use generated agent helpers from `webUI/src/lib/generated/agents.ts` when the WebUI calls external Lambda agents.

Local development and tests use generated mocks from `webUI/src/lib/generated/mockAgents.ts`. Production uses generated AWS Lambda clients with Vercel OIDC credentials configured by the deploy workflow.

Keep API routes under `webUI/app/api/` thin. They should translate HTTP requests into generated agent-helper calls.

## Tests

Add WebUI package tests for generated-client behavior and other non-visual logic.

Add curl smoke coverage for important API endpoints in `.github/workflows/test-webUI.yml`.

Add Playwright screenshot coverage for important user workflows, including phone-sized viewports.
