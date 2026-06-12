import "./globals.css";

import type { ReactNode } from "react";
import localFont from "next/font/local";

import { SessionProvider } from "../lib/session/SessionProvider";

// Stage 4.9a — self-hosted fonts via next/font/local (ADR-044). LOCAL (committed .woff2), not
// next/font/google: the e2e/CI dev images must not depend on a build-time font fetch (matches 4.8's
// offline-image hygiene + the "no external request" intent). The browser fetches these from our own
// origin; nothing reaches Google at build or runtime. Variable-weight files cover the full range.
const fontSans = localFont({
  src: "../fonts/inter-latin-wght-normal.woff2",
  variable: "--font-sans-src",
  weight: "100 900",
  display: "swap",
});

const fontDisplay = localFont({
  src: "../fonts/space-grotesk-latin-wght-normal.woff2",
  variable: "--font-display-src",
  weight: "300 700",
  display: "swap",
});

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${fontSans.variable} ${fontDisplay.variable}`}>
      <body className="min-h-dvh bg-surface text-text font-sans antialiased">
        <SessionProvider>{children}</SessionProvider>
        {/* Stage 4.9a shell infrastructure — portal MOUNT POINTS. The Modal/Toast COMPONENTS that
            render into these land in 4.9b; reserving the anchors here gives them (and Stage 5+) a home
            with deterministic stacking (z tokens: modal < toast). */}
        <div id="modal-root" className="z-modal" />
        <div id="toast-root" className="z-toast" />
      </body>
    </html>
  );
}
