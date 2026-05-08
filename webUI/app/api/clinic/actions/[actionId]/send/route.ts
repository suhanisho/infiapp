import { NextResponse } from "next/server";
import { callClinicAgentApproveAndSendGmail } from "@/src/lib/generated/agents";
import { requireClinicSession, unauthorizedResponse } from "@/src/lib/auth/session";

type RouteContext = {
  params: Promise<{
    actionId: string;
  }>;
};

export async function POST(request: Request, context: RouteContext) {
  const session = await requireClinicSession();
  if (!session) {
    return unauthorizedResponse();
  }

  try {
    const { actionId } = await context.params;
    const payload = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const response = await callClinicAgentApproveAndSendGmail({
      actionId: decodeURIComponent(actionId),
      actorEmail: session.user?.email || "",
      approvedBy: typeof payload.approvedBy === "string" ? payload.approvedBy : "Dr. Shalini",
      finalMessage: typeof payload.finalMessage === "string" ? payload.finalMessage : undefined,
    });
    return NextResponse.json(response);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to send Gmail reply";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
