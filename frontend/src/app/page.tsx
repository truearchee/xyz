'use client';

import { useEffect, useState } from 'react';

import { OpenAPI } from '../lib/api';
import { DefaultService } from '../lib/api/services/DefaultService';

OpenAPI.BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

const POLL_INTERVAL_MS = 2500;
const REQUEST_TIMEOUT_MS = 5000;

function timeoutAfter(ms: number): Promise<never> {
  return new Promise((_, reject) => {
    setTimeout(() => reject(new Error('Health request timed out')), ms);
  });
}

async function checkBackendHealth(): Promise<string> {
  const data = await Promise.race([
    DefaultService.healthHealthGet(),
    timeoutAfter(REQUEST_TIMEOUT_MS),
  ]);
  return data.status ?? 'unreachable';
}

export default function Home() {
  const [status, setStatus] = useState<string>('checking...');

  useEffect(() => {
    const check = () => {
      void checkBackendHealth()
        .then(setStatus)
        .catch(() => setStatus('unreachable'));
    };

    check();
    const id = setInterval(check, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, []);

  return (
    <main>
      <h1>XYZ LMS</h1>
      <p>Backend: {status}</p>
    </main>
  );
}
