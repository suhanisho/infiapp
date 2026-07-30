"use client";

import { useEffect, useState } from "react";
import { signIn } from "next-auth/react";
import { googleProviderId, mockProviderId } from "@/src/lib/auth/providers";

export function SignInPanel({
  googleAuthAvailable,
  mockAuthAvailable,
}: {
  googleAuthAvailable: boolean;
  mockAuthAvailable: boolean;
}) {
  const [authError, setAuthError] = useState("");
  const providerId = googleAuthAvailable ? googleProviderId : mockProviderId;
  const disabled = !googleAuthAvailable && !mockAuthAvailable;
  const callbackUrl = googleAuthAvailable ? "/?googleOAuth=connected" : "/";

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const error = params.get("authError") || params.get("error");
    if (error === "email_not_allowed") {
      setAuthError("This Google account is not allowed for the clinic app.");
    } else if (error === "google_connection_failed") {
      setAuthError("Google connected, but the clinic token store did not complete.");
    } else if (error) {
      setAuthError("Sign-in did not complete.");
    }
  }, []);

  return (
    <main className="signin-shell">
      <section className="signin-panel" aria-labelledby="signin-title">
        <div className="doctor-avatar">N</div>
        <div>
          <p className="date-line">Nora</p>
          <h1 id="signin-title">Sign in to continue</h1>
        </div>
        <p>
          Nora helps Dr. Shalini manage patient actions, calendar-derived appointments, and approval records.
          Use the clinic Google account to continue.
        </p>
        <button
          type="button"
          className="primary-button"
          disabled={disabled}
          onClick={() => void signIn(providerId, { callbackUrl })}
        >
          {googleAuthAvailable ? "Sign in with Google" : "Open local demo"}
        </button>
        {authError ? <small>{authError}</small> : null}
        {disabled ? <small>Auth is not configured yet. Add Google OAuth secrets or run in mock mode.</small> : null}
      </section>
    </main>
  );
}
