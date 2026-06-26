import { expect, request as playwrightRequest, test } from '@playwright/test';

// F-12C-CORS (12f): the committed frontend origin must be accepted by the backend's CORS policy, and a
// foreign origin must not be granted. This pins the committed-config fix (frontend port :3000 ⇄ CORS
// default) so it cannot silently regress and re-break every cross-origin login. It hits the backend
// directly via a preflight OPTIONS, so it needs no login, seed, or run manifest.

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const FRONTEND_ORIGIN = (process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:3000').replace(/\/+$/, '');

test('CORS preflight from the committed frontend origin is allowed', async () => {
  const ctx = await playwrightRequest.newContext();
  try {
    const res = await ctx.fetch(`${API_BASE_URL}/me`, {
      method: 'OPTIONS',
      headers: {
        Origin: FRONTEND_ORIGIN,
        'Access-Control-Request-Method': 'GET',
        'Access-Control-Request-Headers': 'authorization',
      },
    });
    expect(res.status()).toBeLessThan(400);
    expect(res.headers()['access-control-allow-origin']).toBe(FRONTEND_ORIGIN);
  } finally {
    await ctx.dispose();
  }
});

test('CORS preflight from a foreign origin is not granted', async () => {
  const ctx = await playwrightRequest.newContext();
  try {
    const res = await ctx.fetch(`${API_BASE_URL}/me`, {
      method: 'OPTIONS',
      headers: {
        Origin: 'http://evil.example',
        'Access-Control-Request-Method': 'GET',
        'Access-Control-Request-Headers': 'authorization',
      },
    });
    // Starlette's CORSMiddleware returns 400 for a disallowed preflight and never echoes the origin.
    expect(res.headers()['access-control-allow-origin']).toBeUndefined();
  } finally {
    await ctx.dispose();
  }
});
