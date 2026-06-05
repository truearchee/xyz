'use client';

import { useEffect, type ReactNode } from 'react';
import { usePathname, useRouter } from 'next/navigation';

import { AccessDenied } from '../../components/auth/AccessDenied';
import { AppShell } from '../../components/shell/AppShell';
import { useSession } from '../session/SessionProvider';
import { CurrentUserResponse } from '../api';

type Role = CurrentUserResponse['role'];

const roleRouteMap: Record<string, Role> = {
  '/admin': CurrentUserResponse.role.ADMIN,
  '/lecturer': CurrentUserResponse.role.LECTURER,
  '/student': CurrentUserResponse.role.STUDENT,
};

function LoadingState() {
  return <main>Loading...</main>;
}

export function roleHomePath(role: Role): string {
  return `/${role}`;
}

function matchesRoutePrefix(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

function isUnauthorizedPath(pathname: string): boolean {
  return matchesRoutePrefix(pathname, '/unauthorized');
}

function isWrongRole(pathname: string, role: Role): boolean {
  if (isUnauthorizedPath(pathname)) {
    return false;
  }

  return Object.entries(roleRouteMap).some(
    ([prefix, routeRole]) =>
      matchesRoutePrefix(pathname, prefix) && role !== routeRole,
  );
}

export function ProtectedAppLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { state } = useSession();
  const shouldShowUnauthorized =
    state.status === 'authenticated' && isWrongRole(pathname, state.user.role);

  useEffect(() => {
    if (state.status === 'unauthenticated') {
      router.replace('/login');
    }
  }, [router, state.status]);

  useEffect(() => {
    if (shouldShowUnauthorized) {
      router.replace('/unauthorized');
    }
  }, [router, shouldShowUnauthorized]);

  if (state.status === 'loading' || state.status === 'unauthenticated') {
    return <LoadingState />;
  }

  if (state.status === 'forbidden') {
    return <AccessDenied email={state.email} reason={state.reason} />;
  }

  if (shouldShowUnauthorized) {
    return <LoadingState />;
  }

  return <AppShell user={state.user}>{children}</AppShell>;
}
