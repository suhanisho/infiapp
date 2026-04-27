# WebUI

`webUI/` is the single Next.js App Router application for this repo.

## Agent Calls

Use generated agent helpers from `webUI/src/lib/generated/agents.ts` when the WebUI calls external Lambda agents.

Local development and tests use generated mocks from `webUI/src/lib/generated/mockAgents.ts`. Production uses generated AWS Lambda clients with Vercel OIDC credentials configured by the deploy workflow.

Keep API routes under `webUI/app/api/` thin. They should translate HTTP requests into generated agent-helper calls.

## Tests

Install dependencies before running WebUI checks:

```bash
npm --prefix webUI ci
```

Build the Next.js app before Playwright E2E and screenshot tests:

```bash
npm --prefix webUI run build
```

Run Playwright E2E tests for visible workflows and screenshot validation. Playwright runs the built app through `next start`, so run the build first:

```bash
npm --prefix webUI run test:e2e
```

Only iPhone screenshots are checked. Baselines are committed under `webUI/tests/app.spec.ts-snapshots/`.

Regenerate iPhone screenshot baselines intentionally after an accepted UI change:

```bash
npm --prefix webUI run test:e2e:update
```

Review the generated image diff before committing updated baselines.

The GitHub workflow `.github/workflows/test-webUI.yml` builds the app and then runs Playwright E2E plus screenshot tests.
