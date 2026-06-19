import type { ModuleSummary } from "../../lib/api/models/ModuleSummary";
import { Badge } from "../../components/ui/Badge";
import { cn } from "../../components/ui/cn";

type ModuleListViewProps = {
  modules: ModuleSummary[];
  errorMessage?: string | null;
  isLoading?: boolean;
  selectedModuleId?: string;
  getModuleHref?: (module: ModuleSummary) => string;
};

const itemBase =
  "grid gap-2 rounded-lg border border-border bg-surface-raised p-4 text-text no-underline transition-colors hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2";

export function ModuleListView({
  modules,
  errorMessage,
  isLoading = false,
  selectedModuleId,
  getModuleHref = (module) => `/modules/${module.id}`,
}: ModuleListViewProps) {
  if (isLoading) {
    return (
      <section aria-busy="true" aria-label="Modules" className="rounded-lg border border-border p-6">
        <h2 className="m-0 font-display text-base leading-snug text-text">Loading modules</h2>
      </section>
    );
  }

  if (errorMessage) {
    return (
      <section aria-label="Modules" role="alert" className="rounded-lg border border-danger p-6 text-danger-text">
        <h2 className="m-0 font-display text-base leading-snug">Unable to load modules</h2>
        <p className="mt-2 text-sm leading-normal">{errorMessage}</p>
      </section>
    );
  }

  if (modules.length === 0) {
    return (
      <section aria-label="Modules" className="rounded-lg border border-border p-6">
        <h2 className="m-0 font-display text-base leading-snug text-text">No assigned modules</h2>
      </section>
    );
  }

  return (
    <section aria-label="Modules" className="grid gap-2">
      {modules.map((module) => {
        const isSelected = module.id === selectedModuleId;

        return (
          <a
            aria-current={isSelected ? "page" : undefined}
            href={getModuleHref(module)}
            key={module.id}
            className={cn(itemBase, isSelected && "border-primary ring-1 ring-focus-ring")}
          >
            <span className="text-base font-semibold leading-snug">{module.title}</span>
            <span className="flex flex-wrap items-center gap-2 text-xs capitalize text-text-muted">
              <Badge tone={module.isActive ? "success" : "neutral"}>
                {module.isActive ? "Active" : "Inactive"}
              </Badge>
              <span>{module.globalRole}</span>
            </span>
          </a>
        );
      })}
    </section>
  );
}
