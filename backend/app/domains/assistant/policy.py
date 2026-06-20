"""Assistant access gates (Stage 8.1).

Same shape as the 4.7 StudentSummaryAccessPolicy but reimplemented locally so the assistant domain
does not import another domain (rule 8). The visibility READ it pairs with —
``get_visible_student_section`` — lives in ``platform/query`` and is shared. Two gates:

  - ``require_student`` → 403 BEFORE any resource lookup (wrong surface for a non-student).
  - a missing visible section / non-owned conversation → 404 with a pinned body (never 403), so
    unpublished / not-a-member / not-owner / lost-access are indistinguishable (decision 5).

(Open item, recorded in the plan: these gates are generic enough to promote to ``platform/auth``.)
"""

from __future__ import annotations

from fastapi import HTTPException, status

ASSISTANT_FORBIDDEN = "ASSISTANT_FORBIDDEN"
SECTION_NOT_FOUND = "SECTION_NOT_FOUND"
MODULE_NOT_FOUND = "MODULE_NOT_FOUND"  # 8.6a: homework binds a module; a non-visible module → pinned 404
SCOPE_NOT_FOUND = "SCOPE_NOT_FOUND"  # 8.6b: exam-prep binds a scope; a non-visible scope → pinned 404
CONVERSATION_NOT_FOUND = "CONVERSATION_NOT_FOUND"
MESSAGE_NOT_FOUND = "MESSAGE_NOT_FOUND"


def require_student(role: str) -> None:
    """Only a student may use the assistant surface. 403 before any lookup (uniform on all endpoints)."""
    if role != "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ASSISTANT_FORBIDDEN)


def not_found(code: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=code)
