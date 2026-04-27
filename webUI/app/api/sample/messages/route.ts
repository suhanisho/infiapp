import { NextResponse } from "next/server";
import { callSampleAgent } from "@/src/lib/generated/agents";

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

function parseNextKey(value: string | null): Record<string, unknown> | undefined {
  if (!value) {
    return undefined;
  }
  try {
    const parsed = JSON.parse(value) as unknown;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : undefined;
  } catch {
    return undefined;
  }
}

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const response = await callSampleAgent({
      action: "list_messages",
      limit: parseLimit(url.searchParams.get("limit")),
      nextKey: parseNextKey(url.searchParams.get("nextKey")),
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
    const response = await callSampleAgent({
      action: "store_message",
      message: payload.message,
    });
    return NextResponse.json(response);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Backend call failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
