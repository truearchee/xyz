'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

import { AccessDenied } from '../components/auth/AccessDenied';
import { roleHomePath } from '../lib/routing/ProtectedAppLayout';
import { useSession } from '../lib/session/SessionProvider';

export default function Home() {
  const router = useRouter();
  const { state } = useSession();

  useEffect(() => {
    if (state.status === 'unauthenticated') {
      router.replace('/login');
      return;
    }

    if (state.status === 'authenticated') {
      router.replace(roleHomePath(state.user.role));
    }
  }, [router, state]);

  if (state.status === 'forbidden') {
    return <AccessDenied email={state.email} reason={state.reason} />;
  }

  return <main>Loading...</main>;
}
