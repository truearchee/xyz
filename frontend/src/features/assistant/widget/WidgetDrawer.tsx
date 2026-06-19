"use client";

/**
 * Compact assistant drawer (Stage 8.4). On a lecture page it shows that lecture's conversation (shared
 * store → a message sent here also appears in the inline panel, and vice versa); elsewhere it shows
 * recents + "Start with a lecture" + "Open full workspace". Right-side panel on desktop, full-width
 * bottom-anchored sheet on mobile (width clamps to the viewport; 100dvh tracks mobile browser chrome).
 * Keyboard-overlap behavior is not asserted in 8.4. role="dialog" + aria-modal, focus trap, Esc closes
 * and returns focus to the button. Inline idiom.
 */

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { type ConversationListItem } from "../../../lib/api";
import { api } from "../../../lib/api/wrapper";
import { useFocusTrap } from "../a11y/useFocusTrap";
import { useAssistantConversation } from "../AssistantStoreProvider";
import { ConversationView } from "../ConversationView";
import { StarterChips } from "../StarterChips";

type WidgetDrawerProps = {
  mode: "lecture" | "recents";
  conversationId: string | null;
  lectureStatus: "opening" | "processing" | "unavailable" | "error" | null;
  moduleId: string | null;
  sectionId: string | null;
  onClose: () => void;
};

export function WidgetDrawer({ mode, conversationId, lectureStatus, moduleId, sectionId, onClose }: WidgetDrawerProps) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  useFocusTrap(panelRef, true, onClose);
  const conv = useAssistantConversation(conversationId);
  const [detail, setDetail] = useState<ConversationListItem | null>(null);
  const [recents, setRecents] = useState<ConversationListItem[] | null>(null);

  useEffect(() => {
    if (mode !== "lecture" || !conversationId) {
      setDetail(null);
      return;
    }
    let mounted = true;
    void (async () => {
      try {
        const row = await api.assistant.getConversation(conversationId);
        if (mounted) setDetail(row);
      } catch {
        if (mounted) setDetail(null);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [mode, conversationId]);

  useEffect(() => {
    if (mode !== "recents") return;
    let mounted = true;
    void (async () => {
      try {
        const page = await api.assistant.listConversations(5, 0);
        if (mounted) setRecents(page.items);
      } catch {
        if (mounted) setRecents([]);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [mode]);

  return (
    <>
      <div aria-hidden="true" data-testid="assistant-widget-scrim" onClick={onClose} style={styles.scrim} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Lecture assistant"
        data-testid="assistant-widget-drawer"
        tabIndex={-1}
        style={styles.panel}
      >
        <div style={styles.header}>
          <h2 style={styles.heading}>Lecture assistant</h2>
          <button
            type="button"
            data-testid="assistant-widget-close"
            aria-label="Close assistant"
            onClick={onClose}
            style={styles.close}
          >
            ×
          </button>
        </div>

        <div style={styles.body}>
          {mode === "lecture" && conversationId ? (
            <ConversationView
              scope="widget"
              messages={conv.messages}
              loading={conv.loading}
              hasPending={conv.hasPending}
              gone={conv.gone}
              capped={conv.capped}
              sending={conv.sending}
              error={conv.error}
              draft={conv.draft}
              hasMore={conv.hasMore}
              loadingOlder={conv.loadingOlder}
              onSend={conv.send}
              onRetry={conv.retry}
              onLoadOlder={conv.loadOlder}
              onDraftChange={conv.setDraft}
              header={
                <LectureContextHeader
                  detail={detail}
                  moduleId={moduleId}
                  sectionId={sectionId}
                  onClose={onClose}
                />
              }
              starters={<StarterChips scope="widget" onPick={conv.setDraft} />}
            />
          ) : mode === "lecture" ? (
            <LectureReadinessState status={lectureStatus} />
          ) : (
            <div style={styles.recents}>
              <Link
                href="/student/assistant?new=1"
                onClick={onClose}
                data-testid="assistant-widget-start-lecture"
                style={styles.primaryLink}
              >
                Start with a lecture
              </Link>
              {recents === null ? (
                <p style={styles.muted}>Loading…</p>
              ) : recents.length === 0 ? (
                <p style={styles.muted}>No chats yet — start one from a published lecture.</p>
              ) : (
                <ul data-testid="assistant-widget-recents" style={styles.recentList}>
                  {recents.map((c) => (
                    <li key={c.id} style={styles.recentRow}>
                      <Link
                        href={`/student/assistant/${c.id}`}
                        onClick={onClose}
                        data-testid="assistant-widget-recent"
                        style={styles.recentLink}
                      >
                        <span style={styles.recentTitle}>{c.displayTitle}</span>
                        <span style={styles.recentMeta}>
                          {c.moduleTitle} → {c.sectionTitle}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        <Link
          href="/student/assistant"
          onClick={onClose}
          data-testid="assistant-widget-open-workspace"
          style={styles.footerLink}
        >
          Open full workspace
        </Link>
      </div>
    </>
  );
}

function LectureReadinessState({
  status,
}: {
  status: "opening" | "processing" | "unavailable" | "error" | null;
}) {
  const copy =
    status === "processing"
      ? "This lecture is still being prepared for the assistant."
      : status === "unavailable"
        ? "The assistant isn’t available for this section yet."
        : status === "error"
          ? "Couldn’t open this lecture’s chat — try again."
          : "Opening this lecture’s chat…";
  return (
    <p data-testid="assistant-widget-readiness" role={status === "error" ? "alert" : "status"} style={styles.muted}>
      {copy}
    </p>
  );
}

function LectureContextHeader({
  detail,
  moduleId,
  sectionId,
  onClose,
}: {
  detail: ConversationListItem | null;
  moduleId: string | null;
  sectionId: string | null;
  onClose: () => void;
}) {
  const href =
    detail
      ? `/student/modules/${detail.moduleId}/sections/${detail.attachedSectionId}`
      : moduleId && sectionId
        ? `/student/modules/${moduleId}/sections/${sectionId}`
        : null;

  return (
    <div data-testid="assistant-widget-context-pill" style={styles.contextPill}>
      <span style={styles.contextText}>
        Chatting about:{" "}
        <strong style={styles.contextStrong}>{detail?.sectionTitle ?? "this lecture"}</strong> · Grounded in
        published lecture material
      </span>
      {href ? (
        <Link
          href={href}
          onClick={onClose}
          data-testid="assistant-widget-open-lecture"
          style={styles.contextAction}
        >
          Open lecture
        </Link>
      ) : null}
    </div>
  );
}

const styles = {
  scrim: { background: "rgba(17,24,39,0.28)", inset: 0, position: "fixed", zIndex: 60 },
  panel: {
    background: "#ffffff",
    borderLeft: "1px solid #d7dde8",
    boxShadow: "-8px 0 28px rgba(17,24,39,0.18)",
    display: "flex",
    flexDirection: "column",
    gap: 12,
    height: "100dvh",
    maxWidth: "100vw",
    padding: 16,
    position: "fixed",
    right: 0,
    top: 0,
    width: 420,
    zIndex: 61,
  },
  header: { alignItems: "center", display: "flex", justifyContent: "space-between" },
  heading: { color: "#111827", fontSize: 15, fontWeight: 700, margin: 0 },
  close: {
    background: "none", border: "none", color: "#4b5563", cursor: "pointer", fontSize: 24, lineHeight: 1,
    padding: 4,
  },
  body: { flex: 1, minHeight: 0, overflowY: "auto" },
  contextPill: {
    alignItems: "center", background: "#f5f5f7", borderRadius: 8, display: "flex", gap: 10,
    justifyContent: "space-between", padding: "8px 10px",
  },
  contextText: { color: "#4b5563", fontSize: 12, lineHeight: 1.4 },
  contextStrong: { color: "#111827", fontWeight: 600 },
  contextAction: { color: "#174a63", fontSize: 12, fontWeight: 600, textDecoration: "none", whiteSpace: "nowrap" },
  recents: { display: "grid", gap: 12 },
  primaryLink: {
    background: "#174a63", borderRadius: 6, color: "#ffffff", fontSize: 13, fontWeight: 700,
    padding: "8px 14px", textAlign: "center", textDecoration: "none",
  },
  recentList: { display: "grid", gap: 0, listStyle: "none", margin: 0, padding: 0 },
  recentRow: { borderTop: "1px solid #e5e7eb" },
  recentLink: { color: "inherit", display: "grid", gap: 2, padding: "10px 2px", textDecoration: "none" },
  recentTitle: { color: "#111827", fontSize: 14, fontWeight: 600 },
  recentMeta: { color: "#6b7280", fontSize: 12 },
  footerLink: { color: "#174a63", fontSize: 13, fontWeight: 600, textAlign: "center", textDecoration: "none" },
  muted: { color: "#4b5563", fontSize: 14, fontStyle: "italic", margin: 0 },
} satisfies Record<string, React.CSSProperties>;
