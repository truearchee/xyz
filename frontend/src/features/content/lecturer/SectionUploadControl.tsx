"use client";

import { useRef, useState } from "react";

type SectionUploadControlProps = {
  disabled?: boolean;
  errorMessage: string | null;
  isUploading: boolean;
  onUpload: (file: File, dueAt?: string | null) => Promise<void>;
  sectionKey: string;
  sectionTitle: string;
  sectionType: string;
};

const inputClass =
  "min-h-[38px] rounded-md border border-border-strong px-2.5 py-[7px] text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2";
const btnPrimary =
  "min-h-[38px] rounded-full border border-primary bg-primary px-3.5 text-sm font-medium text-on-primary hover:bg-primary-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2";
const btnDisabled =
  "min-h-[38px] cursor-not-allowed rounded-full border border-border bg-surface-muted px-3.5 text-sm font-medium text-text-muted";

export function SectionUploadControl({
  disabled = false,
  errorMessage,
  isUploading,
  onUpload,
  sectionKey,
  sectionTitle,
  sectionType,
}: SectionUploadControlProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dueAt, setDueAt] = useState("");
  const fileInputId = `section-upload-file-${sectionKey}`;
  const dueAtInputId = `section-upload-due-at-${sectionKey}`;
  const isLab = sectionType === "lab";

  async function submitUpload() {
    if (!selectedFile) {
      return;
    }

    await onUpload(selectedFile, isLab && dueAt ? new Date(dueAt).toISOString() : null);
    setSelectedFile(null);
    setDueAt("");
    if (inputRef.current) {
      inputRef.current.value = "";
    }
  }

  return (
    <section
      aria-label={`Upload asset to ${sectionTitle}`}
      data-testid={`section-upload-control-${sectionKey}`}
      className="grid gap-2 border-t border-border pt-3.5"
    >
      <div className="grid items-end gap-2.5 [grid-template-columns:repeat(auto-fit,minmax(160px,1fr))]">
        <label htmlFor={fileInputId} className="text-xs font-medium text-text-muted [grid-column:1/-1]">
          {isLab ? "File" : "PDF file"}
        </label>
        <input
          accept={isLab ? "application/pdf,.pdf,.ipynb,application/x-ipynb+json" : "application/pdf,.pdf"}
          disabled={disabled || isUploading}
          id={fileInputId}
          onChange={(event) => {
            setSelectedFile(event.currentTarget.files?.[0] ?? null);
          }}
          ref={inputRef}
          className={inputClass}
          type="file"
        />
        {isLab ? (
          <label htmlFor={dueAtInputId} className="grid gap-1 text-xs font-medium text-text-muted">
            Due
            <input
              disabled={disabled || isUploading}
              id={dueAtInputId}
              onChange={(event) => setDueAt(event.target.value)}
              className={inputClass}
              type="datetime-local"
              value={dueAt}
            />
          </label>
        ) : null}
        <button
          disabled={disabled || isUploading || !selectedFile}
          onClick={() => void submitUpload()}
          className={disabled || isUploading || !selectedFile ? btnDisabled : btnPrimary}
          type="button"
        >
          {isUploading ? "Uploading..." : "Upload"}
        </button>
      </div>
      {selectedFile ? (
        <p className="m-0 break-words text-xs text-text-muted">Selected: {selectedFile.name}</p>
      ) : null}
      {errorMessage ? (
        <p
          role="alert"
          className="m-0 rounded-md border border-danger bg-danger-surface px-2.5 py-2 text-sm leading-snug text-danger-text"
        >
          {errorMessage}
        </p>
      ) : null}
    </section>
  );
}
