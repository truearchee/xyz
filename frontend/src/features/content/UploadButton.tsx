"use client";

import { useRef } from "react";

type UploadButtonProps = {
  disabled?: boolean;
  label?: string;
  onFileSelected: (file: File) => void;
};

export function UploadButton({
  disabled = false,
  label = "Upload PDF",
  onFileSelected,
}: UploadButtonProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);

  return (
    <>
      <button
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        style={styles.button}
        type="button"
      >
        {label}
      </button>
      <input
        accept="application/pdf,.pdf"
        aria-label={label}
        disabled={disabled}
        onChange={(event) => {
          const file = event.currentTarget.files?.[0];
          event.currentTarget.value = "";
          if (file) {
            onFileSelected(file);
          }
        }}
        ref={inputRef}
        style={styles.input}
        type="file"
      />
    </>
  );
}

const styles = {
  button: {
    background: "#174a63",
    border: "1px solid #174a63",
    borderRadius: 6,
    color: "#ffffff",
    cursor: "pointer",
    fontSize: 14,
    fontWeight: 700,
    lineHeight: 1,
    minHeight: 38,
    padding: "0 14px",
  },
  input: {
    display: "none",
  },
} satisfies Record<string, React.CSSProperties>;
