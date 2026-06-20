"""Student assistant HTTP service (Stage 8.1) — orchestration over the policy gates + scoped reads.

Flow on every endpoint: student-only gate (403 before any lookup) → ownership + live access re-check
(decision 5: zero/lost access ⇒ pinned 404, never 403) → the endpoint's work. Mutations use the request
session and commit once; ``send``/``retry`` enqueue the generation job AFTER commit (a rollback can
never leave a phantom job; an enqueue failure is compensated to ``failed/enqueue_failed``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.assistant.cursor import decode_cursor, encode_cursor
from app.domains.assistant.grounding import (
    CONTEXT_UNAVAILABLE,
    GENERAL_NOT_FROM_LECTURE,
    LECTURE_GROUNDED,
)
from app.domains.assistant.policy import (
    CONVERSATION_NOT_FOUND,
    MESSAGE_NOT_FOUND,
    MODULE_NOT_FOUND,
    SECTION_NOT_FOUND,
    not_found,
    require_student,
)
from app.domains.assistant.schemas import (
    AssistantAvailabilityResponse,
    ConversationListItem,
    ConversationRead,
    CreateConversationRequest,
    MessageRead,
    SendMessageRequest,
    SendMessageResponse,
)
from app.platform.auth.context import CurrentUserContext
from app.platform.db.models import AssistantConversation, AssistantMessage, CourseModule
from app.platform.query.assistant_readiness_read import READY, get_section_assistant_readiness
from app.platform.query.student_summary_read import (
    StudentConversationListRow,
    get_visible_student_conversation_list,
    get_visible_student_module,
    get_visible_student_section,
)
from app.workers.queues import enqueue_generate_assistant_answer

LECTURE_DEFAULT = "lecture_default"
HOMEWORK_HELP = "homework_help"
TITLE_MAX_CHARS = 120

# 8.6a: per-kind chip label for the Workspace list + conversation detail (the non-editable "mode" badge).
# The four legacy kinds are all lecture-grounded general chat → "Lecture grounded" (8.4 behavior preserved).
_MODE_CHIP = {HOMEWORK_HELP: "Homework help"}


def _grounding_chip(conversation_kind: str) -> str:
    return _MODE_CHIP.get(conversation_kind, "Lecture grounded")


def _now() -> datetime:
    return datetime.now(UTC)


def _to_conversation_read(conv: AssistantConversation) -> ConversationRead:
    return ConversationRead(
        id=conv.id,
        conversation_kind=conv.conversation_kind,
        attached_section_id=conv.attached_section_id,
        attached_module_id=conv.attached_module_id,
        title=conv.title,
        title_source=conv.title_source,
        last_activity_at=conv.last_activity_at,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


def _display_title(
    *,
    title: str | None,
    title_source: str,
    section_title: str | None,
    conversation_kind: str = LECTURE_DEFAULT,
    module_title: str | None = None,
) -> str:
    """Derive-on-read title (Stage 8.4): a manual rename wins; otherwise the lecture/lab title. 8.6a: a
    module-bound homework conversation has no section, so it falls back to a mode-derived label (the module
    title). NEVER AI-generated (rule 15); old null-title 8.1 rows need no backfill."""
    if title_source == "manual" and title:
        return title
    if section_title:
        return section_title
    if conversation_kind == HOMEWORK_HELP and module_title:
        return f"Homework help · {module_title}"
    return "Untitled chat"


def _to_conversation_list_item(row: StudentConversationListRow) -> ConversationListItem:
    return ConversationListItem(
        id=row.id,
        conversation_kind=row.conversation_kind,
        display_title=_display_title(
            title=row.title,
            title_source=row.title_source,
            section_title=row.section_title,
            conversation_kind=row.conversation_kind,
            module_title=row.module_title,
        ),
        module_id=row.module_id,
        module_title=row.module_title,
        attached_section_id=row.attached_section_id,
        section_title=row.section_title,
        section_type=row.section_type,
        last_message_preview=row.last_message_preview,
        last_activity_at=row.last_activity_at,
        message_count=row.message_count,
        grounding_chip=_grounding_chip(row.conversation_kind),
    )


def _normalize_title(raw: str) -> str:
    """Plain-text, Unicode-safe, whitespace-collapsed, length-bounded. Stripped of control/format chars
    so a title can never inject markup (it renders as escaped plain text in the UI)."""
    collapsed = " ".join(raw.split())  # collapse any Unicode whitespace run → single space + trim ends
    cleaned = "".join(ch for ch in collapsed if ch.isprintable())
    return cleaned[:TITLE_MAX_CHARS].strip()


def _compose_answer_basis(msg: AssistantMessage) -> str | None:
    """The student-safe "Where did this come from?" line (Stage 8.2, review #3).

    Composed ONLY from the stored generation-time snapshot + grounding_status — never from a fresh join,
    so a later transcript replacement can't retroactively change a past answer's basis. NEVER exposes
    chunk ids, distances, checksums, prompts, or reasoning — only module/section TITLES for the grounded
    case, and static honest text otherwise. educational_redirect / access_denied carry no basis line."""
    status = msg.grounding_status
    if status == LECTURE_GROUNDED:
        snapshot = msg.context_snapshot or {}
        module_title = snapshot.get("moduleTitle")
        section_title = snapshot.get("sectionTitle")
        # 8.6a: a module-scoped homework turn grounds on the module's material with no single section.
        if snapshot.get("retrievalScope") == "module":
            if module_title:
                return f"Based on this module's material: {module_title}"
            return "Based on this module's material"
        noun = "lab" if snapshot.get("contextType") == "lab" else "lecture"
        basis_source = (
            "approved summary and retrieved context"
            if snapshot.get("approvedSummaryRefs")
            else "context"
        )
        if module_title and section_title:
            return f"Based on this {noun}'s {basis_source}: {module_title} → {section_title}"
        return f"Based on this {noun}'s {basis_source}"
    if status == GENERAL_NOT_FROM_LECTURE:
        return (
            "No relevant lecture context was found — general study knowledge, not from this lecture"
        )
    if status == CONTEXT_UNAVAILABLE:
        return "Lecture context is still being prepared"
    return None  # lecture_grounded handled above; educational_redirect / access_denied / None → no line


def _to_message_read(msg: AssistantMessage | None) -> MessageRead | None:
    if msg is None:
        return None
    return MessageRead(
        id=msg.id,
        role=msg.role,
        status=msg.status,
        content=msg.content,
        grounding_status=msg.grounding_status,
        answer_basis=_compose_answer_basis(msg),
        retryable=msg.retryable,
        failure_message=msg.failure_message_sanitized,
        created_at=msg.created_at,
    )


async def _resolve_owned_conversation(
    db: AsyncSession, *, student_id: UUID, conversation_id: UUID
) -> AssistantConversation:
    """Owner + live access re-check (decision 5). Not-owned, missing, soft-deleted, or lost-access ⇒
    pinned 404 (8.4: a soft-deleted conversation is gone for the student — direct reopen / poll 404s,
    which is what closes delete-while-pending, invariant E)."""
    conv = await db.get(AssistantConversation, conversation_id)
    if conv is None or conv.student_id != student_id:
        raise not_found(CONVERSATION_NOT_FOUND)
    if conv.deleted_at is not None:
        raise not_found(CONVERSATION_NOT_FOUND)
    # Re-validate against CURRENT permissions every load: if attached to a section that is no longer
    # published / the student no longer belongs to, the conversation is inaccessible (no messages render).
    if conv.attached_section_id is not None:
        visible = await get_visible_student_section(
            db, student_id=student_id, section_id=conv.attached_section_id
        )
        if visible is None:
            raise not_found(CONVERSATION_NOT_FOUND)
    # 8.6a: a module-bound homework conversation (no section) re-checks MODULE visibility the same way —
    # losing membership / module deactivation makes it inaccessible (404), never a leak.
    elif conv.attached_module_id is not None:
        module = await get_visible_student_module(
            db, student_id=student_id, module_id=conv.attached_module_id
        )
        if module is None:
            raise not_found(CONVERSATION_NOT_FOUND)
    return conv


# ── availability ─────────────────────────────────────────────────────────────────────────────────
async def get_availability(
    db: AsyncSession, *, current_user: CurrentUserContext, section_id: UUID
) -> AssistantAvailabilityResponse:
    require_student(current_user.role)
    visible = await get_visible_student_section(
        db, student_id=current_user.user_id, section_id=section_id
    )
    if visible is None:
        raise not_found(SECTION_NOT_FOUND)
    readiness = await get_section_assistant_readiness(db, section_id=section_id)
    return AssistantAvailabilityResponse(state=readiness)


# ── open or create the lecture_default conversation (race-safe) ───────────────────────────────────
async def open_or_create_conversation(
    db: AsyncSession, *, current_user: CurrentUserContext, section_id: UUID
) -> ConversationRead:
    require_student(current_user.role)
    visible = await get_visible_student_section(
        db, student_id=current_user.user_id, section_id=section_id
    )
    if visible is None:
        raise not_found(SECTION_NOT_FOUND)

    readiness = await get_section_assistant_readiness(db, section_id=section_id)
    if readiness != READY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "assistant_not_ready", "state": readiness},
        )

    existing = await _existing_lecture_default(db, student_id=current_user.user_id, section_id=section_id)
    if existing is not None:
        return _to_conversation_read(existing)

    now = _now()
    conv = AssistantConversation(
        student_id=current_user.user_id,
        conversation_kind=LECTURE_DEFAULT,
        attached_section_id=section_id,
        title_source="auto",
        last_activity_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(conv)
    try:
        await db.commit()
    except IntegrityError:
        # Concurrent "Start chat" race: the partial-unique index rejected our insert. Re-read the winner
        # and return it as an open (a DB rejection is never surfaced as a user error).
        await db.rollback()
        existing = await _existing_lecture_default(
            db, student_id=current_user.user_id, section_id=section_id
        )
        if existing is None:  # pragma: no cover - defensive
            raise
        return _to_conversation_read(existing)
    return _to_conversation_read(conv)


async def _existing_lecture_default(
    db: AsyncSession, *, student_id: UUID, section_id: UUID
) -> AssistantConversation | None:
    return (
        await db.execute(
            select(AssistantConversation).where(
                AssistantConversation.student_id == student_id,
                AssistantConversation.attached_section_id == section_id,
                AssistantConversation.conversation_kind == LECTURE_DEFAULT,
                AssistantConversation.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


# ── create a mode conversation (8.6a — homework; resume-or-create on the natural key) ───────────────
async def create_conversation(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    payload: CreateConversationRequest,
) -> ConversationRead:
    """Create (or resume) a mode conversation. 8.6a supports ONLY ``homework_help``; 8.6b/8.6c add the
    others. The kind→binding matrix is validated here (homework: ``module_id`` required, ``section_id``
    optional + must belong to the visible module, ``assessment_scope_id`` forbidden). Creation is
    idempotent (D2): a double-click resumes the one active homework conversation per (student, module
    [, section]) — the partial-unique indexes make the race safe (re-read the winner on IntegrityError).
    ``conversation_kind`` is set ONCE here and is never mutated afterwards (immutability)."""
    require_student(current_user.role)
    if payload.conversation_kind != HOMEWORK_HELP:
        # lecture_default has its own section endpoint; exam_prep/time_management arrive in 8.6b/8.6c.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "unsupported_conversation_kind", "kind": payload.conversation_kind},
        )
    if payload.assessment_scope_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "assessment_scope_not_allowed_for_homework"},
        )
    if payload.module_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "module_required"},
        )

    module = await get_visible_student_module(
        db, student_id=current_user.user_id, module_id=payload.module_id
    )
    if module is None:  # not visible / not a member / inactive module → pinned 404
        raise not_found(MODULE_NOT_FOUND)
    section_id = payload.section_id
    if section_id is not None:
        visible = await get_visible_student_section(
            db, student_id=current_user.user_id, section_id=section_id
        )
        if visible is None or visible.course_module_id != payload.module_id:
            # not visible, or the section is not in the chosen module → pinned 404 (no cross-module leak)
            raise not_found(SECTION_NOT_FOUND)

    existing = await _existing_homework(
        db, student_id=current_user.user_id, module_id=payload.module_id, section_id=section_id
    )
    if existing is not None:
        return _to_conversation_read(existing)

    now = _now()
    conv = AssistantConversation(
        student_id=current_user.user_id,
        conversation_kind=HOMEWORK_HELP,
        attached_module_id=payload.module_id,
        attached_section_id=section_id,
        title_source="auto",
        last_activity_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(conv)
    try:
        await db.commit()
    except IntegrityError:
        # Double-click / concurrent create: the partial-unique index rejected the duplicate. Re-read the
        # winner and return it (a DB rejection is never surfaced as a user error).
        await db.rollback()
        existing = await _existing_homework(
            db, student_id=current_user.user_id, module_id=payload.module_id, section_id=section_id
        )
        if existing is None:  # pragma: no cover - defensive
            raise
        return _to_conversation_read(existing)
    return _to_conversation_read(conv)


async def _existing_homework(
    db: AsyncSession, *, student_id: UUID, module_id: UUID, section_id: UUID | None
) -> AssistantConversation | None:
    query = select(AssistantConversation).where(
        AssistantConversation.student_id == student_id,
        AssistantConversation.conversation_kind == HOMEWORK_HELP,
        AssistantConversation.attached_module_id == module_id,
        AssistantConversation.deleted_at.is_(None),
    )
    if section_id is None:
        query = query.where(AssistantConversation.attached_section_id.is_(None))
    else:
        query = query.where(AssistantConversation.attached_section_id == section_id)
    return (await db.execute(query)).scalar_one_or_none()


# ── conversation list (Workspace) ─────────────────────────────────────────────────────────────────
async def list_conversations(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    limit: int,
    offset: int,
) -> tuple[list[ConversationListItem], int]:
    """The student's OWN, non-soft-deleted, still-accessible conversations, newest-activity-first. The
    visibility filter is the SAME 4.7 gate as a direct open, so an access-revoked conversation simply
    has no row (invariant C is structural)."""
    require_student(current_user.role)
    rows, total = await get_visible_student_conversation_list(
        db, student_id=current_user.user_id, limit=limit, offset=offset
    )
    return [_to_conversation_list_item(r) for r in rows], total


async def get_conversation_detail(
    db: AsyncSession, *, current_user: CurrentUserContext, conversation_id: UUID
) -> ConversationListItem:
    """One conversation's metadata for the Workspace conversation view + context pill (lecture/module
    titles, display title, message count). Resolves ownership + CURRENT visibility (404 on not-owned /
    soft-deleted / access-revoked — invariant C), so a deep link to a now-inaccessible chat 404s."""
    require_student(current_user.role)
    conv = await _resolve_owned_conversation(
        db, student_id=current_user.user_id, conversation_id=conversation_id
    )
    count = (
        await db.execute(
            select(func.count())
            .select_from(AssistantMessage)
            .where(AssistantMessage.conversation_id == conv.id)
        )
    ).scalar_one()

    # 8.6a: a module-bound homework conversation (no section) — resolve MODULE visibility and render with
    # null section fields + the homework mode chip. Visibility was already re-checked by resolve.
    if conv.attached_section_id is None:
        if conv.attached_module_id is None:  # neither bound → defensive
            raise not_found(CONVERSATION_NOT_FOUND)
        module = await get_visible_student_module(
            db, student_id=current_user.user_id, module_id=conv.attached_module_id
        )
        if module is None:  # resolve already re-checked, but never trust a stale read
            raise not_found(CONVERSATION_NOT_FOUND)
        return ConversationListItem(
            id=conv.id,
            conversation_kind=conv.conversation_kind,
            display_title=_display_title(
                title=conv.title,
                title_source=conv.title_source,
                section_title=None,
                conversation_kind=conv.conversation_kind,
                module_title=module.title,
            ),
            module_id=module.id,
            module_title=module.title,
            attached_section_id=None,
            section_title=None,
            section_type=None,
            last_message_preview=None,
            last_activity_at=conv.last_activity_at or conv.updated_at,
            message_count=int(count),
            grounding_chip=_grounding_chip(conv.conversation_kind),
        )

    visible = await get_visible_student_section(
        db, student_id=current_user.user_id, section_id=conv.attached_section_id
    )
    if visible is None:  # resolve already re-checked, but never trust a stale read
        raise not_found(CONVERSATION_NOT_FOUND)
    module = await db.get(CourseModule, visible.course_module_id)
    return ConversationListItem(
        id=conv.id,
        conversation_kind=conv.conversation_kind,
        display_title=_display_title(
            title=conv.title,
            title_source=conv.title_source,
            section_title=visible.title,
            conversation_kind=conv.conversation_kind,
            module_title=module.title if module is not None else None,
        ),
        module_id=visible.course_module_id,
        module_title=module.title if module is not None else "",
        attached_section_id=conv.attached_section_id,
        section_title=visible.title,
        section_type=visible.type,
        last_message_preview=None,
        last_activity_at=conv.last_activity_at or conv.updated_at,
        message_count=int(count),
        grounding_chip=_grounding_chip(conv.conversation_kind),
    )


# ── message history (KEYSET pagination — ADR-053) ──────────────────────────────────────────────────
async def list_messages(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    conversation_id: UUID,
    before: str | None,
    limit: int,
) -> tuple[list[MessageRead], str | None, bool]:
    """Keyset page over the stable composite ``(created_at, id)``. With no ``before`` the NEWEST page is
    returned; ``before=next_cursor`` walks older. Items come back in display order (oldest→newest within
    the page) so the UI prepends older pages on scroll-up. The ``(created_at, id)`` tiebreak is
    load-bearing: 8.1 stamps a turn's user + assistant rows with the SAME ``created_at``."""
    require_student(current_user.role)
    conv = await _resolve_owned_conversation(
        db, student_id=current_user.user_id, conversation_id=conversation_id
    )
    query = select(AssistantMessage).where(AssistantMessage.conversation_id == conv.id)
    if before is not None:
        before_created_at, before_id = decode_cursor(before)
        query = query.where(
            (AssistantMessage.created_at < before_created_at)
            | (
                (AssistantMessage.created_at == before_created_at)
                & (AssistantMessage.id < before_id)
            )
        )
    rows_desc = (
        (
            await db.execute(
                query.order_by(
                    AssistantMessage.created_at.desc(), AssistantMessage.id.desc()
                ).limit(limit + 1)
            )
        )
        .scalars()
        .all()
    )
    has_more = len(rows_desc) > limit
    page_desc = rows_desc[:limit]
    next_cursor = (
        encode_cursor(page_desc[-1].created_at, page_desc[-1].id)
        if has_more and page_desc
        else None
    )
    return [_to_message_read(m) for m in reversed(page_desc)], next_cursor, has_more


# ── rename / soft-delete (Workspace conversation management) ────────────────────────────────────────
async def rename_conversation(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    conversation_id: UUID,
    title: str,
) -> ConversationRead:
    require_student(current_user.role)
    conv = await _resolve_owned_conversation(
        db, student_id=current_user.user_id, conversation_id=conversation_id
    )
    cleaned = _normalize_title(title)
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": "empty_title"}
        )
    conv.title = cleaned
    conv.title_source = "manual"  # a later auto-title never overwrites a manual one
    conv.updated_at = _now()  # rename does NOT bump last_activity_at → it never reorders the list
    await db.commit()
    return _to_conversation_read(conv)


async def soft_delete_conversation(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    conversation_id: UUID,
) -> None:
    require_student(current_user.role)
    conv = await _resolve_owned_conversation(
        db, student_id=current_user.user_id, conversation_id=conversation_id
    )
    conv.deleted_at = _now()  # frees the one-active slot so reopening the lecture is a FRESH row (A)
    await db.commit()


# ── send a message (user saved first + pending assistant + enqueue-after-commit) ─────────────────
async def send_message(
    db: AsyncSession,
    *,
    current_user: CurrentUserContext,
    conversation_id: UUID,
    payload: SendMessageRequest,
) -> SendMessageResponse:
    require_student(current_user.role)
    conv = await _resolve_owned_conversation(
        db, student_id=current_user.user_id, conversation_id=conversation_id
    )
    conv = await _lock_conversation_for_turn(db, conversation_id=conv.id)

    # Idempotency (decision 8): a re-send with the same client key returns the existing turn — never a
    # duplicate user message or a duplicate AI call.
    existing_user = await _user_message_by_key(
        db, conversation_id=conv.id, key=payload.client_idempotency_key
    )
    if existing_user is not None:
        return await _existing_turn_response(db, user_msg=existing_user)
    if await _has_pending_assistant_turn(db, conversation_id=conv.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "assistant_turn_pending"},
        )

    now = _now()
    user_msg = AssistantMessage(
        conversation_id=conv.id,
        role="user",
        status="completed",
        content=payload.content,
        client_idempotency_key=payload.client_idempotency_key,
        retryable=False,
        created_at=now,
        updated_at=now,
    )
    db.add(user_msg)
    await db.flush()  # populate user_msg.id for the assistant row's prompt_message_id
    assistant_msg = AssistantMessage(
        conversation_id=conv.id,
        role="assistant",
        status="pending",
        prompt_message_id=user_msg.id,
        retryable=False,
        created_at=now,
        updated_at=now,
    )
    db.add(assistant_msg)
    conv.updated_at = now
    conv.last_activity_at = now  # user-message creation bumps activity (orders the Workspace list)
    try:
        await db.commit()
    except IntegrityError:
        # Idempotency race: a concurrent request inserted the same user key first.
        await db.rollback()
        existing_user = await _user_message_by_key(
            db, conversation_id=conv.id, key=payload.client_idempotency_key
        )
        if existing_user is None:  # pragma: no cover - defensive
            raise
        return await _existing_turn_response(db, user_msg=existing_user)

    assistant_id = assistant_msg.id
    try:
        enqueue_generate_assistant_answer(assistant_id)
    except Exception:
        await _mark_enqueue_failed(db, message_id=assistant_id)
        await db.refresh(assistant_msg)
    return SendMessageResponse(
        user_message=_to_message_read(user_msg),
        assistant_message=_to_message_read(assistant_msg),
    )


async def _lock_conversation_for_turn(
    db: AsyncSession, *, conversation_id: UUID
) -> AssistantConversation:
    conv = (
        await db.execute(
            select(AssistantConversation)
            .where(AssistantConversation.id == conversation_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if conv is None or conv.deleted_at is not None:
        raise not_found(CONVERSATION_NOT_FOUND)
    return conv


async def _user_message_by_key(
    db: AsyncSession, *, conversation_id: UUID, key: str
) -> AssistantMessage | None:
    return (
        await db.execute(
            select(AssistantMessage).where(
                AssistantMessage.conversation_id == conversation_id,
                AssistantMessage.role == "user",
                AssistantMessage.client_idempotency_key == key,
            )
        )
    ).scalar_one_or_none()


async def _has_pending_assistant_turn(db: AsyncSession, *, conversation_id: UUID) -> bool:
    value = (
        await db.execute(
            select(AssistantMessage.id)
            .where(
                AssistantMessage.conversation_id == conversation_id,
                AssistantMessage.role == "assistant",
                AssistantMessage.status == "pending",
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return value is not None


async def _existing_turn_response(
    db: AsyncSession, *, user_msg: AssistantMessage
) -> SendMessageResponse:
    assistant = (
        (
            await db.execute(
                select(AssistantMessage)
                .where(
                    AssistantMessage.prompt_message_id == user_msg.id,
                    AssistantMessage.role == "assistant",
                )
                .order_by(AssistantMessage.created_at.desc(), AssistantMessage.id.desc())
            )
        )
        .scalars()
        .first()
    )
    return SendMessageResponse(
        user_message=_to_message_read(user_msg),
        assistant_message=_to_message_read(assistant),
    )


# ── retry a failed assistant message (never duplicates the user message) ─────────────────────────
async def retry_message(
    db: AsyncSession, *, current_user: CurrentUserContext, message_id: UUID
) -> MessageRead:
    require_student(current_user.role)
    msg = await db.get(AssistantMessage, message_id)
    if msg is None or msg.role != "assistant":
        raise not_found(MESSAGE_NOT_FOUND)
    # Ownership + live access (404, never 403).
    await _resolve_owned_conversation(
        db, student_id=current_user.user_id, conversation_id=msg.conversation_id
    )
    # Retryable iff a failed turn OR a context_unavailable turn (the latter completes with safe text +
    # retryable=true so the student can re-ask once processing finishes, review #11). A retry recomputes
    # retrieval/grounding FRESHLY: clear content + grounding + snapshot so nothing stale survives (#15).
    if not (msg.status == "failed" or msg.grounding_status == CONTEXT_UNAVAILABLE):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "not_failed"})

    msg.status = "pending"
    msg.content = None
    msg.grounding_status = None
    msg.context_snapshot = None
    msg.failure_category = None
    msg.failure_message_sanitized = None
    msg.retryable = False
    msg.updated_at = _now()
    await db.commit()

    message_id_value = msg.id
    try:
        enqueue_generate_assistant_answer(message_id_value)
    except Exception:
        await _mark_enqueue_failed(db, message_id=message_id_value)
        await db.refresh(msg)
    return _to_message_read(msg)


async def _mark_enqueue_failed(db: AsyncSession, *, message_id: UUID) -> None:
    msg = await db.get(AssistantMessage, message_id)
    if msg is None or msg.status != "pending":
        return
    msg.status = "failed"
    msg.failure_category = "enqueue_failed"
    msg.failure_message_sanitized = "Could not start the assistant. Please try again."
    msg.retryable = True
    msg.updated_at = _now()
    await db.commit()
