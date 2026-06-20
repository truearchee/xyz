"use client";

/**
 * A single Workspace conversation (Stage 8.4). Loads its messages from the shared store and its metadata
 * (lecture/module titles) from GET /conversations/{id} — so a deep link / refresh shows the context pill
 * and 404s cleanly if access was revoked or the chat was deleted (invariant C/E → "no longer available").
 * Header carries the persistent context pill + "Open lecture", inline rename (manual title, never
 * AI-generated), and delete-with-confirm using the EXACT retention copy ("permanently delete" forbidden).
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ApiError, type ConversationListItem } from "../../../lib/api";
import { ForbiddenError, api } from "../../../lib/api/wrapper";
import { useAssistantConversation, useAssistantStore } from "../AssistantStoreProvider";
import { ConversationView } from "../ConversationView";
import { ExamPrepStarters } from "../ExamPrepStarters";
import { HomeworkStarters } from "../HomeworkStarters";
import { StarterChips } from "../StarterChips";

// 8.6b: the exam-prep quiz pointer is sourced from the quiz domain (the assistant never generates a quiz).
type QuizPointer = { state: "available" | "preparing" | "unavailable" } | null;

type DetailState = "loading" | "loaded" | "gone" | "error";

export function AssistantWorkspaceConversation({ conversationId }: { conversationId: string }) {
  const router = useRouter();
  const store = useAssistantStore();
  // Depend on these STABLE (useCallback) actions, never on the whole `store` value — the value object
  // re-references on every conversation update, so depending on it in the mount effect would re-run the
  // effect in a loop (loadInitial mutates the store → store ref changes → effect re-runs), never letting
  // detailState settle (e.g. "gone") and hammering the backend.
  const { loadInitial: loadMessages, markDeleted } = store;
  const conv = useAssistantConversation(conversationId);
  const [detail, setDetail] = useState<ConversationListItem | null>(null);
  const [detailState, setDetailState] = useState<DetailState>("loading");

  const [renaming, setRenaming] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [quizPointer, setQuizPointer] = useState<QuizPointer>(null);

  // 8.6b: for an exam-prep conversation, resolve the bound scope's quiz availability from the EXISTING quiz
  // endpoint (the assistant never generates a quiz) → the CTA state on the conversation surface.
  const examScopeId = detail?.conversationKind === "exam_prep" ? detail.assessmentScopeId : null;
  const examModuleId = detail?.conversationKind === "exam_prep" ? detail.moduleId : null;
  useEffect(() => {
    if (!examScopeId || !examModuleId) {
      setQuizPointer(null);
      return;
    }
    let mounted = true;
    void (async () => {
      try {
        const scopes = await api.quiz.listExamPrepScopes(examModuleId);
        const scope = scopes.find((s) => s.id === examScopeId);
        if (!mounted) return;
        if (!scope) setQuizPointer(null);
        else if (scope.available) setQuizPointer({ state: "available" });
        else if (scope.reasonCode === "processing") setQuizPointer({ state: "preparing" });
        else setQuizPointer({ state: "unavailable" });
      } catch {
        if (mounted) setQuizPointer(null);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [examScopeId, examModuleId]);

  useEffect(() => {
    let mounted = true;
    setDetailState("loading");
    setDetail(null);
    void loadMessages(conversationId);
    void (async () => {
      try {
        const d = await api.assistant.getConversation(conversationId);
        if (!mounted) return;
        setDetail(d);
        setDetailState("loaded");
      } catch (caught) {
        if (!mounted) return;
        if (caught instanceof ForbiddenError || (caught instanceof ApiError && caught.status === 404)) {
          setDetailState("gone");
        } else {
          setDetailState("error");
        }
      }
    })();
    return () => {
      mounted = false;
    };
  }, [conversationId, loadMessages]);

  const startRename = useCallback(() => {
    setTitleDraft(detail?.displayTitle ?? "");
    setRenaming(true);
    setActionError(null);
  }, [detail]);

  const saveRename = useCallback(async () => {
    const next = titleDraft.trim();
    if (!next) {
      setRenaming(false);
      return;
    }
    try {
      const updated = await api.assistant.rename(conversationId, { title: next });
      setDetail((prev) => (prev ? { ...prev, displayTitle: updated.title ?? prev.displayTitle } : prev));
      setRenaming(false);
    } catch {
      setActionError("Couldn’t rename — try again.");
    }
  }, [conversationId, titleDraft]);

  const confirmDelete = useCallback(async () => {
    try {
      await api.assistant.deleteConversation(conversationId);
      markDeleted(conversationId);
      router.push("/student/assistant");
    } catch {
      setActionError("Couldn’t remove — try again.");
    }
  }, [conversationId, markDeleted, router]);

  if (detailState === "gone") {
    return (
      <section data-testid="assistant-conversation-gone" style={styles.shell}>
        <p style={styles.bodyText}>This conversation is no longer available.</p>
        <Link href="/student/assistant" style={styles.backLink}>
          ← Back to your chats
        </Link>
      </section>
    );
  }

  return (
    <section aria-label="Conversation" data-testid="assistant-workspace-conversation" style={styles.shell}>
      <div style={styles.topBar}>
        <Link href="/student/assistant" data-testid="assistant-back" style={styles.backLink}>
          ← Chats
        </Link>
        <div style={styles.actions}>
          <button type="button" data-testid="assistant-rename" onClick={startRename} style={styles.linkButton}>
            Rename
          </button>
          <button
            type="button"
            data-testid="assistant-delete"
            onClick={() => {
              setConfirmingDelete(true);
              setActionError(null);
            }}
            style={styles.linkButtonDanger}
          >
            Delete
          </button>
        </div>
      </div>

      {detailState === "loaded" && detail && !renaming ? (
        <div style={styles.titleRow}>
          <h2 data-testid="assistant-conversation-title" style={styles.convTitle}>{detail.displayTitle}</h2>
          {/* 8.6a: the mode shown as a non-editable LABEL (never a selector — kind is immutable). */}
          <span data-testid="assistant-mode-label" style={styles.modeLabel}>{detail.groundingChip}</span>
        </div>
      ) : null}

      {detailState === "loaded" && detail ? (
        detail.conversationKind === "exam_prep" ? (
          <div data-testid="assistant-context-pill" style={styles.pill}>
            <span style={styles.pillText}>
              Exam prep ·{" "}
              <strong style={styles.pillStrong}>{detail.assessmentScopeName ?? detail.moduleTitle}</strong>
              {detail.coveredWeeks && detail.coveredWeeks.length ? (
                <> · weeks {detail.coveredWeeks.join(", ")}</>
              ) : null}{" "}
              · Grounded in the covered weeks’ material
            </span>
            {quizPointer?.state === "available" ? (
              <Link
                href={`/student/modules/${detail.moduleId}`}
                data-testid="assistant-examprep-quiz-cta"
                style={styles.pillAction}
              >
                Practice with the exam-prep quiz
              </Link>
            ) : quizPointer?.state === "preparing" ? (
              <span data-testid="assistant-examprep-quiz-state" style={styles.pillMutedAction}>
                Practice quiz is being prepared
              </span>
            ) : quizPointer?.state === "unavailable" ? (
              <span data-testid="assistant-examprep-quiz-state" style={styles.pillMutedAction}>
                Practice quiz not available yet
              </span>
            ) : null}
          </div>
        ) : detail.conversationKind === "homework_help" ? (
          <div data-testid="assistant-context-pill" style={styles.pill}>
            <span style={styles.pillText}>
              Homework help ·{" "}
              {detail.sectionTitle ? (
                <>
                  Focused on <strong style={styles.pillStrong}>{detail.sectionTitle}</strong>
                </>
              ) : (
                <>
                  Across <strong style={styles.pillStrong}>{detail.moduleTitle}</strong>
                </>
              )}{" "}
              · Hints and coaching, never the final answer
            </span>
            {detail.attachedSectionId ? (
              <Link
                href={`/student/modules/${detail.moduleId}/sections/${detail.attachedSectionId}`}
                data-testid="assistant-open-lecture"
                style={styles.pillAction}
              >
                Open lecture
              </Link>
            ) : null}
          </div>
        ) : (
          <div data-testid="assistant-context-pill" style={styles.pill}>
            <span style={styles.pillText}>
              Chatting about: <strong style={styles.pillStrong}>{detail.sectionTitle}</strong> · Grounded in
              published lecture material
            </span>
            <Link
              href={`/student/modules/${detail.moduleId}/sections/${detail.attachedSectionId}`}
              data-testid="assistant-open-lecture"
              style={styles.pillAction}
            >
              Open lecture
            </Link>
          </div>
        )
      ) : detailState === "loading" ? (
        <p style={styles.muted}>Loading conversation…</p>
      ) : null}

      {renaming ? (
        <div style={styles.renameRow}>
          <label htmlFor="assistant-rename-input" style={styles.srOnly}>
            Conversation title
          </label>
          <input
            id="assistant-rename-input"
            data-testid="assistant-rename-input"
            autoFocus
            maxLength={120}
            onChange={(e) => setTitleDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void saveRename();
              if (e.key === "Escape") setRenaming(false);
            }}
            style={styles.renameInput}
            value={titleDraft}
          />
          <button type="button" data-testid="assistant-rename-save" onClick={() => void saveRename()} style={styles.primaryButton}>
            Save
          </button>
          <button type="button" onClick={() => setRenaming(false)} style={styles.secondaryButton}>
            Cancel
          </button>
        </div>
      ) : null}

      {confirmingDelete ? (
        <div data-testid="assistant-delete-confirm" role="alertdialog" aria-label="Remove conversation" style={styles.confirm}>
          <p style={styles.bodyText}>
            Remove this conversation from your chat list? (It is hidden from you; this is not a permanent
            data purge.)
          </p>
          <div style={styles.actions}>
            <button type="button" data-testid="assistant-delete-cancel" onClick={() => setConfirmingDelete(false)} style={styles.secondaryButton}>
              Cancel
            </button>
            <button type="button" data-testid="assistant-delete-remove" onClick={() => void confirmDelete()} style={styles.dangerButton}>
              Remove
            </button>
          </div>
        </div>
      ) : null}

      {actionError ? (
        <p role="alert" style={styles.muted}>
          {actionError}
        </p>
      ) : null}

      <ConversationView
        scope="workspace"
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
        conversationId={conversationId}
        saveSectionId={detail?.attachedSectionId ?? null}
        starters={
          detail?.conversationKind === "exam_prep" ? (
            <ExamPrepStarters scope="workspace" onPick={conv.setDraft} />
          ) : detail?.conversationKind === "homework_help" ? (
            <HomeworkStarters scope="workspace" onPick={conv.setDraft} />
          ) : (
            <StarterChips scope="workspace" onPick={conv.setDraft} />
          )
        }
      />
    </section>
  );
}

const styles = {
  shell: { display: "grid", gap: 12, margin: "0 auto", maxWidth: 720 },
  topBar: { alignItems: "center", display: "flex", justifyContent: "space-between" },
  titleRow: { alignItems: "baseline", display: "flex", flexWrap: "wrap", gap: 8 },
  convTitle: { color: "#111827", fontSize: 18, fontWeight: 600, lineHeight: 1.3, margin: 0 },
  modeLabel: {
    background: "#f5f5f7", borderRadius: 9999, color: "#4b5563", fontSize: 11, fontWeight: 600,
    padding: "2px 8px", whiteSpace: "nowrap",
  },
  actions: { display: "flex", gap: 8 },
  backLink: { color: "#174a63", fontSize: 14, fontWeight: 600, textDecoration: "none" },
  linkButton: { background: "none", border: "none", color: "#174a63", cursor: "pointer", fontSize: 13, fontWeight: 600, padding: 0 },
  linkButtonDanger: { background: "none", border: "none", color: "#b91c1c", cursor: "pointer", fontSize: 13, fontWeight: 600, padding: 0 },
  pill: {
    alignItems: "center", background: "#f5f5f7", borderRadius: 8, display: "flex", gap: 12,
    justifyContent: "space-between", padding: "8px 12px",
  },
  pillText: { color: "#4b5563", fontSize: 13, lineHeight: 1.4 },
  pillStrong: { color: "#111827", fontWeight: 600 },
  pillAction: { color: "#174a63", fontSize: 13, fontWeight: 600, textDecoration: "none", whiteSpace: "nowrap" },
  pillMutedAction: { color: "#6b7280", fontSize: 13, fontStyle: "italic", whiteSpace: "nowrap" },
  renameRow: { alignItems: "center", display: "flex", flexWrap: "wrap", gap: 8 },
  renameInput: {
    border: "1px solid #b8c0cc", borderRadius: 6, color: "#111827", flex: 1, fontSize: 14, minWidth: 200, padding: "6px 10px",
  },
  confirm: { border: "1px solid #d7dde8", borderRadius: 8, display: "grid", gap: 8, padding: 12 },
  bodyText: { color: "#111827", fontSize: 14, lineHeight: 1.5, margin: 0 },
  muted: { color: "#4b5563", fontSize: 14, fontStyle: "italic", margin: 0 },
  primaryButton: {
    background: "#174a63", border: "1px solid #174a63", borderRadius: 6, color: "#ffffff",
    cursor: "pointer", fontSize: 13, fontWeight: 700, minHeight: 32, padding: "0 12px",
  },
  secondaryButton: {
    background: "#ffffff", border: "1px solid #174a63", borderRadius: 6, color: "#174a63",
    cursor: "pointer", fontSize: 13, fontWeight: 700, minHeight: 32, padding: "0 12px",
  },
  dangerButton: {
    background: "#b91c1c", border: "1px solid #b91c1c", borderRadius: 6, color: "#ffffff",
    cursor: "pointer", fontSize: 13, fontWeight: 700, minHeight: 32, padding: "0 12px",
  },
  srOnly: {
    border: 0, clip: "rect(0 0 0 0)", height: 1, margin: -1, overflow: "hidden", padding: 0,
    position: "absolute", whiteSpace: "nowrap", width: 1,
  },
} satisfies Record<string, React.CSSProperties>;
