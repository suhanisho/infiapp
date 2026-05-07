import { NextResponse } from "next/server";
import { callClinicAgentScanGmailInbox } from "@/src/lib/generated/agents";
import { requireClinicSession, unauthorizedResponse } from "@/src/lib/auth/session";

export async function POST() {
  const session = await requireClinicSession();
  if (!session) {
    return unauthorizedResponse();
  }

  try {
    const response = await callClinicAgentScanGmailInbox({ actorEmail: session.user?.email || "" });
    return NextResponse.json(response);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to scan Gmail";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
