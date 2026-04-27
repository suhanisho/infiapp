import { NextResponse } from "next/server";
import { callHelloAgent } from "@/src/lib/generated/agents";

export async function POST(request: Request) {
  try {
    const payload = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const response = await callHelloAgent(payload);
    return NextResponse.json(response);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Backend call failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
