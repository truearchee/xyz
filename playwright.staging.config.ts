import { defineConfig, devices } from "@playwright/test";

// Stage 4.8d — the HOOK-FREE staging smoke (NOT the local active suite; umbrella §2). Separate config:
// staging baseURL, NO webServer (the stack is already deployed), real Supabase creds from env, no
// __xyzE2E. The 15-min budget is enforced IN the spec via bounded polling, so the spec — not the
// Playwright timeout — fails loud on pipeline-not-complete.
//
// Run (operator): run the pooler pair (deploy/staging-runbook.md) FIRST, then:
//   STAGING_BASE_URL=https://<frontend> STAGING_API_URL=https://<backend> \
//   STAGING_SUPABASE_URL=... STAGING_SUPABASE_ANON_KEY=... \
//   BOOTSTRAP_ADMIN_EMAIL/PASSWORD BOOTSTRAP_LECTURER_* BOOTSTRAP_STUDENT_* \
//   npx playwright test --config playwright.staging.config.ts
export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "4.8-staging-smoke.spec.ts",
  fullyParallel: false,
  workers: 1,
  forbidOnly: true,
  retries: 0,
  timeout: 16 * 60_000, // > the in-spec 15-min budget so the spec's bounded poll is the loud failure
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  use: {
    baseURL: process.env.STAGING_BASE_URL ?? "https://xyz-lms-frontend-staging.fly.dev",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
