import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Stage 4.8 (B5): emit a self-contained server (.next/standalone/server.js) for a small hosted
  // image. Only affects `next build` — `next dev` (local + e2e) is unaffected, so runtime
  // NEXT_PUBLIC_* injection for the e2e hooks still works in the dev image.
  output: "standalone",

  // Stage 4.8c (§8, O1): in the PRODUCTION build only, replace the e2e hook modules with a no-op stub
  // so the hosted bundle contains no token-override hook and never installs window.__xyzE2E
  // (build-time absence, byte-clean — not just runtime-gated). `next dev` (dev === true) keeps the
  // real modules, so the e2e suite is untouched by construction.
  webpack: (config, { dev, webpack }) => {
    if (!dev) {
      // Match BOTH the bare request (`../e2e/testHooks`, beforeResolve) and the resolved absolute
      // path (`…/e2e/testHooks.ts`, afterResolve) so every reference is replaced in both the client
      // and server bundles.
      config.plugins.push(
        new webpack.NormalModuleReplacementPlugin(
          /(^|[\\/])e2e[\\/](testHooks|e2eAuthOverride)(\.tsx?)?$/,
          path.resolve(process.cwd(), "src/lib/e2e/e2eHooks.prod-stub.ts"),
        ),
      );
    }
    return config;
  },
};

export default nextConfig;
