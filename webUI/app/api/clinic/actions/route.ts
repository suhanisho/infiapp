import { NextResponse } from "next/server";
import { callClinicAgentListActions } from "@/src/lib/generated/agents";
import { requireClinicSession, unauthorizedResponse } from "@/src/lib/auth/session";

export async function GET(request: Request) {
  const session = await requireClinicSession();
  if (!session) {
    return unauthorizedResponse();
  }

  try {
    const url = new URL(request.url);
    const includeCompleted = url.searchParams.get("includeCompleted") === "true";
    const response = await callClinicAgentListActions({ includeCompleted });
    return NextResponse.json(response);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to load actions";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
