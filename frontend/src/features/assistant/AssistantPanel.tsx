"use client";

/**
 * Lecture assistant panel (Stage 8.1). Thin chat surface on the student section page, built in the
 * existing inline-style idiom (the monochrome design system is not in code yet — see
 * knowledge/steps/stage-08/findings-design-doc-reality-gap.md).
 *
 * States: availability (ready / processing / unavailable) → "Start chat" → message list + composer.
 * User vs assistant messages are distinguished by ALIGNMENT + surface tone, never a hue. The pending
 * answer uses a passive "thinking…" state polled with the 4.5d backoff (no hard timeout); a failed
 * answer shows an inline Retry; the student's question is preserved on failure. Enter sends,
 * Shift+Enter inserts a newline. Assistant answers render through the existing SummaryMarkdown.
 *
 * Stage 8.2 adds the backend-set grounding presentation: a neutral "Not from this lecture" label for
 * general answers and a collapsed "Where did this come from?" basis line (server-composed, safe — never
 * chunks/distances/prompts). No streaming (8.3), no conversation-list sidebar (8.4).
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, type MessageRead } from "../../lib/api";
import { ForbiddenError, api } from "../../lib/api/wrapper";
import { SummaryMarkdown } from "../content/student/SummaryMarkdown";

// Reuse the 4.5d backoff (no hard timeout). Chat answers are usually quicker than summaries, so start
// faster; a generous wall-clock ceiling absorbs limiter queueing under a cohort burst.
const POLL_INITIAL_MS = 800;
const POLL_MAX_MS = 8_000;
const POLL_BACKOFF = 1.5;
const POLL_WALLCLOCK_CAP_MS = 4 * 60_000;
const STICK_THRESHOLD_PX = 80;

type AvailabilityState = "ready" | "processing" | "unavailable";

export function AssistantPanel({ sectionId }: { sectionId: string }) {
  const [availability, setAvailability] = useState<AvailabilityState | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageRead[]>([]);
  const [input, setInput] = useState("");
  const [opening, setOpening] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [capped, setCapped] = useState(false);

  const scrollRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const stickToBottom = useRef(true);

  const hasPending = messages.some((m) => m.status === "pending");

  // ── availability ────────────────────────────────────────────────────────────────────────────
  useEffect(() => {
    let mounted = true;
    setAvailability(null);
    setConversationId(null);
    setMessages([]);
    setError(null);
    void (async () => {
      try {
        const res = await api.assistant.getAvailability(sectionId);
        if (!mounted) return;
        setAvailability((res.state as AvailabilityState) ?? "unavailable");
      } catch (caught) {
        if (!mounted) return;
        if (caught instanceof ForbiddenError || (caught instanceof ApiError && caught.status === 404)) {
          setAvailability("unavailable");
        } else {
          setError("Couldn’t load the assistant — refresh to try again.");
        }
      }
    })();
    return () => {
      mounted = false;
    };
  }, [sectionId]);

  const loadMessages = useCallback(async (convId: string) => {
    const list = await api.assistant.listMessages(convId);
    setMessages(list.items);
  }, []);

  const onStartChat = useCallback(async () => {
    setOpening(true);
    setError(null);
    try {
      const conv = await api.assistant.openConversation(sectionId);
      setConversationId(conv.id);
      await loadMessages(conv.id);
      stickToBottom.current = true;
    } catch (caught) {
      if (caught instanceof ForbiddenError || (caught instanceof ApiError && caught.status === 404)) {
        setAvailability("unavailable");
      } else {
        setError("Couldn’t open the chat — try again.");
      }
    } finally {
      setOpening(false);
    }
  }, [sectionId, loadMessages]);

  // ── poll while a turn is generating (4.5d backoff) ────────────────────────────────────────────
  useEffect(() => {
    if (!conversationId || !hasPending) return;
    let mounted = true;
    let timeoutId = 0;
    let delay = POLL_INITIAL_MS;
    let startedAt = 0;
    const tick = async (): Promise<void> => {
      try {
        const list = await api.assistant.listMessages(conversationId);
        if (!mounted) return;
        setMessages(list.items);
        if (!list.items.some((m) => m.status === "pending")) return; // settled
      } catch {
        if (!mounted) return; // transient — keep polling
      }
      if (!mounted) return;
      if (startedAt === 0) startedAt = Date.now();
      else if (Date.now() - startedAt > POLL_WALLCLOCK_CAP_MS) {
        setCapped(true);
        return;
      }
      delay = Math.min(Math.round(delay * POLL_BACKOFF), POLL_MAX_MS);
      timeoutId = window.setTimeout(() => void tick(), delay);
    };
    timeoutId = window.setTimeout(() => void tick(), POLL_INITIAL_MS);
    return () => {
      mounted = false;
      window.clearTimeout(timeoutId);
    };
  }, [conversationId, hasPending]);

  // ── auto-scroll to follow new messages, unless the student scrolled up ────────────────────────
  useEffect(() => {
    const el = scrollRef.current;
    if (el && stickToBottom.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages]);

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < STICK_THRESHOLD_PX;
  }, []);

  const onSend = useCallback(async () => {
    const content = input.trim();
    if (!content || sending || hasPending || !conversationId) return;
    setSending(true);
    setError(null);
    setCapped(false);
    try {
      const key = crypto.randomUUID();
      await api.assistant.send(conversationId, { content, clientIdempotencyKey: key });
      setInput(""); // cleared only on success — a failed send preserves the question (decision 7)
      stickToBottom.current = true;
      await loadMessages(conversationId);
    } catch {
      setError("Couldn’t send your message — try again.");
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  }, [input, sending, hasPending, conversationId, loadMessages]);

  const onRetry = useCallback(
    async (messageId: string) => {
      if (!conversationId) return;
      setError(null);
      setCapped(false);
      try {
        await api.assistant.retry(messageId);
        await loadMessages(conversationId);
      } catch {
        setError("Couldn’t retry — try again.");
      } finally {
        inputRef.current?.focus();
      }
    },
    [conversationId, loadMessages],
  );

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        void onSend();
      }
    },
    [onSend],
  );

  // ── render ────────────────────────────────────────────────────────────────────────────────────
  function body() {
    if (error && availability === null) {
      return <p role="alert" style={styles.muted}>{error}</p>;
    }
    if (availability === null) {
      return <p style={styles.muted}>Loading assistant…</p>;
    }
    if (availability === "unavailable") {
      return (
        <p data-testid="assistant-unavailable" role="status" style={styles.muted}>
          The assistant isn’t available for this section yet.
        </p>
      );
    }
    if (availability === "processing") {
      return (
        <p data-testid="assistant-processing" role="status" style={styles.muted}>
          This lecture is still being prepared for the assistant.
        </p>
      );
    }
    if (!conversationId) {
      return (
        <div style={styles.startBlock}>
          <p style={styles.bodyText}>Ask questions about this lecture.</p>
          <button
            type="button"
            data-testid="assistant-start-chat"
            disabled={opening}
            onClick={() => void onStartChat()}
            style={styles.primaryButton}
          >
            {opening ? "Opening…" : "Start chat"}
          </button>
          {error ? <p role="alert" style={styles.muted}>{error}</p> : null}
        </div>
      );
    }
    return (
      <div style={styles.chat}>
        <div
          aria-label="Conversation"
          aria-live="polite"
          data-testid="assistant-messages"
          onScroll={onScroll}
          ref={scrollRef}
          style={styles.messageList}
        >
          {messages.length === 0 ? (
            <p data-testid="assistant-empty" style={styles.muted}>
              No messages yet — ask your first question below.
            </p>
          ) : (
            messages.map((m) => <MessageBubble key={m.id} message={m} capped={capped} onRetry={onRetry} />)
          )}
        </div>
        <div style={styles.composer}>
          <label htmlFor="assistant-input" style={styles.srOnly}>
            Ask a question about this lecture
          </label>
          <textarea
            id="assistant-input"
            data-testid="assistant-input"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Ask about this lecture…"
            ref={inputRef}
            rows={2}
            style={styles.textarea}
            value={input}
          />
          <button
            type="button"
            data-testid="assistant-send"
            disabled={sending || hasPending || input.trim().length === 0}
            onClick={() => void onSend()}
            style={styles.primaryButton}
          >
            {sending ? "Sending…" : "Send"}
          </button>
        </div>
        {error ? <p role="alert" style={styles.muted}>{error}</p> : null}
      </div>
    );
  }

  return (
    <section aria-label="Lecture assistant" data-testid="assistant-panel" style={styles.block}>
      <h2 style={styles.blockHeading}>Ask the lecture assistant</h2>
      {body()}
    </section>
  );
}

function MessageBubble({
  message,
  capped,
  onRetry,
}: {
  message: MessageRead;
  capped: boolean;
  onRetry: (messageId: string) => void;
}) {
  if (message.role === "user") {
    return (
      <div data-testid="assistant-message-user" style={styles.userRow}>
        <div style={styles.userBubble}>{message.content}</div>
      </div>
    );
  }
  // assistant
  return (
    <div data-state={message.status} data-testid="assistant-message-assistant" style={styles.assistantRow}>
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
              data-testid="assistant-retry"
              onClick={() => onRetry(message.id)}
              style={styles.secondaryButton}
            >
              Retry
            </button>
          </div>
        ) : (
          <AssistantAnswerBody message={message} onRetry={onRetry} />
        )}
      </div>
    </div>
  );
}

// Completed answer (Stage 8.2): the backend-set groundingStatus drives a neutral label + a collapsed,
// safe "Where did this come from?" basis line. The label is text-only / no colour (decision §12); the
// basis exposes only the human answerBasis the server composed — never chunks, distances, or prompts.
function AssistantAnswerBody({
  message,
  onRetry,
}: {
  message: MessageRead;
  onRetry: (messageId: string) => void;
}) {
  const isGeneral = message.groundingStatus === "general_not_from_lecture";
  const isUnavailable = message.groundingStatus === "context_unavailable";
  return (
    <div style={styles.answerBody}>
      {isGeneral ? (
        <p data-testid="assistant-not-from-lecture" style={styles.notFromLecture}>
          Not from this lecture
        </p>
      ) : null}
      {message.content ? (
        <SummaryMarkdown content={message.content} testId={`assistant-answer-${message.id}`} />
      ) : (
        <p style={styles.muted}>No answer.</p>
      )}
      {message.answerBasis ? (
        <details data-testid="assistant-basis" style={styles.basis}>
          <summary style={styles.basisSummary}>Where did this come from?</summary>
          <p data-testid="assistant-basis-text" style={styles.basisText}>
            {message.answerBasis}
          </p>
        </details>
      ) : null}
      {isUnavailable && message.retryable ? (
        <button
          type="button"
          data-testid="assistant-retry"
          onClick={() => onRetry(message.id)}
          style={styles.secondaryButton}
        >
          Retry
        </button>
      ) : null}
    </div>
  );
}

const styles = {
  block: { border: "1px solid #d7dde8", borderRadius: 8, display: "grid", gap: 12, padding: 16 },
  blockHeading: {
    color: "#111827", fontSize: 13, fontWeight: 700, letterSpacing: "0.03em", margin: 0,
    textTransform: "uppercase",
  },
  startBlock: { display: "grid", gap: 10, justifyItems: "start" },
  chat: { display: "grid", gap: 12 },
  messageList: {
    display: "grid", gap: 10, maxHeight: 420, overflowY: "auto", paddingRight: 4,
  },
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
  // Neutral, no colour (decision §12) — distinguishes "general study answer" from a grounded one by text.
  notFromLecture: { color: "#4b5563", fontSize: 12, fontWeight: 600, margin: 0 },
  basis: { fontSize: 12, width: "100%" },
  basisSummary: { color: "#4b5563", cursor: "pointer", fontSize: 12 },
  basisText: { color: "#4b5563", fontSize: 12, lineHeight: 1.4, margin: "4px 0 0 0" },
  bodyText: { color: "#111827", fontSize: 14, lineHeight: 1.5, margin: 0 },
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
