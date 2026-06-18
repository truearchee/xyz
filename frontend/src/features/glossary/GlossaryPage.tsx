"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import type {
  GlossaryEntryDetail,
  GlossaryEntryRead,
  GlossaryFolderRead,
} from "../../lib/api";
import { api } from "../../lib/api/wrapper";
import { MarkdownView } from "./MarkdownView";
import { ManualEntryModal } from "./ManualEntryModal";

const POLL_MS = 2500;
const ALL = "__all__";

type View = "table" | "cards";

const LANGUAGE_LABEL: Record<string, string> = {
  en: "English",
  ar: "Arabic",
  zh: "Chinese",
  es: "Spanish",
  fr: "French",
};

export function GlossaryPage() {
  const [folders, setFolders] = useState<GlossaryFolderRead[]>([]);
  const [folderId, setFolderId] = useState<string>(ALL);
  const [entries, setEntries] = useState<GlossaryEntryRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [view, setView] = useState<View>("table");
  const [detail, setDetail] = useState<GlossaryEntryDetail | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const loadFolders = useCallback(async () => {
    try {
      setFolders(await api.glossary.listFolders());
    } catch {
      /* folders are non-critical; the list still renders */
    }
  }, []);

  const loadEntries = useCallback(async (selected: string) => {
    try {
      const page = await api.glossary.listEntries({
        folderId: selected === ALL ? undefined : selected,
      });
      setEntries(page.items);
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadFolders();
  }, [loadFolders]);

  useEffect(() => {
    setLoading(true);
    void loadEntries(folderId);
  }, [folderId, loadEntries]);

  // Poll while any entry is still generating its definition (reuses the summary async pattern).
  useEffect(() => {
    if (!entries.some((e) => e.definitionStatus === "pending")) {
      return;
    }
    const id = window.setTimeout(() => {
      void loadEntries(folderId);
      void loadFolders();
    }, POLL_MS);
    return () => window.clearTimeout(id);
  }, [entries, folderId, loadEntries, loadFolders]);

  const openDetail = useCallback(async (entryId: string) => {
    setDetail(null);
    try {
      setDetail(await api.glossary.getEntry(entryId));
    } catch {
      /* ignore — the row stays in the list */
    }
  }, []);

  const archiveEntry = useCallback(
    async (entryId: string) => {
      await api.glossary.deleteEntry(entryId);
      setDetail(null);
      await loadEntries(folderId);
      await loadFolders();
    },
    [folderId, loadEntries, loadFolders],
  );

  return (
    <section data-testid="glossary-page" style={styles.layout}>
      <aside style={styles.sidebar}>
        <h2 style={styles.sidebarHeading}>Folders</h2>
        <button
          type="button"
          data-testid={`glossary-folder-${ALL}`}
          onClick={() => setFolderId(ALL)}
          style={folderId === ALL ? styles.folderActive : styles.folder}
        >
          All terms
        </button>
        {folders.map((f) => (
          <button
            key={f.id}
            type="button"
            data-testid={`glossary-folder-${f.id}`}
            onClick={() => setFolderId(f.id)}
            style={folderId === f.id ? styles.folderActive : styles.folder}
          >
            {f.name} ({f.entryCount})
          </button>
        ))}
      </aside>

      <div style={styles.main}>
        <header style={styles.header}>
          <h1 style={styles.title}>Glossary</h1>
          <div style={styles.headerActions}>
            <Link href="/student/glossary/practice" data-testid="glossary-practice-link" style={styles.secondary}>
              Practice
            </Link>
            <button
              type="button"
              data-testid="glossary-view-toggle"
              onClick={() => setView((v) => (v === "table" ? "cards" : "table"))}
              style={styles.secondary}
            >
              {view === "table" ? "Card view" : "Table view"}
            </button>
            <button
              type="button"
              data-testid="glossary-add-term"
              onClick={() => setModalOpen(true)}
              style={styles.primary}
            >
              Add term
            </button>
          </div>
        </header>

        {loading ? (
          <p style={styles.muted}>Loading your glossary…</p>
        ) : error ? (
          <p role="alert" style={styles.error}>
            Couldn’t load your glossary — refresh to try again.
          </p>
        ) : entries.length === 0 ? (
          <div data-testid="glossary-empty" style={styles.empty}>
            <p style={styles.muted}>No saved terms yet.</p>
            <p style={styles.muted}>
              Highlight text in a lecture summary and choose “Save to glossary”, or add a term manually.
            </p>
          </div>
        ) : view === "table" ? (
          <TableView entries={entries} onOpen={openDetail} />
        ) : (
          <CardsView entries={entries} onOpen={openDetail} />
        )}
      </div>

      {detail ? (
        <EntryDetail detail={detail} onClose={() => setDetail(null)} onArchive={archiveEntry} />
      ) : null}

      {modalOpen ? (
        <ManualEntryModal
          onClose={() => setModalOpen(false)}
          onSaved={() => {
            setModalOpen(false);
            void loadEntries(folderId);
            void loadFolders();
          }}
        />
      ) : null}
    </section>
  );
}

function StatusBadge({ entry }: { entry: GlossaryEntryRead }) {
  const map: Record<string, { label: string; color: string }> = {
    pending: { label: "Generating…", color: "#92400e" },
    failed: { label: "Failed", color: "#7f1d1d" },
    generated: { label: "Ready", color: "#065f46" },
    manual: { label: "Manual", color: "#374151" },
  };
  const s = map[entry.definitionStatus] ?? { label: entry.definitionStatus, color: "#374151" };
  return (
    <span
      data-testid={`glossary-entry-status-${entry.id}`}
      data-status={entry.definitionStatus}
      style={{ color: s.color, fontSize: 12, fontWeight: 700 }}
    >
      {s.label}
    </span>
  );
}

function TableView({
  entries,
  onOpen,
}: {
  entries: GlossaryEntryRead[];
  onOpen: (id: string) => void;
}) {
  return (
    <table style={styles.table}>
      <thead>
        <tr>
          <th style={styles.th}>Term</th>
          <th style={styles.th}>Type</th>
          <th style={styles.th}>Language</th>
          <th style={styles.th}>Status</th>
        </tr>
      </thead>
      <tbody>
        {entries.map((e) => (
          <tr
            key={e.id}
            data-testid={`glossary-entry-${e.id}`}
            onClick={() => onOpen(e.id)}
            style={styles.row}
          >
            <td style={styles.td}>{e.term}</td>
            <td style={styles.td}>{e.entryType}</td>
            <td style={styles.td}>{LANGUAGE_LABEL[e.language] ?? e.language}</td>
            <td style={styles.td}>
              <StatusBadge entry={e} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function CardsView({
  entries,
  onOpen,
}: {
  entries: GlossaryEntryRead[];
  onOpen: (id: string) => void;
}) {
  return (
    <div style={styles.cards}>
      {entries.map((e) => (
        <button
          key={e.id}
          type="button"
          data-testid={`glossary-entry-${e.id}`}
          onClick={() => onOpen(e.id)}
          style={styles.card}
        >
          <span style={styles.cardTerm}>{e.term}</span>
          <StatusBadge entry={e} />
          {e.shortDefinition ? (
            <span style={styles.cardPreview}>{e.shortDefinition.slice(0, 120)}</span>
          ) : null}
        </button>
      ))}
    </div>
  );
}

function EntryDetail({
  detail,
  onClose,
  onArchive,
}: {
  detail: GlossaryEntryDetail;
  onClose: () => void;
  onArchive: (id: string) => Promise<void>;
}) {
  const { entry, sources } = detail;
  const [busy, setBusy] = useState(false);
  return (
    <aside data-testid="glossary-detail" style={styles.detail}>
      <div style={styles.detailHead}>
        <h2 dir={entry.language === "ar" ? "rtl" : "ltr"} style={styles.detailTerm}>
          {entry.term}
        </h2>
        <button type="button" onClick={onClose} style={styles.secondary}>
          Close
        </button>
      </div>
      <p style={styles.detailMeta}>
        {LANGUAGE_LABEL[entry.language] ?? entry.language} · {entry.entryType}
      </p>

      {entry.definitionStatus === "pending" ? (
        <p role="status" style={styles.muted}>
          Definition is being generated…
        </p>
      ) : entry.definitionStatus === "failed" ? (
        <p role="status" style={styles.error}>
          Definition could not be generated.
        </p>
      ) : entry.shortDefinition ? (
        <MarkdownView
          content={entry.shortDefinition}
          testId="glossary-detail-definition"
          language={entry.language}
        />
      ) : (
        <p style={styles.muted}>No definition yet.</p>
      )}

      <h3 style={styles.sourcesHeading}>Sources</h3>
      <ul style={styles.sourceList}>
        {sources.map((s) => (
          <li key={s.id} style={styles.sourceItem}>
            {s.sourceType}
            {s.selectedText ? `: “${s.selectedText.slice(0, 80)}”` : ""}
          </li>
        ))}
      </ul>

      <button
        type="button"
        data-testid="glossary-delete"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          await onArchive(entry.id);
        }}
        style={styles.danger}
      >
        {busy ? "Deleting…" : "Delete"}
      </button>
    </aside>
  );
}

const styles = {
  layout: { display: "grid", gap: 18, gridTemplateColumns: "200px 1fr", alignItems: "start" },
  sidebar: { display: "grid", gap: 6 },
  sidebarHeading: { color: "#4b5563", fontSize: 12, fontWeight: 700, margin: "0 0 4px", textTransform: "uppercase" },
  folder: {
    background: "#ffffff",
    border: "1px solid #d7dde8",
    borderRadius: 6,
    color: "#111827",
    cursor: "pointer",
    fontSize: 13,
    padding: "8px 10px",
    textAlign: "left",
  },
  folderActive: {
    background: "#eef2f7",
    border: "1px solid #174a63",
    borderRadius: 6,
    color: "#111827",
    cursor: "pointer",
    fontSize: 13,
    fontWeight: 700,
    padding: "8px 10px",
    textAlign: "left",
  },
  main: { display: "grid", gap: 14 },
  header: { alignItems: "center", display: "flex", justifyContent: "space-between" },
  headerActions: { display: "flex", gap: 10 },
  title: { color: "#111827", fontSize: 24, margin: 0 },
  table: { borderCollapse: "collapse", width: "100%" },
  th: {
    borderBottom: "2px solid #d7dde8",
    color: "#4b5563",
    fontSize: 12,
    padding: "8px 10px",
    textAlign: "left",
    textTransform: "uppercase",
  },
  row: { cursor: "pointer" },
  td: { borderBottom: "1px solid #eef1f5", color: "#111827", fontSize: 14, padding: "10px" },
  cards: { display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))" },
  card: {
    background: "#ffffff",
    border: "1px solid #d7dde8",
    borderRadius: 8,
    cursor: "pointer",
    display: "grid",
    gap: 6,
    padding: 12,
    textAlign: "left",
  },
  cardTerm: { color: "#111827", fontSize: 15, fontWeight: 700 },
  cardPreview: { color: "#4b5563", fontSize: 13 },
  empty: { border: "1px dashed #d7dde8", borderRadius: 8, display: "grid", gap: 6, padding: 24 },
  detail: {
    border: "1px solid #d7dde8",
    borderRadius: 8,
    display: "grid",
    gap: 10,
    gridColumn: "1 / -1",
    padding: 16,
  },
  detailHead: { alignItems: "center", display: "flex", justifyContent: "space-between" },
  detailTerm: { color: "#111827", fontSize: 20, margin: 0 },
  detailMeta: { color: "#4b5563", fontSize: 13, margin: 0 },
  sourcesHeading: { color: "#374151", fontSize: 13, fontWeight: 700, margin: "8px 0 0", textTransform: "uppercase" },
  sourceList: { color: "#374151", display: "grid", gap: 4, fontSize: 13, listStyle: "none", margin: 0, padding: 0 },
  sourceItem: { color: "#374151", fontSize: 13 },
  muted: { color: "#4b5563", fontSize: 14, fontStyle: "italic", margin: 0 },
  error: { color: "#7f1d1d", fontSize: 14, margin: 0 },
  primary: {
    background: "#174a63",
    border: "1px solid #174a63",
    borderRadius: 6,
    color: "#ffffff",
    cursor: "pointer",
    fontSize: 13,
    fontWeight: 700,
    minHeight: 34,
    padding: "0 14px",
  },
  secondary: {
    background: "#ffffff",
    border: "1px solid #d7dde8",
    borderRadius: 6,
    color: "#374151",
    cursor: "pointer",
    fontSize: 13,
    minHeight: 34,
    padding: "0 14px",
  },
  danger: {
    background: "#fef2f2",
    border: "1px solid #f0b4b4",
    borderRadius: 6,
    color: "#7f1d1d",
    cursor: "pointer",
    fontSize: 13,
    fontWeight: 700,
    justifySelf: "start",
    minHeight: 34,
    padding: "0 14px",
  },
} satisfies Record<string, React.CSSProperties>;
