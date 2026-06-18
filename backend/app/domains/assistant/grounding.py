"""Grounding decision (Stage 8.2, review #1).

``groundingStatus`` is BACKEND-DERIVED — never parsed from the model's prose. The only model signal is
``is_study_related`` (one structured flag); everything else (visibility, readiness, has-relevant-chunk)
is computed server-side. ``decide_grounding`` combines them in a FIXED precedence order so an unrelated
question can never become "grounded" on an accidental weak vector match: the redirect (study-relatedness)
is evaluated BEFORE the chunk match.
"""

from __future__ import annotations

# The five values of assistant_messages.grounding_status (mirrors the 0032 CHECK).
ACCESS_DENIED = "access_denied"
CONTEXT_UNAVAILABLE = "context_unavailable"
EDUCATIONAL_REDIRECT = "educational_redirect"
LECTURE_GROUNDED = "lecture_grounded"
GENERAL_NOT_FROM_LECTURE = "general_not_from_lecture"


def decide_grounding(
    *,
    section_visible: bool,
    ready: bool,
    is_study_related: bool,
    has_relevant_chunk: bool,
) -> str:
    """Return the grounding status. Order is load-bearing (review #1):

    1. not visible            → access_denied        (access lost between send and generation)
    2. not ready              → context_unavailable   (no active/embedded transcript yet)
    3. not study-related      → educational_redirect  (off-topic — redirect BEFORE any chunk match)
    4. study-related + chunk   → lecture_grounded
    5. study-related, no chunk → general_not_from_lecture
    """
    if not section_visible:
        return ACCESS_DENIED
    if not ready:
        return CONTEXT_UNAVAILABLE
    if not is_study_related:
        return EDUCATIONAL_REDIRECT
    if has_relevant_chunk:
        return LECTURE_GROUNDED
    return GENERAL_NOT_FROM_LECTURE
