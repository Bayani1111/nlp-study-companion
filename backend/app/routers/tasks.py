"""Task management routes."""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Task
from app.schemas.tasks import (
    AdvisoryCleanupCandidate,
    AdvisoryCleanupResponse,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
)
from app.services.task_cleanup_rules import decide_advisory_subtask_cleanup
from app.services import task_service

router = APIRouter()


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    status_filter: str | None = Query(None, alias="status"),
    priority: str | None = Query(None),
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the current user's task list with optional filters."""
    tasks = await task_service.list_tasks(
        user_id,
        db,
        status_filter=status_filter,
        priority_filter=priority,
    )
    return [TaskResponse.model_validate(task_service.serialize_task(task)) for task in tasks]


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: TaskCreate,
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a task for the current user."""
    task = await task_service.create_task(user_id, body.model_dump(), db)
    return TaskResponse.model_validate(task_service.serialize_task(task))


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: int,
    body: TaskUpdate,
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a task after ownership checks pass."""
    task = await task_service.update_task(
        user_id,
        task_id,
        body.model_dump(exclude_unset=True),
        db,
    )
    return TaskResponse.model_validate(task_service.serialize_task(task))


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: int,
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a task after ownership checks pass."""
    await task_service.delete_task(user_id, task_id, db)


@router.post("/cleanup/advisory", response_model=AdvisoryCleanupResponse)
async def cleanup_advisory_subtasks(
    dry_run: bool = Query(True, description="Preview only. Set false to apply deletion."),
    limit: int | None = Query(None, ge=1, le=5000, description="Max subtasks to scan."),
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Clean historical advisory-like subtasks polluted from conversational text."""
    stmt = (
        select(Task)
        .where(Task.user_id == user_id, Task.parent_task_id.is_not(None))
        .order_by(Task.id.asc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = await db.execute(stmt)
    subtasks = list(rows.scalars().all())

    candidates: list[AdvisoryCleanupCandidate] = []
    matched_ids: list[int] = []
    for item in subtasks:
        decision = decide_advisory_subtask_cleanup(item.title, item.description)
        if not decision.should_delete:
            continue
        matched_ids.append(item.id)
        candidates.append(
            AdvisoryCleanupCandidate(
                id=item.id,
                parent_task_id=item.parent_task_id,
                title=item.title,
                reason=decision.reason,
            )
        )

    deleted_count = 0
    if not dry_run:
        for task_id in matched_ids:
            await task_service.delete_task(user_id, task_id, db)
        deleted_count = len(matched_ids)

    return AdvisoryCleanupResponse(
        dry_run=dry_run,
        scanned_subtasks=len(subtasks),
        matched_count=len(matched_ids),
        deleted_count=deleted_count,
        candidates=candidates,
    )
