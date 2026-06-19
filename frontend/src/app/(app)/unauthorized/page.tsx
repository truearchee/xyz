'use client';

import Link from 'next/link';

import { cn } from '../../../components/ui/cn';
import { EmptyState } from '../../../components/ui/EmptyState';
import { buttonBase, buttonSizes, buttonVariants } from '../../../components/ui/variants';
import { roleHomePath } from '../../../lib/routing/ProtectedAppLayout';
import { useSession } from '../../../lib/session/SessionProvider';

export default function UnauthorizedPage() {
  const { state } = useSession();
  const homePath =
    state.status === 'authenticated' ? roleHomePath(state.user.role) : '/';

  return (
    <section className="mx-auto flex max-w-md flex-col items-center py-16">
      <EmptyState
        headingLevel={1}
        title="Unauthorized"
        description="You are signed in, but this area is not available to your role."
        action={
          <Link href={homePath} className={cn(buttonBase, buttonVariants.primary, buttonSizes.md)}>
            Go to your workspace
          </Link>
        }
      />
    </section>
  );
}
