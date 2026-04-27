from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.errors import not_found, validation_error
from app.models import PlanPhase, StudyPlan, Task
from app.schemas.plans import (
    PlanCreate,
    PlanPhaseInput,
    PlanPhaseResponse,
    PlanQuickCreate,
    PlanResponse,
    PlanScheduleItem,
    PlanStatusUpdate,
    PlanTemplateResponse,
    PlanUpdate,
    PlanWeekSummary,
)

PLAN_TEMPLATE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "exam_sprint": {
        "title": "考试冲刺模板",
        "description": "适合一周左右的集中复习，包含知识梳理、刷题、复盘和模拟。",
        "duration_days": 7,
        "phases": [
            {
                "title": "知识梳理",
                "description": "先把章节框架和薄弱点梳理清楚",
                "offset_days": 0,
                "length_days": 2,
            },
            {
                "title": "专项刷题",
                "description": "围绕重点题型做高频训练",
                "offset_days": 2,
                "length_days": 3,
            },
            {
                "title": "复盘冲刺",
                "description": "整理错题并进行模拟检查",
                "offset_days": 5,
                "length_days": 2,
            },
        ],
        "tasks": [
            {
                "title": "梳理本周重点章节",
                "phase_index": 0,
                "offset_days": 0,
                "estimated_minutes": 90,
            },
            {
                "title": "完成两组专项训练题",
                "phase_index": 1,
                "offset_days": 2,
                "estimated_minutes": 120,
            },
            {
                "title": "整理错题并做一次模拟",
                "phase_index": 2,
                "offset_days": 5,
                "estimated_minutes": 120,
            },
        ],
    },
    "weekly_review": {
        "title": "周复习模板",
        "description": "适合按天推进的周计划，强调输入、练习和复盘节奏。",
        "duration_days": 7,
        "phases": [
            {
                "title": "输入与理解",
                "description": "看笔记、回顾知识点",
                "offset_days": 0,
                "length_days": 2,
            },
            {
                "title": "练习与反馈",
                "description": "刷题、订正、查漏补缺",
                "offset_days": 2,
                "length_days": 3,
            },
            {
                "title": "总结与调整",
                "description": "复盘本周节奏并安排下周",
                "offset_days": 5,
                "length_days": 2,
            },
        ],
        "tasks": [
            {
                "title": "回顾本周课堂笔记",
                "phase_index": 0,
                "offset_days": 0,
                "estimated_minutes": 60,
            },
            {
                "title": "完成一轮配套练习",
                "phase_index": 1,
                "offset_days": 2,
                "estimated_minutes": 90,
            },
            {"title": "写一份周复盘", "phase_index": 2, "offset_days": 6, "estimated_minutes": 45},
        ],
    },
    "vocabulary_boost": {
        "title": "背词冲刺模板",
        "description": "适合单词、短语或记忆类任务，强调每天输入和复习。",
        "duration_days": 5,
        "phases": [
            {
                "title": "输入记忆",
                "description": "分批背词并标记易错项",
                "offset_days": 0,
                "length_days": 2,
            },
            {
                "title": "循环复习",
                "description": "按天重复复习高频难词",
                "offset_days": 2,
                "length_days": 2,
            },
            {"title": "检测巩固", "description": "自测并补漏", "offset_days": 4, "length_days": 1},
        ],
        "tasks": [
            {
                "title": "背诵今日新词并做标记",
                "phase_index": 0,
                "offset_days": 0,
                "estimated_minutes": 45,
            },
            {
                "title": "复习昨天难词并再次默写",
                "phase_index": 1,
                "offset_days": 2,
                "estimated_minutes": 30,
            },
            {
                "title": "做一次单词自测",
                "phase_index": 2,
                "offset_days": 4,
                "estimated_minutes": 40,
            },
        ],
    },
}


async def get_owned_plan(plan_id: int, user_id: int, db: AsyncSession) -> StudyPlan:
    result = await db.execute(
        select(StudyPlan)
        .where(StudyPlan.id == plan_id, StudyPlan.user_id == user_id)
        .options(selectinload(StudyPlan.phases))
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise not_found("学习计划不存在")
    return plan


async def list_plans(user_id: int, db: AsyncSession) -> list[StudyPlan]:
    result = await db.execute(
        select(StudyPlan)
        .where(StudyPlan.user_id == user_id)
        .options(selectinload(StudyPlan.phases))
        .order_by(StudyPlan.created_at.desc())
    )
    return list(result.scalars().all())


def list_plan_templates() -> list[dict[str, Any]]:
    templates: list[dict[str, Any]] = []
    for key, definition in PLAN_TEMPLATE_DEFINITIONS.items():
        payload = PlanTemplateResponse(
            key=key,
            title=definition["title"],
            description=definition["description"],
            duration_days=definition["duration_days"],
            phases=[
                PlanPhaseInput(
                    title=phase["title"],
                    description=phase.get("description"),
                    sequence=index,
                )
                for index, phase in enumerate(definition["phases"])
            ],
            default_tasks=definition["tasks"],
        )
        templates.append(payload.model_dump())
    return templates


async def _replace_plan_phases(
    plan: StudyPlan, phases: list[PlanPhaseInput], db: AsyncSession
) -> None:
    existing_result = await db.execute(select(PlanPhase).where(PlanPhase.plan_id == plan.id))
    for phase in existing_result.scalars().all():
        await db.delete(phase)
    await db.flush()

    for phase_input in phases:
        db.add(
            PlanPhase(
                plan_id=plan.id,
                title=phase_input.title,
                description=phase_input.description,
                sequence=phase_input.sequence,
                start_date=phase_input.start_date,
                end_date=phase_input.end_date,
            )
        )
    await db.flush()


async def create_plan(user_id: int, data: PlanCreate, db: AsyncSession) -> StudyPlan:
    plan = StudyPlan(
        title=data.title,
        description=data.description,
        template_key=data.template_key,
        start_date=data.start_date,
        end_date=data.end_date,
        status="active",
        user_id=user_id,
    )
    db.add(plan)
    await db.flush()
    if data.phases:
        await _replace_plan_phases(plan, data.phases, db)
    await db.refresh(plan)
    return await get_owned_plan(plan.id, user_id, db)


async def create_plan_from_template(
    user_id: int, data: PlanQuickCreate, db: AsyncSession
) -> StudyPlan:
    definition = PLAN_TEMPLATE_DEFINITIONS.get(data.template_key)
    if definition is None:
        raise not_found("计划模板不存在")

    start_date = data.start_date
    end_date = start_date + timedelta(days=definition["duration_days"] - 1)
    phases = [
        PlanPhaseInput(
            title=phase["title"],
            description=phase.get("description"),
            sequence=index,
            start_date=start_date + timedelta(days=phase["offset_days"]),
            end_date=start_date + timedelta(days=phase["offset_days"] + phase["length_days"] - 1),
        )
        for index, phase in enumerate(definition["phases"])
    ]

    plan = await create_plan(
        user_id,
        PlanCreate(
            title=data.title or definition["title"],
            description=data.description or definition["description"],
            start_date=start_date,
            end_date=end_date,
            template_key=data.template_key,
            phases=phases,
        ),
        db,
    )

    phase_map = {phase.sequence: phase for phase in plan.phases}
    for order, task in enumerate(definition["tasks"]):
        phase = phase_map.get(task["phase_index"])
        db.add(
            Task(
                user_id=user_id,
                plan_id=plan.id,
                phase_id=phase.id if phase else None,
                title=task["title"],
                description=phase.description if phase else None,
                priority="medium",
                status="pending",
                estimated_minutes=task.get("estimated_minutes"),
                scheduled_date=start_date + timedelta(days=task["offset_days"]),
                sort_order=order,
            )
        )
    await db.flush()
    return await get_owned_plan(plan.id, user_id, db)


async def update_plan(plan: StudyPlan, data: PlanUpdate, db: AsyncSession) -> StudyPlan:
    update_data = data.model_dump(exclude_unset=True, exclude={"phases"})

    if (
        "start_date" in update_data
        and "end_date" not in update_data
        and update_data["start_date"] > plan.end_date
    ):
        raise validation_error("开始日期不能晚于结束日期")
    if (
        "end_date" in update_data
        and "start_date" not in update_data
        and plan.start_date > update_data["end_date"]
    ):
        raise validation_error("开始日期不能晚于结束日期")

    for key, value in update_data.items():
        setattr(plan, key, value)

    if data.phases is not None:
        await _replace_plan_phases(plan, data.phases, db)

    await db.flush()
    await db.refresh(plan)
    return await get_owned_plan(plan.id, plan.user_id, db)


async def delete_plan(plan: StudyPlan, db: AsyncSession) -> None:
    await db.delete(plan)
    await db.flush()


async def update_plan_status(
    plan: StudyPlan, data: PlanStatusUpdate, db: AsyncSession
) -> StudyPlan:
    plan.status = data.status
    await db.flush()
    await db.refresh(plan)
    return plan


async def _load_plan_tasks(plan_ids: list[int], db: AsyncSession) -> list[Task]:
    if not plan_ids:
        return []
    result = await db.execute(
        select(Task)
        .where(Task.plan_id.in_(plan_ids))
        .order_by(Task.sort_order.asc(), Task.created_at.asc())
    )
    return list(result.scalars().all())


def _build_schedule_items(tasks: list[Task]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_date: dict[date, list[Task]] = defaultdict(list)
    by_week: dict[str, list[Task]] = defaultdict(list)

    for task in tasks:
        schedule_date = task.scheduled_date or (task.due_date.date() if task.due_date else None)
        if schedule_date is None:
            continue
        by_date[schedule_date].append(task)
        iso_year, iso_week, _ = schedule_date.isocalendar()
        by_week[f"{iso_year}-W{iso_week:02d}"].append(task)

    day_schedule = [
        PlanScheduleItem(
            date=day,
            label=f"{day.month:02d}/{day.day:02d}",
            task_count=len(items),
            completed_task_count=sum(1 for item in items if item.status == "completed"),
            task_titles=[item.title for item in items[:4]],
        ).model_dump()
        for day, items in sorted(by_date.items(), key=lambda item: item[0])
    ]

    week_schedule = [
        PlanWeekSummary(
            week_label=week_label,
            task_count=len(items),
            completed_task_count=sum(1 for item in items if item.status == "completed"),
            dates=sorted(
                {
                    str(task.scheduled_date or due_day)
                    for task in items
                    for due_day in [task.due_date.date() if task.due_date is not None else None]
                    if task.scheduled_date is not None or due_day is not None
                }
            ),
        ).model_dump()
        for week_label, items in sorted(by_week.items(), key=lambda item: item[0])
    ]
    return day_schedule, week_schedule


def _build_phase_payloads(phases: list[PlanPhase], tasks: list[Task]) -> list[dict[str, Any]]:
    phase_tasks: dict[int, list[Task]] = defaultdict(list)
    for task in tasks:
        if task.parent_task_id is None and task.phase_id is not None:
            phase_tasks[task.phase_id].append(task)

    payloads: list[dict[str, Any]] = []
    for phase in phases:
        items = phase_tasks.get(phase.id, [])
        completed_count = sum(1 for item in items if item.status == "completed")
        task_count = len(items)
        payloads.append(
            PlanPhaseResponse(
                id=phase.id,
                title=phase.title,
                description=phase.description,
                sequence=phase.sequence,
                start_date=phase.start_date,
                end_date=phase.end_date,
                task_count=task_count,
                completed_task_count=completed_count,
                progress_percent=round(
                    (completed_count / task_count) * 100 if task_count else 0.0, 1
                ),
            ).model_dump()
        )
    return payloads


async def _load_plan_stats(
    plans: Iterable[StudyPlan], db: AsyncSession
) -> dict[int, dict[str, Any]]:
    plan_list = list(plans)
    plan_ids = [plan.id for plan in plan_list]
    if not plan_ids:
        return {}

    tasks = await _load_plan_tasks(plan_ids, db)
    phase_result = await db.execute(
        select(PlanPhase)
        .where(PlanPhase.plan_id.in_(plan_ids))
        .order_by(PlanPhase.plan_id.asc(), PlanPhase.sequence.asc(), PlanPhase.id.asc())
    )

    phases_by_plan: dict[int, list[PlanPhase]] = defaultdict(list)
    for phase in phase_result.scalars().all():
        phases_by_plan[phase.plan_id].append(phase)

    grouped: dict[int, list[Task]] = defaultdict(list)
    for task in tasks:
        if task.plan_id is not None:
            grouped[task.plan_id].append(task)

    stats: dict[int, dict[str, Any]] = {}
    for plan in plan_list:
        items = grouped.get(plan.id, [])
        top_level = [task for task in items if task.parent_task_id is None]
        subtasks = [task for task in items if task.parent_task_id is not None]
        completed_top = sum(1 for task in top_level if task.status == "completed")
        completed_subtasks = sum(1 for task in subtasks if task.status == "completed")
        day_schedule, week_schedule = _build_schedule_items(top_level)

        stats[plan.id] = {
            "task_count": len(top_level),
            "completed_task_count": completed_top,
            "progress_percent": round(
                (completed_top / len(top_level)) * 100 if top_level else 0.0, 1
            ),
            "subtask_count": len(subtasks),
            "completed_subtask_count": completed_subtasks,
            "status_breakdown": {
                "pending": sum(1 for task in items if task.status == "pending"),
                "in_progress": sum(1 for task in items if task.status == "in_progress"),
                "completed": sum(1 for task in items if task.status == "completed"),
                "overdue": sum(1 for task in items if task.status == "overdue"),
            },
            "day_schedule": day_schedule,
            "week_schedule": week_schedule,
            "phases": _build_phase_payloads(phases_by_plan.get(plan.id, []), items),
        }
    return stats


def _plan_base_payload(plan: StudyPlan) -> dict[str, Any]:
    return {
        "id": plan.id,
        "title": plan.title,
        "description": plan.description,
        "template_key": plan.template_key,
        "start_date": plan.start_date,
        "end_date": plan.end_date,
        "status": plan.status,
        "created_at": plan.created_at,
    }


async def serialize_plan(plan: StudyPlan, db: AsyncSession) -> dict[str, Any]:
    stats = await _load_plan_stats([plan], db)
    payload = _plan_base_payload(plan)
    payload.update(stats.get(plan.id, {}))
    return PlanResponse.model_validate(payload).model_dump()


async def serialize_plan_list(plans: list[StudyPlan], db: AsyncSession) -> list[dict[str, Any]]:
    stats = await _load_plan_stats(plans, db)
    serialized: list[dict[str, Any]] = []
    for plan in plans:
        payload = _plan_base_payload(plan)
        payload.update(stats.get(plan.id, {}))
        serialized.append(PlanResponse.model_validate(payload).model_dump())
    return serialized
