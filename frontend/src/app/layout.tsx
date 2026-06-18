import type { ReactNode } from "react";

import "katex/dist/katex.min.css";

import { SessionProvider } from "../lib/session/SessionProvider";

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <SessionProvider>{children}</SessionProvider>
      </body>
    </html>
  );
}
