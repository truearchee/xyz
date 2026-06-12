"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

import { cn } from "./cn";

// Owned (NOT React Aria): RAC's Toast is UNSTABLE_ in 1.18, and a frozen public contract should not ride
// an unstable API (ADR-046 amendment). The behavior here is simple and meets §4.2: a polite live region,
// errors do NOT auto-dismiss, every toast is keyboard-dismissible. Renders via the 4.9a #toast-root.

type ToastTone = "info" | "success" | "error";
type ToastItem = { id: number; tone: ToastTone; message: string };
type ToastApi = { show: (tone: ToastTone, message: string) => void };

const ToastContext = createContext<ToastApi | null>(null);
const AUTO_DISMISS_MS = 5000;
let nextId = 0;

const toneClass: Record<ToastTone, string> = {
  info: "border-info bg-info-surface text-info-text",
  success: "border-success bg-success-surface text-success-text",
  error: "border-danger bg-danger-surface text-danger-text",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((t) => t.id !== id));
  }, []);

  const show = useCallback(
    (tone: ToastTone, message: string) => {
      const id = (nextId += 1);
      setToasts((current) => [...current, { id, tone, message }]);
      if (tone !== "error") {
        // §4.2: errors do NOT auto-dismiss; info/success do.
        setTimeout(() => dismiss(id), AUTO_DISMISS_MS);
      }
    },
    [dismiss],
  );

  const api = useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within a ToastProvider");
  return ctx;
}

function ToastViewport({ toasts, onDismiss }: { toasts: ToastItem[]; onDismiss: (id: number) => void }) {
  if (typeof document === "undefined") return null;
  const root = document.getElementById("toast-root") ?? document.body;
  return createPortal(
    <div
      role="region"
      aria-label="Notifications"
      className="pointer-events-none fixed bottom-4 right-4 z-toast flex w-full max-w-sm flex-col gap-2"
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          role={t.tone === "error" ? "alert" : "status"}
          aria-live={t.tone === "error" ? "assertive" : "polite"}
          className={cn(
            "pointer-events-auto flex items-start justify-between gap-3 rounded-md border p-3 text-sm shadow-md",
            toneClass[t.tone],
          )}
        >
          <span>{t.message}</span>
          <button
            type="button"
            onClick={() => onDismiss(t.id)}
            aria-label="Dismiss notification"
            className="shrink-0 rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
          >
            <span aria-hidden="true">✕</span>
          </button>
        </div>
      ))}
    </div>,
    root,
  );
}
