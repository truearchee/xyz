"use client";

/**
 * The shared, presentational chat surface (Stage 8.4) — extracted verbatim-in-behavior from the 8.1/8.2
 * AssistantPanel so the inline lecture panel, the Workspace conversation, and the floating widget all
 * render ONE implementation. State + polling live in the store (useAssistantConversation); this is pure
 * presentation. `scope` namespaces every data-testid ("assistant" for the inline panel preserves the
 * exact IDs the 8.1/8.2 specs assert; "widget"/"workspace" avoid collisions when two views show the same
 * conversation on one page). aria-live="polite" announces assistant answers as they arrive via polling.
 */

import { useCallback, useEffect, useRef, type ReactNode } from "react";

import { type MessageRead } from "../../lib/api";
import { SummaryMarkdown } from "../content/student/SummaryMarkdown";

const STICK_THRESHOLD_PX = 80;

type ConversationViewProps = {
  scope: string;
  messages: MessageRead[];
  loading: boolean;
  hasPending: boolean;
  gone: boolean;
  capped: boolean;
  sending: boolean;
  error: string | null;
  draft: string;
  hasMore: boolean;
  loadingOlder: boolean;
  onSend: (content: string) => void | Promise<void>;
  onRetry: (messageId: string) => void | Promise<void>;
  onLoadOlder: () => void | Promise<void>;
  onDraftChange: (text: string) => void;
  header?: ReactNode;
  starters?: ReactNode;
  placeholder?: string;
  inputLabel?: string;
  emptyHint?: string;
};

export function ConversationView({
  scope,
  messages,
  loading,
  hasPending,
  gone,
  capped,
  sending,
  error,
  draft,
  hasMore,
  loadingOlder,
  onSend,
  onRetry,
  onLoadOlder,
  onDraftChange,
  header,
  starters,
  placeholder = "Ask about this lecture…",
  inputLabel = "Ask a question about this lecture",
  emptyHint = "No messages yet — ask your first question below.",
}: ConversationViewProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const stickToBottom = useRef(true);

  useEffect(() => {
    const el = scrollRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < STICK_THRESHOLD_PX;
  }, []);

  const submit = useCallback(() => {
    const content = draft.trim();
    if (!content || loading || gone || sending || hasPending) return;
    stickToBottom.current = true;
    void onSend(content);
    inputRef.current?.focus();
  }, [draft, loading, gone, sending, hasPending, onSend]);

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        submit();
      }
    },
    [submit],
  );

  return (
    <div style={styles.chat}>
      {header}
      <div
        aria-label="Conversation"
        aria-live="polite"
        data-testid={`${scope}-messages`}
        onScroll={onScroll}
        ref={scrollRef}
        style={styles.messageList}
      >
        {gone ? (
          <p data-testid={`${scope}-gone`} role="status" style={styles.muted}>
            This conversation is no longer available.
          </p>
        ) : loading ? (
          <p data-testid={`${scope}-loading`} role="status" style={styles.muted}>
            Loading conversation…
          </p>
        ) : hasMore ? (
          <button
            type="button"
            data-testid={`${scope}-load-older`}
            disabled={loadingOlder}
            onClick={() => void onLoadOlder()}
            style={styles.loadOlder}
          >
            {loadingOlder ? "Loading…" : "Load older messages"}
          </button>
        ) : null}
        {!gone && !loading && messages.length === 0 ? (
          <p data-testid={`${scope}-empty`} style={styles.muted}>
            {emptyHint}
          </p>
        ) : !gone && !loading ? (
          messages.map((m) => (
            <MessageBubble key={m.id} message={m} scope={scope} capped={capped} onRetry={onRetry} />
          ))
        ) : null}
      </div>
      {!gone && !loading && messages.length === 0 && starters ? <div style={styles.starters}>{starters}</div> : null}
      <div style={styles.composer}>
        <label htmlFor={`${scope}-input`} style={styles.srOnly}>
          {inputLabel}
        </label>
        <textarea
          id={`${scope}-input`}
          data-testid={`${scope}-input`}
          onChange={(e) => onDraftChange(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          ref={inputRef}
          rows={2}
          disabled={loading || gone || sending || hasPending}
          style={styles.textarea}
          value={draft}
        />
        <button
          type="button"
          data-testid={`${scope}-send`}
          disabled={loading || gone || sending || hasPending || draft.trim().length === 0}
          onClick={submit}
          style={styles.primaryButton}
        >
          {sending ? "Sending…" : "Send"}
        </button>
      </div>
      {error ? (
        <p role="alert" style={styles.muted}>
          {error}
        </p>
      ) : null}
    </div>
  );
}

function MessageBubble({
  message,
  scope,
  capped,
  onRetry,
}: {
  message: MessageRead;
  scope: string;
  capped: boolean;
  onRetry: (messageId: string) => void | Promise<void>;
}) {
  if (message.role === "user") {
    return (
      <div data-testid={`${scope}-message-user`} style={styles.userRow}>
        <div style={styles.userBubble}>{message.content}</div>
      </div>
    );
  }
  return (
    <div data-state={message.status} data-testid={`${scope}-message-assistant`} style={styles.assistantRow}>
      <div style={styles.assistantBubble}>
        {message.status === "pending" ? (
          <p role="status" style={styles.muted}>
            {capped ? "Still thinking — this is taking a while." : "Thinking…"}
          </p>
        ) : message.status === "failed" ? (
          <div style={styles.failed}>
            <p role="alert" style={styles.muted}>
              {message.failureMessage ?? "The assistant couldn’t answer that."}
            </p>
            <button
              type="button"
              data-testid={`${scope}-retry`}
              onClick={() => void onRetry(message.id)}
              style={styles.secondaryButton}
            >
              Retry
            </button>
          </div>
        ) : (
          <AssistantAnswerBody message={message} scope={scope} onRetry={onRetry} />
        )}
      </div>
    </div>
  );
}

// Completed answer (Stage 8.2): backend-set groundingStatus drives a neutral label + a collapsed, safe
// "Where did this come from?" basis line. Text-only label (decision §12); basis exposes only the
// server-composed answerBasis — never chunks, distances, or prompts.
function AssistantAnswerBody({
  message,
  scope,
  onRetry,
}: {
  message: MessageRead;
  scope: string;
  onRetry: (messageId: string) => void | Promise<void>;
}) {
  const isGeneral = message.groundingStatus === "general_not_from_lecture";
  const isUnavailable = message.groundingStatus === "context_unavailable";
  return (
    <div style={styles.answerBody}>
      {isGeneral ? (
        <p data-testid={`${scope}-not-from-lecture`} style={styles.notFromLecture}>
          Not from this lecture
        </p>
      ) : null}
      {message.content ? (
        <SummaryMarkdown content={message.content} testId={`${scope}-answer-${message.id}`} />
      ) : (
        <p style={styles.muted}>No answer.</p>
      )}
      {message.answerBasis ? (
        <details data-testid={`${scope}-basis`} style={styles.basis}>
          <summary style={styles.basisSummary}>Where did this come from?</summary>
          <p data-testid={`${scope}-basis-text`} style={styles.basisText}>
            {message.answerBasis}
          </p>
        </details>
      ) : null}
      {isUnavailable && message.retryable ? (
        <button
          type="button"
          data-testid={`${scope}-retry`}
          onClick={() => void onRetry(message.id)}
          style={styles.secondaryButton}
        >
          Retry
        </button>
      ) : null}
    </div>
  );
}

const styles = {
  chat: { display: "grid", gap: 12 },
  messageList: { display: "grid", gap: 10, maxHeight: 420, overflowY: "auto", paddingRight: 4 },
  loadOlder: {
    background: "#ffffff", border: "1px solid #d7dde8", borderRadius: 6, color: "#4b5563",
    cursor: "pointer", fontSize: 12, justifySelf: "center", minHeight: 28, padding: "0 12px",
  },
  starters: { display: "grid", gap: 8 },
  userRow: { display: "flex", justifyContent: "flex-end" },
  assistantRow: { display: "flex", justifyContent: "flex-start" },
  userBubble: {
    background: "#eef1f5", borderRadius: 12, color: "#111827", fontSize: 14, lineHeight: 1.5,
    maxWidth: "85%", padding: "8px 12px", whiteSpace: "pre-wrap",
  },
  assistantBubble: {
    background: "#ffffff", border: "1px solid #d7dde8", borderRadius: 12, color: "#111827",
    fontSize: 14, lineHeight: 1.5, maxWidth: "90%", padding: "8px 12px",
  },
  composer: { display: "grid", gap: 8 },
  textarea: {
    border: "1px solid #b8c0cc", borderRadius: 8, color: "#111827", fontFamily: "inherit",
    fontSize: 14, lineHeight: 1.5, padding: "8px 10px", resize: "vertical", width: "100%",
  },
  failed: { display: "grid", gap: 8, justifyItems: "start" },
  answerBody: { display: "grid", gap: 6, justifyItems: "start" },
  notFromLecture: { color: "#4b5563", fontSize: 12, fontWeight: 600, margin: 0 },
  basis: { fontSize: 12, width: "100%" },
  basisSummary: { color: "#4b5563", cursor: "pointer", fontSize: 12 },
  basisText: { color: "#4b5563", fontSize: 12, lineHeight: 1.4, margin: "4px 0 0 0" },
  muted: { color: "#4b5563", fontSize: 14, fontStyle: "italic", margin: 0 },
  primaryButton: {
    background: "#174a63", border: "1px solid #174a63", borderRadius: 6, color: "#ffffff",
    cursor: "pointer", fontSize: 13, fontWeight: 700, justifySelf: "start", minHeight: 34, padding: "0 14px",
  },
  secondaryButton: {
    background: "#ffffff", border: "1px solid #174a63", borderRadius: 6, color: "#174a63",
    cursor: "pointer", fontSize: 13, fontWeight: 700, minHeight: 30, padding: "0 12px",
  },
  srOnly: {
    border: 0, clip: "rect(0 0 0 0)", height: 1, margin: -1, overflow: "hidden", padding: 0,
    position: "absolute", whiteSpace: "nowrap", width: 1,
  },
} satisfies Record<string, React.CSSProperties>;
