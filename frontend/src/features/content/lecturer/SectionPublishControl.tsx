"use client";

type SectionPublishControlProps = {
  errorMessage: string | null;
  isSubmitting: boolean;
  onToggle: () => Promise<void>;
  publishStatus: string;
  sectionKey: string;
  sectionTitle: string;
};

export function SectionPublishControl({
  errorMessage,
  isSubmitting,
  onToggle,
  publishStatus,
  sectionKey,
  sectionTitle,
}: SectionPublishControlProps) {
  const isPublished = publishStatus === "published";
  const action = isPublished ? "Unpublish" : "Publish";

  return (
    <div style={styles.shell}>
      <span
        data-testid={`section-publish-status-${sectionKey}`}
        style={isPublished ? styles.publishedBadge : styles.draftBadge}
      >
        Section visibility: {formatPublishStatus(publishStatus)}
      </span>
      <button
        aria-label={`${action} ${sectionTitle}`}
        disabled={isSubmitting}
        onClick={() => void onToggle()}
        style={isSubmitting ? styles.disabledButton : styles.button}
        type="button"
      >
        {isSubmitting ? `${action}ing...` : `${action} ${sectionTitle}`}
      </button>
      {errorMessage ? (
        <p role="alert" style={styles.error}>
          {errorMessage}
        </p>
      ) : null}
    </div>
  );
}

export function formatPublishStatus(status: string): string {
  if (status === "published") {
    return "Published";
  }
  if (status === "unpublished") {
    return "Unpublished";
  }
  return "Draft";
}

const badgeBase = {
  borderRadius: 999,
  flex: "0 0 auto",
  fontSize: 13,
  fontWeight: 800,
  padding: "4px 10px",
} satisfies React.CSSProperties;

const buttonBase = {
  borderRadius: 6,
  fontSize: 14,
  fontWeight: 700,
  minHeight: 38,
  padding: "0 14px",
} satisfies React.CSSProperties;

const styles = {
  shell: {
    alignItems: "center",
    display: "flex",
    flexWrap: "wrap",
    gap: 10,
    justifyContent: "flex-end",
  },
  draftBadge: {
    ...badgeBase,
    background: "#eef2ff",
    border: "1px solid #c7d2fe",
    color: "#3730a3",
  },
  publishedBadge: {
    ...badgeBase,
    background: "#ecfdf5",
    border: "1px solid #a7f3d0",
    color: "#047857",
  },
  button: {
    ...buttonBase,
    background: "#174a63",
    border: "1px solid #174a63",
    color: "#ffffff",
    cursor: "pointer",
  },
  disabledButton: {
    ...buttonBase,
    background: "#e5e7eb",
    border: "1px solid #d1d5db",
    color: "#6b7280",
    cursor: "not-allowed",
  },
  error: {
    background: "#fef2f2",
    border: "1px solid #fecaca",
    borderRadius: 6,
    color: "#7f1d1d",
    flexBasis: "100%",
    fontSize: 14,
    lineHeight: 1.45,
    margin: 0,
    padding: "8px 10px",
  },
} satisfies Record<string, React.CSSProperties>;
