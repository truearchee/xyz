import { act } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

// §6.3 — SessionProvider state transitions (session authority, the GET /me rule).
//   loading → authenticated (getSession + GET /me resolve)
//   any resolution failure → a clean error state (unauthenticated), NOT a hang
//   SIGNED_OUT → unauthenticated + cleared app context
//   exposed role comes from GET /me (active memberships), NOT from a JWT claim on the session.

const h = vi.hoisted(() => {
  class AuthRequiredError extends Error {
    status = 401;
  }
  class ForbiddenError extends Error {
    status = 403;
    body: unknown;
    constructor(message?: string, body?: unknown) {
      super(message);
      this.body = body;
    }
  }
  return {
    meGet: vi.fn(),
    getSession: vi.fn(),
    onAuthStateChange: vi.fn(),
    AuthRequiredError,
    ForbiddenError,
  };
});

vi.mock("../api/wrapper", () => ({
  api: { me: { get: h.meGet } },
  AuthRequiredError: h.AuthRequiredError,
  ForbiddenError: h.ForbiddenError,
}));
vi.mock("../supabase/client", () => ({
  getSupabaseBrowserClient: () => ({
    auth: { getSession: h.getSession, onAuthStateChange: h.onAuthStateChange },
  }),
}));
vi.mock("../e2e/testHooks", () => ({ registerE2ETestHooks: () => {} }));

import { SessionProvider, useSession } from "./SessionProvider";

let authCallback: ((event: string, session: unknown) => void) | undefined;

function Probe() {
  const { status, user } = useSession();
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="role">{user?.role ?? "none"}</span>
    </div>
  );
}

function renderProvider() {
  return render(
    <SessionProvider>
      <Probe />
    </SessionProvider>,
  );
}

const sessionWithJwtRole = {
  access_token: "jwt",
  // a stale/forged role claim on the token — the client must NOT trust this.
  user: { email: "u@example.test", app_metadata: { role: "admin" } },
};

beforeEach(() => {
  vi.clearAllMocks();
  authCallback = undefined;
  h.onAuthStateChange.mockImplementation((cb: (e: string, s: unknown) => void) => {
    authCallback = cb;
    return { data: { subscription: { unsubscribe: vi.fn() } } };
  });
  Object.defineProperty(window, "location", {
    value: { assign: vi.fn(), href: "http://localhost/" },
    writable: true,
    configurable: true,
  });
});

describe("SessionProvider — happy path + GET /me authority", () => {
  it("loading → authenticated, exposing the role from GET /me (NOT the JWT claim)", async () => {
    h.getSession.mockResolvedValue({ data: { session: sessionWithJwtRole }, error: null });
    h.meGet.mockResolvedValue({ id: "1", email: "u@example.test", role: "student" });

    renderProvider();
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("authenticated"));
    // active-membership authority: role is "student" from /me, not "admin" from the token claim
    expect(screen.getByTestId("role").textContent).toBe("student");
  });
});

describe("SessionProvider — failure lands clean, never hangs", () => {
  it("no session → unauthenticated", async () => {
    h.getSession.mockResolvedValue({ data: { session: null }, error: null });
    renderProvider();
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("unauthenticated"));
  });

  it("a generic /me failure resolves to unauthenticated (clean error state, not stuck loading)", async () => {
    h.getSession.mockResolvedValue({ data: { session: sessionWithJwtRole }, error: null });
    h.meGet.mockRejectedValue(new Error("network blip"));
    renderProvider();
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("unauthenticated"));
  });

  it("a ForbiddenError from /me → forbidden state (session kept, app context not granted)", async () => {
    h.getSession.mockResolvedValue({ data: { session: sessionWithJwtRole }, error: null });
    h.meGet.mockRejectedValue(new h.ForbiddenError("no app account"));
    renderProvider();
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("forbidden"));
    expect(screen.getByTestId("role").textContent).toBe("none"); // no leaked role
  });
});

describe("SessionProvider — SIGNED_OUT clears context", () => {
  it("returns to unauthenticated and clears the resolved user", async () => {
    h.getSession.mockResolvedValue({ data: { session: sessionWithJwtRole }, error: null });
    h.meGet.mockResolvedValue({ id: "1", email: "u@example.test", role: "lecturer" });
    renderProvider();
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("authenticated"));

    act(() => authCallback?.("SIGNED_OUT", null));

    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("unauthenticated"));
    expect(screen.getByTestId("role").textContent).toBe("none"); // app context cleared
  });
});
