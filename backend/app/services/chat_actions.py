import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task
from app.schemas.plans import PlanCreate
from app.services import plan_service, task_service
from app.services.chat_rule_parser import infer_plan_date_range
from app.services.stats_service import record_learning_activity

logger = logging.getLogger(__name__)

# Must match Pydantic PlanCreate / Task API limits — long LLM plan drafts can exceed and fail validation.
PLAN_TITLE_MAX = 200
PLAN_DESC_MAX = 2000
TASK_TITLE_MAX = 200
TASK_DESC_MAX = 2000


def _clip_for_schema(
    value: str | None,
    max_len: int,
) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if len(s) <= max_len:
        return s
    if max_len <= 1:
        return "…"[:max_len]
    return s[: max_len - 1] + "…"


@dataclass
class ChatActionResult:
    payload: Any = None
    extracted_tasks: list[dict] | None = None
    extracted_plans: list[dict] | None = None


async def _create_subtasks(
    *,
    user_id: int,
    parent_task_id: int,
    parent_plan_id: int | None,
    subtasks: list[Any],
    priority: str,
    due_date: Any,
    db: AsyncSession,
) -> list[dict]:
    extracted: list[dict] = []
    for item in subtasks:
        if isinstance(item, dict):
            raw_title = str(item.get("title") or "").strip()
            desc = item.get("description")
        else:
            raw_title = str(item or "")
            desc = None
        clipped = _clip_for_schema(raw_title, TASK_TITLE_MAX) or "子任务"
        desc_clipped = _clip_for_schema(str(desc) if desc is not None else None, TASK_DESC_MAX)
        child = await task_service.create_task(
            user_id,
            {
                "title": clipped,
                "description": desc_clipped,
                "priority": priority,
                "due_date": due_date,
                "plan_id": parent_plan_id,
                "parent_task_id": parent_task_id,
            },
            db,
        )
        extracted.append(
            {
                "id": child.id,
                "title": child.title,
                "plan_id": child.plan_id,
                "parent_task_id": child.parent_task_id,
            }
        )
    return extracted


async def _resolve_existing_root_task(
    *,
    user_id: int,
    db: AsyncSession,
    plan_id: int | None,
    task_id: int | None,
) -> Task | None:
    if task_id is not None:
        return await task_service.get_task(user_id, int(task_id), db)

    if plan_id is None:
        return None

    result = await db.execute(
        select(Task)
        .where(
            Task.user_id == user_id,
            Task.plan_id == plan_id,
            Task.parent_task_id.is_(None),
        )
        .order_by(Task.sort_order.asc(), Task.created_at.desc())
    )
    task = result.scalars().first()
    if task is None:
        return None
    return await task_service.get_task(user_id, task.id, db)


async def execute_chat_action(
    user_id: int,
    intent: str,
    entities: dict[str, Any],
    fallback_message: str,
    db: AsyncSession,
    *,
    due_date: Any = None,
) -> ChatActionResult:
    if intent == "create_task":
        try:
            task_data = {
                "title": entities.get("task_title") or fallback_message[:30],
                "due_date": due_date,
                "priority": entities.get("priority", "medium"),
                "description": entities.get("description") or fallback_message,
                "plan_id": entities.get("plan_id"),
            }
            created_task = await task_service.create_task(user_id, task_data, db)

            extracted_tasks = [
                {
                    "id": created_task.id,
                    "title": created_task.title,
                    "plan_id": created_task.plan_id,
                    "parent_task_id": created_task.parent_task_id,
                }
            ]

            subtasks = entities.get("subtasks") or []
            if subtasks:
                child_tasks = await _create_subtasks(
                    user_id=user_id,
                    parent_task_id=created_task.id,
                    parent_plan_id=created_task.plan_id,
                    subtasks=subtasks,
                    priority=created_task.priority,
                    due_date=due_date,
                    db=db,
                )
                extracted_tasks.extend(child_tasks)

            await record_learning_activity(user_id, "task_create", db, task_id=created_task.id)
            refreshed_task = await task_service.get_task(user_id, created_task.id, db)
            return ChatActionResult(
                payload=refreshed_task,
                extracted_tasks=extracted_tasks,
            )
        except Exception as exc:
            logger.warning("Failed to create task from chat: %s", exc)
            return ChatActionResult()

    if intent == "create_plan":
        bound_task: Any | None = None
        try:
            start_date, end_date = infer_plan_date_range(fallback_message, due_date)
            span = entities.get("plan_day_span")
            if isinstance(span, int) and span >= 2:
                end_date = start_date + timedelta(days=span - 1)
            raw_title = (
                entities.get("plan_title") or entities.get("task_title") or (fallback_message[:30])
            )
            plan_title = _clip_for_schema(str(raw_title), PLAN_TITLE_MAX) or "学习计划"
            raw_desc = (
                entities.get("plan_description") or entities.get("description") or fallback_message
            )
            plan_description = _clip_for_schema(str(raw_desc), PLAN_DESC_MAX)
            plan = await plan_service.create_plan(
                user_id,
                PlanCreate(
                    title=plan_title,
                    description=plan_description,
                    start_date=start_date,
                    end_date=end_date,
                    template_key=None,
                ),
                db,
            )

            plan_extracted_tasks: list[dict] | None = None
            if entities.get("should_create_task"):
                task_title = _clip_for_schema(
                    str(entities.get("task_title") or plan.title),
                    TASK_TITLE_MAX,
                ) or plan.title
                task_desc = _clip_for_schema(
                    str(entities.get("description") or raw_desc or fallback_message),
                    TASK_DESC_MAX,
                )
                task_data = {
                    "title": task_title,
                    "due_date": due_date,
                    "priority": entities.get("priority", "medium"),
                    "description": task_desc,
                    "plan_id": plan.id,
                }
                bound_task = await task_service.create_task(user_id, task_data, db)
                plan_extracted_tasks = [
                    {
                        "id": bound_task.id,
                        "title": bound_task.title,
                        "plan_id": plan.id,
                        "parent_task_id": bound_task.parent_task_id,
                    }
                ]

                subtasks = entities.get("subtasks") or []
                if subtasks:
                    child_tasks = await _create_subtasks(
                        user_id=user_id,
                        parent_task_id=bound_task.id,
                        parent_plan_id=plan.id,
                        subtasks=subtasks,
                        priority=bound_task.priority,
                        due_date=due_date,
                        db=db,
                    )
                    plan_extracted_tasks.extend(child_tasks)

                await record_learning_activity(user_id, "task_create", db, task_id=bound_task.id)
                bound_task = await task_service.get_task(user_id, bound_task.id, db)

            return ChatActionResult(
                payload={"plan": plan, "task": bound_task},
                extracted_tasks=plan_extracted_tasks,
                extracted_plans=[{"id": plan.id, "title": plan.title}],
            )
        except (ValidationError, Exception) as exc:
            logger.warning("Failed to create plan from chat: %s", exc)
            return ChatActionResult()

    if intent == "refine_plan":
        try:
            plan_id = entities.get("plan_id")
            if plan_id is None:
                return ChatActionResult()

            plan = await plan_service.get_owned_plan(int(plan_id), user_id, db)
            bound_task = await _resolve_existing_root_task(
                user_id=user_id,
                db=db,
                plan_id=plan.id,
                task_id=entities.get("task_id"),
            )

            if bound_task is None:
                fallback_task_title = (
                    entities.get("task_title")
                    if not entities.get("refine_existing")
                    else entities.get("task_title") or entities.get("plan_title") or plan.title
                )
                task_data = {
                    "title": fallback_task_title or plan.title,
                    "due_date": due_date,
                    "priority": entities.get("priority", "medium"),
                    "description": entities.get("description") or plan.description or fallback_message,
                    "plan_id": plan.id,
                }
                bound_task = await task_service.create_task(user_id, task_data, db)
                await record_learning_activity(user_id, "task_create", db, task_id=bound_task.id)

            return ChatActionResult(
                payload={"plan": plan, "task": bound_task, "refinement_mode": True},
                extracted_tasks=[
                    {
                        "id": bound_task.id,
                        "title": bound_task.title,
                        "plan_id": bound_task.plan_id,
                        "parent_task_id": bound_task.parent_task_id,
                    }
                ],
                extracted_plans=[{"id": plan.id, "title": plan.title}],
            )
        except Exception as exc:
            logger.warning("Failed to refine plan from chat: %s", exc)
            return ChatActionResult()

    if intent == "query_task":
        tasks = await task_service.list_tasks(user_id, db)
        return ChatActionResult(payload=tasks)

    if intent == "update_task":
        task_id = entities.get("task_id")
        if task_id is None:
            return ChatActionResult()
        updates = {
            key: value for key, value in entities.items() if key != "task_id" and value is not None
        }
        try:
            updated_task = await task_service.update_task(user_id, int(task_id), updates, db)
            return ChatActionResult(payload=updated_task)
        except Exception as exc:
            logger.warning("Failed to update task from chat: %s", exc)
            return ChatActionResult()

    if intent == "complete_task":
        task_id = entities.get("task_id")
        if task_id is None:
            return ChatActionResult()
        try:
            completed_task = await task_service.complete_task(user_id, int(task_id), db)
            await record_learning_activity(
                user_id,
                "task_complete",
                db,
                task_id=int(task_id),
            )
            return ChatActionResult(payload=completed_task)
        except Exception as exc:
            logger.warning("Failed to complete task from chat: %s", exc)
            return ChatActionResult()

    return ChatActionResult()
