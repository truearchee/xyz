import Link from "next/link";

// Stage 4.9a — route-level 404 surface, token-styled. 4.9b refactors onto the Empty State component.

export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col items-center justify-center gap-4 px-4 text-center">
      <h1 className="font-display text-2xl font-bold text-text">Page not found</h1>
      <p className="text-text-muted">The page you are looking for does not exist or has moved.</p>
      <Link
        href="/"
        className="rounded-md bg-primary px-4 py-2 font-medium text-on-primary hover:bg-primary-hover focus:outline-none focus:ring-2 focus:ring-focus-ring focus:ring-offset-2"
      >
        Go home
      </Link>
    </main>
  );
}
