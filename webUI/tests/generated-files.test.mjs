import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("generated web agent client exposes sample agent", async () => {
  const source = await readFile(new URL("../src/lib/generated/agents.ts", import.meta.url), "utf8");

  assert.match(source, /callSampleAgent/);
  assert.match(source, /payload: AgentRequest/);
  assert.match(source, /SAMPLE_AGENT_URL/);
  assert.match(source, /mockCallSampleAgent/);
});
