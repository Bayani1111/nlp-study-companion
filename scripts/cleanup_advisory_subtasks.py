from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import Select, select

from app.database import async_session_factory
from app.models import Task
from app.services.task_cleanup_rules import decide_advisory_subtask_cleanup


def _build_query(user_id: int | None, limit: int | None) -> Select[tuple[Task]]:
    stmt: Select[tuple[Task]] = select(Task).where(Task.parent_task_id.is_not(None)).order_by(Task.id.asc())
    if user_id is not None:
        stmt = stmt.where(Task.user_id == user_id)
    if limit is not None and limit > 0:
        stmt = stmt.limit(limit)
    return stmt


async def run_cleanup(*, user_id: int | None, limit: int | None, apply: bool) -> None:
    async with async_session_factory() as session:
        stmt = _build_query(user_id, limit)
        rows = await session.execute(stmt)
        subtasks = list(rows.scalars().all())

        candidates: list[Task] = []
        for task in subtasks:
            decision = decide_advisory_subtask_cleanup(task.title, task.description)
            if decision.should_delete:
                candidates.append(task)
                print(
                    f"[CANDIDATE] task_id={task.id} user_id={task.user_id} parent_task_id={task.parent_task_id} "
                    f"title={task.title!r} reason={decision.reason}"
                )

        print(
            f"\nScanned {len(subtasks)} subtasks, found {len(candidates)} advisory subtasks."
        )

        if not apply:
            print("Dry-run mode: no data deleted. Add --apply to execute deletion.")
            await session.rollback()
            return

        for task in candidates:
            await session.delete(task)
        await session.commit()
        print(f"Deleted {len(candidates)} advisory subtasks.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean advisory subtasks polluted from chat suggestions.")
    parser.add_argument("--user-id", type=int, default=None, help="Only clean tasks for this user.")
    parser.add_argument("--limit", type=int, default=None, help="Only scan first N subtasks.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete records. Without this flag, script runs in dry-run mode.",
    )
    args = parser.parse_args()
    asyncio.run(run_cleanup(user_id=args.user_id, limit=args.limit, apply=args.apply))


if __name__ == "__main__":
    main()
