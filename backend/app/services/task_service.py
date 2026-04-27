from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.errors import not_found, validation_error
from app.models import PlanPhase, StudyPlan, Task

VALID_STATUSES = {"pending", "in_progress", "completed", "overdue"}
VALID_PRIORITIES = {"high", "medium", "low"}


def _normalize_due_date(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None

    due_date = value
    if isinstance(due_date, str):
        due_date = datetime.fromisoformat(due_date)
    if due_date.tzinfo is None:
        due_date = due_date.replace(tzinfo=timezone.utc)
    if due_date < datetime.now(timezone.utc):
        raise validation_error("截止时间不能早于当前时间")
    return due_date


def _normalize_scheduled_date(value: date | str | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return date.fromisoformat(value)
    return value


async def _validate_plan_ownership(
    user_id: int,
    plan_id: int | None,
    db: AsyncSession,
) -> int | None:
    if plan_id is None:
        return None

    result = await db.execute(
        select(StudyPlan).where(
            StudyPlan.id == plan_id,
            StudyPlan.user_id == user_id,
        )
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise not_found("学习计划不存在")
    return plan_id


async def _validate_phase_ownership(
    *,
    user_id: int,
    phase_id: int | None,
    plan_id: int | None,
    db: AsyncSession,
) -> int | None:
    if phase_id is None:
        return None

    result = await db.execute(
        select(PlanPhase)
        .join(StudyPlan, PlanPhase.plan_id == StudyPlan.id)
        .where(
            PlanPhase.id == phase_id,
            StudyPlan.user_id == user_id,
        )
    )
    phase = result.scalar_one_or_none()
    if phase is None:
        raise not_found("计划阶段不存在")
    if plan_id is not None and phase.plan_id != plan_id:
        raise validation_error("任务绑定的阶段必须属于同一个学习计划")
    return phase.id


async def _get_task_with_children(user_id: int, task_id: int, db: AsyncSession) -> Task:
    result = await db.execute(
        select(Task)
        .where(Task.id == task_id, Task.user_id == user_id)
        .options(selectinload(Task.children).selectinload(Task.children))
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise not_found("任务不存在")
    return task


async def _validate_parent_task(
    *,
    user_id: int,
    parent_task_id: int | None,
    plan_id: int | None,
    phase_id: int | None,
    db: AsyncSession,
    current_task_id: int | None = None,
) -> Task | None:
    if parent_task_id is None:
        return None

    parent = await _get_task_with_children(user_id, parent_task_id, db)
    if current_task_id is not None:
        if parent.id == current_task_id:
            raise validation_error("任务不能把自己设为父任务")
        if parent.parent_task_id == current_task_id:
            raise validation_error("不能把任务移动到自己的子任务下面")

    if parent.parent_task_id is not None:
        raise validation_error("当前仅支持一级子任务，请选择顶层任务作为父任务")

    if plan_id is not None and parent.plan_id is not None and plan_id != parent.plan_id:
        raise validation_error("子任务必须和父任务属于同一个学习计划")
    if phase_id is not None and parent.phase_id is not None and phase_id != parent.phase_id:
        raise validation_error("子任务必须和父任务属于同一个计划阶段")

    return parent


async def _get_child_tasks(task_id: int, db: AsyncSession) -> list[Task]:
    result = await db.execute(
        select(Task)
        .where(Task.parent_task_id == task_id)
        .order_by(Task.sort_order.asc(), Task.created_at.asc())
    )
    return list(result.scalars().all())


async def _ensure_parent_completion_allowed(task: Task, db: AsyncSession) -> None:
    child_tasks = await _get_child_tasks(task.id, db)
    if child_tasks and any(child.status != "completed" for child in child_tasks):
        raise validation_error("只有全部子任务完成后，主任务才能标记为完成")


async def _sync_parent_status(parent_task_id: int | None, db: AsyncSession) -> None:
    if parent_task_id is None:
        return

    parent_result = await db.execute(select(Task).where(Task.id == parent_task_id))
    parent = parent_result.scalar_one_or_none()
    if parent is None:
        return

    status_result = await db.execute(
        select(Task.status).where(Task.parent_task_id == parent_task_id)
    )
    child_statuses = [status for status in status_result.scalars().all()]
    if not child_statuses:
        return

    if all(status == "completed" for status in child_statuses):
        parent.status = "completed"
    elif all(status == "pending" for status in child_statuses):
        parent.status = "pending"
    else:
        parent.status = "in_progress"

    await db.flush()


async def _sync_children_scope(parent_task_id: int, task: Task, db: AsyncSession) -> None:
    children = await _get_child_tasks(parent_task_id, db)
    for child in children:
        child.plan_id = task.plan_id
        child.phase_id = task.phase_id
        if child.scheduled_date is None:
            child.scheduled_date = task.scheduled_date
    if children:
        await db.flush()


def _serialize_task(task: Task) -> dict[str, Any]:
    children = sorted(
        task.children,
        key=lambda item: (item.sort_order, item.created_at or datetime.min),
    )
    serialized_children = [_serialize_task(child) for child in children]
    completed_subtasks = sum(1 for child in children if child.status == "completed")

    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "priority": task.priority,
        "status": task.status,
        "due_date": task.due_date,
        "scheduled_date": task.scheduled_date,
        "estimated_minutes": task.estimated_minutes,
        "actual_minutes": task.actual_minutes,
        "plan_id": task.plan_id,
        "phase_id": task.phase_id,
        "sort_order": task.sort_order,
        "parent_task_id": task.parent_task_id,
        "subtask_count": len(children),
        "completed_subtask_count": completed_subtasks,
        "children": serialized_children,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def serialize_task(task: Task) -> dict[str, Any]:
    return _serialize_task(task)


def serialize_task_list(tasks: Sequence[Task]) -> list[dict[str, Any]]:
    return [serialize_task(task) for task in tasks]


async def list_tasks(
    user_id: int,
    db: AsyncSession,
    *,
    status_filter: str | None = None,
    priority_filter: str | None = None,
) -> list[Task]:
    stmt = (
        select(Task)
        .where(Task.user_id == user_id, Task.parent_task_id.is_(None))
        .options(selectinload(Task.children).selectinload(Task.children))
        .order_by(
            Task.sort_order.asc(), Task.scheduled_date.asc().nulls_last(), Task.created_at.desc()
        )
    )
    if status_filter and status_filter in VALID_STATUSES:
        stmt = stmt.where(Task.status == status_filter)
    if priority_filter and priority_filter in VALID_PRIORITIES:
        stmt = stmt.where(Task.priority == priority_filter)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_task(
    user_id: int,
    data: dict[str, Any],
    db: AsyncSession,
) -> Task:
    title = (data.get("title") or "").strip()
    if not title:
        raise validation_error("任务标题不能为空")

    priority = data.get("priority", "medium")
    if priority not in VALID_PRIORITIES:
        raise validation_error(f"无效的优先级: {priority}")

    task_status = data.get("status", "pending")
    if task_status not in VALID_STATUSES:
        raise validation_error(f"无效的状态: {task_status}")

    due_date = _normalize_due_date(data.get("due_date"))
    scheduled_date = _normalize_scheduled_date(data.get("scheduled_date"))
    requested_plan_id = await _validate_plan_ownership(user_id, data.get("plan_id"), db)
    requested_phase_id = await _validate_phase_ownership(
        user_id=user_id,
        phase_id=data.get("phase_id"),
        plan_id=requested_plan_id,
        db=db,
    )
    parent = await _validate_parent_task(
        user_id=user_id,
        parent_task_id=data.get("parent_task_id"),
        plan_id=requested_plan_id,
        phase_id=requested_phase_id,
        db=db,
    )

    plan_id = parent.plan_id if parent is not None else requested_plan_id
    phase_id = parent.phase_id if parent is not None else requested_phase_id
    if parent is not None and task_status == "completed":
        raise validation_error("请先创建子任务，再逐项完成，不要直接把新子任务设为完成")

    task = Task(
        user_id=user_id,
        title=title,
        description=data.get("description"),
        priority=priority,
        status=task_status,
        due_date=due_date,
        scheduled_date=scheduled_date or (parent.scheduled_date if parent is not None else None),
        sort_order=data.get("sort_order", 0) or 0,
        estimated_minutes=data.get("estimated_minutes"),
        plan_id=plan_id,
        phase_id=phase_id,
        parent_task_id=parent.id if parent is not None else None,
    )
    db.add(task)
    await db.flush()
    await _sync_parent_status(task.parent_task_id, db)
    return await _get_task_with_children(user_id, task.id, db)


async def get_task(user_id: int, task_id: int, db: AsyncSession) -> Task:
    return await _get_task_with_children(user_id, task_id, db)


async def update_task(
    user_id: int,
    task_id: int,
    data: dict[str, Any],
    db: AsyncSession,
) -> Task:
    task = await _get_task_with_children(user_id, task_id, db)
    previous_parent_id = task.parent_task_id

    if "title" in data:
        title = (data["title"] or "").strip()
        if not title:
            raise validation_error("任务标题不能为空")
        task.title = title

    if "description" in data:
        task.description = data["description"]

    if "priority" in data:
        if data["priority"] not in VALID_PRIORITIES:
            raise validation_error(f"无效的优先级: {data['priority']}")
        task.priority = data["priority"]

    if "due_date" in data:
        task.due_date = _normalize_due_date(data["due_date"])

    if "scheduled_date" in data:
        task.scheduled_date = _normalize_scheduled_date(data["scheduled_date"])

    if "sort_order" in data and data["sort_order"] is not None:
        task.sort_order = int(data["sort_order"])

    if "estimated_minutes" in data:
        task.estimated_minutes = data["estimated_minutes"]

    if "actual_minutes" in data:
        task.actual_minutes = data["actual_minutes"]

    requested_plan_id = task.plan_id
    if "plan_id" in data:
        requested_plan_id = await _validate_plan_ownership(user_id, data["plan_id"], db)

    requested_phase_id = task.phase_id
    if "phase_id" in data:
        requested_phase_id = await _validate_phase_ownership(
            user_id=user_id,
            phase_id=data["phase_id"],
            plan_id=requested_plan_id,
            db=db,
        )

    if "parent_task_id" in data:
        if task.children:
            raise validation_error("已有子任务的大任务不能再绑定到其他父任务下")
        parent = await _validate_parent_task(
            user_id=user_id,
            parent_task_id=data["parent_task_id"],
            plan_id=requested_plan_id,
            phase_id=requested_phase_id,
            db=db,
            current_task_id=task.id,
        )
        task.parent_task_id = parent.id if parent is not None else None
        task.plan_id = parent.plan_id if parent is not None else requested_plan_id
        task.phase_id = parent.phase_id if parent is not None else requested_phase_id
        if task.scheduled_date is None and parent is not None:
            task.scheduled_date = parent.scheduled_date
    else:
        if "plan_id" in data:
            task.plan_id = requested_plan_id
        if "phase_id" in data:
            task.phase_id = requested_phase_id

    if "status" in data:
        next_status = data["status"]
        if next_status not in VALID_STATUSES:
            raise validation_error(f"无效的状态: {next_status}")
        if next_status == "completed":
            await _ensure_parent_completion_allowed(task, db)
        task.status = next_status

    if task.children and {"plan_id", "phase_id", "scheduled_date"} & set(data.keys()):
        await _sync_children_scope(task.id, task, db)

    await db.flush()
    await _sync_parent_status(previous_parent_id, db)
    await _sync_parent_status(task.parent_task_id, db)
    return await _get_task_with_children(user_id, task.id, db)


async def delete_task(user_id: int, task_id: int, db: AsyncSession) -> None:
    task = await _get_task_with_children(user_id, task_id, db)
    parent_task_id = task.parent_task_id
    await db.delete(task)
    await db.flush()
    await _sync_parent_status(parent_task_id, db)


async def complete_task(user_id: int, task_id: int, db: AsyncSession) -> Task:
    return await update_task(user_id, task_id, {"status": "completed"}, db)
