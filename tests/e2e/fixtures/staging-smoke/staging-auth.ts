import {
  request as playwrightRequest,
  type APIRequestContext,
  type BrowserContext,
} from "@playwright/test";

// Stage 4.8d — HOOK-FREE auth for the staging smoke. A REAL Supabase password grant returns a REAL
// user JWT (NOT a service-role mint, NOT an __xyzE2E override). Skipping the /login form is not
// skipping the auth — the token below is exactly what the app would persist after a real sign-in.

export type StagingEnv = {
  baseURL: string; // frontend origin (Playwright baseURL)
  apiURL: string; // backend origin
  supabaseURL: string;
  supabaseAnonKey: string;
};

export type Identity = { email: string; password: string };

export type Session = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  expires_at: number;
  token_type: string;
  user: { id: string; email?: string; role?: string };
};

export function stagingEnv(): StagingEnv {
  const required = (name: string): string => {
    const value = process.env[name];
    if (!value) throw new Error(`staging smoke requires env ${name}`);
    return value;
  };
  return {
    baseURL: required("STAGING_BASE_URL"),
    apiURL: required("STAGING_API_URL"),
    supabaseURL: required("STAGING_SUPABASE_URL"),
    supabaseAnonKey: required("STAGING_SUPABASE_ANON_KEY"),
  };
}

export function identity(prefix: string): Identity {
  const email = process.env[`${prefix}_EMAIL`];
  const password = process.env[`${prefix}_PASSWORD`];
  if (!email || !password) throw new Error(`staging smoke requires ${prefix}_EMAIL/${prefix}_PASSWORD`);
  return { email, password };
}

// Real Supabase password grant → real user session. Throws on anything that isn't a bearer user token.
export async function signIn(env: StagingEnv, id: Identity): Promise<Session> {
  const anon = await playwrightRequest.newContext();
  try {
    const res = await anon.post(`${env.supabaseURL}/auth/v1/token?grant_type=password`, {
      headers: { apikey: env.supabaseAnonKey, "Content-Type": "application/json" },
      data: { email: id.email, password: id.password },
    });
    if (!res.ok()) {
      throw new Error(`Supabase sign-in failed for ${id.email}: ${res.status()} ${await res.text()}`);
    }
    const session = (await res.json()) as Session;
    if (!session.access_token || session.token_type?.toLowerCase() !== "bearer" || !session.user?.id) {
      throw new Error(`unexpected Supabase session for ${id.email} (not a real user bearer token)`);
    }
    return session;
  } finally {
    await anon.dispose();
  }
}

export async function apiContextFor(env: StagingEnv, session: Session): Promise<APIRequestContext> {
  return playwrightRequest.newContext({
    baseURL: env.apiURL,
    extraHTTPHeaders: { Authorization: `Bearer ${session.access_token}` },
  });
}

function projectRef(supabaseURL: string): string {
  return new URL(supabaseURL).host.split(".")[0]; // https://<ref>.supabase.co → <ref>
}

// Seed the REAL Supabase session into the browser context so UI navigation is authenticated WITHOUT
// the login form and WITHOUT any test hook — it is the same persisted session a real sign-in produces.
export async function seedBrowserSession(
  context: BrowserContext,
  env: StagingEnv,
  session: Session,
): Promise<void> {
  const storageKey = `sb-${projectRef(env.supabaseURL)}-auth-token`;
  const storageValue = JSON.stringify({
    access_token: session.access_token,
    refresh_token: session.refresh_token,
    expires_in: session.expires_in,
    expires_at: session.expires_at,
    token_type: "bearer",
    user: session.user,
  });
  await context.addInitScript(
    ([key, value]) => window.localStorage.setItem(key, value),
    [storageKey, storageValue] as const,
  );
}
