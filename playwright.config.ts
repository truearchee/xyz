import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  // The Stage 4.8d staging smoke is hook-free and runs ONLY via playwright.staging.config.ts against a
  // deployed staging URL (umbrella §2). It must never run in the LOCAL active suite (it requires staging
  // env + a deployed stack).
  testIgnore: '**/4.8-staging-smoke.spec.ts',
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
