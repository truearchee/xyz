"use client";

import type { SectionAssetResponse } from "../../lib/api/models/SectionAssetResponse";

type SectionAssetListProps = {
  assets: SectionAssetResponse[];
  emptyMessage?: string;
  onReplace?: (asset: SectionAssetResponse, file: File) => void;
};

export function SectionAssetList({
  assets,
  emptyMessage = "No files uploaded",
  onReplace,
}: SectionAssetListProps) {
  if (assets.length === 0) {
    return <p style={styles.empty}>{emptyMessage}</p>;
  }

  return (
    <ul aria-label="Section assets" style={styles.list}>
      {assets.map((asset) => (
        <li key={asset.id} style={styles.item}>
          <div style={styles.meta}>
            <span style={styles.name}>{asset.fileName}</span>
            <span style={styles.detail}>{formatBytes(asset.fileSize)}</span>
          </div>
          {onReplace ? (
            <label style={styles.replace}>
              Replace
              <input
                accept="application/pdf,.pdf"
                aria-label={`Replace ${asset.fileName}`}
                onChange={(event) => {
                  const file = event.currentTarget.files?.[0];
                  event.currentTarget.value = "";
                  if (file) {
                    onReplace(asset, file);
                  }
                }}
                style={styles.input}
                type="file"
              />
            </label>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

const styles = {
  empty: {
    color: "#4b5563",
    fontSize: 14,
    margin: 0,
  },
  list: {
    display: "grid",
    gap: 8,
    listStyle: "none",
    margin: 0,
    padding: 0,
  },
  item: {
    alignItems: "center",
    border: "1px solid #d7dde8",
    borderRadius: 6,
    display: "flex",
    gap: 12,
    justifyContent: "space-between",
    minHeight: 48,
    padding: "8px 10px",
  },
  meta: {
    display: "grid",
    gap: 2,
    minWidth: 0,
  },
  name: {
    color: "#111827",
    fontSize: 14,
    fontWeight: 700,
    overflowWrap: "anywhere",
  },
  detail: {
    color: "#4b5563",
    fontSize: 12,
  },
  replace: {
    border: "1px solid #9ca3af",
    borderRadius: 6,
    color: "#111827",
    cursor: "pointer",
    flex: "0 0 auto",
    fontSize: 13,
    fontWeight: 700,
    padding: "7px 10px",
  },
  input: {
    display: "none",
  },
} satisfies Record<string, React.CSSProperties>;
