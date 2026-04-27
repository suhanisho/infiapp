import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("generated web agent client exposes hello agent", async () => {
  const source = await readFile(new URL("../src/lib/generated/agents.ts", import.meta.url), "utf8");

  assert.match(source, /callHelloAgent/);
  assert.match(source, /HELLO_AGENT_URL/);
  assert.match(source, /mockCallHelloAgent/);
});

