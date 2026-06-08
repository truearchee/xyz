"use client";

import type { SectionAssetResponse } from "../../../lib/api";
import { SectionAssetRow } from "./SectionAssetRow";

type SectionAssetListProps = {
  assets: SectionAssetResponse[];
  disabled?: boolean;
  replaceErrors: Record<string, string>;
  replacingAssetId: string | null;
  sectionTitle: string;
  onReplace: (assetId: string, file: File) => Promise<void>;
};

export function SectionAssetList({
  assets,
  disabled = false,
  replaceErrors,
  replacingAssetId,
  sectionTitle,
  onReplace,
}: SectionAssetListProps) {
  return (
    <section aria-label={`Assets for ${sectionTitle}`} style={styles.shell}>
      <h3 style={styles.title}>Files</h3>
      {assets.length === 0 ? (
        <p style={styles.empty}>No files uploaded</p>
      ) : (
        <ul style={styles.list}>
          {assets.map((asset) => (
            <SectionAssetRow
              asset={asset}
              disabled={disabled || replacingAssetId !== null}
              errorMessage={replaceErrors[asset.id] ?? null}
              isReplacing={replacingAssetId === asset.id}
              key={asset.id}
              onReplace={onReplace}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

const styles = {
  shell: {
    borderTop: "1px solid #e5e7eb",
    display: "grid",
    gap: 10,
    paddingTop: 14,
  },
  title: {
    color: "#111827",
    fontSize: 15,
    lineHeight: 1.3,
    margin: 0,
  },
  empty: {
    color: "#4b5563",
    fontSize: 14,
    margin: 0,
  },
  list: {
    display: "grid",
    gap: 10,
    listStyle: "none",
    margin: 0,
    padding: 0,
  },
} satisfies Record<string, React.CSSProperties>;
