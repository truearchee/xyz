import { describe, it, expect, vi, beforeEach } from "vitest";

// §6.1 — wrapper.ts auth recovery (the 401/403 boundary, rule 5). The executable form of:
//   401 → session cleared + redirect to /login
//   403 → session KEPT + ForbiddenError surfaced, and NEVER a login redirect (the dangerous bug)
//   5xx / network → neither; the original error propagates, session intact.
// We drive it through api.me.get() (the simplest withAuthRecovery path).

// Mock the generated client: a REAL ApiError class (so `instanceof ApiError` in wrapper.ts holds),
// an OpenAPI stub (wrapper sets OpenAPI.BASE/TOKEN at import), and a MeService.getMeMeGet mock.
vi.mock("./index", () => {
  class ApiError extends Error {
    status: number;
    body: unknown;
    constructor(status: number, body?: unknown, message = "api error") {
      super(message);
      this.name = "ApiError";
      this.status = status;
      this.body = body;
    }
  }
  return {
    ApiError,
    OpenAPI: { BASE: "", TOKEN: undefined },
    MeService: { getMeMeGet: vi.fn() },
    AdminService: {},
    ContentService: {},
    ModulesService: {},
    StudentSummariesService: {},
    TranscriptsService: {},
  };
});

// redirectToLogin() calls getSupabaseBrowserClient().auth.signOut() — the "session cleared" signal.
const signOut = vi.fn().mockResolvedValue({ error: null });
vi.mock("../supabase/client", () => ({
  getSupabaseBrowserClient: () => ({ auth: { signOut, getSession: vi.fn() } }),
}));
vi.mock("../e2e/e2eAuthOverride", () => ({ consumeForcedBearerToken: () => null }));

// Imports resolve to the mocks above (vi.mock is hoisted).
import { ApiError, MeService } from "./index";
import { api, AuthRequiredError, ForbiddenError } from "./wrapper";

const getMe = MeService.getMeMeGet as unknown as ReturnType<typeof vi.fn>;
const makeApiError = (status: number, body?: unknown): Error =>
  new (ApiError as unknown as new (s: number, b?: unknown) => Error)(status, body);

// Spy on the redirect without triggering jsdom navigation.
const assign = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  Object.defineProperty(window, "location", {
    value: { assign, href: "http://localhost/" },
    writable: true,
    configurable: true,
  });
});

describe("withAuthRecovery — 401", () => {
  it("clears the session AND redirects to /login, surfacing AuthRequiredError", async () => {
    getMe.mockRejectedValueOnce(makeApiError(401, { detail: "expired" }));
    await expect(api.me.get()).rejects.toBeInstanceOf(AuthRequiredError);
    expect(signOut).toHaveBeenCalledTimes(1); // session cleared
    expect(assign).toHaveBeenCalledWith("/login"); // redirect produced
  });
});

describe("withAuthRecovery — 403 (the boundary that matters)", () => {
  it("surfaces ForbiddenError with the body, KEEPS the session, and produces NO login redirect", async () => {
    getMe.mockRejectedValueOnce(makeApiError(403, { detail: "NOT_A_MEMBER" }));

    const error = await api.me.get().then(
      () => null,
      (caught) => caught,
    );

    expect(error).toBeInstanceOf(ForbiddenError);
    expect((error as ForbiddenError).body).toEqual({ detail: "NOT_A_MEMBER" });
    // NEGATIVE assertions — the dangerous bug a 403 must NOT trigger:
    expect(signOut).not.toHaveBeenCalled(); // session KEPT
    expect(assign).not.toHaveBeenCalled(); // NO redirect to /login
  });
});

describe("withAuthRecovery — 5xx / network", () => {
  it("propagates a 5xx ApiError unchanged; no signOut, no redirect", async () => {
    const original = makeApiError(500, { detail: "boom" });
    getMe.mockRejectedValueOnce(original);

    const error = await api.me.get().then(
      () => null,
      (caught) => caught,
    );

    expect(error).toBe(original); // same error object, not wrapped
    expect(error).not.toBeInstanceOf(AuthRequiredError);
    expect(error).not.toBeInstanceOf(ForbiddenError);
    expect(signOut).not.toHaveBeenCalled();
    expect(assign).not.toHaveBeenCalled();
  });

  it("propagates a non-ApiError (network) unchanged; session intact", async () => {
    const network = new TypeError("Failed to fetch");
    getMe.mockRejectedValueOnce(network);

    const error = await api.me.get().then(
      () => null,
      (caught) => caught,
    );

    expect(error).toBe(network);
    expect(signOut).not.toHaveBeenCalled();
    expect(assign).not.toHaveBeenCalled();
  });
});
