'use client';

import type { AuthChangeEvent, Session, User } from '@supabase/supabase-js';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import type { CurrentUserResponse } from '../api';
import { AuthRequiredError, ForbiddenError, api } from '../api/wrapper';
import { registerE2ETestHooks } from '../e2e/testHooks';
import { getSupabaseBrowserClient } from '../supabase/client';

export type SessionState =
  | { status: 'loading' }
  | { status: 'unauthenticated' }
  | { status: 'authenticated'; user: CurrentUserResponse }
  | { status: 'forbidden'; reason?: string; email?: string };

type SessionContextValue = {
  state: SessionState;
  session: Session | null;
  supabaseUser: User | null;
  user: CurrentUserResponse | null;
  status: SessionState['status'];
  refreshSession: () => Promise<void>;
};

const SessionContext = createContext<SessionContextValue | null>(null);

function forbiddenState(reason: string, session: Session): SessionState {
  return {
    status: 'forbidden',
    reason,
    email: session.user.email ?? undefined,
  };
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [state, setState] = useState<SessionState>({ status: 'loading' });

  const loadApplicationSession = useCallback(async (nextSession: Session) => {
    setSession(nextSession);

    try {
      const currentUser = await api.me.get();
      setState({ status: 'authenticated', user: currentUser });
    } catch (caught) {
      if (caught instanceof AuthRequiredError) {
        setSession(null);
        setState({ status: 'unauthenticated' });
        return;
      }

      if (caught instanceof ForbiddenError) {
        if (process.env.NODE_ENV !== 'production') {
          console.warn('Supabase user has no application account', caught);
        }
        setState(forbiddenState('Application access is not enabled for this account.', nextSession));
        return;
      }

      throw caught;
    }
  }, []);

  const refreshSession = useCallback(async () => {
    const supabase = getSupabaseBrowserClient();
    const { data, error: sessionError } = await supabase.auth.getSession();
    if (sessionError) {
      throw sessionError;
    }

    if (!data.session) {
      setSession(null);
      setState({ status: 'unauthenticated' });
      return;
    }

    await loadApplicationSession(data.session);
  }, [loadApplicationSession]);

  useEffect(() => {
    registerE2ETestHooks();

    void refreshSession().catch((caught) => {
      console.error('Unable to load session', caught);
      setSession(null);
      setState({ status: 'unauthenticated' });
    });

    let unsubscribe: (() => void) | undefined;
    try {
      const supabase = getSupabaseBrowserClient();
      const { data } = supabase.auth.onAuthStateChange((event: AuthChangeEvent, nextSession) => {
        if (event === 'SIGNED_OUT') {
          setSession(null);
          setState({ status: 'unauthenticated' });
          window.location.assign('/login');
          return;
        }

        if (event === 'TOKEN_REFRESHED') {
          setSession(nextSession);
          return;
        }

        if (event === 'SIGNED_IN' && nextSession) {
          void loadApplicationSession(nextSession).catch((caught) => {
            console.error('Unable to load application session', caught);
            setSession(null);
            setState({ status: 'unauthenticated' });
          });
        }
      });
      unsubscribe = () => data.subscription.unsubscribe();
    } catch (caught) {
      setSession(null);
      setState({ status: 'unauthenticated' });
      console.error('Unable to subscribe to session', caught);
    }

    return () => {
      unsubscribe?.();
    };
  }, [refreshSession]);

  const value = useMemo<SessionContextValue>(
    () => ({
      state,
      session,
      supabaseUser: session?.user ?? null,
      user: state.status === 'authenticated' ? state.user : null,
      status: state.status,
      refreshSession,
    }),
    [refreshSession, session, state],
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

export function useRole() {
  const { state } = useSession();
  return state.status === 'authenticated' ? state.user.role : null;
}
