'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';
import Link from 'next/link';

import type { CurrentUserResponse } from '../../lib/api';
import { roleHomePath } from '../../lib/routing/ProtectedAppLayout';
import { getSupabaseBrowserClient } from '../../lib/supabase/client';

type AppShellProps = {
  children: ReactNode;
  user: CurrentUserResponse;
};

const NAV_LABEL: Record<string, string> = {
  admin: 'Admin',
  lecturer: 'My modules',
  student: 'My modules',
};

export function AppShell({ children, user }: AppShellProps) {
  const [isSigningOut, setIsSigningOut] = useState(false);
  const displayName = user.fullName || user.email;
  const homePath = roleHomePath(user.role);

  async function signOut() {
    setIsSigningOut(true);
    try {
      const supabase = getSupabaseBrowserClient();
      const { error } = await supabase.auth.signOut();
      if (error) {
        throw error;
      }
    } catch (caught) {
      setIsSigningOut(false);
      throw caught;
    }
  }

  return (
    <div className="min-h-dvh bg-surface-muted text-text">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-toast focus:rounded-md focus:bg-primary focus:px-4 focus:py-2 focus:text-on-primary focus:shadow-md focus:outline-none focus:ring-2 focus:ring-focus-ring focus:ring-offset-2"
      >
        Skip to content
      </a>
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex items-center gap-4">
            <strong className="font-display text-lg font-bold text-primary">XYZ LMS</strong>
            <nav aria-label="Role navigation" className="text-sm">
              <Link
                href={homePath}
                className="rounded-md px-2 py-1 font-medium text-text-muted hover:bg-surface-muted hover:text-text focus:outline-none focus:ring-2 focus:ring-focus-ring focus:ring-offset-2"
              >
                {NAV_LABEL[user.role] ?? 'Home'}
              </Link>
            </nav>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <p className="text-text-muted">
              {displayName} · {user.role}
            </p>
            <button
              disabled={isSigningOut}
              onClick={signOut}
              type="button"
              className="rounded-md border border-border bg-surface px-3 py-1.5 font-medium text-text hover:bg-surface-muted focus:outline-none focus:ring-2 focus:ring-focus-ring focus:ring-offset-2 disabled:opacity-60"
            >
              Log out
            </button>
          </div>
        </div>
      </header>
      <main id="main-content" className="mx-auto max-w-6xl px-4 py-6">
        {children}
      </main>
      {/* Stage 4.9a — reserved Stage 8 floating-assistant slot (anchor + z-layer only; no widget).
          Below toast so error toasts always overlay it. */}
      <div id="assistant-anchor" className="fixed bottom-4 right-4 z-assistant" aria-hidden="true" />
    </div>
  );
}
