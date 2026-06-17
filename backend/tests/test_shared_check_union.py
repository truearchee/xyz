"""Stage 7 (D2) — the shared-CHECK union guard.

Both Stage 6 and Stage 7 widen ``ck_ai_request_logs_feature`` and
``ck_student_activity_events_event_type`` by drop-and-recreate (a CHECK is rewritten wholesale). This
test asserts the LIVE DB constraint == the model's source-of-truth tuple. If a later, parallel-stage
migration recreates a CHECK without unioning both stages' values, the earlier stage's values are
silently dropped and THIS test fails loudly at CI — the guard the reserved blocks alone cannot provide.
See knowledge/steps/findings-stage-07.md.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models.ai_request_log import AI_REQUEST_LOG_FEATURES
from app.platform.db.models.student_activity_event import STUDENT_ACTIVITY_EVENT_TYPES

pytestmark = pytest.mark.anyio


async def _check_literals(db: AsyncSession, conname: str) -> set[str]:
    constraint_def = await db.scalar(
        text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = :name"),
        {"name": conname},
    )
    assert constraint_def is not None, f"missing constraint {conname}"
    return set(re.findall(r"'([a-z_]+)'", constraint_def))


async def test_ai_request_log_feature_check_equals_model_tuple(db_session: AsyncSession) -> None:
    literals = await _check_literals(db_session, "ck_ai_request_logs_feature")
    assert literals == set(AI_REQUEST_LOG_FEATURES)
    assert "glossary_definition" in literals
    # Stage 5 values must survive the Stage 7 widening (the union property).
    assert {"summary_brief", "summary_detailed", "post_class_quiz"} <= literals


async def test_student_activity_event_type_check_equals_model_tuple(
    db_session: AsyncSession,
) -> None:
    literals = await _check_literals(db_session, "ck_student_activity_events_event_type")
    assert literals == set(STUDENT_ACTIVITY_EVENT_TYPES)
    assert {"glossary_term_saved", "glossary_practice_completed"} <= literals
    assert {"completed_quiz", "perfect_quiz_score"} <= literals
