"use client";

/**
 * Single source of truth for assistant conversations across student surfaces (Stage 8.4).
 *
 * Mounted once in the student layout so the inline lecture panel, the floating widget, and the
 * Workspace all read/write the SAME per-conversation state. This is what makes the browser gate's
 * "a message sent in one view is visible in the other" true without duplicate polling: one store, one
 * poll loop over every conversation that currently has a pending turn (the 4.5d backoff, no hard
 * timeout). Drafts persist per conversation for the page session; a soft-deleted conversation is dropped
 * (and its section mapping cleared) so reopening the lecture starts a FRESH conversation (invariant A/E).
 *
 * Built in the existing inline-style idiom (no Tailwind / monochrome system yet — findings-design-doc-
 * reality-gap). Streaming-ready: messages still "fill in" via polling, so 8.3 SSE drops in unchanged.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { ApiError, type MessageRead } from "../../lib/api";
import { api } from "../../lib/api/wrapper";
import { decideSendAttempt, hasPendingAssistantTurn, type SendAttempt } from "./sendIdempotency";

// Reuse the 4.5d backoff (no hard timeout); chat turns are usually quick, a generous ceiling absorbs
// limiter queueing under a cohort burst.
const POLL_INITIAL_MS = 800;
const POLL_MAX_MS = 8_000;
const POLL_BACKOFF = 1.5;
const POLL_WALLCLOCK_CAP_MS = 4 * 60_000;

export type ConversationState = {
  messages: MessageRead[];
  nextCursor: string | null;
  hasMore: boolean;
  loading: boolean;
  loadingOlder: boolean;
  sending: boolean;
  error: string | null;
  gone: boolean;
  capped: boolean;
  draft: string;
};

const EMPTY: ConversationState = {
  messages: [],
  nextCursor: null,
  hasMore: false,
  loading: true,
  loadingOlder: false,
  sending: false,
  error: null,
  gone: false,
  capped: false,
  draft: "",
};

type StoreValue = {
  get: (conversationId: string) => ConversationState;
  hasAnyPending: boolean;
  ensureOpenForSection: (sectionId: string) => Promise<string>;
  ensureOpenForMode: (
    conversationKind: string,
    opts: { moduleId?: string; sectionId?: string; assessmentScopeId?: string },
  ) => Promise<string>;
  loadInitial: (conversationId: string) => Promise<void>;
  loadOlder: (conversationId: string) => Promise<void>;
  send: (conversationId: string, content: string) => Promise<void>;
  retry: (conversationId: string, messageId: string) => Promise<void>;
  setDraft: (conversationId: string, text: string) => void;
  markDeleted: (conversationId: string) => void;
};

const StoreContext = createContext<StoreValue | null>(null);

export function AssistantStoreProvider({ children }: { children: ReactNode }) {
  const [convs, setConvs] = useState<Record<string, ConversationState>>({});
  const convsRef = useRef<Record<string, ConversationState>>({});
  const sectionToConv = useRef<Record<string, string>>({});
  const openInFlight = useRef<Record<string, Promise<string>>>({});
  const sendAttempts = useRef<Record<string, SendAttempt>>({});
  const sendInFlight = useRef<Record<string, Promise<void>>>({});
  const deletedConversationIds = useRef<Set<string>>(new Set());

  useEffect(() => {
    convsRef.current = convs;
  }, [convs]);

  const patch = useCallback((id: string, p: Partial<ConversationState>) => {
    if (deletedConversationIds.current.has(id)) return;
    setConvs((prev) => ({ ...prev, [id]: { ...(prev[id] ?? EMPTY), ...p } }));
  }, []);

  const clearConversationRefs = useCallback((id: string) => {
    for (const [sectionId, convId] of Object.entries(sectionToConv.current)) {
      if (convId === id) delete sectionToConv.current[sectionId];
    }
    delete sendAttempts.current[id];
    delete sendInFlight.current[id];
  }, []);

  const markGone = useCallback(
    (id: string) => {
      deletedConversationIds.current.add(id);
      clearConversationRefs(id);
      setConvs((prev) => ({
        ...prev,
        [id]: {
          ...EMPTY,
          loading: false,
          gone: true,
          error: null,
        },
      }));
    },
    [clearConversationRefs],
  );

  const fetchNewest = useCallback(
    async (id: string, opts: { silent?: boolean } = {}) => {
      if (!opts.silent) patch(id, { loading: true, error: null });
      try {
        const page = await api.assistant.listMessages(id); // newest page, oldest→newest within page
        patch(id, {
          messages: page.items,
          nextCursor: page.nextCursor ?? null,
          hasMore: page.hasMore ?? false,
          loading: false,
        });
      } catch (caught) {
        if (caught instanceof ApiError && caught.status === 404) {
          markGone(id);
          return;
        }
        throw caught;
      }
    },
    [markGone, patch],
  );

  const loadInitial = useCallback(
    async (id: string) => {
      try {
        await fetchNewest(id);
      } catch {
        patch(id, { loading: false, error: "Couldn’t load this conversation — try again." });
      }
    },
    [fetchNewest, patch],
  );

  const ensureOpenForSection = useCallback(
    async (sectionId: string): Promise<string> => {
      const existing = sectionToConv.current[sectionId];
      if (existing) return existing;
      const pending = openInFlight.current[sectionId];
      if (pending) return pending;
      const promise = (async () => {
        const conv = await api.assistant.openConversation(sectionId); // race-safe get-or-create
        deletedConversationIds.current.delete(conv.id);
        sectionToConv.current[sectionId] = conv.id;
        setConvs((prev) => (prev[conv.id] ? prev : { ...prev, [conv.id]: { ...EMPTY } }));
        await loadInitial(conv.id);
        return conv.id;
      })();
      openInFlight.current[sectionId] = promise;
      try {
        return await promise;
      } finally {
        delete openInFlight.current[sectionId];
      }
    },
    [loadInitial],
  );

  // 8.6a: open (or resume) a MODE conversation — homework binds a module (optionally a section). The
  // backend is idempotent (resume-or-create on the natural key), so a double-click never duplicates; the
  // in-flight guard (keyed on kind+module+section) just avoids a double navigation. Mirrors
  // ensureOpenForSection; send/poll/markGone are mode-agnostic and reused.
  const ensureOpenForMode = useCallback(
    async (
      conversationKind: string,
      opts: { moduleId?: string; sectionId?: string; assessmentScopeId?: string },
    ): Promise<string> => {
      const key = `mode:${conversationKind}:${opts.moduleId ?? ""}:${opts.sectionId ?? ""}:${opts.assessmentScopeId ?? ""}`;
      const pending = openInFlight.current[key];
      if (pending) return pending;
      const promise = (async () => {
        const conv = await api.assistant.createConversation({
          conversationKind,
          moduleId: opts.moduleId ?? null,
          sectionId: opts.sectionId ?? null,
          assessmentScopeId: opts.assessmentScopeId ?? null,
        });
        deletedConversationIds.current.delete(conv.id);
        setConvs((prev) => (prev[conv.id] ? prev : { ...prev, [conv.id]: { ...EMPTY } }));
        await loadInitial(conv.id);
        return conv.id;
      })();
      openInFlight.current[key] = promise;
      try {
        return await promise;
      } finally {
        delete openInFlight.current[key];
      }
    },
    [loadInitial],
  );

  const loadOlder = useCallback(
    async (id: string) => {
      const cur = convs[id];
      if (!cur || !cur.hasMore || !cur.nextCursor || cur.loadingOlder) return;
      patch(id, { loadingOlder: true });
      try {
        const page = await api.assistant.listMessages(id, cur.nextCursor);
        setConvs((prev) => {
          const c = prev[id] ?? EMPTY;
          return {
            ...prev,
            [id]: {
              ...c,
              messages: [...page.items, ...c.messages], // prepend older
              nextCursor: page.nextCursor ?? null,
              hasMore: page.hasMore ?? false,
              loadingOlder: false,
            },
          };
        });
      } catch (caught) {
        if (caught instanceof ApiError && caught.status === 404) {
          markGone(id);
          return;
        }
        patch(id, { loadingOlder: false });
      }
    },
    [convs, markGone, patch],
  );

  const send = useCallback(
    async (id: string, content: string) => {
      const inFlight = sendInFlight.current[id];
      if (inFlight) return inFlight;

      const current = convsRef.current[id] ?? EMPTY;
      const decision = decideSendAttempt({
        content,
        sending: current.sending,
        hasPending: hasPendingAssistantTurn(current.messages),
        existingAttempt: sendAttempts.current[id],
        createKey: () => crypto.randomUUID(),
      });
      if (decision.action === "reject") return;

      const { content: trimmed, key } = decision.attempt;
      sendAttempts.current[id] = decision.attempt;
      patch(id, { sending: true, error: null, capped: false });
      const promise = (async () => {
        try {
          await api.assistant.send(id, { content: trimmed, clientIdempotencyKey: key });
          delete sendAttempts.current[id];
          patch(id, { draft: "" }); // cleared on success only — a failed send preserves the question
          try {
            await fetchNewest(id, { silent: true });
          } catch {
            patch(id, { error: "Sent, but couldn’t refresh the conversation — reload to update." });
          }
        } catch (caught) {
          if (caught instanceof ApiError && caught.status === 404) {
            markGone(id);
            return;
          }
          patch(id, { error: "Couldn’t send your message — try again." });
        } finally {
          delete sendInFlight.current[id];
          patch(id, { sending: false });
        }
      })();
      sendInFlight.current[id] = promise;
      return promise;
    },
    [markGone, patch, fetchNewest],
  );

  const retry = useCallback(
    async (id: string, messageId: string) => {
      patch(id, { error: null, capped: false });
      try {
        await api.assistant.retry(messageId);
        await fetchNewest(id, { silent: true });
      } catch (caught) {
        if (caught instanceof ApiError && caught.status === 404) {
          markGone(id);
          return;
        }
        patch(id, { error: "Couldn’t retry — try again." });
      }
    },
    [markGone, patch, fetchNewest],
  );

  const setDraft = useCallback((id: string, text: string) => {
    const attempt = sendAttempts.current[id];
    if (attempt && text.trim() !== attempt.content) {
      delete sendAttempts.current[id];
    }
    setConvs((prev) => ({ ...prev, [id]: { ...(prev[id] ?? EMPTY), draft: text } }));
  }, []);

  const markDeleted = useCallback((id: string) => {
    deletedConversationIds.current.add(id);
    clearConversationRefs(id);
    setConvs((prev) => ({
      ...prev,
      [id]: {
        ...EMPTY,
        loading: false,
        gone: true,
      },
    }));
  }, [clearConversationRefs]);

  // One poll loop over every conversation with a pending turn (poll only while pending; stop on settle).
  const pendingKey = useMemo(
    () =>
      Object.entries(convs)
        .filter(([, c]) => hasPendingAssistantTurn(c.messages))
        .map(([id]) => id)
        .sort()
        .join(","),
    [convs],
  );
  useEffect(() => {
    if (!pendingKey) return;
    const ids = pendingKey.split(",");
    let alive = true;
    let delay = POLL_INITIAL_MS;
    let startedAt = 0;
    let timeout = 0;
    const tick = async (): Promise<void> => {
      await Promise.all(ids.map((id) => fetchNewest(id, { silent: true }).catch(() => undefined)));
      if (!alive) return;
      if (startedAt === 0) startedAt = Date.now();
      else if (Date.now() - startedAt > POLL_WALLCLOCK_CAP_MS) {
        ids.forEach((id) => patch(id, { capped: true }));
        return;
      }
      delay = Math.min(Math.round(delay * POLL_BACKOFF), POLL_MAX_MS);
      timeout = window.setTimeout(() => void tick(), delay);
    };
    timeout = window.setTimeout(() => void tick(), POLL_INITIAL_MS);
    return () => {
      alive = false;
      window.clearTimeout(timeout);
    };
  }, [pendingKey, fetchNewest, patch]);

  const value = useMemo<StoreValue>(
    () => ({
      get: (id) => convs[id] ?? EMPTY,
      hasAnyPending: pendingKey.length > 0,
      ensureOpenForSection,
      ensureOpenForMode,
      loadInitial,
      loadOlder,
      send,
      retry,
      setDraft,
      markDeleted,
    }),
    [convs, pendingKey, ensureOpenForSection, ensureOpenForMode, loadInitial, loadOlder, send, retry, setDraft, markDeleted],
  );

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useAssistantStore(): StoreValue {
  const value = useContext(StoreContext);
  if (value === null) {
    throw new Error("useAssistantStore must be used within AssistantStoreProvider");
  }
  return value;
}

/** Per-conversation selector + bound actions (the home of the chat surface's behavior). */
export function useAssistantConversation(conversationId: string | null) {
  const store = useAssistantStore();
  const state = conversationId ? store.get(conversationId) : EMPTY;
  return {
    ...state,
    hasPending: hasPendingAssistantTurn(state.messages),
    send: (content: string) => (conversationId ? store.send(conversationId, content) : Promise.resolve()),
    retry: (messageId: string) =>
      conversationId ? store.retry(conversationId, messageId) : Promise.resolve(),
    loadOlder: () => (conversationId ? store.loadOlder(conversationId) : Promise.resolve()),
    loadInitial: () => (conversationId ? store.loadInitial(conversationId) : Promise.resolve()),
    setDraft: (text: string) => {
      if (conversationId) store.setDraft(conversationId, text);
    },
  };
}
