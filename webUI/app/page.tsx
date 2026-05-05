import { ClinicApp } from "./clinic-app";
import { SignInPanel } from "./sign-in-panel";
import { getClinicSession } from "@/src/lib/auth/session";
import { googleAuthIsConfigured, mockAuthIsConfigured } from "@/src/lib/auth/options";

export default async function Home() {
  const session = await getClinicSession();
  const googleAuthAvailable = googleAuthIsConfigured();
  const mockAuthAvailable = mockAuthIsConfigured();

  if (!session?.user?.email) {
    return <SignInPanel googleAuthAvailable={googleAuthAvailable} mockAuthAvailable={mockAuthAvailable} />;
  }

  return (
    <ClinicApp
      doctorEmail={session.user.email}
      doctorName={session.user.name || "Dr. Shalini"}
      googleAuthAvailable={googleAuthAvailable}
      mockAuthAvailable={mockAuthAvailable}
    />
  );
}
