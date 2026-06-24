---
type: adr
id: adr-063
stage: "12"
status: accepted
created: 2026-06-23
related-session: "12d"
---

# ADR-063 — Recording / transcript retention: course-lifetime (D-12-C)

## Status
Accepted (Stage 12, 2026-06-23). Owner decision **D-12-C**. The deletion **mechanism** is
deferred-with-owner to go-live (rule 13); this ADR (the policy) is required now and is recorded here. The
post-MVP watchlist flags retention as required **before any real-student deployment** — this ADR discharges
the *decision* half of that obligation.

## Context
All AI-bearing course material derives from lecture recordings/transcripts of identifiable people:
`transcripts`, `transcript_segments`, `transcript_chunks`, `generated_lecture_summaries`, the section
`section_assets`, and the `ai_request_logs` provenance (hashes/metadata only — no raw speech, per rule 6).
"Indefinite by default with no documented decision" is not an acceptable end state for a university context.

## Decision
**Course-lifetime retention.** All course-related material — recordings, transcripts, derived summaries, and
section assets — is **retained for as long as the course (`course_modules` row) exists**. **Deleting a course
deletes all of its associated material** (a cascading delete across the course's transcripts/segments/chunks/
summaries/assets and their stored objects).

Rationale: students return to course material after the course ends to revise, so the material must stay
accessible while the course exists. Retention is therefore tied to the course's own lifecycle, not a fixed
clock — the simplest policy that matches how the material is actually used at single-university MVP scale.

**Backup-retention alignment (required by the spec).** Course deletion removes the **primary** material
immediately, but managed-Postgres automated backups / point-in-time-recovery and object-storage
versioning (the durability posture defined in the 12f deploy procedure) will retain a copy for their
configured window. That **backup window is the residual retention** and is part of this privacy decision: it
must be **bounded and documented** in the 12f backups section, so "deleting the course deletes the material"
is honest modulo a stated, finite backup horizon (after which the copy is irrecoverable). The backup
retention window must not silently exceed the course lifetime by an unbounded amount.

## Consequences
- **Mechanism deferred-with-owner to go-live.** No real student data exists yet (no hosting; seed-only), so
  the course-deletion cascade (primary rows + loss-safe, prefix-scoped object-store deletion, reusing the 4.6
  reconciliation patterns) is **not built in Stage 12**. It is an explicit gate item in
  `docs/go-live-checklist.md`: **enable the course-deletion retention mechanism before any real-student data**.
- When built, the cascade must reuse the 4.6 reconciliation job's loss-safe, prefix-scoped, deletion-capped
  patterns for the object-store half; the DB half is FK-cascade from `course_modules`.
- The 12f backups section must record the concrete backup-retention window and confirm it aligns with this
  policy (bounded residual retention).
- No schema change in Stage 12 for this decision.

## Linked documents
- Stage spec: [[specs/stage-12/12-release-hardening]]
- Findings: [[steps/findings-12]]
- Architecture: [[architecture/storage]] · [[architecture/transcript-lifecycle]]
- Roadmap watchlist: [[roadmap]] (transcript retention/deletion policy — before any real-student deployment)
