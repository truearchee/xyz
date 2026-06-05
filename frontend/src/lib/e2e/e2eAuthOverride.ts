const E2E_TEST_HOOKS_ENABLED =
  process.env.NEXT_PUBLIC_E2E_TEST_HOOKS === 'true';

let forcedToken: string | null = null;

export function forceNextBearerToken(token: string) {
  if (!E2E_TEST_HOOKS_ENABLED) {
    return;
  }

  forcedToken = token;
}

export function consumeForcedBearerToken(): string | null {
  if (!E2E_TEST_HOOKS_ENABLED) {
    forcedToken = null;
    return null;
  }

  const token = forcedToken;
  forcedToken = null;
  return token;
}
