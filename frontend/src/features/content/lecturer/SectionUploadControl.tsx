"use client";

import { useRef, useState } from "react";

type SectionUploadControlProps = {
  disabled?: boolean;
  errorMessage: string | null;
  isUploading: boolean;
  onUpload: (file: File) => Promise<void>;
  sectionKey: string;
  sectionTitle: string;
};

export function SectionUploadControl({
  disabled = false,
  errorMessage,
  isUploading,
  onUpload,
  sectionKey,
  sectionTitle,
}: SectionUploadControlProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const fileInputId = `section-upload-file-${sectionKey}`;

  async function submitUpload() {
    if (!selectedFile) {
      return;
    }

    await onUpload(selectedFile);
    setSelectedFile(null);
    if (inputRef.current) {
      inputRef.current.value = "";
    }
  }

  return (
    <section
      aria-label={`Upload asset to ${sectionTitle}`}
      data-testid={`section-upload-control-${sectionKey}`}
      style={styles.shell}
    >
      <div style={styles.fields}>
        <label htmlFor={fileInputId} style={styles.label}>
          PDF file
        </label>
        <input
          accept="application/pdf,.pdf"
          disabled={disabled || isUploading}
          id={fileInputId}
          onChange={(event) => {
            setSelectedFile(event.currentTarget.files?.[0] ?? null);
          }}
          ref={inputRef}
          style={styles.input}
          type="file"
        />
        <button
          disabled={disabled || isUploading || !selectedFile}
          onClick={() => void submitUpload()}
          style={
            disabled || isUploading || !selectedFile
              ? styles.disabledButton
              : styles.button
          }
          type="button"
        >
          {isUploading ? "Uploading..." : "Upload"}
        </button>
      </div>
      {selectedFile ? (
        <p style={styles.selected}>Selected: {selectedFile.name}</p>
      ) : null}
      {errorMessage ? (
        <p role="alert" style={styles.error}>
          {errorMessage}
        </p>
      ) : null}
    </section>
  );
}

const buttonBase = {
  borderRadius: 6,
  fontSize: 14,
  fontWeight: 700,
  minHeight: 38,
  padding: "0 14px",
} satisfies React.CSSProperties;

const styles = {
  shell: {
    borderTop: "1px solid #e5e7eb",
    display: "grid",
    gap: 8,
    paddingTop: 14,
  },
  fields: {
    alignItems: "end",
    display: "grid",
    gap: 10,
    gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
  },
  label: {
    color: "#374151",
    fontSize: 13,
    fontWeight: 700,
    gridColumn: "1 / -1",
  },
  input: {
    border: "1px solid #cbd5e1",
    borderRadius: 6,
    fontSize: 14,
    minHeight: 38,
    padding: "7px 9px",
  },
  button: {
    ...buttonBase,
    background: "#174a63",
    border: "1px solid #174a63",
    color: "#ffffff",
    cursor: "pointer",
  },
  disabledButton: {
    ...buttonBase,
    background: "#e5e7eb",
    border: "1px solid #d1d5db",
    color: "#6b7280",
    cursor: "not-allowed",
  },
  selected: {
    color: "#374151",
    fontSize: 13,
    margin: 0,
    overflowWrap: "anywhere",
  },
  error: {
    background: "#fef2f2",
    border: "1px solid #fecaca",
    borderRadius: 6,
    color: "#7f1d1d",
    fontSize: 14,
    lineHeight: 1.45,
    margin: 0,
    padding: "8px 10px",
  },
} satisfies Record<string, React.CSSProperties>;
