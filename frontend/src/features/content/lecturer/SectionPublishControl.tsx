"use client";

type SectionPublishControlProps = {
  errorMessage: string | null;
  isSubmitting: boolean;
  onToggle: () => Promise<void>;
  publishStatus: string;
  sectionKey: string;
  sectionTitle: string;
};

const badgeBase =
  "inline-flex shrink-0 items-center rounded-full border px-2.5 py-1 text-xs font-bold";
const btnPrimary =
  "min-h-[38px] rounded-md border border-primary bg-primary px-3.5 text-sm font-bold text-on-primary hover:bg-primary-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2";
const btnDisabled =
  "min-h-[38px] cursor-not-allowed rounded-md border border-border bg-surface-muted px-3.5 text-sm font-bold text-text-muted";

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
    <div className="flex flex-wrap items-center justify-end gap-2.5">
      <span
        data-testid={`section-publish-status-${sectionKey}`}
        className={
          isPublished
            ? `${badgeBase} border-success bg-success-surface text-success-text`
            : `${badgeBase} border-info bg-info-surface text-info-text`
        }
      >
        Section visibility: {formatPublishStatus(publishStatus)}
      </span>
      <button
        aria-label={`${action} ${sectionTitle}`}
        disabled={isSubmitting}
        onClick={() => void onToggle()}
        className={isSubmitting ? btnDisabled : btnPrimary}
        type="button"
      >
        {isSubmitting ? `${action}ing...` : `${action} ${sectionTitle}`}
      </button>
      {errorMessage ? (
        <p
          role="alert"
          className="m-0 basis-full rounded-md border border-danger bg-danger-surface px-2.5 py-2 text-sm leading-snug text-danger-text"
        >
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
