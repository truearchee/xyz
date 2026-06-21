"""Reconcile gamification badges against the event log (Stage 10 — DEV / VERIFICATION tool, NOT a
product path).

Re-derives, purely from each student's events + schedule + Stage 9 snapshots, the badge set on-read
evaluation WOULD award (``service.compute_expected_badges`` — the SAME code the live read uses), and
compares it to the stored ``student_badges`` rows. This is the proof that badges are "reproducible from
events" and that on-read awarding is not silently dropping anything.

Because awards are STICKY (never revoked even if data later changes), the invariant checked is:
    stored ⊇ currently-qualified            (no MISSING award is drift / a bug)
A stored badge that is no longer currently-qualified is EXPECTED (stickiness / changed data) and is
reported as informational, never a failure.

Usage:
    docker compose ... run --rm backend python scripts/reconcile_gamification.py            # all students
    docker compose ... run --rm backend python scripts/reconcile_gamification.py --student-id <uuid>
Exits non-zero if any student is missing a badge they currently qualify for.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import os
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.domains.gamification.service import compute_expected_badges
from app.platform.db.models import StudentActivityEvent, StudentBadge


@dataclass(frozen=True)
class StudentReconcileResult:
    student_id: UUID
    stored: set
    expected: set
    missing: set  # qualified-from-events but NOT stored → drift (bug)
    extra: set    # stored but not currently qualified → acceptable (sticky / changed data)


async def reconcile_student(db, *, student_id: UUID, now_utc: datetime) -> StudentReconcileResult:
    stored_rows = (
        await db.scalars(select(StudentBadge).where(StudentBadge.student_id == student_id))
    ).all()
    stored = {(row.badge_key, row.scope_type, row.scope_id) for row in stored_rows}
    expected = await compute_expected_badges(db, student_id=student_id, now_utc=now_utc)
    return StudentReconcileResult(
        student_id=student_id,
        stored=stored,
        expected=expected,
        missing=expected - stored,
        extra=stored - expected,
    )


async def _student_ids(db, student_id: UUID | None) -> list[UUID]:
    if student_id is not None:
        return [student_id]
    # All students who have any activity event or any stored badge.
    event_ids = (await db.scalars(select(StudentActivityEvent.student_id).distinct())).all()
    badge_ids = (await db.scalars(select(StudentBadge.student_id).distinct())).all()
    return sorted(set(event_ids) | set(badge_ids), key=str)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile gamification badges against events.")
    parser.add_argument("--student-id", type=UUID, default=None)
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    now_utc = datetime.now(UTC)
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    drift = 0
    try:
        async with session_factory() as db:
            for student_id in await _student_ids(db, args.student_id):
                result = await reconcile_student(db, student_id=student_id, now_utc=now_utc)
                if result.missing:
                    drift += 1
                    print(f"DRIFT student={student_id} missing={sorted(result.missing)}")
                elif result.extra:
                    print(f"ok    student={student_id} (sticky extras={len(result.extra)})")
                else:
                    print(f"ok    student={student_id} ({len(result.stored)} badges)")
    finally:
        await engine.dispose()

    if drift:
        raise SystemExit(f"reconcile FAILED: {drift} student(s) missing currently-qualified badges")
    print("reconcile OK: stored badges reproduce on-read evaluation for every student")


if __name__ == "__main__":
    asyncio.run(main())
