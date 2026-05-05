import { NextResponse } from "next/server";
import { callClinicAgentListSchedule } from "@/src/lib/generated/agents";
import { requireClinicSession, unauthorizedResponse } from "@/src/lib/auth/session";

export async function GET() {
  const session = await requireClinicSession();
  if (!session) {
    return unauthorizedResponse();
  }

  try {
    const response = await callClinicAgentListSchedule({});
    return NextResponse.json(response);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to load schedule";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
