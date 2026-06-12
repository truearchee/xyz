// Stage 4.8c (§8, O1) — PRODUCTION stub. `next build` replaces src/lib/e2e/testHooks and
// src/lib/e2e/e2eAuthOverride with this module (NormalModuleReplacementPlugin in next.config.ts,
// guarded by `!dev`), so the hosted bundle contains NO token-override hook and never installs
// window.__xyzE2E — build-time absence, not just a runtime gate. `next dev` (the e2e suite) keeps the
// real modules. The exports here are the union of what SessionProvider + the api wrapper import.

export function registerE2ETestHooks(): void {}

export function consumeForcedBearerToken(): string | null {
  return null;
}

export function forceNextBearerToken(_token: string): void {}
