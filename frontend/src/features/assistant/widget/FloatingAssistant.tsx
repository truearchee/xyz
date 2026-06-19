"use client";

/**
 * Persistent floating assistant button on every student page (Stage 8.4). On a lecture page it opens
 * THAT lecture's grounded conversation (the SAME row the inline panel uses — single source of truth via
 * the store); elsewhere it opens a compact drawer (recents + start-with-a-lecture + open-workspace).
 * Deterministic placement: bottom-right + safe-area inset, lifted above any [data-assistant-safe-area]
 * action bar (e.g. a quiz Submit) so it never overlaps it. Student-role only; an SVG icon, never an emoji.
 */

import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { useRole } from "../../../lib/session/SessionProvider";
import { api } from "../../../lib/api/wrapper";
import { useAssistantStore } from "../AssistantStoreProvider";
import { assistantReadinessFromError } from "../readiness";
import { WidgetDrawer } from "./WidgetDrawer";

const LECTURE_PATH = /^\/student\/modules\/([^/]+)\/sections\/([^/]+)/;

export function FloatingAssistant() {
  const role = useRole();
  const pathname = usePathname();
  const store = useAssistantStore();
  const [open, setOpen] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [lectureStatus, setLectureStatus] = useState<"opening" | "processing" | "unavailable" | "error" | null>(null);
  const [lift, setLift] = useState(0);
  const buttonRef = useRef<HTMLButtonElement | null>(null);

  const match = pathname ? LECTURE_PATH.exec(pathname) : null;
  const moduleId = match?.[1] ?? null;
  const sectionId = match?.[2] ?? null;
  const onLecture = Boolean(sectionId);

  useEffect(() => {
    const measure = () => {
      const anchor = document.querySelector<HTMLElement>("[data-assistant-safe-area]");
      if (!anchor) {
        setLift(0);
        return;
      }
      const rect = anchor.getBoundingClientRect();
      const vh = window.innerHeight;
      // Lift above the action bar only while it sits in the bottom band of the viewport.
      setLift(rect.top < vh && rect.bottom > vh - 96 ? Math.max(0, vh - rect.top) + 12 : 0);
    };
    measure();
    window.addEventListener("scroll", measure, true);
    window.addEventListener("resize", measure);
    return () => {
      window.removeEventListener("scroll", measure, true);
      window.removeEventListener("resize", measure);
    };
  }, [pathname]);

  const onToggle = useCallback(async () => {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    setConversationId(null);
    setLectureStatus(null);
    if (onLecture && sectionId) {
      try {
        setLectureStatus("opening");
        const availability = await api.assistant.getAvailability(sectionId);
        if (availability.state !== "ready") {
          setLectureStatus(availability.state === "processing" ? "processing" : "unavailable");
          return;
        }
        setConversationId(await store.ensureOpenForSection(sectionId));
        setLectureStatus(null);
      } catch (caught) {
        const readiness = assistantReadinessFromError(caught);
        setLectureStatus(readiness ?? "error");
        setConversationId(null);
      }
    } else {
      setConversationId(null);
    }
  }, [open, onLecture, sectionId, store]);

  const onClose = useCallback(() => {
    setOpen(false);
    buttonRef.current?.focus();
  }, []);

  if (role !== "student") return null;

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        data-testid="assistant-widget-button"
        aria-label={store.hasAnyPending ? "Open lecture assistant (answer in progress)" : "Open lecture assistant"}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => void onToggle()}
        style={{ ...styles.button, bottom: `calc(16px + env(safe-area-inset-bottom, 0px) + ${lift}px)` }}
      >
        <svg aria-hidden="true" focusable="false" height="24" viewBox="0 0 24 24" width="24">
          <path
            d="M4 5h16a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H9l-4 3v-3H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z"
            fill="currentColor"
          />
        </svg>
        {store.hasAnyPending ? <span aria-hidden="true" data-testid="assistant-widget-pending" style={styles.dot} /> : null}
      </button>
      {open ? (
        <WidgetDrawer
          mode={onLecture ? "lecture" : "recents"}
          conversationId={conversationId}
          lectureStatus={lectureStatus}
          moduleId={moduleId}
          sectionId={sectionId}
          onClose={onClose}
        />
      ) : null}
    </>
  );
}

const styles = {
  button: {
    alignItems: "center",
    background: "#174a63",
    border: "none",
    borderRadius: 9999,
    boxShadow: "0 6px 20px rgba(17,24,39,0.22)",
    color: "#ffffff",
    cursor: "pointer",
    display: "flex",
    height: 56,
    justifyContent: "center",
    position: "fixed",
    right: 16,
    width: 56,
    zIndex: 50,
  },
  dot: {
    background: "#d97706",
    border: "2px solid #ffffff",
    borderRadius: 9999,
    height: 12,
    position: "absolute",
    right: 12,
    top: 12,
    width: 12,
  },
} satisfies Record<string, React.CSSProperties>;
