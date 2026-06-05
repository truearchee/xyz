'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import type { CurrentUserResponse } from '../../lib/api';
import { getSupabaseBrowserClient } from '../../lib/supabase/client';

type AppShellProps = {
  children: ReactNode;
  user: CurrentUserResponse;
};

export function AppShell({ children, user }: AppShellProps) {
  const [isSigningOut, setIsSigningOut] = useState(false);
  const displayName = user.fullName || user.email;

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
    <div>
      <header>
        <div>
          <strong>XYZ LMS</strong>
          <p>
            {displayName} · {user.role}
          </p>
        </div>
        <nav aria-label="Role navigation">Role navigation placeholder</nav>
        <button disabled={isSigningOut} onClick={signOut} type="button">
          Log out
        </button>
      </header>
      <main>{children}</main>
    </div>
  );
}
