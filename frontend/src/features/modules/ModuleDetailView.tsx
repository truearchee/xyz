import type { ModuleDetail } from "../../lib/api/models/ModuleDetail";

type ModuleDetailViewProps = {
  errorMessage?: string | null;
  isLoading?: boolean;
  module?: ModuleDetail | null;
};

export function ModuleDetailView({
  errorMessage,
  isLoading = false,
  module,
}: ModuleDetailViewProps) {
  if (isLoading) {
    return (
      <article aria-busy="true" aria-label="Module detail" style={styles.detail}>
        <h1 style={styles.stateTitle}>Loading module</h1>
      </article>
    );
  }

  if (errorMessage) {
    return (
      <article aria-label="Module detail" role="alert" style={styles.errorDetail}>
        <h1 style={styles.stateTitle}>Unable to load module</h1>
        <p style={styles.stateText}>{errorMessage}</p>
      </article>
    );
  }

  if (!module) {
    return (
      <article aria-label="Module detail" style={styles.detail}>
        <h1 style={styles.stateTitle}>No module selected</h1>
      </article>
    );
  }

  const createdAt = new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(module.createdAt));

  return (
    <article aria-labelledby="module-title" style={styles.detail}>
      <header style={styles.header}>
        <div>
          <p style={styles.eyebrow}>{module.globalRole}</p>
          <h1 id="module-title" style={styles.title}>
            {module.title}
          </h1>
        </div>
        <span style={styles.badge}>{module.isActive ? "Active" : "Inactive"}</span>
      </header>

      <dl style={styles.facts}>
        <div style={styles.fact}>
          <dt style={styles.label}>Publish</dt>
          <dd style={styles.value}>{module.canPublish ? "Allowed" : "Not allowed"}</dd>
        </div>
        <div style={styles.fact}>
          <dt style={styles.label}>Created</dt>
          <dd style={styles.value}>{createdAt}</dd>
        </div>
      </dl>
    </article>
  );
}

const styles = {
  detail: {
    border: "1px solid #d7dde8",
    borderRadius: 8,
    color: "#111827",
    padding: 24,
  },
  errorDetail: {
    border: "1px solid #f0b4b4",
    borderRadius: 8,
    color: "#7f1d1d",
    padding: 24,
  },
  header: {
    alignItems: "flex-start",
    display: "flex",
    gap: 16,
    justifyContent: "space-between",
  },
  eyebrow: {
    color: "#4b5563",
    fontSize: 13,
    fontWeight: 700,
    letterSpacing: 0,
    margin: "0 0 6px",
    textTransform: "capitalize",
  },
  title: {
    fontSize: 24,
    lineHeight: 1.2,
    margin: 0,
  },
  badge: {
    background: "#e8f5e9",
    border: "1px solid #a7d8ad",
    borderRadius: 999,
    color: "#1f6f35",
    flex: "0 0 auto",
    fontSize: 13,
    padding: "4px 10px",
  },
  facts: {
    display: "grid",
    gap: 12,
    gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
    margin: "24px 0 0",
  },
  fact: {
    borderTop: "1px solid #e5e7eb",
    paddingTop: 12,
  },
  label: {
    color: "#4b5563",
    fontSize: 12,
    fontWeight: 700,
    marginBottom: 4,
    textTransform: "uppercase",
  },
  value: {
    fontSize: 15,
    margin: 0,
  },
  stateTitle: {
    fontSize: 18,
    lineHeight: 1.35,
    margin: 0,
  },
  stateText: {
    fontSize: 14,
    lineHeight: 1.5,
    margin: "8px 0 0",
  },
} satisfies Record<string, React.CSSProperties>;
