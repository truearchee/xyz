---
type: adr
stage: "4.7"
status: accepted
created: 2026-06-12
updated: 2026-06-12
related-session: knowledge/specs/stage-04/4.7-student-facing-summaries.md
---

# ADR-037 — AI-content sanitization on the student page (spec ADR-4.7-4)

> Spec label "ADR-4.7-4". Remapped to repo slot adr-037.

## Linked documents
- Spec: [[specs/stage-04/4.7-student-facing-summaries]]
- Report: [[steps/stage-04/4.7b-student-page-browser-gate]]

## Context
4.7 is the one place AI-generated text reaches the browser as markup. AI output is treated as UNTRUSTED
even though it is ours (it can emit raw HTML; prompts change; content becomes editable post-MVP). The
detailed summary is stored structured; §3.3 excludes client-side structured rendering, so content is
served as a markdown string and rendered as markup.

## Decision
Server shapes summary `content_json` into a markdown STRING (`domains/student_summaries/markdown.py`).
The student page renders it with **`react-markdown`, raw HTML DISABLED** — `rehype-raw` is deliberately
NOT added, so embedded HTML (e.g. `<script>`) is inert text, never executed
(`features/content/student/SummaryMarkdown.tsx`). Additionally: image/iframe/script/style/form/embed
elements are disallowed (no remote image fetches), and link hrefs are gated to `http(s):`/`mailto:`
(other protocols, incl. `javascript:`/`data:`, render as plain text).

## Consequences
The summary blob cannot inject script, load remote resources, or carry unsafe link protocols. The shaping
lives behind one hardened server path + one render component, which 4.8's hosted smoke reuses (§20).
Pre-existing Next.js advisories (frontend) remain a Stage 4.9/12 hygiene concern, untouched by this ADR.
