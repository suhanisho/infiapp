import { NextResponse } from "next/server";
import { callClinicAgentListPatientRequests } from "@/src/lib/generated/agents";
import { requireClinicSession, unauthorizedResponse } from "@/src/lib/auth/session";

export async function GET(request: Request) {
  const session = await requireClinicSession();
  if (!session) {
    return unauthorizedResponse();
  }

  try {
    const url = new URL(request.url);
    const includeCompleted = url.searchParams.get("includeCompleted") === "true";
    const response = await callClinicAgentListPatientRequests({
      actorEmail: session.user?.email || "",
      includeCompleted,
    });
    return NextResponse.json(response);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to load patient requests";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
