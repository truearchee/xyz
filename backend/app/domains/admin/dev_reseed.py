from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from io import BytesIO
from uuid import UUID

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.domains.admin.schemas import (
    CreateModuleRequest,
    ModuleScheduleInput,
    SessionPatternEntry,
)
from app.domains.admin.service import create_module
from app.domains.content.validators import NOTEBOOK_MIME_TYPE, PDF_MIME_TYPE
from app.platform.auth.context import CurrentUserContext
from app.platform.db.models import (
    AIRequestLog,
    CourseMembership,
    CourseModule,
    GeneratedLectureSummary,
    IngestionJob,
    ModuleSection,
    SectionAsset,
    Transcript,
    TranscriptChunk,
    TranscriptSegment,
)
from app.platform.storage.base import StorageProvider
from app.platform.storage.keys import generate_section_asset_storage_key


EXPECTED_ALEMBIC_VERSION = "0022"
REFERENCE_COURSE_START_DATE = date(2026, 5, 11)
REFERENCE_COURSE_END_DATE = date(2026, 6, 26)
REFERENCE_WEEK_START_DAY = "monday"
REFERENCE_QUIZ_DAY = "friday"
REFERENCE_SESSION_PATTERN: tuple[dict[str, str], ...] = (
    {"weekday": "monday", "sectionType": "lecture"},
    {"weekday": "tuesday", "sectionType": "lecture"},
    {"weekday": "wednesday", "sectionType": "lecture"},
    {"weekday": "thursday", "sectionType": "lab"},
)
REFERENCE_GENERATED_SECTION_COUNT = 28
LAB_FIXTURE_DUE_AT = datetime(2026, 6, 26, 17, 0, tzinfo=UTC)
LAB_FIXTURE_PDF_BYTES = b"%PDF-1.7\n% Stage 5.5d dev lab fixture\n"
LAB_FIXTURE_NOTEBOOK_BYTES = (
    b'{"cells":[],"metadata":{"language_info":{"name":"python"}},'
    b'"nbformat":4,"nbformat_minor":5}\n'
)
LAB_FIXTURE_PDF_NAME = "stage-55-reference-lab.pdf"
LAB_FIXTURE_NOTEBOOK_NAME = "stage-55-reference-lab.ipynb"

_LOCAL_DATABASE_HOSTS = {"", "localhost", "127.0.0.1", "::1", "db", "postgres"}


class DevReseedError(RuntimeError):
    pass


@dataclass(frozen=True)
class MembershipSnapshot:
    user_id: UUID
    role: str
    status: str
    archived_at: datetime | None


@dataclass(frozen=True)
class ModuleSnapshot:
    id: UUID
    title: str
    description: str | None
    owner_id: UUID
    timezone: str
    is_active: bool
    memberships: tuple[MembershipSnapshot, ...]


@dataclass(frozen=True)
class LabFixtureSummary:
    module_id: UUID
    lab_section_id: UUID
    pdf_asset_id: UUID
    notebook_asset_id: UUID
    pdf_storage_key: str
    notebook_storage_key: str


@dataclass(frozen=True)
class DevReseedSummary:
    modules_replaced: int
    modules_recreated: int
    sections_deleted: int
    sections_generated: int
    memberships_restored: int
    lab_fixture: LabFixtureSummary

    def to_jsonable(self) -> dict:
        return asdict(self)


async def assert_reseed_preconditions(
    db: AsyncSession,
    *,
    confirmed: bool,
    database_url: str | None,
    environment: str,
    allow_remote_db: bool = False,
) -> None:
    if not confirmed:
        raise DevReseedError("Refusing dev reseed without --confirm-dev-reseed")
    if environment.strip().lower() in {"production", "staging"}:
        raise DevReseedError("Refusing dev reseed in production or staging")
    _assert_safe_database_url(database_url, allow_remote_db=allow_remote_db)

    versions = (
        await db.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num"))
    ).scalars().all()
    if versions != [EXPECTED_ALEMBIC_VERSION]:
        found = ", ".join(versions) if versions else "<none>"
        raise DevReseedError(
            f"Dev reseed requires Alembic {EXPECTED_ALEMBIC_VERSION}; found {found}"
        )


async def reseed_dev_modules(
    db: AsyncSession,
    *,
    storage_provider: StorageProvider,
) -> DevReseedSummary:
    snapshots = await _snapshot_modules(db)
    if not snapshots:
        raise DevReseedError("No dev modules found to reseed")

    uploaded_keys: list[str] = []
    try:
        deleted_counts = await _delete_snapshot_modules(db, [snapshot.id for snapshot in snapshots])
        created_modules, memberships_restored = await _recreate_modules(db, snapshots)
        fixture = await _seed_lab_fixture(
            db,
            storage_provider=storage_provider,
            modules=created_modules,
            uploaded_keys=uploaded_keys,
        )
        sections_generated = await _count_generated_sections(
            db,
            module_ids=[module.id for module in created_modules],
        )
        summary = DevReseedSummary(
            modules_replaced=len(snapshots),
            modules_recreated=len(created_modules),
            sections_deleted=deleted_counts.get("module_sections", 0),
            sections_generated=sections_generated,
            memberships_restored=memberships_restored,
            lab_fixture=fixture,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        for key in uploaded_keys:
            try:
                await storage_provider.delete_object(key=key)
            except Exception:
                pass
        raise

    return summary


def reference_schedule_input() -> ModuleScheduleInput:
    return ModuleScheduleInput(
        course_start_date=REFERENCE_COURSE_START_DATE,
        course_end_date=REFERENCE_COURSE_END_DATE,
        week_start_day=REFERENCE_WEEK_START_DAY,
        session_pattern=[
            SessionPatternEntry(weekday=entry["weekday"], section_type=entry["sectionType"])
            for entry in REFERENCE_SESSION_PATTERN
        ],
        quiz_day=REFERENCE_QUIZ_DAY,
    )


def _assert_safe_database_url(
    database_url: str | None,
    *,
    allow_remote_db: bool,
) -> None:
    if not database_url:
        raise DevReseedError("DATABASE_URL is required for dev reseed")

    url = make_url(database_url)
    host = (url.host or "").lower()
    database = (url.database or "").lower()
    if any(token in database for token in ("prod", "production", "staging")):
        raise DevReseedError("Refusing dev reseed against production/staging-looking database")
    if not allow_remote_db and host not in _LOCAL_DATABASE_HOSTS:
        raise DevReseedError(
            f"Refusing dev reseed against non-local database host {host!r}"
        )


async def _snapshot_modules(db: AsyncSession) -> list[ModuleSnapshot]:
    modules = (
        await db.execute(select(CourseModule).order_by(CourseModule.title, CourseModule.id))
    ).scalars().all()
    if not modules:
        return []

    memberships = (
        await db.execute(
            select(CourseMembership)
            .where(CourseMembership.module_id.in_([module.id for module in modules]))
            .order_by(CourseMembership.module_id, CourseMembership.created_at, CourseMembership.id)
        )
    ).scalars().all()
    memberships_by_module: dict[UUID, list[MembershipSnapshot]] = {}
    for membership in memberships:
        memberships_by_module.setdefault(membership.module_id, []).append(
            MembershipSnapshot(
                user_id=membership.user_id,
                role=membership.role,
                status=membership.status,
                archived_at=membership.archived_at,
            )
        )

    return [
        ModuleSnapshot(
            id=module.id,
            title=module.title,
            description=module.description,
            owner_id=module.owner_id,
            timezone=module.timezone,
            is_active=module.is_active,
            memberships=tuple(memberships_by_module.get(module.id, ())),
        )
        for module in modules
    ]


async def _delete_snapshot_modules(
    db: AsyncSession,
    module_ids: list[UUID],
) -> dict[str, int]:
    section_ids = select(ModuleSection.id).where(ModuleSection.course_module_id.in_(module_ids))
    transcript_ids = select(Transcript.id).where(Transcript.module_section_id.in_(section_ids))
    ingestion_job_ids = select(IngestionJob.id).where(IngestionJob.transcript_id.in_(transcript_ids))

    await db.execute(
        update(Transcript)
        .where(Transcript.replacement_of_transcript_id.in_(transcript_ids))
        .values(replacement_of_transcript_id=None)
    )
    await db.execute(
        update(Transcript)
        .where(Transcript.superseded_by_transcript_id.in_(transcript_ids))
        .values(superseded_by_transcript_id=None)
    )

    counts: dict[str, int] = {}
    counts["generated_lecture_summaries"] = await _delete_count(
        db,
        delete(GeneratedLectureSummary).where(
            GeneratedLectureSummary.module_section_id.in_(section_ids)
        ),
    )
    counts["ai_request_logs"] = await _delete_count(
        db,
        delete(AIRequestLog).where(AIRequestLog.ingestion_job_id.in_(ingestion_job_ids)),
    )
    counts["transcript_chunks"] = await _delete_count(
        db,
        delete(TranscriptChunk).where(TranscriptChunk.transcript_id.in_(transcript_ids)),
    )
    counts["transcript_segments"] = await _delete_count(
        db,
        delete(TranscriptSegment).where(TranscriptSegment.transcript_id.in_(transcript_ids)),
    )
    counts["ingestion_jobs"] = await _delete_count(
        db,
        delete(IngestionJob).where(IngestionJob.transcript_id.in_(transcript_ids)),
    )
    counts["transcripts"] = await _delete_count(
        db,
        delete(Transcript).where(Transcript.module_section_id.in_(section_ids)),
    )
    counts["section_assets"] = await _delete_count(
        db,
        delete(SectionAsset).where(SectionAsset.module_section_id.in_(section_ids)),
    )
    counts["course_memberships"] = await _delete_count(
        db,
        delete(CourseMembership).where(CourseMembership.module_id.in_(module_ids)),
    )
    counts["module_sections"] = await _delete_count(
        db,
        delete(ModuleSection).where(ModuleSection.course_module_id.in_(module_ids)),
    )
    counts["course_modules"] = await _delete_count(
        db,
        delete(CourseModule).where(CourseModule.id.in_(module_ids)),
    )
    return counts


async def _delete_count(db: AsyncSession, statement) -> int:
    result = await db.execute(statement)
    return int(result.rowcount or 0)


async def _recreate_modules(
    db: AsyncSession,
    snapshots: list[ModuleSnapshot],
) -> tuple[list[CourseModule], int]:
    created_modules: list[CourseModule] = []
    memberships_restored = 0
    current_user = _reseed_admin_context()
    for snapshot in snapshots:
        module = await create_module(
            db,
            CreateModuleRequest(
                title=snapshot.title,
                description=snapshot.description,
                owner_id=snapshot.owner_id,
                timezone=snapshot.timezone,
                schedule=reference_schedule_input(),
            ),
            current_user,
        )
        module.is_active = snapshot.is_active
        created_modules.append(module)
        memberships_restored += await _restore_memberships(db, module=module, snapshot=snapshot)

    await db.flush()
    return created_modules, memberships_restored


async def _restore_memberships(
    db: AsyncSession,
    *,
    module: CourseModule,
    snapshot: ModuleSnapshot,
) -> int:
    restored = 0
    for membership in snapshot.memberships:
        if (
            membership.user_id == module.owner_id
            and membership.role == "lecturer"
            and membership.status == "active"
        ):
            continue
        db.add(
            CourseMembership(
                user_id=membership.user_id,
                module_id=module.id,
                role=membership.role,
                status=membership.status,
                archived_at=membership.archived_at,
            )
        )
        restored += 1
    return restored


def _reseed_admin_context() -> CurrentUserContext:
    return CurrentUserContext(
        user_id=uuid7(),
        auth_provider_id="dev-reseed",
        email="dev-reseed@example.invalid",
        full_name="Dev Reseed",
        role="admin",
        is_active=True,
        timezone="UTC",
    )


async def _seed_lab_fixture(
    db: AsyncSession,
    *,
    storage_provider: StorageProvider,
    modules: list[CourseModule],
    uploaded_keys: list[str],
) -> LabFixtureSummary:
    active_modules = [module for module in modules if module.is_active]
    if not active_modules:
        raise DevReseedError("No active recreated module available for the lab fixture")

    module = active_modules[0]
    lab = await db.scalar(
        select(ModuleSection)
        .where(
            ModuleSection.course_module_id == module.id,
            ModuleSection.type == "lab",
            ModuleSection.status == "active",
        )
        .order_by(ModuleSection.order_index)
        .limit(1)
        .with_for_update()
    )
    if lab is None:
        raise DevReseedError("No generated lab section available for the lab fixture")

    lab.publish_status = "published"
    lab.due_at = LAB_FIXTURE_DUE_AT
    lab.updated_at = datetime.now(UTC)

    pdf_asset = await _store_asset(
        db,
        storage_provider=storage_provider,
        module=module,
        lab=lab,
        uploaded_keys=uploaded_keys,
        file_name=LAB_FIXTURE_PDF_NAME,
        mime_type=PDF_MIME_TYPE,
        content=LAB_FIXTURE_PDF_BYTES,
        asset_kind="processable",
        extension=".pdf",
    )
    notebook_asset = await _store_asset(
        db,
        storage_provider=storage_provider,
        module=module,
        lab=lab,
        uploaded_keys=uploaded_keys,
        file_name=LAB_FIXTURE_NOTEBOOK_NAME,
        mime_type=NOTEBOOK_MIME_TYPE,
        content=LAB_FIXTURE_NOTEBOOK_BYTES,
        asset_kind="attachment",
        extension=".ipynb",
    )

    return LabFixtureSummary(
        module_id=module.id,
        lab_section_id=lab.id,
        pdf_asset_id=pdf_asset.id,
        notebook_asset_id=notebook_asset.id,
        pdf_storage_key=pdf_asset.storage_key,
        notebook_storage_key=notebook_asset.storage_key,
    )


async def _store_asset(
    db: AsyncSession,
    *,
    storage_provider: StorageProvider,
    module: CourseModule,
    lab: ModuleSection,
    uploaded_keys: list[str],
    file_name: str,
    mime_type: str,
    content: bytes,
    asset_kind: str,
    extension: str,
) -> SectionAsset:
    asset_id = uuid7()
    storage_key = generate_section_asset_storage_key(
        module_id=module.id,
        section_id=lab.id,
        asset_id=asset_id,
        extension=extension,
    )
    await storage_provider.put_object(
        key=storage_key,
        content=BytesIO(content),
        content_type=mime_type,
        content_length=len(content),
        metadata={"asset_id": str(asset_id), "section_id": str(lab.id)},
        overwrite=False,
    )
    uploaded_keys.append(storage_key)

    asset = SectionAsset(
        id=asset_id,
        module_section_id=lab.id,
        storage_key=storage_key,
        file_name=file_name,
        mime_type=mime_type,
        file_size=len(content),
        checksum_sha256=sha256(content).hexdigest(),
        asset_kind=asset_kind,
        processing_status="completed",
        uploaded_by_user_id=module.owner_id,
    )
    db.add(asset)
    return asset


async def _count_generated_sections(db: AsyncSession, *, module_ids: list[UUID]) -> int:
    count = await db.scalar(
        select(func.count())
        .select_from(ModuleSection)
        .where(
            ModuleSection.course_module_id.in_(module_ids),
            ModuleSection.week_number.is_not(None),
            ModuleSection.session_date.is_not(None),
        )
    )
    return int(count or 0)


async def assert_reseed_shape(db: AsyncSession, *, summary: DevReseedSummary) -> dict[str, int]:
    module_count = await db.scalar(select(func.count()).select_from(CourseModule))
    schedule_count = await db.scalar(
        select(func.count())
        .select_from(CourseModule)
        .where(
            CourseModule.starts_on == REFERENCE_COURSE_START_DATE,
            CourseModule.ends_on == REFERENCE_COURSE_END_DATE,
            CourseModule.week_start_day == REFERENCE_WEEK_START_DAY,
            CourseModule.quiz_day == REFERENCE_QUIZ_DAY,
        )
    )
    section_count = await db.scalar(select(func.count()).select_from(ModuleSection))
    stamped_section_count = await db.scalar(
        select(func.count())
        .select_from(ModuleSection)
        .where(
            ModuleSection.week_number.is_not(None),
            ModuleSection.session_date.is_not(None),
        )
    )
    legacy_title_count = await db.scalar(
        select(func.count())
        .select_from(ModuleSection)
        .where(ModuleSection.title.in_(["Lecture 1", "Lecture 2", "Lab 1", "Assignment 1"]))
    )
    fixture_asset_count = await db.scalar(
        select(func.count())
        .select_from(SectionAsset)
        .where(
            SectionAsset.module_section_id == summary.lab_fixture.lab_section_id,
            SectionAsset.asset_kind.in_(["processable", "attachment"]),
        )
    )
    return {
        "module_count": int(module_count or 0),
        "reference_schedule_module_count": int(schedule_count or 0),
        "section_count": int(section_count or 0),
        "stamped_section_count": int(stamped_section_count or 0),
        "legacy_template_title_count": int(legacy_title_count or 0),
        "fixture_asset_count": int(fixture_asset_count or 0),
    }
