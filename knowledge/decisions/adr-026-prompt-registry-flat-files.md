---
type: adr
stage: "4.5"
status: accepted
created: 2026-06-10
updated: 2026-06-10
related-session: knowledge/specs/stage-04/4.5a-platform-llm-foundation.md
---

# ADR-026 - PromptRegistry = Flat Files

> Spec label ADR-016. Renumbered to adr-026 because adr-015..024 already exist (transcript topics).

## Linked documents
- Master spec: [[specs/stage-04/4.5-ai-infra-summary-generation]]
- Spec: [[specs/stage-04/4.5a-platform-llm-foundation]]
- Report: [[steps/stage-04/4.5a]]
- Related: [[adr-028-llm-gateway-provider-separation]]

## Context
Prompts need versioning, review, audit, and deploy semantics, plus a way to detect that a prompt's
content changed without a deliberate version bump (which would silently invalidate the
`promptContentHash` provenance recorded on every AIRequestLog and GeneratedLectureSummary row). The
v2 design left "prompt store = DB table vs flat files" open.

## Decision
The PromptRegistry loads prompts from a version-controlled flat-file directory of YAML files
(`<name>/<version>.yaml` with `name`, `version`, `content`, `max_tokens`, `model`, `backend`,
optional `reasoning_level`). The registry **loads and validates at startup** — a malformed or missing
prompt is a boot failure — and computes a SHA-256 content hash per file. A committed
`prompts/CHECKSUMS.json` baseline plus a CI drift guard (`backend/tests/ci/prompt_drift_guard.py`)
fails when a file's content changes without its `name/version` hash being re-recorded (the intentional
version-bump act).

Prompts live at **`backend/prompts/`** (not the spec's repo-root `prompts/`) because the backend
Docker build context is `./backend` (`COPY . .`); a repo-root directory would not ship in the image.
The path is resolved via `parents[3]` and overridable by `LLM_PROMPTS_DIR`.

## Rationale
- Git gives review/audit/deploy/rollback for free; no DB migration to change a prompt.
- Startup validation turns a bad prompt into a fast boot failure instead of a runtime surprise.
- The content hash + drift guard make accidental prompt edits a CI failure, protecting provenance.
- The registry abstraction keeps a future DB-backed store open without changing call sites.

## Consequences
- Prompt edits require a `version` bump + a `CHECKSUMS.json` update, enforced by CI.
- A DB-backed prompt table is explicitly out of scope (post-MVP, behind the same registry interface).
- Stage 7's glossary definition cache keys off `promptVersion`, which this scheme makes explicit.
