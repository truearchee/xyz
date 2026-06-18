# ADR-047 — Glossary `subject` vs `folder`, and the two distinct keys

**Status:** Accepted (Stage 7a, 2026-06-17)
**Context:** Slice 6 collapsed "subject" and "folder" into one concept. Stage 7 introduces an Unsorted
inbox, movable folders, and course-scoped practice — none coherent if folder == subject == dedup key.

## Decision
A glossary entry has **two independent axes**:
- **`subject_id` (= course module)** — the dedup / cache / practice-scope key. Derived from the source
  summary's module on highlight-save; chosen by the student on manual-add (restricted to enrolled
  modules). Effectively immutable.
- **`folder_id`** — a free-form per-student bucket, defaulting to a lazily-created system **"Unsorted"**
  folder. Movable later. Does **not** participate in dedup/cache/practice.

Two distinct keys, never conflated:
- **Dedup** = `studentId + normalizedTerm + subjectId`, **language-independent** (first save wins; the
  entry keeps the language it was generated in). Enforced by a partial-unique index on active rows.
- **Cache** = `normalizedTerm + subjectId + entryType + language`, **shared across students**, unique on
  `(cache_key, prompt_version)` so a prompt bump is a fresh miss, never an overwrite.

`normalized_term` is a deterministic NFKC/casefold/whitespace-collapse transform — **no AI** at save
(no "canonical English" generation). Stored verbatim `term` + `normalized_term` + `normalize_version`.

## Consequences
A folder may hold terms from multiple subjects (fine). Moving a term *between subjects* is out of scope
(it's part of the dedup key). "Unsorted" is a real system row (non-deletable), chosen over
null-resolves-on-read so folder counts/moves are uniform.
