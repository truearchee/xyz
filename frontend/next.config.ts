import type { NextConfig } from "next";

// 12f production hardening: security response headers, applied ONLY to production builds (next build /
// the standalone prod image). `next dev` (the base/E2E stack) returns no extra headers, so the
// Playwright gate is unaffected. CSP is intentionally pragmatic — 'unsafe-inline' is permitted for
// script/style because the App Router injects inline bootstrap/runtime; a nonce-based CSP is a post-MVP
// hardening. connect-src is derived from the build-time NEXT_PUBLIC_* origins. The /qa smoke + /cso
// review validate this; loosen any directive that blocks a real interaction.
const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const supabaseWs = supabaseUrl.replace(/^https:/, "wss:").replace(/^http:/, "ws:");

const connectSrc = ["'self'", apiBase, supabaseUrl, supabaseWs].filter(Boolean).join(" ");

const contentSecurityPolicy = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https:",
  "font-src 'self' data:",
  `connect-src ${connectSrc}`,
  "form-action 'self'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: contentSecurityPolicy },
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "no-referrer" },
];

const nextConfig: NextConfig = {
  output: "standalone",
  async headers() {
    if (process.env.NODE_ENV !== "production") {
      return [];
    }
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
