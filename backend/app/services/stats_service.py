from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatMessage, ChatSession, LearningRecord, PlanPhase, StudyPlan, Task


def _range_to_datetimes(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    return start_dt, end_dt


def _record_day_key(recorded_at: datetime | None, fallback: date) -> str:
    return recorded_at.strftime("%Y-%m-%d") if recorded_at else fallback.isoformat()


def _count_streak(record_days: set[date], end_date: date) -> int:
    streak = 0
    cursor = end_date
    while cursor in record_days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


async def record_learning_activity(
    user_id: int,
    activity_type: str,
    db: AsyncSession,
    task_id: int | None = None,
    duration_minutes: int = 0,
    metadata: dict[str, Any] | None = None,
    recorded_at: datetime | None = None,
) -> LearningRecord:
    record = LearningRecord(
        user_id=user_id,
        task_id=task_id,
        activity_type=activity_type,
        duration_minutes=duration_minutes,
        metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
        recorded_at=recorded_at or datetime.now(timezone.utc),
    )
    db.add(record)
    await db.flush()
    return record


async def record_study_session(
    user_id: int,
    db: AsyncSession,
    *,
    duration_minutes: int,
    task_id: int | None = None,
    source: str = "focus_timer",
) -> LearningRecord:
    return await record_learning_activity(
        user_id=user_id,
        activity_type="study_session",
        db=db,
        task_id=task_id,
        duration_minutes=duration_minutes,
        metadata={"source": source},
    )


async def _load_records(
    user_id: int,
    start_dt: datetime,
    end_dt: datetime,
    db: AsyncSession,
) -> list[LearningRecord]:
    result = await db.execute(
        select(LearningRecord).where(
            LearningRecord.user_id == user_id,
            LearningRecord.recorded_at >= start_dt,
            LearningRecord.recorded_at <= end_dt,
        )
    )
    return list(result.scalars().all())


async def _load_tasks(user_id: int, db: AsyncSession) -> list[Task]:
    result = await db.execute(select(Task).where(Task.user_id == user_id))
    return list(result.scalars().all())


async def _load_phase_completion_rate(user_id: int, db: AsyncSession) -> float:
    phase_result = await db.execute(
        select(PlanPhase)
        .join(StudyPlan, PlanPhase.plan_id == StudyPlan.id)
        .where(StudyPlan.user_id == user_id)
    )
    phases = list(phase_result.scalars().all())
    if not phases:
        return 0.0

    phase_ids = [phase.id for phase in phases]
    task_result = await db.execute(
        select(Task).where(
            Task.user_id == user_id, Task.phase_id.in_(phase_ids), Task.parent_task_id.is_(None)
        )
    )
    tasks = list(task_result.scalars().all())
    tasks_by_phase: dict[int, list[Task]] = defaultdict(list)
    for task in tasks:
        if task.phase_id is not None:
            tasks_by_phase[task.phase_id].append(task)

    completed_phases = 0
    for phase in phases:
        phase_tasks = tasks_by_phase.get(phase.id, [])
        if phase_tasks and all(task.status == "completed" for task in phase_tasks):
            completed_phases += 1

    return round(completed_phases / len(phases), 4)


async def aggregate_learning_stats(
    user_id: int,
    start_date: date,
    end_date: date,
    db: AsyncSession,
) -> dict[str, Any]:
    start_dt, end_dt = _range_to_datetimes(start_date, end_date)
    tasks = await _load_tasks(user_id, db)
    records = await _load_records(user_id, start_dt, end_dt, db)

    total_tasks = len(tasks)
    completed_tasks = sum(1 for task in tasks if task.status == "completed")
    priority_distribution = {"high": 0, "medium": 0, "low": 0}
    for task in tasks:
        if task.priority in priority_distribution:
            priority_distribution[task.priority] += 1

    daily_breakdown: dict[str, int] = {}
    activity_breakdown: dict[str, int] = defaultdict(int)
    weekday_distribution = {
        label: 0 for label in ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    }
    completion_rhythm = {f"{hour:02d}:00": 0 for hour in range(24)}
    total_study_minutes = 0
    total_sessions = 0
    record_days: set[date] = set()

    for record in records:
        activity_breakdown[record.activity_type] += 1
        if record.activity_type == "study_session":
            total_sessions += 1

        record_day = record.recorded_at.date() if record.recorded_at else start_date
        day_key = _record_day_key(record.recorded_at, start_date)
        daily_breakdown.setdefault(day_key, 0)
        daily_breakdown[day_key] += record.duration_minutes
        total_study_minutes += record.duration_minutes
        if record.duration_minutes > 0:
            record_days.add(record_day)
            weekday_distribution[list(weekday_distribution.keys())[record_day.weekday()]] += (
                record.duration_minutes
            )

        if record.activity_type == "task_complete" and record.recorded_at:
            completion_rhythm[f"{record.recorded_at.hour:02d}:00"] += 1

    completion_rate = completed_tasks / total_tasks if total_tasks > 0 else 0.0
    phase_completion_rate = await _load_phase_completion_rate(user_id, db)
    diagnostic_metrics = await _aggregate_chat_diagnostics(user_id, start_dt, end_dt, db)

    return {
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "total_study_minutes": total_study_minutes,
        "completion_rate": round(completion_rate, 4),
        "daily_breakdown": daily_breakdown,
        "priority_distribution": priority_distribution,
        "activity_breakdown": dict(activity_breakdown),
        "weekday_distribution": weekday_distribution,
        "completion_rhythm": completion_rhythm,
        "streak_days": _count_streak(record_days, end_date),
        "total_sessions": total_sessions,
        "phase_completion_rate": phase_completion_rate,
        "chat_diagnostic_total": diagnostic_metrics["chat_diagnostic_total"],
        "clarify_reason_distribution": diagnostic_metrics["clarify_reason_distribution"],
        "orchestration_event_distribution": diagnostic_metrics["orchestration_event_distribution"],
        "clarify_path_switch_hit_rate": diagnostic_metrics["clarify_path_switch_hit_rate"],
        "action_completion_rate": diagnostic_metrics["action_completion_rate"],
    }


async def _aggregate_chat_diagnostics(
    user_id: int,
    start_dt: datetime,
    end_dt: datetime,
    db: AsyncSession,
) -> dict[str, Any]:
    result = await db.execute(
        select(ChatMessage.entities_json)
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .where(
            ChatSession.user_id == user_id,
            ChatMessage.role == "assistant",
            ChatMessage.entities_json.is_not(None),
            ChatMessage.created_at >= start_dt,
            ChatMessage.created_at <= end_dt,
        )
    )
    rows = result.scalars().all()
    event_distribution: dict[str, int] = defaultdict(int)
    clarify_reason_distribution: dict[str, int] = defaultdict(int)
    diagnostics_total = 0
    switch_hits = 0
    action_completed = 0
    clarify_total = 0

    for entities_json in rows:
        if not entities_json:
            continue
        try:
            payload = json.loads(entities_json)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        diagnostics = payload.get("orchestration_diagnostics")
        if not isinstance(diagnostics, dict):
            continue
        event = diagnostics.get("event")
        if not isinstance(event, str) or not event:
            continue
        diagnostics_total += 1
        event_distribution[event] += 1
        if event in {
            "force_clarify_initial",
            "force_clarify_seeded",
            "clarify_before_action",
            "pending_clarify_continue",
        }:
            clarify_total += 1
            clarify_reason_distribution[event] += 1
        if event == "force_clarify_seeded":
            switch_hits += 1
        if event == "action_completed":
            action_completed += 1

    clarify_switch_rate = round(switch_hits / clarify_total, 4) if clarify_total else 0.0
    action_completion_rate = (
        round(action_completed / diagnostics_total, 4) if diagnostics_total else 0.0
    )
    return {
        "chat_diagnostic_total": diagnostics_total,
        "clarify_reason_distribution": dict(clarify_reason_distribution),
        "orchestration_event_distribution": dict(event_distribution),
        "clarify_path_switch_hit_rate": clarify_switch_rate,
        "action_completion_rate": action_completion_rate,
    }


async def get_daily_stats(
    user_id: int,
    target: date,
    db: AsyncSession,
) -> dict[str, Any]:
    start_dt, end_dt = _range_to_datetimes(target, target)
    records = await _load_records(user_id, start_dt, end_dt, db)

    return {
        "date": target.isoformat(),
        "study_minutes": sum(record.duration_minutes for record in records),
        "tasks_created": sum(1 for record in records if record.activity_type == "task_create"),
        "tasks_completed": sum(1 for record in records if record.activity_type == "task_complete"),
        "chat_count": sum(1 for record in records if record.activity_type == "chat"),
        "session_count": sum(1 for record in records if record.activity_type == "study_session"),
    }


async def get_weekly_stats(
    user_id: int,
    week_start: date | None,
    db: AsyncSession,
) -> dict[str, Any]:
    today = date.today()
    start = week_start or (today - timedelta(days=today.weekday()))
    end = start + timedelta(days=6)
    stats = await aggregate_learning_stats(user_id, start, end, db)
    return {
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "total_study_minutes": stats["total_study_minutes"],
        "total_tasks": stats["total_tasks"],
        "completed_tasks": stats["completed_tasks"],
        "daily_breakdown": stats["daily_breakdown"],
        "streak_days": stats["streak_days"],
    }


async def get_task_stats(user_id: int, db: AsyncSession) -> dict[str, Any]:
    tasks = await _load_tasks(user_id, db)

    total = len(tasks)
    completed = sum(1 for task in tasks if task.status == "completed")
    pending = sum(1 for task in tasks if task.status == "pending")
    in_progress = sum(1 for task in tasks if task.status == "in_progress")
    overdue = sum(1 for task in tasks if task.status == "overdue")
    priority_dist = {"high": 0, "medium": 0, "low": 0}
    for task in tasks:
        if task.priority in priority_dist:
            priority_dist[task.priority] += 1

    return {
        "total_tasks": total,
        "completed_tasks": completed,
        "pending_tasks": pending,
        "in_progress_tasks": in_progress,
        "overdue_tasks": overdue,
        "completion_rate": round(completed / total, 4) if total > 0 else 0.0,
        "priority_distribution": priority_dist,
        "phase_completion_rate": await _load_phase_completion_rate(user_id, db),
    }
