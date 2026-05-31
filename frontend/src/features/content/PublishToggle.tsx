"use client";

import type { SectionDetail } from "../../lib/api/models/SectionDetail";

type PublishToggleProps = {
  disabled?: boolean;
  errorMessage?: string | null;
  onPublish: () => void;
  onUnpublish: () => void;
  section: SectionDetail;
};

export function PublishToggle({
  disabled = false,
  errorMessage = null,
  onPublish,
  onUnpublish,
  section,
}: PublishToggleProps) {
  const isPublished = section.publishStatus === "published";

  return (
    <div style={styles.shell}>
      <div style={styles.meta}>
        <span style={styles.label}>Visibility</span>
        <span style={styles.status}>{formatStatus(section.publishStatus)}</span>
      </div>
      <button
        disabled={disabled}
        onClick={isPublished ? onUnpublish : onPublish}
        style={isPublished ? styles.secondaryButton : styles.primaryButton}
        type="button"
      >
        {isPublished ? "Unpublish" : "Publish"}
      </button>
      {errorMessage ? <p style={styles.error}>{errorMessage}</p> : null}
    </div>
  );
}

function formatStatus(status: SectionDetail["publishStatus"]): string {
  if (status === "published") {
    return "Published";
  }
  if (status === "unpublished") {
    return "Unpublished";
  }
  return "Draft";
}

const baseButton = {
  borderRadius: 6,
  cursor: "pointer",
  fontSize: 14,
  fontWeight: 700,
  lineHeight: 1,
  minHeight: 38,
  padding: "0 14px",
} satisfies React.CSSProperties;

const styles = {
  shell: {
    alignItems: "center",
    display: "flex",
    flexWrap: "wrap",
    gap: 10,
  },
  meta: {
    display: "grid",
    gap: 2,
    minWidth: 140,
  },
  label: {
    color: "#4b5563",
    fontSize: 12,
    fontWeight: 700,
    textTransform: "uppercase",
  },
  status: {
    color: "#111827",
    fontSize: 14,
    fontWeight: 700,
  },
  primaryButton: {
    ...baseButton,
    background: "#174a63",
    border: "1px solid #174a63",
    color: "#ffffff",
  },
  secondaryButton: {
    ...baseButton,
    background: "#ffffff",
    border: "1px solid #9ca3af",
    color: "#111827",
  },
  error: {
    color: "#b42318",
    flexBasis: "100%",
    fontSize: 13,
    margin: 0,
  },
} satisfies Record<string, React.CSSProperties>;
