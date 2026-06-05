import { notFound } from 'next/navigation';

import TracerClient from './TracerClient';

export default function TracerPage() {
  if (process.env.NEXT_PUBLIC_TRACER_ENABLED !== 'true') {
    notFound();
  }

  return <TracerClient />;
}
