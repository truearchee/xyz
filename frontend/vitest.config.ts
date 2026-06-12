import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Stage 4.9d — runs ALL Vitest specs: the §6.1–6.3 logic tests (*.test.ts(x)) + the §6.4 static-a11y
// smokes (*.a11y.test.tsx, which also match *.test.tsx). The package.json scripts split them:
//   test:unit  → vitest run --exclude '**/*.a11y.test.tsx'   (logic)
//   test:a11y  → vitest run src/components/ui/*.a11y.test.tsx (component a11y smokes)
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
