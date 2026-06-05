'use client';

import Link from 'next/link';

import { roleHomePath } from '../../../lib/routing/ProtectedAppLayout';
import { useSession } from '../../../lib/session/SessionProvider';

export default function UnauthorizedPage() {
  const { state } = useSession();
  const homePath =
    state.status === 'authenticated' ? roleHomePath(state.user.role) : '/';

  return (
    <section>
      <h1>Unauthorized</h1>
      <p>You are signed in, but this area is not available to your role.</p>
      <Link href={homePath}>Go to your workspace</Link>
    </section>
  );
}
