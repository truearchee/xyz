from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.admin.dev_reseed import (
    DevReseedError,
    EXPECTED_ALEMBIC_VERSION,
    LAB_FIXTURE_DUE_AT,
    LAB_FIXTURE_NOTEBOOK_BYTES,
    LAB_FIXTURE_PDF_BYTES,
    REFERENCE_COURSE_END_DATE,
    REFERENCE_COURSE_START_DATE,
    REFERENCE_GENERATED_SECTION_COUNT,
    REFERENCE_QUIZ_DAY,
    REFERENCE_WEEK_START_DAY,
    assert_reseed_preconditions,
    reseed_dev_modules,
)
from app.platform.db.models import (
    AppUser,
    CourseMembership,
    CourseModule,
    IngestionJob,
    ModuleSection,
    SectionAsset,
    Transcript,
)
from app.platform.storage.base import StoredObject


class FakeStorageProvider:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    async def put_object(
        self,
        *,
        key: str,
        content,
        content_type: str,
        content_length: int,
        metadata: dict[str, str] | None = None,
        overwrite: bool = False,
    ) -> StoredObject:
        content.seek(0)
        self.objects[key] = content.read()
        return StoredObject(key=key, size=content_length, content_type=content_type)

    async def get_object(self, *, key: str) -> bytes:
        return self.objects[key]

    async def delete_object(self, *, key: str) -> None:
        self.deleted.append(key)
        self.objects.pop(key, None)

    async def list_objects(self, *, prefix: str, max_objects: int):
        return []

    async def create_signed_read_url(self, *, key: str, expires_in_seconds: int) -> str:
        return f"https://storage.example/{key}?ttl={expires_in_seconds}"


async def _create_user(
    session: AsyncSession,
    *,
    email: str,
    role: str = "student",
) -> AppUser:
    user = AppUser(
        auth_provider_id=f"provider-{uuid4()}",
        email=email,
        full_name="Dev Reseed User",
        role=role,
        is_active=True,
        timezone="UTC",
    )
    session.add(user)
    await session.flush()
    return user


async def _create_legacy_module(
    session: AsyncSession,
    *,
    owner: AppUser,
    student: AppUser,
) -> CourseModule:
    module = CourseModule(
        title="Legacy Module",
        description="Created before Stage 5.5",
        owner_id=owner.id,
        timezone="UTC",
        starts_on=None,
        ends_on=None,
        is_active=True,
    )
    session.add(module)
    await session.flush()
    session.add_all(
        [
            CourseMembership(user_id=owner.id, module_id=module.id, role="lecturer"),
            CourseMembership(user_id=student.id, module_id=module.id, role="student"),
        ]
    )
    await session.flush()
    for index, (title, section_type) in enumerate(
        [
            ("Lecture 1", "lecture"),
            ("Lecture 2", "lecture"),
            ("Lab 1", "lab"),
            ("Assignment 1", "assignment"),
        ]
    ):
        session.add(
            ModuleSection(
                course_module_id=module.id,
                title=title,
                type=section_type,
                order_index=index,
                week_number=None,
                session_date=None,
                publish_status="draft",
                status="active",
            )
        )
    await session.flush()
    return module


@pytest.mark.anyio
async def test_reseed_replaces_legacy_modules_with_reference_schedule_and_assets(
    db_session: AsyncSession,
) -> None:
    lecturer = await _create_user(
        db_session,
        email="dev-reseed-lecturer@example.com",
        role="lecturer",
    )
    student = await _create_user(db_session, email="dev-reseed-student@example.com")
    legacy = await _create_legacy_module(db_session, owner=lecturer, student=student)
    old_module_id = legacy.id
    fake_storage = FakeStorageProvider()

    summary = await reseed_dev_modules(db_session, storage_provider=fake_storage)

    assert summary.modules_replaced == 1
    assert summary.modules_recreated == 1
    assert summary.sections_deleted == 4
    assert summary.sections_generated == REFERENCE_GENERATED_SECTION_COUNT
    old_module_count = await db_session.scalar(
        select(func.count()).select_from(CourseModule).where(CourseModule.id == old_module_id)
    )
    assert old_module_count == 0

    module = (await db_session.execute(select(CourseModule))).scalar_one()
    assert module.title == "Legacy Module"
    assert module.description == "Created before Stage 5.5"
    assert module.owner_id == lecturer.id
    assert module.starts_on == REFERENCE_COURSE_START_DATE
    assert module.ends_on == REFERENCE_COURSE_END_DATE
    assert module.week_start_day == REFERENCE_WEEK_START_DAY
    assert module.quiz_day == REFERENCE_QUIZ_DAY

    sections = (
        await db_session.execute(
            select(ModuleSection)
            .where(ModuleSection.course_module_id == module.id)
            .order_by(ModuleSection.order_index)
        )
    ).scalars().all()
    assert len(sections) == REFERENCE_GENERATED_SECTION_COUNT
    assert all(section.week_number is not None for section in sections)
    assert all(section.session_date is not None for section in sections)
    assert [section.title for section in sections[:2]] == [
        "Lecture \u2014 Week 1 (Mon 11 May)",
        "Lecture \u2014 Week 1 (Tue 12 May)",
    ]
    assert not any(section.title in {"Lecture 1", "Lecture 2", "Lab 1", "Assignment 1"} for section in sections)

    memberships = (
        await db_session.execute(
            select(CourseMembership).where(CourseMembership.module_id == module.id)
        )
    ).scalars().all()
    assert {(membership.user_id, membership.role, membership.status) for membership in memberships} == {
        (lecturer.id, "lecturer", "active"),
        (student.id, "student", "active"),
    }

    lab = await db_session.get(ModuleSection, summary.lab_fixture.lab_section_id)
    assert lab is not None
    assert lab.type == "lab"
    assert lab.publish_status == "published"
    assert lab.due_at == LAB_FIXTURE_DUE_AT

    assets = (
        await db_session.execute(
            select(SectionAsset)
            .where(SectionAsset.module_section_id == lab.id)
            .order_by(SectionAsset.file_name)
        )
    ).scalars().all()
    assert [(asset.file_name, asset.asset_kind, asset.processing_status) for asset in assets] == [
        ("stage-55-reference-lab.ipynb", "attachment", "completed"),
        ("stage-55-reference-lab.pdf", "processable", "completed"),
    ]
    assert fake_storage.objects[summary.lab_fixture.pdf_storage_key] == LAB_FIXTURE_PDF_BYTES
    assert fake_storage.objects[summary.lab_fixture.notebook_storage_key] == LAB_FIXTURE_NOTEBOOK_BYTES

    transcript_count = await db_session.scalar(select(func.count()).select_from(Transcript))
    ingestion_count = await db_session.scalar(select(func.count()).select_from(IngestionJob))
    assert transcript_count == 0
    assert ingestion_count == 0


@pytest.mark.anyio
async def test_reseed_refuses_empty_module_set(db_session: AsyncSession) -> None:
    with pytest.raises(DevReseedError, match="No dev modules found"):
        await reseed_dev_modules(db_session, storage_provider=FakeStorageProvider())


@pytest.mark.anyio
async def test_reseed_preconditions_require_confirmation_and_safe_context(
    db_session: AsyncSession,
    migrated_test_database: str,
) -> None:
    with pytest.raises(DevReseedError, match="without --confirm-dev-reseed"):
        await assert_reseed_preconditions(
            db_session,
            confirmed=False,
            database_url=migrated_test_database,
            environment="development",
        )

    with pytest.raises(DevReseedError, match="production or staging"):
        await assert_reseed_preconditions(
            db_session,
            confirmed=True,
            database_url=migrated_test_database,
            environment="production",
        )

    with pytest.raises(DevReseedError, match="non-local database host"):
        await assert_reseed_preconditions(
            db_session,
            confirmed=True,
            database_url="postgresql+asyncpg://user:pass@db.example.com/xyz_lms",
            environment="development",
        )

    await assert_reseed_preconditions(
        db_session,
        confirmed=True,
        database_url=migrated_test_database,
        environment="development",
        allow_remote_db=True,
    )

    version = (
        await db_session.execute(text("SELECT version_num FROM alembic_version"))
    ).scalar_one()
    assert version == EXPECTED_ALEMBIC_VERSION
