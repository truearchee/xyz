from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
import hashlib
import json
from uuid import UUID
from zoneinfo import ZoneInfo


WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
WINDOWS = ("morning", "afternoon", "evening")
PREFERRED_WINDOWS = (*WINDOWS, "no_preference")
SEVERITY_RANK = {"watch": 1, "needs_support": 2}


@dataclass(frozen=True)
class WorkloadConfig:
    algorithm_version: str
    daily_overflow_percent: int
    deadline_estimate_minutes: int
    gap_estimate_minutes: int
    window_morning_start: str
    window_morning_end: str
    window_afternoon_start: str
    window_afternoon_end: str
    window_evening_start: str
    window_evening_end: str
    legacy_fallback_horizon_days: int
    min_availability_minutes: int
    max_availability_minutes: int


@dataclass(frozen=True)
class AvailabilityInput:
    study_days: tuple[str, ...]
    preferred_window: str
    max_study_minutes_per_day: int
    availability_version: int


@dataclass(frozen=True)
class DeadlineInput:
    section_id: UUID
    title: str
    section_type: str
    week_number: int | None
    due_at: datetime


@dataclass(frozen=True)
class RiskSnapshotInput:
    id: UUID | None
    risk_reasons: tuple[dict, ...]
    input_hash: str | None
    source_cutoff_at: datetime | None


@dataclass(frozen=True)
class WorkloadInputs:
    student_id: UUID
    module_id: UUID
    module_title: str
    module_timezone: str
    course_ends_on: date | None
    source_cutoff_at: datetime
    availability: AvailabilityInput
    deadlines: tuple[DeadlineInput, ...]
    risk_snapshot: RiskSnapshotInput | None
    forecast_context: dict


@dataclass(frozen=True)
class PlannedWorkloadItem:
    task_key: str
    source_section_id: UUID | None
    scheduled_date: date | None
    window: str | None
    scheduled_start_at: datetime | None
    scheduled_end_at: datetime | None
    label: str
    estimate_minutes: int
    reason: str
    source_reason_code: str | None
    source_metadata: dict
    tight: bool
    tight_message: str | None
    sort_index: int


@dataclass(frozen=True)
class WorkloadPlanResult:
    algorithm_version: str
    input_hash: str
    availability_version: int
    source_cutoff_at: datetime
    provenance: dict
    items: tuple[PlannedWorkloadItem, ...]


@dataclass
class _Task:
    key: str
    label: str
    estimate_minutes: int
    reason: str
    due_at: datetime | None
    source_section_id: UUID | None
    source_reason_code: str | None
    source_metadata: dict
    severity_rank: int = 0


@dataclass(frozen=True)
class _Slot:
    day: date
    window: str
    start_at: datetime
    end_at: datetime


def build_workload_plan(inputs: WorkloadInputs, *, config: WorkloadConfig) -> WorkloadPlanResult:
    availability = validate_availability(inputs.availability, config=config)
    horizon_end, horizon_provenance = resolve_horizon(
        course_ends_on=inputs.course_ends_on,
        deadlines=inputs.deadlines,
        source_cutoff_at=inputs.source_cutoff_at,
        module_timezone=inputs.module_timezone,
        fallback_horizon_days=config.legacy_fallback_horizon_days,
    )
    tasks = _prioritized_tasks(_build_tasks(inputs, config=config))
    slots = _candidate_slots(
        availability=availability,
        source_cutoff_at=inputs.source_cutoff_at,
        horizon_end=horizon_end,
        module_timezone=inputs.module_timezone,
        config=config,
    )
    items = _layout_tasks(tasks, slots=slots, availability=availability, config=config)
    hash_value = workload_input_hash(inputs=inputs, config=config, horizon_end=horizon_end, tasks=tasks)
    provenance = {
        "moduleTitle": inputs.module_title,
        "horizonEnd": horizon_end.isoformat(),
        "horizon": horizon_provenance,
        "riskSnapshotId": str(inputs.risk_snapshot.id) if inputs.risk_snapshot and inputs.risk_snapshot.id else None,
        "riskSnapshotInputHash": inputs.risk_snapshot.input_hash if inputs.risk_snapshot else None,
        "forecastContext": _jsonable(inputs.forecast_context),
        "taskCount": len(tasks),
    }
    return WorkloadPlanResult(
        algorithm_version=config.algorithm_version,
        input_hash=hash_value,
        availability_version=availability.availability_version,
        source_cutoff_at=inputs.source_cutoff_at,
        provenance=provenance,
        items=tuple(items),
    )


def validate_availability(availability: AvailabilityInput, *, config: WorkloadConfig) -> AvailabilityInput:
    days = tuple(dict.fromkeys(day.strip().lower() for day in availability.study_days))
    if not days:
        raise ValueError("At least one study day is required")
    invalid_days = sorted(set(days) - set(WEEKDAYS))
    if invalid_days:
        raise ValueError(f"Invalid study days: {', '.join(invalid_days)}")
    preferred = availability.preferred_window.strip().lower()
    if preferred not in PREFERRED_WINDOWS:
        raise ValueError("Invalid preferred study window")
    if availability.max_study_minutes_per_day < config.min_availability_minutes:
        raise ValueError(f"maxStudyMinutesPerDay must be >= {config.min_availability_minutes}")
    if availability.max_study_minutes_per_day > config.max_availability_minutes:
        raise ValueError(f"maxStudyMinutesPerDay must be <= {config.max_availability_minutes}")
    if availability.availability_version <= 0:
        raise ValueError("availabilityVersion must be positive")
    canonical_days = tuple(day for day in WEEKDAYS if day in days)
    return AvailabilityInput(
        study_days=canonical_days,
        preferred_window=preferred,
        max_study_minutes_per_day=availability.max_study_minutes_per_day,
        availability_version=availability.availability_version,
    )


def resolve_horizon(
    *,
    course_ends_on: date | None,
    deadlines: tuple[DeadlineInput, ...],
    source_cutoff_at: datetime,
    module_timezone: str,
    fallback_horizon_days: int,
) -> tuple[datetime, dict]:
    tz = ZoneInfo(module_timezone or "UTC")
    if course_ends_on is not None:
        local_end = datetime.combine(course_ends_on, time(23, 59, 59), tzinfo=tz)
        return local_end.astimezone(UTC), {
            "mode": "course_end",
            "fallbackUsed": False,
            "courseEndsOn": course_ends_on.isoformat(),
        }

    latest_deadline = max((deadline.due_at.astimezone(UTC) for deadline in deadlines), default=None)
    fallback_end = source_cutoff_at.astimezone(UTC) + timedelta(days=fallback_horizon_days)
    horizon_end = max([candidate for candidate in (latest_deadline, fallback_end) if candidate is not None])
    return horizon_end, {
        "mode": "legacy_fallback",
        "fallbackUsed": True,
        "latestKnownDueAt": latest_deadline.isoformat() if latest_deadline else None,
        "fallbackHorizonDays": fallback_horizon_days,
    }


def workload_input_hash(
    *,
    inputs: WorkloadInputs,
    config: WorkloadConfig,
    horizon_end: datetime,
    tasks: list[_Task],
) -> str:
    payload = {
        "algorithmVersion": config.algorithm_version,
        "availability": _jsonable(asdict(inputs.availability)),
        "config": _jsonable(asdict(config)),
        "deadlines": [_jsonable(asdict(deadline)) for deadline in inputs.deadlines],
        "forecastContext": _jsonable(inputs.forecast_context),
        "horizonEnd": horizon_end.isoformat(),
        "moduleId": str(inputs.module_id),
        "riskSnapshot": _jsonable(asdict(inputs.risk_snapshot)) if inputs.risk_snapshot else None,
        "studentId": str(inputs.student_id),
        "tasks": [_jsonable(asdict(task)) for task in tasks],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _build_tasks(inputs: WorkloadInputs, *, config: WorkloadConfig) -> list[_Task]:
    deadline_tasks = [
        _Task(
            key=f"deadline:{deadline.section_id}",
            label=f"Prepare for {deadline.title}",
            estimate_minutes=config.deadline_estimate_minutes,
            reason="deadline",
            due_at=deadline.due_at.astimezone(UTC),
            source_section_id=deadline.section_id,
            source_reason_code=None,
            source_metadata={
                "sectionId": str(deadline.section_id),
                "sectionType": deadline.section_type,
                "title": deadline.title,
                "weekNumber": deadline.week_number,
                "dueAt": deadline.due_at.astimezone(UTC).isoformat(),
            },
        )
        for deadline in inputs.deadlines
    ]
    deadline_by_normalized_title = {
        _normalize(task.source_metadata["title"]): task for task in deadline_tasks
    }

    for reason in _risk_reasons(inputs.risk_snapshot):
        if reason.get("code") != "topic_deadline_gap":
            continue
        metrics = reason.get("supportingMetrics") or {}
        topic = str(metrics.get("topicTitle") or "").strip()
        if not topic:
            continue
        match = deadline_by_normalized_title.get(_normalize(topic))
        if match is not None:
            match.source_reason_code = "topic_deadline_gap"
            match.source_metadata = {
                **match.source_metadata,
                "mergedGap": {
                    "reasonCode": "topic_deadline_gap",
                    "severity": reason.get("severity"),
                    "topicTitle": topic,
                },
            }
            continue
        severity = str(reason.get("severity") or "watch")
        deadline_tasks.append(
            _Task(
                key=f"gap:topic_deadline_gap:{_stable_key(topic)}",
                label=f"Reinforce {topic}",
                estimate_minutes=config.gap_estimate_minutes,
                reason="gap",
                due_at=None,
                source_section_id=None,
                source_reason_code="topic_deadline_gap",
                source_metadata={
                    "reasonCode": "topic_deadline_gap",
                    "severity": severity,
                    "topicTitle": topic,
                    "supportingMetrics": _jsonable(metrics),
                },
                severity_rank=SEVERITY_RANK.get(severity, 0),
            )
        )
    return deadline_tasks


def _risk_reasons(snapshot: RiskSnapshotInput | None) -> tuple[dict, ...]:
    return snapshot.risk_reasons if snapshot is not None else ()


def _prioritized_tasks(tasks: list[_Task]) -> list[_Task]:
    deadline_tasks = sorted(
        (task for task in tasks if task.due_at is not None),
        key=lambda task: (task.due_at, task.key),
    )
    gap_tasks = sorted(
        (task for task in tasks if task.due_at is None),
        key=lambda task: (-task.severity_rank, task.key),
    )
    return [*deadline_tasks, *gap_tasks]


def _candidate_slots(
    *,
    availability: AvailabilityInput,
    source_cutoff_at: datetime,
    horizon_end: datetime,
    module_timezone: str,
    config: WorkloadConfig,
) -> list[_Slot]:
    tz = ZoneInfo(module_timezone or "UTC")
    cutoff = source_cutoff_at.astimezone(UTC)
    horizon = horizon_end.astimezone(UTC)
    windows = _windows_for_preference(availability.preferred_window)
    window_times = _window_times(config)
    current_day = cutoff.astimezone(tz).date()
    final_day = horizon.astimezone(tz).date()
    slots: list[_Slot] = []
    while current_day <= final_day:
        weekday = WEEKDAYS[current_day.weekday()]
        if weekday in availability.study_days:
            for window_name in windows:
                start_time, end_time = window_times[window_name]
                local_start = datetime.combine(current_day, start_time, tzinfo=tz)
                local_end = datetime.combine(current_day, end_time, tzinfo=tz)
                start_at = max(local_start.astimezone(UTC), cutoff)
                end_at = min(local_end.astimezone(UTC), horizon)
                if end_at > start_at:
                    slots.append(_Slot(day=current_day, window=window_name, start_at=start_at, end_at=end_at))
        current_day += timedelta(days=1)
    return slots


def _layout_tasks(
    tasks: list[_Task],
    *,
    slots: list[_Slot],
    availability: AvailabilityInput,
    config: WorkloadConfig,
) -> list[PlannedWorkloadItem]:
    items: list[PlannedWorkloadItem] = []
    day_minutes: dict[date, int] = {}
    window_minutes: dict[tuple[date, str], int] = {}
    daily_cap = availability.max_study_minutes_per_day
    overflow_allowance = daily_cap * config.daily_overflow_percent // 100
    overflow_cap = daily_cap + overflow_allowance

    for task in tasks:
        start_index = len(items)
        remaining = _allocate_task(
            task,
            remaining_minutes=task.estimate_minutes,
            slots=slots,
            day_minutes=day_minutes,
            window_minutes=window_minutes,
            day_cap=daily_cap,
            items=items,
        )
        if task.reason == "deadline" and remaining > 0:
            remaining = _allocate_task(
                task,
                remaining_minutes=remaining,
                slots=slots,
                day_minutes=day_minutes,
                window_minutes=window_minutes,
                day_cap=overflow_cap,
                items=items,
            )
        if remaining > 0:
            message = _tight_message(task)
            for index in range(start_index, len(items)):
                item = items[index]
                if item.task_key == task.key:
                    items[index] = PlannedWorkloadItem(
                        task_key=item.task_key,
                        source_section_id=item.source_section_id,
                        scheduled_date=item.scheduled_date,
                        window=item.window,
                        scheduled_start_at=item.scheduled_start_at,
                        scheduled_end_at=item.scheduled_end_at,
                        label=item.label,
                        estimate_minutes=item.estimate_minutes,
                        reason=item.reason,
                        source_reason_code=item.source_reason_code,
                        source_metadata=item.source_metadata,
                        tight=True,
                        tight_message=message,
                        sort_index=item.sort_index,
                    )
            items.append(
                PlannedWorkloadItem(
                    task_key=task.key,
                    source_section_id=task.source_section_id,
                    scheduled_date=None,
                    window=None,
                    scheduled_start_at=None,
                    scheduled_end_at=None,
                    label=task.label,
                    estimate_minutes=remaining,
                    reason=task.reason,
                    source_reason_code=task.source_reason_code,
                    source_metadata=task.source_metadata,
                    tight=True,
                    tight_message=message,
                    sort_index=len(items),
                )
            )

    return [
        PlannedWorkloadItem(
            task_key=item.task_key,
            source_section_id=item.source_section_id,
            scheduled_date=item.scheduled_date,
            window=item.window,
            scheduled_start_at=item.scheduled_start_at,
            scheduled_end_at=item.scheduled_end_at,
            label=item.label,
            estimate_minutes=item.estimate_minutes,
            reason=item.reason,
            source_reason_code=item.source_reason_code,
            source_metadata=item.source_metadata,
            tight=item.tight,
            tight_message=item.tight_message,
            sort_index=index,
        )
        for index, item in enumerate(items)
    ]


def _allocate_task(
    task: _Task,
    *,
    remaining_minutes: int,
    slots: list[_Slot],
    day_minutes: dict[date, int],
    window_minutes: dict[tuple[date, str], int],
    day_cap: int,
    items: list[PlannedWorkloadItem],
) -> int:
    remaining = remaining_minutes
    for slot in slots:
        if remaining <= 0:
            break
        slot_end = slot.end_at
        if task.due_at is not None:
            due_at = task.due_at.astimezone(UTC)
            if slot.start_at >= due_at:
                continue
            slot_end = min(slot.end_at, due_at)
        used_day = day_minutes.get(slot.day, 0)
        available_day = max(0, day_cap - used_day)
        if available_day <= 0:
            continue
        used_window = window_minutes.get((slot.day, slot.window), 0)
        slot_capacity = max(0, int((slot_end - slot.start_at).total_seconds() // 60) - used_window)
        if slot_capacity <= 0:
            continue
        minutes = min(remaining, available_day, slot_capacity)
        start_at = slot.start_at + timedelta(minutes=used_window)
        end_at = start_at + timedelta(minutes=minutes)
        if task.due_at is not None and end_at > task.due_at.astimezone(UTC):
            continue
        items.append(
            PlannedWorkloadItem(
                task_key=task.key,
                source_section_id=task.source_section_id,
                scheduled_date=slot.day,
                window=slot.window,
                scheduled_start_at=start_at,
                scheduled_end_at=end_at,
                label=task.label,
                estimate_minutes=minutes,
                reason=task.reason,
                source_reason_code=task.source_reason_code,
                source_metadata=task.source_metadata,
                tight=False,
                tight_message=None,
                sort_index=len(items),
            )
        )
        day_minutes[slot.day] = used_day + minutes
        window_minutes[(slot.day, slot.window)] = used_window + minutes
        remaining -= minutes
    return remaining


def _tight_message(task: _Task) -> str:
    if task.due_at is None:
        return "Plan may not fully fit within the current planning horizon."
    due_label = task.due_at.date().isoformat()
    return f"Plan may not fully fit before {due_label}."


def _windows_for_preference(preferred_window: str) -> tuple[str, ...]:
    return WINDOWS if preferred_window == "no_preference" else (preferred_window,)


def _window_times(config: WorkloadConfig) -> dict[str, tuple[time, time]]:
    return {
        "morning": (_parse_time(config.window_morning_start), _parse_time(config.window_morning_end)),
        "afternoon": (_parse_time(config.window_afternoon_start), _parse_time(config.window_afternoon_end)),
        "evening": (_parse_time(config.window_evening_start), _parse_time(config.window_evening_end)),
    }


def _parse_time(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _stable_key(value: str) -> str:
    return hashlib.sha256(_normalize(value).encode("utf-8")).hexdigest()[:16]


def _jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value
