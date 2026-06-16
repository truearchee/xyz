from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.db.models import AppUser, CourseModule, ModuleSection
from app.platform.query.section_week_resolver import resolve_sections_by_weeks


async def _create_owner(session: AsyncSession) -> AppUser:
    owner = AppUser(
        auth_provider_id=f"provider-{uuid4()}",
        email=f"section-week-{uuid4()}@example.com",
        full_name="Section Week Owner",
        role="lecturer",
        is_active=True,
        timezone="UTC",
    )
    session.add(owner)
    await session.flush()
    return owner


async def _create_module(session: AsyncSession, *, owner_id) -> CourseModule:
    module = CourseModule(
        title="Resolver Module",
        owner_id=owner_id,
        timezone="UTC",
        starts_on=date(2026, 5, 11),
        week_start_day="monday",
        is_active=True,
    )
    session.add(module)
    await session.flush()
    return module


async def _create_section(
    session: AsyncSession,
    *,
    module_id,
    title: str,
    section_type: str = "lecture",
    order_index: int,
    week_number: int | None,
    session_date: date | None,
    publish_status: str = "draft",
    status: str = "active",
) -> ModuleSection:
    section = ModuleSection(
        course_module_id=module_id,
        title=title,
        type=section_type,
        order_index=order_index,
        week_number=week_number,
        session_date=session_date,
        publish_status=publish_status,
        status=status,
    )
    session.add(section)
    await session.flush()
    return section


@pytest.mark.anyio
async def test_resolver_default_excludes_unstamped_and_uses_stored_week(
    db_session: AsyncSession,
) -> None:
    owner = await _create_owner(db_session)
    module = await _create_module(db_session, owner_id=owner.id)
    week1_lecture = await _create_section(
        db_session,
        module_id=module.id,
        title="Week 1 Lecture",
        order_index=2,
        week_number=1,
        session_date=date(2026, 5, 12),
    )
    week1_lab = await _create_section(
        db_session,
        module_id=module.id,
        title="Week 1 Lab",
        section_type="lab",
        order_index=1,
        week_number=1,
        session_date=date(2026, 5, 14),
        publish_status="unpublished",
    )
    stored_week_wins = await _create_section(
        db_session,
        module_id=module.id,
        title="Stored Week 1, Date Looks Later",
        order_index=3,
        week_number=1,
        session_date=date(2026, 5, 28),
    )
    await _create_section(
        db_session,
        module_id=module.id,
        title="Week 2 Lecture",
        order_index=4,
        week_number=2,
        session_date=date(2026, 5, 18),
    )
    await _create_section(
        db_session,
        module_id=module.id,
        title="Null Week",
        order_index=5,
        week_number=None,
        session_date=date(2026, 5, 19),
    )
    await _create_section(
        db_session,
        module_id=module.id,
        title="Null Date",
        order_index=6,
        week_number=1,
        session_date=None,
    )
    await _create_section(
        db_session,
        module_id=module.id,
        title="Assignment",
        section_type="assignment",
        order_index=7,
        week_number=1,
        session_date=date(2026, 5, 13),
    )

    rows = await resolve_sections_by_weeks(db_session, module_id=module.id, covered_weeks=[1])
    week3_rows = await resolve_sections_by_weeks(db_session, module_id=module.id, covered_weeks=[3])

    assert [row.id for row in rows] == [
        week1_lecture.id,
        week1_lab.id,
        stored_week_wins.id,
    ]
    assert rows[1].publish_status == "unpublished"
    assert week3_rows == []


@pytest.mark.anyio
async def test_resolver_include_unstamped_is_admin_curation_mode(
    db_session: AsyncSession,
) -> None:
    owner = await _create_owner(db_session)
    module = await _create_module(db_session, owner_id=owner.id)
    stamped = await _create_section(
        db_session,
        module_id=module.id,
        title="Stamped",
        order_index=1,
        week_number=1,
        session_date=date(2026, 5, 11),
    )
    later_week = await _create_section(
        db_session,
        module_id=module.id,
        title="Later Week",
        section_type="lab",
        order_index=2,
        week_number=2,
        session_date=date(2026, 5, 18),
    )
    null_week = await _create_section(
        db_session,
        module_id=module.id,
        title="Null Week",
        order_index=3,
        week_number=None,
        session_date=date(2026, 5, 19),
    )
    null_date = await _create_section(
        db_session,
        module_id=module.id,
        title="Null Date",
        order_index=4,
        week_number=1,
        session_date=None,
    )
    assignment = await _create_section(
        db_session,
        module_id=module.id,
        title="Assignment",
        section_type="assignment",
        order_index=5,
        week_number=1,
        session_date=date(2026, 5, 13),
    )
    archived = await _create_section(
        db_session,
        module_id=module.id,
        title="Archived",
        section_type="lab",
        order_index=6,
        week_number=1,
        session_date=date(2026, 5, 14),
        status="archived",
    )

    rows = await resolve_sections_by_weeks(
        db_session,
        module_id=module.id,
        covered_weeks=[1],
        include_unstamped=True,
    )

    assert {row.id for row in rows} == {
        stamped.id,
        later_week.id,
        null_week.id,
        null_date.id,
    }
    assert assignment.id not in {row.id for row in rows}
    assert archived.id not in {row.id for row in rows}


@pytest.mark.anyio
async def test_resolver_rejects_non_positive_weeks(db_session: AsyncSession) -> None:
    owner = await _create_owner(db_session)
    module = await _create_module(db_session, owner_id=owner.id)

    with pytest.raises(ValueError, match="positive"):
        await resolve_sections_by_weeks(db_session, module_id=module.id, covered_weeks=[0])
