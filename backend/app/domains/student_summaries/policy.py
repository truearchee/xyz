"""StudentSummaryAccessPolicy (Stage 4.7 §5) — the access × availability security decision.

The decision lives HERE, explicitly, not smeared into the read layer (ADR-4.7-6). Two gates:

  Row R — a non-student caller (lecturer/admin) on the student surface → 403, fired BEFORE any
          resource lookup, so it leaks nothing about specific resources ("wrong surface"). No
          "preview as student" (D3, ratified).
  Rows D/P/I — a student with NO visible section (unpublished / not a member of the module / inactive
          membership) → 404 with a SINGLE pinned, byte-identical body. Unpublished, other-module, and
          inactive-membership are indistinguishable (S2). Visibility is what the scoped query returns;
          this gate never fetches-then-branches.

Rows 1–6 / T (the summary STATE) are decided by ``precedence``; row A (401 unauthenticated) is the auth
dependency's job.
"""

from __future__ import annotations

from fastapi import HTTPException, status

# 403 row R — wrong surface for a non-student. Generic on purpose (no resource info).
STUDENT_SUMMARY_FORBIDDEN = "STUDENT_SUMMARY_FORBIDDEN"
# 404 rows D/P/I — ONE pinned, identical body for unpublished / not-member / inactive.
SECTION_NOT_FOUND = "SECTION_NOT_FOUND"


def _coded_error(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=code)


class StudentSummaryAccessPolicy:
    """Pure access gates — no DB, no I/O. Unit-testable row by row."""

    @staticmethod
    def require_student(role: str) -> None:
        """Row R: only a student may use the student summary surface. 403 before any lookup."""
        if role != "student":
            raise _coded_error(status.HTTP_403_FORBIDDEN, STUDENT_SUMMARY_FORBIDDEN)

    @staticmethod
    def require_visible(visible_section: object | None) -> object:
        """Rows D/P/I: a missing scoped row ⇒ 404 with the pinned identical body. Never 403 here."""
        if visible_section is None:
            raise _coded_error(status.HTTP_404_NOT_FOUND, SECTION_NOT_FOUND)
        return visible_section
