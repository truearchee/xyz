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
    <section aria-label={`Assets for ${sectionTitle}`} className="grid gap-2.5 border-t border-border pt-3.5">
      <h3 className="m-0 font-display text-base leading-snug text-text">Files</h3>
      {assets.length === 0 ? (
        <p className="m-0 text-sm text-text-muted">No files uploaded</p>
      ) : (
        <ul className="m-0 grid list-none gap-2.5 p-0">
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
