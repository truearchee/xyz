import type { ModuleSummary } from "../../lib/api/models/ModuleSummary";

type ModuleListViewProps = {
  modules: ModuleSummary[];
  errorMessage?: string | null;
  isLoading?: boolean;
  selectedModuleId?: string;
  getModuleHref?: (module: ModuleSummary) => string;
};

export function ModuleListView({
  modules,
  errorMessage,
  isLoading = false,
  selectedModuleId,
  getModuleHref = (module) => `/modules/${module.id}`,
}: ModuleListViewProps) {
  if (isLoading) {
    return (
      <section aria-busy="true" aria-label="Modules" style={styles.statePanel}>
        <h2 style={styles.stateTitle}>Loading modules</h2>
      </section>
    );
  }

  if (errorMessage) {
    return (
      <section aria-label="Modules" role="alert" style={styles.errorPanel}>
        <h2 style={styles.stateTitle}>Unable to load modules</h2>
        <p style={styles.stateText}>{errorMessage}</p>
      </section>
    );
  }

  if (modules.length === 0) {
    return (
      <section aria-label="Modules" style={styles.emptyState}>
        <h2 style={styles.emptyTitle}>No assigned modules</h2>
      </section>
    );
  }

  return (
    <section aria-label="Modules" style={styles.list}>
      {modules.map((module) => {
        const isSelected = module.id === selectedModuleId;

        return (
          <a
            aria-current={isSelected ? "page" : undefined}
            href={getModuleHref(module)}
            key={module.id}
            style={{
              ...styles.item,
              ...(isSelected ? styles.selectedItem : undefined),
            }}
          >
            <span style={styles.title}>{module.title}</span>
            <span style={styles.meta}>
              <span style={styles.badge}>{module.isActive ? "Active" : "Inactive"}</span>
              <span>{module.globalRole}</span>
            </span>
          </a>
        );
      })}
    </section>
  );
}

const styles = {
  list: {
    display: "grid",
    gap: 8,
  },
  item: {
    border: "1px solid #d7dde8",
    borderRadius: 8,
    color: "#111827",
    display: "grid",
    gap: 8,
    padding: 16,
    textDecoration: "none",
  },
  selectedItem: {
    borderColor: "#2563eb",
    boxShadow: "inset 3px 0 0 #2563eb",
  },
  title: {
    fontSize: 16,
    fontWeight: 700,
    lineHeight: 1.35,
  },
  meta: {
    alignItems: "center",
    color: "#4b5563",
    display: "flex",
    flexWrap: "wrap",
    fontSize: 13,
    gap: 8,
    textTransform: "capitalize",
  },
  badge: {
    background: "#e8f5e9",
    border: "1px solid #a7d8ad",
    borderRadius: 999,
    color: "#1f6f35",
    padding: "2px 8px",
  },
  emptyState: {
    border: "1px solid #d7dde8",
    borderRadius: 8,
    padding: 24,
  },
  statePanel: {
    border: "1px solid #d7dde8",
    borderRadius: 8,
    padding: 24,
  },
  errorPanel: {
    border: "1px solid #f0b4b4",
    borderRadius: 8,
    color: "#7f1d1d",
    padding: 24,
  },
  stateTitle: {
    fontSize: 16,
    lineHeight: 1.4,
    margin: 0,
  },
  stateText: {
    fontSize: 14,
    lineHeight: 1.5,
    margin: "8px 0 0",
  },
  emptyTitle: {
    fontSize: 16,
    lineHeight: 1.4,
    margin: 0,
  },
} satisfies Record<string, React.CSSProperties>;
