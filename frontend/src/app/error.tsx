'use client';

// Stage 4.9a — route-level error boundary. Token-styled so a Stage 5+ failure shows the interface's
// voice, not an unstyled React crash. 4.9b refactors this onto the Empty State component (tracked).

export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col items-center justify-center gap-4 px-4 text-center">
      <h1 className="font-display text-2xl font-bold text-text">Something went wrong</h1>
      <p className="text-text-muted">
        An unexpected error occurred while loading this page. You can try again.
      </p>
      <button
        type="button"
        onClick={reset}
        className="rounded-md bg-primary px-4 py-2 font-medium text-on-primary hover:bg-primary-hover focus:outline-none focus:ring-2 focus:ring-focus-ring focus:ring-offset-2"
      >
        Try again
      </button>
    </main>
  );
}
