import Link from "next/link";

import { cn } from "../components/ui/cn";
import { EmptyState } from "../components/ui/EmptyState";
import { buttonBase, buttonSizes, buttonVariants } from "../components/ui/variants";

// Stage 4.9b — route-level 404, on the Empty State component.
export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-md items-center justify-center px-4">
      <EmptyState
        headingLevel={1}
        title="Page not found"
        description="The page you are looking for does not exist or has moved."
        action={
          <Link href="/" className={cn(buttonBase, buttonVariants.primary, buttonSizes.md)}>
            Go home
          </Link>
        }
      />
    </main>
  );
}
