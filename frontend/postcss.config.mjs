// Stage 4.9a — Tailwind v4 via the PostCSS plugin (ADR-044). Deliberately NOT the Next/Turbopack
// plugin: PostCSS behaves identically across `next dev` (local + e2e image), `next build`, and the
// standalone output, and leaves the Stage 4.8c e2e-hook webpack stub in next.config.ts untouched.
const config = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};

export default config;
