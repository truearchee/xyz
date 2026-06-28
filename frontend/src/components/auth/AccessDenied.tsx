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
    <main className="flex min-h-dvh items-center justify-center bg-login-page p-8">
      <div className="w-full max-w-[404px] rounded-[18px] border border-[rgba(0,0,0,0.06)] bg-login-card px-9 pt-10 pb-[30px] shadow-login-card">
        {/* Brand — same mark as the sign-in card, for a cohesive auth surface */}
        <div className="mb-2 flex flex-col items-center gap-[14px]">
          <span className="inline-flex h-[46px] w-[46px] items-center justify-center rounded-[13px] bg-login-ink text-login-on-ink">
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.4"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <line x1="6" y1="6" x2="18" y2="18" />
              <line x1="18" y1="6" x2="6" y2="18" />
            </svg>
          </span>
          <span className="text-[17px] font-semibold tracking-[-0.01em] text-login-ink">XYZ Learn</span>
        </div>

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
      </div>
    </main>
  );
}
