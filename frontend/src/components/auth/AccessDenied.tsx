'use client';

import { useState } from 'react';

import { getSupabaseBrowserClient } from '../../lib/supabase/client';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';

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
    <main className="mx-auto flex min-h-dvh max-w-md items-center justify-center px-4">
      <EmptyState
        headingLevel={1}
        title="Access denied"
        description={
          <>
            You do not have access to this application.
            {email ? (
              <>
                <br />
                Signed in as: {email}
              </>
            ) : null}
            {reason ? (
              <>
                <br />
                {reason}
              </>
            ) : null}
          </>
        }
        action={
          <div className="flex flex-col items-center gap-2">
            {message ? (
              <p role="alert" className="text-sm text-danger-text">
                {message}
              </p>
            ) : null}
            <Button variant="secondary" isLoading={isSigningOut} onClick={signOut}>
              Log out
            </Button>
          </div>
        }
      />
    </main>
  );
}
