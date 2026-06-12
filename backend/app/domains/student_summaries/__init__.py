"""Student-facing summary read surface (Stage 4.7).

This domain owns the SECURITY BOUNDARY for exposing AI-generated summaries to students:

  - ``policy``      — ``StudentSummaryAccessPolicy``: the §5 access × availability decision (role gate
                      before any resource lookup; visible/not). The security decision lives here.
  - ``precedence``  — the §6 per-slot state precedence as a PURE function. The trickiest correctness
                      point: corruption (id-match + checksum-mismatch → UNAVAILABLE+log) is kept DISTINCT
                      from supersession (no row for the active transcript → GENERATING).
  - ``markdown``    — server-side shaping of the stored summary ``content_json`` into a sanitized-render
                      markdown string (§3.3: no structured detailed rendering on the client).
  - ``schemas``     — student-reachable response models that are structurally incapable of serializing
                      transcript text / provenance / job internals (§8.3 hygiene).
  - ``service``     — orchestration: student-only context → scoped query → §4 identity guard → §6
                      precedence → DTO; pinned 404 body for zero-visible-rows.

Reads run through ``platform/query/student_summary_read`` (read models only — rule 8). 4.6 decides what
is active; 4.7 reads the marker (rule 8 — a filter, not new write logic).
"""
