'use client';

import { FormEvent, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

import { ApiError } from '../../../lib/api';
import { AccessDenied } from '../../../components/auth/AccessDenied';
import { api } from '../../../lib/api/wrapper';
import { roleHomePath } from '../../../lib/routing/ProtectedAppLayout';
import { useSession } from '../../../lib/session/SessionProvider';
import { getSupabaseBrowserClient } from '../../../lib/supabase/client';

type RawResult =
  | { ok: true; data: unknown }
  | { ok: false; status?: number; message: string; body?: unknown };

function formatResult(result: RawResult | null): string {
  if (result === null) {
    return 'No API call yet';
  }

  return JSON.stringify(result, null, 2);
}

export default function LoginPage() {
  const router = useRouter();
  const { session, state, status, refreshSession } = useSession();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [meResult, setMeResult] = useState<RawResult | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setMessage(null);
    setMeResult(null);

    try {
      const supabase = getSupabaseBrowserClient();
      const { error: signInError } = await supabase.auth.signInWithPassword({
        email,
        password,
      });

      if (signInError) {
        throw signInError;
      }

      await refreshSession();
      setMessage('signed in');
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : 'sign-in failed');
    } finally {
      setIsSubmitting(false);
    }
  }

  async function signOut() {
    setIsSubmitting(true);
    setMessage(null);
    setMeResult(null);

    try {
      const supabase = getSupabaseBrowserClient();
      const { error: signOutError } = await supabase.auth.signOut();
      if (signOutError) {
        throw signOutError;
      }

      await refreshSession();
      setMessage('signed out');
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : 'sign-out failed');
    } finally {
      setIsSubmitting(false);
    }
  }

  async function callMe() {
    setMessage(null);
    setMeResult(null);

    try {
      const data = await api.me.get();
      setMeResult({ ok: true, data });
    } catch (caught) {
      if (caught instanceof ApiError) {
        setMeResult({
          ok: false,
          status: caught.status,
          message: caught.message,
          body: caught.body,
        });
        return;
      }

      setMeResult({
        ok: false,
        message: caught instanceof Error ? caught.message : 'GET /me failed',
      });
    }
  }

  useEffect(() => {
    if (state.status === 'authenticated') {
      router.replace(roleHomePath(state.user.role));
    }
  }, [router, state]);

  if (state.status === 'loading' || state.status === 'authenticated') {
    return <main>Loading...</main>;
  }

  if (state.status === 'forbidden') {
    return <AccessDenied email={state.email} reason={state.reason} />;
  }

  return (
    <main>
      <h1>Login</h1>
      <p>Session status: {status}</p>
      <p>Session email: {session?.user.email ?? 'none'}</p>
      <p>Access token present: {session?.access_token ? 'yes' : 'no'}</p>
      {message ? <p>Message: {message}</p> : null}

      <form onSubmit={signIn}>
        <label>
          Email
          <input
            autoComplete="email"
            name="email"
            onChange={(event) => setEmail(event.target.value)}
            type="email"
            value={email}
          />
        </label>
        <label>
          Password
          <input
            autoComplete="current-password"
            name="password"
            onChange={(event) => setPassword(event.target.value)}
            type="password"
            value={password}
          />
        </label>
        <button disabled={isSubmitting} type="submit">
          Sign in
        </button>
      </form>

      <button disabled={isSubmitting || status !== 'authenticated'} onClick={signOut} type="button">
        Sign out
      </button>
      <button disabled={status !== 'authenticated'} onClick={callMe} type="button">
        GET /me
      </button>

      <pre>{formatResult(meResult)}</pre>
    </main>
  );
}
