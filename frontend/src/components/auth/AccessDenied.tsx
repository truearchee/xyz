'use client';

import { useState } from 'react';

import { getSupabaseBrowserClient } from '../../lib/supabase/client';

type AccessDeniedProps = {
  email?: string;
  reason?: string;
};

export function AccessDenied({ email, reason }: AccessDeniedProps) {
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function signOut() {
    setIsSigningOut(true);
    setMessage(null);

    try {
      const supabase = getSupabaseBrowserClient();
      const { error } = await supabase.auth.signOut();
      if (error) {
        throw error;
      }
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : 'Unable to sign out');
      setIsSigningOut(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col items-center justify-center gap-3 px-4 text-center">
      <h1 className="font-display text-2xl font-bold text-text">Access denied</h1>
      <p className="text-text-muted">You do not have access to this application.</p>
      {email ? <p className="text-sm text-text-muted">Signed in as: {email}</p> : null}
      {reason ? <p className="text-sm text-text-muted">{reason}</p> : null}
      {message ? (
        <p role="alert" className="text-sm text-danger-text">
          {message}
        </p>
      ) : null}
      <button
        disabled={isSigningOut}
        onClick={signOut}
        type="button"
        className="mt-1 rounded-md border border-border bg-surface px-4 py-2 font-medium text-text hover:bg-surface-muted focus:outline-none focus:ring-2 focus:ring-focus-ring focus:ring-offset-2 disabled:opacity-60"
      >
        Log out
      </button>
    </main>
  );
}
