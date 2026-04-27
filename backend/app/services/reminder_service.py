"""Reminder scheduling and WebSocket delivery."""

from __future__ import annotations

from datetime import datetime, time, timezone

from fastapi import WebSocket
from sqlalchemy import select

from app.database import async_session_factory
from app.models import PlanPhase, ReminderSetting, StudyPlan, Task


class ConnectionManager:
    """Track active WebSocket connections by user id."""

    def __init__(self) -> None:
        self._connections: dict[int, list[WebSocket]] = {}
        self._pending: dict[int, list[dict]] = {}

    async def connect(self, user_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.setdefault(user_id, []).append(ws)
        pending = self._pending.pop(user_id, [])
        for message in pending:
            try:
                await ws.send_json(message)
            except Exception:
                pass

    def disconnect(self, user_id: int, ws: WebSocket) -> None:
        connections = self._connections.get(user_id, [])
        if ws in connections:
            connections.remove(ws)
        if not connections:
            self._connections.pop(user_id, None)

    async def send_to_user(self, user_id: int, data: dict) -> None:
        connections = self._connections.get(user_id, [])
        if not connections:
            self._pending.setdefault(user_id, []).append(data)
            return

        dead_connections: list[WebSocket] = []
        for ws in connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead_connections.append(ws)

        for ws in dead_connections:
            self.disconnect(user_id, ws)

    def is_connected(self, user_id: int) -> bool:
        return bool(self._connections.get(user_id))


manager = ConnectionManager()

_sent_reminders: dict[str, datetime] = {}
_DEDUP_WINDOWS = {
    "approaching_deadline": 30,
    "overdue": 120,
    "overdue_critical": 360,
    "phase_checkpoint": 720,
}


def _reminder_key(user_id: int, item_id: int, reminder_type: str) -> str:
    return f"{user_id}:{item_id}:{reminder_type}"


def _already_reminded(user_id: int, item_id: int, reminder_type: str) -> bool:
    key = _reminder_key(user_id, item_id, reminder_type)
    last_sent = _sent_reminders.get(key)
    if last_sent is None:
        return False
    elapsed = (datetime.now(timezone.utc) - last_sent).total_seconds() / 60
    return elapsed < _DEDUP_WINDOWS.get(reminder_type, 30)


def _record_reminder_sent(user_id: int, item_id: int, reminder_type: str) -> None:
    key = _reminder_key(user_id, item_id, reminder_type)
    _sent_reminders[key] = datetime.now(timezone.utc)


def _in_quiet_hours(hour: int, quiet_start: int, quiet_end: int) -> bool:
    if quiet_start <= quiet_end:
        return quiet_start <= hour < quiet_end
    return hour >= quiet_start or hour < quiet_end


def _phase_end_datetime(phase: PlanPhase) -> datetime | None:
    if phase.end_date is None:
        return None
    return datetime.combine(
        phase.end_date, time(hour=23, minute=59, second=59), tzinfo=timezone.utc
    )


async def _send_task_reminders(
    user_id: int, setting: ReminderSetting, tasks: list[Task], now: datetime
) -> None:
    for task in tasks:
        reminder_type: str | None = None
        overdue_minutes = 0

        if task.due_date is not None:
            due = task.due_date
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)

            diff_minutes = (due - now).total_seconds() / 60
            if 0 < diff_minutes <= setting.before_due_minutes:
                reminder_type = "approaching_deadline"
            elif diff_minutes <= -1440 and setting.overdue_enabled:
                reminder_type = "overdue_critical"
                overdue_minutes = abs(int(diff_minutes))
            elif diff_minutes <= 0 and setting.overdue_enabled:
                reminder_type = "overdue"
                overdue_minutes = abs(int(diff_minutes))

        if reminder_type and not _already_reminded(user_id, task.id, reminder_type):
            await manager.send_to_user(
                user_id,
                {
                    "type": reminder_type,
                    "task_id": task.id,
                    "task_title": task.title,
                    "due_date": task.due_date.isoformat() if task.due_date else None,
                    "overdue_minutes": overdue_minutes,
                },
            )
            _record_reminder_sent(user_id, task.id, reminder_type)


async def check_and_send_reminders() -> None:
    """Scan pending tasks and push reminder notifications."""
    now = datetime.now(timezone.utc)
    current_hour = now.hour

    async with async_session_factory() as db:
        settings_result = await db.execute(select(ReminderSetting))
        all_settings = list(settings_result.scalars().all())

        for setting in all_settings:
            if _in_quiet_hours(current_hour, setting.quiet_start_hour, setting.quiet_end_hour):
                continue

            user_id = setting.user_id
            task_result = await db.execute(
                select(Task).where(
                    Task.user_id == user_id,
                    Task.status.in_(["pending", "in_progress"]),
                    Task.due_date.isnot(None),
                )
            )
            tasks = list(task_result.scalars().all())
            await _send_task_reminders(user_id, setting, tasks, now)

            phase_result = await db.execute(
                select(PlanPhase, StudyPlan)
                .join(StudyPlan, PlanPhase.plan_id == StudyPlan.id)
                .where(StudyPlan.user_id == user_id, StudyPlan.status == "active")
            )
            phases_with_plan = list(phase_result.all())

            for phase, plan in phases_with_plan:
                phase_end = _phase_end_datetime(phase)
                if phase_end is None:
                    continue

                remaining_minutes = (phase_end - now).total_seconds() / 60
                if remaining_minutes < 0 or remaining_minutes > max(
                    setting.before_start_minutes, 180
                ):
                    continue

                phase_task_result = await db.execute(
                    select(Task).where(
                        Task.user_id == user_id,
                        Task.phase_id == phase.id,
                        Task.parent_task_id.is_(None),
                        Task.status.in_(["pending", "in_progress", "overdue"]),
                    )
                )
                remaining_tasks = list(phase_task_result.scalars().all())
                if not remaining_tasks or _already_reminded(user_id, phase.id, "phase_checkpoint"):
                    continue

                await manager.send_to_user(
                    user_id,
                    {
                        "type": "phase_checkpoint",
                        "plan_id": plan.id,
                        "plan_title": plan.title,
                        "phase_id": phase.id,
                        "phase_title": phase.title,
                        "remaining_task_count": len(remaining_tasks),
                        "phase_end_date": phase.end_date.isoformat() if phase.end_date else None,
                    },
                )
                _record_reminder_sent(user_id, phase.id, "phase_checkpoint")
