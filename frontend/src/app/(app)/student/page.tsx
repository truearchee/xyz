import Link from "next/link";

import { AssignedModulesList } from "../../../features/modules/AssignedModulesList";

export default function StudentPage() {
  return (
    <section className="grid gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <h1 className="m-0 font-display text-2xl font-semibold text-text">Student</h1>
        <nav aria-label="Student navigation" className="flex flex-wrap items-center gap-2">
          <Link
            className="rounded-full border border-border bg-surface px-3 py-1.5 text-sm font-medium text-text no-underline hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2"
            href="/student/glossary"
            data-testid="nav-glossary"
          >
          Glossary
          </Link>
          <Link
            className="rounded-full border border-border bg-surface px-3 py-1.5 text-sm font-medium text-text no-underline hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2"
            href="/student/progress"
            data-testid="nav-progress"
          >
          My Progress
          </Link>
          <Link
            className="rounded-full border border-border bg-surface px-3 py-1.5 text-sm font-medium text-text no-underline hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2"
            href="/student/settings"
            data-testid="nav-settings"
          >
          Settings
          </Link>
        </nav>
      </div>
      <AssignedModulesList moduleHrefPrefix="/student/modules" />
    </section>
  );
}
