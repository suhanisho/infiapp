import { NextResponse } from "next/server";
import { callSampleAgent } from "@/src/lib/generated/agents";

export async function POST(request: Request) {
  try {
    const payload = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const response = await callSampleAgent(payload);
    return NextResponse.json(response);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Backend call failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
