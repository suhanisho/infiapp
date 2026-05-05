import type { Account, NextAuthOptions, Profile, User } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";
import GoogleProvider from "next-auth/providers/google";
import { callClinicAgentConnectGoogleWorkspace } from "@/src/lib/generated/agents";
import { googleProviderId, mockProviderId } from "./providers";

const GOOGLE_OAUTH_SCOPES = [
  "openid",
  "email",
  "https://www.googleapis.com/auth/calendar.events.readonly",
  "https://www.googleapis.com/auth/gmail.readonly",
];

const LOCAL_AUTH_SECRET = "local-development-auth-secret-for-shalini-clinic";
export function googleAuthIsConfigured() {
  return Boolean(process.env.GOOGLE_OAUTH_CLIENT_ID && process.env.GOOGLE_OAUTH_CLIENT_SECRET);
}

export function mockAuthIsConfigured() {
  return process.env.SHALINI_CLINIC_AGENT_BACKEND_MODE === "mock";
}

function authSecret() {
  const configured = process.env.NEXTAUTH_SECRET || process.env.AUTH_SECRET;
  if (configured) {
    return configured;
  }
  return mockAuthIsConfigured() ? LOCAL_AUTH_SECRET : undefined;
}

function allowedClinicEmails() {
  return (process.env.CLINIC_ALLOWED_EMAILS || "")
    .split(",")
    .map((email) => email.trim().toLowerCase())
    .filter(Boolean);
}

function clinicEmailIsAllowed(email: string) {
  const allowedEmails = allowedClinicEmails();
  if (allowedEmails.length === 0) {
    return mockAuthIsConfigured() || process.env.NODE_ENV !== "production";
  }
  return allowedEmails.includes(email.trim().toLowerCase());
}

function authProviders() {
  const providers: NextAuthOptions["providers"] = [];
  if (googleAuthIsConfigured()) {
    providers.push(
      GoogleProvider({
        clientId: process.env.GOOGLE_OAUTH_CLIENT_ID || "",
        clientSecret: process.env.GOOGLE_OAUTH_CLIENT_SECRET || "",
        authorization: {
          params: {
            access_type: "offline",
            include_granted_scopes: "true",
            prompt: "consent",
            scope: GOOGLE_OAUTH_SCOPES.join(" "),
          },
        },
      }),
    );
  }

  if (mockAuthIsConfigured()) {
    providers.push(
      CredentialsProvider({
        id: mockProviderId,
        name: "Local clinic demo",
        credentials: {},
        async authorize() {
          return {
            id: "clinic-demo-user",
            email: "doctor@example.com",
            name: "Dr. Shalini",
          };
        },
      }),
    );
  }

  return providers;
}

function stringFromProfile(profile: Profile | undefined, key: string) {
  const value = profile?.[key as keyof Profile];
  return typeof value === "string" ? value : "";
}

function tokenResponseFromAccount(account: Account) {
  const tokenResponse: Record<string, unknown> = {};
  for (const key of ["access_token", "refresh_token", "id_token", "scope", "token_type", "expires_at", "expires_in"]) {
    const value = account[key as keyof Account];
    if (value !== undefined && value !== null) {
      tokenResponse[key] = value;
    }
  }
  return tokenResponse;
}

function googleAccountEmail(user: User, profile?: Profile) {
  return user.email || stringFromProfile(profile, "email");
}

async function storeGoogleConnection(accountEmail: string, account: Account) {
  const tokenResponse = tokenResponseFromAccount(account);
  await callClinicAgentConnectGoogleWorkspace({
    accountEmail,
    tokenResponse,
  });
}

export const authOptions: NextAuthOptions = {
  providers: authProviders(),
  secret: authSecret(),
  session: {
    strategy: "jwt",
  },
  pages: {
    signIn: "/",
    error: "/",
  },
  callbacks: {
    async signIn({ user, account, profile }) {
      if (!account) {
        return false;
      }
      if (account.provider === mockProviderId) {
        return mockAuthIsConfigured();
      }
      if (account.provider === googleProviderId) {
        const accountEmail = googleAccountEmail(user, profile);
        if (!accountEmail || !clinicEmailIsAllowed(accountEmail)) {
          return "/?authError=email_not_allowed";
        }
        try {
          await storeGoogleConnection(accountEmail, account);
          return true;
        } catch (error) {
          console.error("Unable to store Google connection", error);
          return "/?authError=google_connection_failed";
        }
      }
      return false;
    },
    async session({ session, token }) {
      if (session.user) {
        session.user.name = session.user.name || (typeof token.name === "string" ? token.name : "Dr. Shalini");
        session.user.email = session.user.email || (typeof token.email === "string" ? token.email : "doctor@example.com");
      }
      return session;
    },
  },
};
