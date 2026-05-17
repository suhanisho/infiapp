import { NextResponse } from "next/server";
import { callClinicAgentGetDailyBriefing } from "@/src/lib/generated/agents";
import { requireClinicSession, unauthorizedResponse } from "@/src/lib/auth/session";

export async function GET() {
  const session = await requireClinicSession();
  if (!session) {
    return unauthorizedResponse();
  }

  try {
    const response = await callClinicAgentGetDailyBriefing({ actorEmail: session.user?.email || "" });
    return NextResponse.json(response);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to generate daily briefing";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
