"use client";

import type { ReactNode } from "react";
import { Dialog, Heading, Modal as AriaModal, ModalOverlay } from "react-aria-components";

// Built on React Aria Components (ADR-046): focus trap, Esc-to-close, focus restoration to the trigger,
// and role=dialog + labelling are handled by the library; we supply only token styling. `confirm` uses
// role=alertdialog for destructive confirmations. React Aria manages the overlay portal (layered via the
// z-modal token); the 4.9a #modal-root anchor is retained for any manual (non-RA) portal need.
type ModalProps = {
  isOpen: boolean;
  onOpenChange: (isOpen: boolean) => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  variant?: "default" | "confirm";
};

export function Modal({ isOpen, onOpenChange, title, children, footer, variant = "default" }: ModalProps) {
  return (
    <ModalOverlay
      isOpen={isOpen}
      onOpenChange={onOpenChange}
      isDismissable
      className="fixed inset-0 z-modal flex items-center justify-center bg-overlay p-4"
    >
      <AriaModal className="w-full max-w-lg rounded-xl bg-surface-raised shadow-lg outline-none">
        <Dialog role={variant === "confirm" ? "alertdialog" : "dialog"} className="outline-none">
          <div className="flex flex-col gap-4 p-5">
            <Heading slot="title" className="font-display text-lg font-semibold text-text">
              {title}
            </Heading>
            <div className="text-sm text-text">{children}</div>
            {footer ? <div className="flex justify-end gap-2">{footer}</div> : null}
          </div>
        </Dialog>
      </AriaModal>
    </ModalOverlay>
  );
}
