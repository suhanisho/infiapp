import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("generated web agent client exposes sample agent", async () => {
  const source = await readFile(new URL("../src/lib/generated/agents.ts", import.meta.url), "utf8");

  assert.match(source, /callSampleAgentStoreMessage/);
  assert.match(source, /callSampleAgentListMessages/);
  assert.match(source, /SampleAgentStoreMessageInput/);
  assert.match(source, /SampleAgentListMessagesOutput/);
  assert.match(source, /invokeLambda/);
  assert.match(source, /INFIAPP_AGENT_BACKEND_MODE/);
  assert.match(source, /awsCredentialsProvider/);
  assert.match(source, /mockCallSampleAgent/);
  const mockSource = await readFile(new URL("../src/lib/generated/mockAgents.ts", import.meta.url), "utf8");
  assert.match(mockSource, /SampleAgentStoreMessageInput/);
  assert.match(mockSource, /SampleAgentListMessagesOutput/);
  assert.match(mockSource, /list_messages/);
  assert.match(mockSource, /nextMessageId/);
});
