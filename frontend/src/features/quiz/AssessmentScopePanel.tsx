"use client";

import type React from "react";
import { useCallback, useEffect, useState } from "react";

import { ApiError, type AssessmentScopeResponse } from "../../lib/api";
import { ForbiddenError, api } from "../../lib/api/wrapper";

function parseWeeks(value: string): number[] {
  return value
    .split(",")
    .map((part) => Number(part.trim()))
    .filter((n) => Number.isInteger(n) && n > 0);
}

function errorMessage(caught: unknown): string {
  if (caught instanceof ForbiddenError) return "You are not allowed to manage assessment scopes.";
  if (caught instanceof ApiError) {
    const detail = caught.body?.detail;
    if (typeof detail === "string") return detail;
    return caught.message;
  }
  if (caught instanceof Error) return caught.message;
  return "Unexpected error";
}

export function AssessmentScopePanel({ moduleId }: { moduleId: string }) {
  const [name, setName] = useState("");
  const [weeks, setWeeks] = useState("");
  const [items, setItems] = useState<AssessmentScopeResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const page = await api.assessments.list(moduleId, 50, 0);
      setItems(page.items);
      setTotal(page.pagination.total);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setLoading(false);
    }
  }, [moduleId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const coveredWeeks = parseWeeks(weeks);
    if (!name.trim() || coveredWeeks.length === 0) {
      setError("Enter a name and at least one week.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setStatus(null);
    try {
      await api.assessments.create(moduleId, { name: name.trim(), coveredWeeks });
      setName("");
      setWeeks("");
      setStatus("Scope created.");
      await load();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section aria-label="Assessment scopes" data-testid="assessment-scope-panel" style={styles.block}>
      <header>
        <h2 style={styles.heading}>Assessment scopes</h2>
        <p style={styles.muted}>Create named week ranges for exam-prep quizzes.</p>
      </header>
      <form onSubmit={submit} style={styles.form}>
        <label style={styles.label}>
          Name
          <input
            aria-label="Assessment scope name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
            style={styles.input}
          />
        </label>
        <label style={styles.label}>
          Covered weeks
          <input
            aria-label="Assessment scope covered weeks"
            placeholder="1,2,3"
            value={weeks}
            onChange={(event) => setWeeks(event.target.value)}
            required
            style={styles.input}
          />
        </label>
        <button type="submit" disabled={submitting} style={styles.primaryButton}>
          {submitting ? "Creating..." : "Create scope"}
        </button>
      </form>
      {error ? <p role="alert" style={styles.errorText}>{error}</p> : null}
      {status ? <p role="status" style={styles.statusText}>{status}</p> : null}
      {loading ? <p style={styles.muted}>Loading scopes...</p> : null}
      {!loading && items.length === 0 ? <p style={styles.muted}>No assessment scopes yet.</p> : null}
      {items.length > 0 ? (
        <div style={styles.tableWrap}>
          <table data-testid="assessment-scope-table" style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Name</th>
                <th style={styles.th}>Weeks</th>
                <th style={styles.th}>Status</th>
                <th style={styles.th}>Updated</th>
              </tr>
            </thead>
            <tbody>
              {items.map((scope) => (
                <tr key={scope.id} data-testid={`assessment-scope-row-${scope.id}`}>
                  <td style={styles.td}>{scope.name}</td>
                  <td style={styles.td}>{scope.coveredWeeks.join(", ")}</td>
                  <td style={styles.td}>{scope.status}</td>
                  <td style={styles.td}>{new Date(scope.updatedAt).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p style={styles.muted}>{total === 1 ? "1 scope" : `${total} scopes`}</p>
        </div>
      ) : null}
    </section>
  );
}

const styles = {
  block: {
    background: "var(--color-surface)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-lg)",
    display: "grid",
    gap: 12,
    padding: 16,
  },
  heading: { color: "var(--color-text)", fontSize: 18, lineHeight: 1.3, margin: 0 },
  muted: { color: "var(--color-text-muted)", fontSize: 14, lineHeight: 1.5, margin: 0 },
  form: {
    alignItems: "end", display: "grid", gap: 10,
    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
  },
  label: { color: "var(--color-text)", display: "grid", fontSize: 13, fontWeight: 600, gap: 6 },
  input: {
    background: "var(--color-surface)", border: "1px solid var(--color-border-strong)", borderRadius: "var(--radius-md)", color: "var(--color-text)", fontSize: 14,
    minHeight: 36, padding: "0 10px",
  },
  primaryButton: {
    background: "var(--color-primary)", border: "1px solid var(--color-primary)", borderRadius: 999, color: "var(--color-on-primary)",
    cursor: "pointer", fontSize: 13, fontWeight: 700, minHeight: 36, padding: "0 14px",
  },
  errorText: { color: "var(--color-danger-text)", fontSize: 13, margin: 0 },
  statusText: { color: "var(--color-success-text)", fontSize: 13, fontWeight: 700, margin: 0 },
  tableWrap: { display: "grid", gap: 8, overflowX: "auto" },
  table: { borderCollapse: "collapse", fontSize: 13, minWidth: 520, width: "100%" },
  th: {
    borderBottom: "1px solid var(--color-border)", color: "var(--color-text-muted)", fontWeight: 700,
    padding: "8px 10px", textAlign: "left",
  },
  td: { borderBottom: "1px solid var(--color-border)", color: "var(--color-text)", padding: "8px 10px" },
} satisfies Record<string, React.CSSProperties>;
