import { NextResponse } from "next/server";
import { callClinicAgentGetConversation } from "@/src/lib/generated/agents";
import { requireClinicSession, unauthorizedResponse } from "@/src/lib/auth/session";

export async function GET(_request: Request, context: { params: Promise<{ conversationId: string }> }) {
  const session = await requireClinicSession();
  if (!session) {
    return unauthorizedResponse();
  }

  try {
    const { conversationId } = await context.params;
    const response = await callClinicAgentGetConversation({
      actorEmail: session.user?.email || "",
      conversationId: decodeURIComponent(conversationId),
    });
    return NextResponse.json(response);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to load conversation";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
