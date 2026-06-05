import type { ReactNode } from 'react';

import { ProtectedAppLayout } from '../../lib/routing/ProtectedAppLayout';

export default function AppGroupLayout({ children }: { children: ReactNode }) {
  return <ProtectedAppLayout>{children}</ProtectedAppLayout>;
}
