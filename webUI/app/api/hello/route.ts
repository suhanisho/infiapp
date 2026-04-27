import { NextResponse } from "next/server";
import { callHelloAgent } from "@/src/lib/generated/agents";

export async function POST() {
  try {
    const response = await callHelloAgent();
    return NextResponse.json(response);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Backend call failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}

