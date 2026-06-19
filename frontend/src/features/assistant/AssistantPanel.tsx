"use client";

/**
 * Lecture assistant panel (Stage 8.1/8.2, refactored in 8.4 to a thin adapter over the shared store).
 *
 * Keeps the lecture-page-specific concerns — the availability gate (ready/processing/unavailable) and the
 * "Start chat" entry — then renders the shared ConversationView driven by useAssistantConversation. State
 * + polling now live in AssistantStoreProvider, so a message sent here is also visible in the floating
 * widget for the SAME lecture conversation (single source of truth). Behavior + every data-testid are
 * preserved from 8.1/8.2 (scope="assistant"). Styling follows the Stage 4.9 tokenized class system now on
 * main.
 */

import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../../lib/api";
import { ForbiddenError, api } from "../../lib/api/wrapper";
import { useAssistantConversation, useAssistantStore } from "./AssistantStoreProvider";
import { ConversationView } from "./ConversationView";
import { StarterChips } from "./StarterChips";
import {
  assistantReadinessFromError,
  type AssistantReadiness as AvailabilityState,
} from "./readiness";

export function AssistantPanel({ sectionId }: { sectionId: string }) {
  const store = useAssistantStore();
  const [availability, setAvailability] = useState<AvailabilityState | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [opening, setOpening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const conv = useAssistantConversation(conversationId);

  useEffect(() => {
    let mounted = true;
    setAvailability(null);
    setConversationId(null);
    setError(null);
    void (async () => {
      try {
        const res = await api.assistant.getAvailability(sectionId);
        if (!mounted) return;
        setAvailability((res.state as AvailabilityState) ?? "unavailable");
      } catch (caught) {
        if (!mounted) return;
        const readiness = assistantReadinessFromError(caught);
        if (readiness) {
          setAvailability(readiness);
        } else if (caught instanceof ForbiddenError || (caught instanceof ApiError && caught.status === 404)) {
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

  const onStartChat = useCallback(async () => {
    setOpening(true);
    setError(null);
    try {
      const id = await store.ensureOpenForSection(sectionId);
      setConversationId(id);
    } catch (caught) {
      const readiness = assistantReadinessFromError(caught);
      if (readiness) {
        setAvailability(readiness);
      } else if (caught instanceof ForbiddenError || (caught instanceof ApiError && caught.status === 404)) {
        setAvailability("unavailable");
      } else {
        setError("Couldn’t open the chat — try again.");
      }
    } finally {
      setOpening(false);
    }
  }, [sectionId, store]);

  function body() {
    if (error && availability === null) {
      return <p role="alert" className={classes.muted}>{error}</p>;
    }
    if (availability === null) {
      return <p className={classes.muted}>Loading assistant...</p>;
    }
    if (availability === "unavailable") {
      return (
        <p data-testid="assistant-unavailable" role="status" className={classes.muted}>
          The assistant isn’t available for this section yet.
        </p>
      );
    }
    if (availability === "processing") {
      return (
        <p data-testid="assistant-processing" role="status" className={classes.muted}>
          This lecture is still being prepared for the assistant.
        </p>
      );
    }
    if (!conversationId) {
      return (
        <div className={classes.startBlock}>
          <p className={classes.bodyText}>Ask questions about this lecture.</p>
          <button
            type="button"
            data-testid="assistant-start-chat"
            disabled={opening}
            onClick={() => void onStartChat()}
            className={classes.primaryButton}
          >
            {opening ? "Opening..." : "Start chat"}
          </button>
          {error ? <p role="alert" className={classes.muted}>{error}</p> : null}
        </div>
      );
    }
    return (
      <ConversationView
        scope="assistant"
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
        starters={<StarterChips scope="assistant" onPick={conv.setDraft} />}
      />
    );
  }

  return (
    <section aria-label="Lecture assistant" data-testid="assistant-panel" className={classes.block}>
      <h2 className={classes.blockHeading}>Ask the lecture assistant</h2>
      {body()}
    </section>
  );
}

const classes = {
  block: "grid gap-3 rounded-lg border border-border bg-surface p-4",
  blockHeading: "m-0 text-xs font-semibold uppercase text-text",
  startBlock: "grid justify-items-start gap-2.5",
  bodyText: "m-0 text-sm leading-6 text-text",
  muted: "m-0 text-sm italic text-text-muted",
  primaryButton:
    "min-h-9 justify-self-start rounded-full border border-primary bg-primary px-4 text-sm font-semibold text-on-primary hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2",
} as const;
