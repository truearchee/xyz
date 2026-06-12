'use client';

import Link from 'next/link';

import { roleHomePath } from '../../../lib/routing/ProtectedAppLayout';
import { useSession } from '../../../lib/session/SessionProvider';

export default function UnauthorizedPage() {
  const { state } = useSession();
  const homePath =
    state.status === 'authenticated' ? roleHomePath(state.user.role) : '/';

  return (
    <section className="mx-auto flex max-w-md flex-col items-center gap-3 py-16 text-center">
      <h1 className="font-display text-2xl font-bold text-text">Unauthorized</h1>
      <p className="text-text-muted">You are signed in, but this area is not available to your role.</p>
      <Link
        href={homePath}
        className="rounded-md bg-primary px-4 py-2 font-medium text-on-primary hover:bg-primary-hover focus:outline-none focus:ring-2 focus:ring-focus-ring focus:ring-offset-2"
      >
        Go to your workspace
      </Link>
    </section>
  );
}
