import { getServerSession } from "next-auth/next";
import { NextResponse } from "next/server";
import { authOptions } from "./options";

export async function getClinicSession() {
  return getServerSession(authOptions);
}

export async function requireClinicSession() {
  const session = await getClinicSession();
  return session?.user?.email ? session : null;
}

export function unauthorizedResponse() {
  return NextResponse.json({ error: "Please sign in to access the clinic app." }, { status: 401 });
}
