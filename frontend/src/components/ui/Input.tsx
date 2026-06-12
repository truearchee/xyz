"use client";

import type { ChangeEvent, ReactNode } from "react";

import { cn } from "./cn";

// text / textarea / select with: label association (htmlFor/id), error linked via aria-describedby +
// aria-invalid, and error signalled by an icon + text + role=alert (NOT color alone). The control
// boundary uses border-strong (zinc-500, 3:1) so it is a perceivable functional edge (§4.1 / WCAG 1.4.11).
type InputProps = {
  id: string;
  label: string;
  as?: "input" | "textarea" | "select";
  type?: string;
  value?: string;
  defaultValue?: string;
  onChange?: (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => void;
  placeholder?: string;
  required?: boolean;
  disabled?: boolean;
  readOnly?: boolean;
  name?: string;
  autoComplete?: string;
  rows?: number;
  error?: string;
  description?: string;
  className?: string;
  children?: ReactNode; // <option>s when as="select"
};

export function Input({
  id,
  label,
  as = "input",
  type = "text",
  value,
  defaultValue,
  onChange,
  placeholder,
  required,
  disabled,
  readOnly,
  name,
  autoComplete,
  rows,
  error,
  description,
  className,
  children,
}: InputProps) {
  const descId = description ? `${id}-desc` : undefined;
  const errId = error ? `${id}-err` : undefined;
  const describedBy = [descId, errId].filter(Boolean).join(" ") || undefined;

  const controlClass = cn(
    "w-full rounded-md border bg-surface px-3 py-2 text-sm text-text placeholder:text-text-muted",
    "focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2",
    error ? "border-danger" : "border-border-strong focus-visible:border-primary",
    "disabled:cursor-not-allowed disabled:bg-surface-muted disabled:opacity-70",
    "read-only:bg-surface-muted",
    className,
  );

  const shared = {
    id,
    name,
    required,
    disabled,
    "aria-invalid": error ? (true as const) : undefined,
    "aria-describedby": describedBy,
    className: controlClass,
  };

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-text">
        {label}
        {required ? <span className="text-danger-text"> *</span> : null}
      </label>
      {description ? (
        <p id={descId} className="text-xs text-text-muted">
          {description}
        </p>
      ) : null}
      {as === "textarea" ? (
        <textarea
          {...shared}
          rows={rows}
          readOnly={readOnly}
          placeholder={placeholder}
          value={value}
          defaultValue={defaultValue}
          onChange={onChange}
        />
      ) : as === "select" ? (
        <select {...shared} value={value} defaultValue={defaultValue} onChange={onChange}>
          {children}
        </select>
      ) : (
        <input
          {...shared}
          type={type}
          readOnly={readOnly}
          placeholder={placeholder}
          autoComplete={autoComplete}
          value={value}
          defaultValue={defaultValue}
          onChange={onChange}
        />
      )}
      {error ? (
        <p id={errId} role="alert" className="flex items-center gap-1 text-xs font-medium text-danger-text">
          <span aria-hidden="true">⚠</span>
          {error}
        </p>
      ) : null}
    </div>
  );
}
