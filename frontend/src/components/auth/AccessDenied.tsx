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
    <main>
      <h1>Access denied</h1>
      <p>You do not have access to this application.</p>
      {email ? <p>Signed in as: {email}</p> : null}
      {reason ? <p>{reason}</p> : null}
      {message ? <p>{message}</p> : null}
      <button disabled={isSigningOut} onClick={signOut} type="button">
        Log out
      </button>
    </main>
  );
}
