"use client";

import { Button } from "../components/ui/Button";
import { EmptyState } from "../components/ui/EmptyState";

// Stage 4.9b — route-level error boundary, now on the Empty State component (§4.3 styled error boundary).
export default function RouteError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="mx-auto flex min-h-dvh max-w-md items-center justify-center px-4">
      <EmptyState
        headingLevel={1}
        title="Something went wrong"
        description="An unexpected error occurred while loading this page. You can try again."
        action={<Button onClick={reset}>Try again</Button>}
      />
    </main>
  );
}
