type E2EApiResult<T = unknown> =
  | { ok: true; status: number; data: T }
  | { ok: false; status?: number; errorName: string; message?: string };

declare global {
  interface Window {
    __xyzE2E?: {
      refreshSession: () => Promise<unknown>;
      getSession: () => Promise<unknown>;
      forceNextBearerToken: (token: string) => void;
      callMe: () => Promise<E2EApiResult>;
      callAdminUsers: () => Promise<E2EApiResult>;
    };
  }
}

export {};
