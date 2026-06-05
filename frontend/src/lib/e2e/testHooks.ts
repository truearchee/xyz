'use client';

import { api } from '../api/wrapper';
import { forceNextBearerToken } from './e2eAuthOverride';
import { getSupabaseBrowserClient } from '../supabase/client';

type E2EApiResult<T = unknown> =
  | { ok: true; status: number; data: T }
  | { ok: false; status?: number; errorName: string; message?: string };

function errorResult<T = unknown>(caught: unknown): E2EApiResult<T> {
  const maybeStatus = caught instanceof Error && 'status' in caught
    ? Number(caught.status)
    : undefined;

  return {
    ok: false,
    status: Number.isFinite(maybeStatus) ? maybeStatus : undefined,
    errorName: caught instanceof Error ? caught.name : 'UnknownError',
    message: caught instanceof Error ? caught.message : undefined,
  };
}

async function envelope<T>(request: () => Promise<T>): Promise<E2EApiResult<T>> {
  try {
    const data = await request();
    return { ok: true, status: 200, data };
  } catch (caught) {
    return errorResult<T>(caught);
  }
}

export function registerE2ETestHooks() {
  if (
    process.env.NEXT_PUBLIC_E2E_TEST_HOOKS !== 'true' ||
    typeof window === 'undefined'
  ) {
    return;
  }

  const supabase = getSupabaseBrowserClient();

  window.__xyzE2E = {
    refreshSession: async () => supabase.auth.refreshSession(),
    getSession: async () => supabase.auth.getSession(),
    forceNextBearerToken,
    callMe: async () => envelope(() => api.me.get()),
    callAdminUsers: async () => envelope(() => api.admin.listUsers()),
  };
}
