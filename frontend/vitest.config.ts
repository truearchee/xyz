import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Stage 4.9b — MINIMAL runner: executes the co-located component static-a11y smokes (§6.4) as each
// component lands. The FULL gate surface (the §6.1–6.3 logic tests, the test:unit/test:a11y/check:*
// scripts, CI, pre-commit) is 4.9d; this config's include is deliberately scoped to *.a11y.test.tsx.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.a11y.test.{ts,tsx}"],
  },
});
