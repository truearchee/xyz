import { ApiError } from "../../lib/api";

export function slugify(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

export function errorMessage(caught: unknown): string {
  if (caught instanceof ApiError) {
    if (typeof caught.body === "object" && caught.body !== null && "detail" in caught.body) {
      const detail = (caught.body as { detail?: unknown }).detail;
      if (typeof detail === "string") {
        return detail;
      }
    }
    return caught.message;
  }

  if (caught instanceof Error) {
    return caught.message;
  }

  return "Unexpected error";
}

export const panelStyles = {
  panel: {
    border: "1px solid #d7dde8",
    borderRadius: 8,
    display: "grid",
    gap: 16,
    padding: 16,
  },
  stack: {
    display: "grid",
    gap: 12,
  },
  grid: {
    display: "grid",
    gap: 12,
    gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
  },
  table: {
    borderCollapse: "collapse",
    width: "100%",
  },
  th: {
    borderBottom: "1px solid #d7dde8",
    fontSize: 13,
    padding: "8px 6px",
    textAlign: "left",
  },
  td: {
    borderBottom: "1px solid #eef2f7",
    fontSize: 14,
    padding: "8px 6px",
    verticalAlign: "top",
  },
  label: {
    display: "grid",
    fontSize: 13,
    gap: 4,
  },
  input: {
    border: "1px solid #cbd5e1",
    borderRadius: 6,
    fontSize: 14,
    padding: "8px 10px",
  },
  buttonRow: {
    alignItems: "center",
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
  },
  alert: {
    border: "1px solid #f0b4b4",
    borderRadius: 6,
    color: "#7f1d1d",
    fontSize: 14,
    padding: 10,
  },
  status: {
    border: "1px solid #9ad4aa",
    borderRadius: 6,
    color: "#14532d",
    fontSize: 14,
    padding: 10,
  },
  hint: {
    color: "#64748b",
    fontSize: 12,
    margin: 0,
  },
} satisfies Record<string, React.CSSProperties>;
