---
type: adr
id: adr-062
stage: "12"
status: accepted
created: 2026-06-23
related-session: "12b"
---

# ADR-062 — Signed-URL access cutoff on unpublish: accept the short TTL window (D-12-B)

## Status
Accepted (Stage 12b, 2026-06-23). Owner decision **D-12-B**.

## Context
When a section is unpublished (or a transcript/asset replaced), a student who already obtained a signed
read URL could keep using it until it expires. Decision: implement instant revocation, or accept the short
TTL window?

Verified behaviour (`backend/app/domains/content/service.py::_resolve_asset_download_ref`, lines 374-382):
- **Future minting IS already blocked on unpublish.** Every signed-URL mint re-validates publish status for
  a student: unpublished → 403, not-published / inactive / not-completed → 404. The moment a section is
  unpublished, **no new signed URL can be issued** to a student.
- The only residual exposure is an **already-issued** signed URL, valid until the provider TTL expires.
- TTL = `SIGNED_READ_URL_TTL_SECONDS`, default **300 s (5 min)**; responses set `Cache-Control: no-store`;
  the backend never persists / caches / proxies signed URLs (storage architecture).

(This corrects an earlier kickoff note that questioned whether the mint re-validates visibility — it does;
the storage architecture doc was accurate. Reconciliation recorded in `findings-12`.)

## Decision
**Accept the short TTL window; do not implement instant revocation for the MVP.** A student holding a signed
URL issued just before unpublish may read that one already-authorised object for at most the remaining TTL
(≤5 min). Future minting is already blocked, so the window cannot be reopened or extended.

Rationale:
- Supabase signed URLs are stateless bearer tokens with **no server-side revocation**. Honouring revocation
  would require rotating the storage key on every unpublish, or proxying every download through the backend
  — defeating the signed-URL design — for little MVP value.
- The exposure is bounded: ≤5 min, a single object, by a student who was authorised to view it moments
  earlier. 5 min is well within the spec's ≤15-min recommendation.
- No real student data exists yet (no hosting); this is a deploy-readiness posture, revisitable post-MVP.

## Consequences
- **No code change in Stage 12b for signed URLs** — the future-minting gate already exists and is correct.
- The TTL value is the only lever: lowering `SIGNED_READ_URL_TTL_SECONDS` shrinks the window with no code
  change.
- The post-MVP watchlist trigger stands recorded: "Signed-URL revocation — if the Stage 12 TTL acceptance is
  revisited" (roadmap).

## Linked documents
- Stage spec: [[specs/stage-12/12-release-hardening]]
- 12b spec: [[specs/stage-12/12b-security-audit-build-hygiene]]
- Findings: [[steps/findings-12]]
- Architecture: [[architecture/storage]]
- Roadmap watchlist: [[roadmap]]
