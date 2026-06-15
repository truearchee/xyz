'use client';

import { FormEvent, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

import { ApiError } from '../../../lib/api';
import { AccessDenied } from '../../../components/auth/AccessDenied';
import { Button } from '../../../components/ui/Button';
import { Card } from '../../../components/ui/Card';
import { Input } from '../../../components/ui/Input';
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
    return <main className="grid min-h-dvh place-items-center text-text-muted">Loading...</main>;
  }

  if (state.status === 'forbidden') {
    return <AccessDenied email={state.email} reason={state.reason} />;
  }

  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col justify-center gap-4 px-4 py-10">
      <div className="text-center">
        <strong className="font-display text-2xl font-semibold text-primary">XYZ LMS</strong>
        <h1 className="mt-1 font-display text-lg font-semibold text-text">Login</h1>
      </div>

      <Card className="grid gap-4">
        <form onSubmit={signIn} className="grid gap-3">
          <Input
            id="email"
            label="Email"
            type="email"
            name="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <Input
            id="password"
            label="Password"
            type="password"
            name="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <Button disabled={isSubmitting} type="submit" className="w-full">
            Sign in
          </Button>
        </form>

        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            size="sm"
            disabled={isSubmitting || status !== 'authenticated'}
            onClick={signOut}
          >
            Sign out
          </Button>
          <Button
            variant="ghost"
            size="sm"
            disabled={status !== 'authenticated'}
            onClick={callMe}
          >
            GET /me
          </Button>
        </div>
      </Card>

      <div className="grid gap-1 text-xs text-text-muted">
        <p className="m-0">Session status: {status}</p>
        <p className="m-0">Session email: {session?.user.email ?? 'none'}</p>
        <p className="m-0">Access token present: {session?.access_token ? 'yes' : 'no'}</p>
        {message ? <p className="m-0">Message: {message}</p> : null}
        <pre className="overflow-x-auto rounded-md bg-surface-muted p-2 text-text">{formatResult(meResult)}</pre>
      </div>
    </main>
  );
}
