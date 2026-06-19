import "./globals.css";

import type { ReactNode } from "react";

import "katex/dist/katex.min.css";

import { SessionProvider } from "../lib/session/SessionProvider";

// Stage 4.9f — ONE system font family (design-system §3). No web-font request and no committed
// .woff2: `--font-sans`/`--font-display` resolve to the `-apple-system, …` stack in globals.css, so
// nothing is fetched at build or runtime (keeps 4.8/4.9's offline-image hygiene). The page is parchment
// (bg-surface-muted); content cards are white and read via the tone step.
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-dvh bg-surface-muted text-text font-sans antialiased">
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
