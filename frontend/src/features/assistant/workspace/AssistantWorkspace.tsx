"use client";

/**
 * The Assistant Workspace list (Stage 8.4) — one place to see and continue every lecture chat. Flat list
 * ordered newest-activity-first (course shown as per-row context, not hard group headers — MVP scale).
 * Hairline rows (App-UI density, not a card grid). Full state triad: skeleton loading, warm empty state
 * with a CTA, inline error with retry, "Load more" for the offset envelope. Built in the inline idiom.
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { type ConversationListItem } from "../../../lib/api";
import { api } from "../../../lib/api/wrapper";
import { useAssistantStore } from "../AssistantStoreProvider";
import { ExamPrepPicker } from "./ExamPrepPicker";
import { HomeworkPicker } from "./HomeworkPicker";
import { LecturePicker } from "./LecturePicker";

const PAGE = 30;

export function AssistantWorkspace() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const store = useAssistantStore();
  const [items, setItems] = useState<ConversationListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState<"loading" | "loaded" | "error">("loading");
  const [loadingMore, setLoadingMore] = useState(false);
  const [picking, setPicking] = useState(searchParams.get("new") === "1");
  // 8.6a/8.6b: mode entries — separate starters so the 8.4 lecture-chat flow (New chat → LecturePicker) is
  // unchanged. Only one picker panel is open at a time.
  const [pickingHomework, setPickingHomework] = useState(false);
  const [pickingExamPrep, setPickingExamPrep] = useState(false);
  const [startingTime, setStartingTime] = useState(false);

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      const page = await api.assistant.listConversations(PAGE, 0);
      setItems(page.items);
      setTotal(page.pagination.total);
      setStatus("loaded");
    } catch {
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const loadMore = useCallback(async () => {
    setLoadingMore(true);
    try {
      const page = await api.assistant.listConversations(PAGE, items.length);
      setItems((prev) => [...prev, ...page.items]);
      setTotal(page.pagination.total);
    } catch {
      // keep what we have; the list error state is reserved for the initial load
    } finally {
      setLoadingMore(false);
    }
  }, [items.length]);

  const openTimeManagement = useCallback(async () => {
    setStartingTime(true);
    setPicking(false);
    setPickingHomework(false);
    setPickingExamPrep(false);
    try {
      const id = await store.ensureOpenForMode("time_management", {});
      router.push(`/student/assistant/${id}`);
    } finally {
      setStartingTime(false);
    }
  }, [router, store]);

  return (
    <section aria-labelledby="assistant-workspace-title" data-testid="assistant-workspace" style={styles.shell}>
      <header style={styles.header}>
        <div>
          <h1 id="assistant-workspace-title" style={styles.title}>
            Assistant
          </h1>
          <p style={styles.subtext}>Your lecture chats.</p>
        </div>
        <div style={styles.headerActions}>
          <button
            type="button"
            data-testid="assistant-new-time-management"
            disabled={startingTime}
            onClick={() => void openTimeManagement()}
            style={styles.secondaryButton}
          >
            {startingTime ? "Opening…" : "Time management"}
          </button>
          <button
            type="button"
            data-testid="assistant-new-examprep"
            onClick={() => {
              setPickingExamPrep((v) => !v);
              setPicking(false);
              setPickingHomework(false);
            }}
            style={styles.secondaryButton}
          >
            {pickingExamPrep ? "Close" : "Exam prep"}
          </button>
          <button
            type="button"
            data-testid="assistant-new-homework"
            onClick={() => {
              setPickingHomework((v) => !v);
              setPicking(false);
              setPickingExamPrep(false);
            }}
            style={styles.secondaryButton}
          >
            {pickingHomework ? "Close" : "Help with homework"}
          </button>
          <button
            type="button"
            data-testid="assistant-new-chat"
            onClick={() => {
              setPicking((v) => !v);
              setPickingHomework(false);
              setPickingExamPrep(false);
            }}
            style={styles.primaryButton}
          >
            {picking ? "Close" : "New chat"}
          </button>
        </div>
      </header>

      {picking ? <LecturePicker onClose={() => setPicking(false)} /> : null}
      {pickingHomework ? <HomeworkPicker onClose={() => setPickingHomework(false)} /> : null}
      {pickingExamPrep ? <ExamPrepPicker onClose={() => setPickingExamPrep(false)} /> : null}

      {status === "loading" ? (
        <ul aria-busy="true" style={styles.list}>
          {[0, 1, 2].map((i) => (
            <li key={i} style={styles.skeletonRow} />
          ))}
        </ul>
      ) : status === "error" ? (
        <div role="alert" style={styles.errorCard}>
          <p style={styles.bodyText}>Couldn’t load your chats.</p>
          <button type="button" onClick={() => void load()} style={styles.secondaryButton}>
            Try again
          </button>
        </div>
      ) : items.length === 0 ? (
        <div data-testid="assistant-workspace-empty" style={styles.empty}>
          <p style={styles.emptyTitle}>No lecture chats yet</p>
          <p style={styles.muted}>
            Open a published lecture or start a workspace mode — it stays here so you can continue later.
          </p>
          <Link href="/student" data-testid="assistant-empty-cta" style={styles.primaryLink}>
            Browse your modules
          </Link>
        </div>
      ) : (
        <>
          <ul data-testid="assistant-conversation-list" style={styles.list}>
            {items.map((c) => (
              <ConversationListRow key={c.id} item={c} />
            ))}
          </ul>
          {items.length < total ? (
            <button
              type="button"
              data-testid="assistant-load-more"
              disabled={loadingMore}
              onClick={() => void loadMore()}
              style={styles.secondaryButton}
            >
              {loadingMore ? "Loading…" : "Load more"}
            </button>
          ) : null}
        </>
      )}
    </section>
  );
}

function ConversationListRow({ item }: { item: ConversationListItem }) {
  return (
    <li style={styles.row}>
      <Link href={`/student/assistant/${item.id}`} data-testid="assistant-conversation-row" style={styles.rowLink}>
        <div style={styles.rowTop}>
          <span style={styles.rowTitle}>{item.displayTitle}</span>
          <span style={styles.rowTime}>{formatRelative(item.lastActivityAt)}</span>
        </div>
        <div style={styles.rowMeta}>
          <span>
            {conversationContext(item)} ·{" "}
            {item.messageCount} {item.messageCount === 1 ? "message" : "messages"}
          </span>
          <span data-testid="assistant-grounded-chip" style={styles.chip}>
            {item.groundingChip}
          </span>
        </div>
        {item.lastMessagePreview ? <p style={styles.rowPreview}>{item.lastMessagePreview}</p> : null}
      </Link>
    </li>
  );
}

function conversationContext(item: ConversationListItem): string {
  if (item.sectionTitle && item.moduleTitle) return `${item.moduleTitle} → ${item.sectionTitle}`;
  if (item.moduleTitle) return item.moduleTitle;
  return "Your deadlines and progress";
}

function formatRelative(iso: string): string {
  const then = new Date(iso).getTime();
  const diff = Date.now() - then;
  const min = Math.round(diff / 60_000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.round(hr / 24);
  if (day < 7) return `${day}d ago`;
  return new Intl.DateTimeFormat("en", { dateStyle: "medium" }).format(new Date(iso));
}

const styles = {
  shell: { display: "grid", gap: 16, margin: "0 auto", maxWidth: 720 },
  header: { alignItems: "start", display: "flex", gap: 12, justifyContent: "space-between" },
  headerActions: { display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "flex-end" },
  title: { color: "#111827", fontSize: 24, lineHeight: 1.2, margin: 0 },
  subtext: { color: "#4b5563", fontSize: 14, margin: "4px 0 0" },
  list: { display: "grid", gap: 0, listStyle: "none", margin: 0, padding: 0 },
  row: { borderTop: "1px solid #e5e7eb" },
  rowLink: { color: "inherit", display: "grid", gap: 4, padding: "14px 4px", textDecoration: "none" },
  rowTop: { alignItems: "baseline", display: "flex", gap: 12, justifyContent: "space-between" },
  rowTitle: { color: "#111827", fontSize: 15, fontWeight: 600 },
  rowTime: { color: "#6b7280", fontSize: 12, whiteSpace: "nowrap" },
  rowMeta: { alignItems: "center", color: "#4b5563", display: "flex", fontSize: 13, gap: 8, justifyContent: "space-between" },
  rowPreview: {
    color: "#4b5563", fontSize: 13, margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
  },
  chip: {
    background: "#f5f5f7", borderRadius: 9999, color: "#4b5563", fontSize: 11, padding: "2px 8px", whiteSpace: "nowrap",
  },
  skeletonRow: { background: "#f5f5f7", borderRadius: 8, height: 56, marginTop: 8 },
  empty: { border: "1px dashed #d7dde8", borderRadius: 8, display: "grid", gap: 8, justifyItems: "start", padding: 24 },
  emptyTitle: { color: "#111827", fontSize: 16, fontWeight: 600, margin: 0 },
  errorCard: { border: "1px solid #f0b4b4", borderRadius: 8, display: "grid", gap: 8, justifyItems: "start", padding: 16 },
  bodyText: { color: "#111827", fontSize: 14, margin: 0 },
  muted: { color: "#4b5563", fontSize: 14, lineHeight: 1.5, margin: 0 },
  primaryButton: {
    background: "#174a63", border: "1px solid #174a63", borderRadius: 6, color: "#ffffff",
    cursor: "pointer", fontSize: 13, fontWeight: 700, minHeight: 34, padding: "0 14px",
  },
  primaryLink: {
    background: "#174a63", borderRadius: 6, color: "#ffffff", fontSize: 13, fontWeight: 700,
    padding: "8px 14px", textDecoration: "none",
  },
  secondaryButton: {
    background: "#ffffff", border: "1px solid #174a63", borderRadius: 6, color: "#174a63",
    cursor: "pointer", fontSize: 13, fontWeight: 700, justifySelf: "start", minHeight: 32, padding: "0 12px",
  },
} satisfies Record<string, React.CSSProperties>;
