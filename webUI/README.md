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

Run package tests for generated-client behavior and other non-visual logic:

```bash
npm --prefix webUI test
```

Build the Next.js app before curl smoke tests and Playwright screenshot tests:

```bash
npm --prefix webUI run build
```

Run curl smoke tests for important API endpoints:

```bash
npm --prefix webUI run test:curl
```

Curl smoke coverage lives in `webUI/tests/test-endpoints.sh`. Keep endpoint assertions there instead of embedding curl logic in GitHub workflow YAML.

Run Playwright screenshot tests for visible workflows, including phone-sized viewports. Playwright runs the built app through `next start`, so run the build first:

```bash
npm --prefix webUI run test:e2e
```

The GitHub workflow `.github/workflows/test-webUI.yml` runs package tests, builds the app, runs the curl smoke script, and then runs screenshot tests.
