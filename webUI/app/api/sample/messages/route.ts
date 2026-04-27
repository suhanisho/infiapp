import { NextResponse } from "next/server";
import { callSampleAgentListMessages, callSampleAgentStoreMessage } from "@/src/lib/generated/agents";

function parseLimit(value: string | null): number {
  if (!value) {
    return 10;
  }
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) {
    return 10;
  }
  return Math.max(1, Math.min(parsed, 50));
}

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const response = await callSampleAgentListMessages({
      limit: parseLimit(url.searchParams.get("limit")),
      nextMessageId: url.searchParams.get("nextMessageId"),
    });
    return NextResponse.json(response);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Backend call failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}

export async function POST(request: Request) {
  try {
    const payload = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const response = await callSampleAgentStoreMessage({
      message: typeof payload.message === "string" ? payload.message : "",
    });
    return NextResponse.json(response);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Backend call failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
