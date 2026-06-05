'use client';

import type { Session, User } from '@supabase/supabase-js';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import { getSupabaseBrowserClient } from '../supabase/client';

type SessionStatus = 'loading' | 'authenticated' | 'unauthenticated' | 'error';

type SessionContextValue = {
  session: Session | null;
  user: User | null;
  status: SessionStatus;
  error: string | null;
  refreshSession: () => Promise<void>;
};

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [status, setStatus] = useState<SessionStatus>('loading');
  const [error, setError] = useState<string | null>(null);

  const refreshSession = useCallback(async () => {
    try {
      const supabase = getSupabaseBrowserClient();
      const { data, error: sessionError } = await supabase.auth.getSession();
      if (sessionError) {
        throw sessionError;
      }

      setSession(data.session);
      setStatus(data.session ? 'authenticated' : 'unauthenticated');
      setError(null);
    } catch (caught) {
      setSession(null);
      setStatus('error');
      setError(caught instanceof Error ? caught.message : 'Unable to load session');
    }
  }, []);

  useEffect(() => {
    void refreshSession();

    let unsubscribe: (() => void) | undefined;
    try {
      const supabase = getSupabaseBrowserClient();
      const { data } = supabase.auth.onAuthStateChange((_event, nextSession) => {
        setSession(nextSession);
        setStatus(nextSession ? 'authenticated' : 'unauthenticated');
        setError(null);
      });
      unsubscribe = () => data.subscription.unsubscribe();
    } catch (caught) {
      setSession(null);
      setStatus('error');
      setError(caught instanceof Error ? caught.message : 'Unable to subscribe to session');
    }

    return () => {
      unsubscribe?.();
    };
  }, [refreshSession]);

  const value = useMemo<SessionContextValue>(
    () => ({
      session,
      user: session?.user ?? null,
      status,
      error,
      refreshSession,
    }),
    [error, refreshSession, session, status],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const value = useContext(SessionContext);
  if (value === null) {
    throw new Error('useSession must be used within SessionProvider');
  }
  return value;
}
