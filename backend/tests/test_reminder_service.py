from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PlanPhase, ReminderSetting, StudyPlan, Task, User
from app.services import reminder_service


class FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.sent_messages: list[dict] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, data: dict) -> None:
        self.sent_messages.append(data)


class SessionFactoryStub:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def __aenter__(self) -> AsyncSession:
        return self.session

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def __call__(self):
        return self


async def create_user(session: AsyncSession, username: str, email: str) -> User:
    user = User(username=username, email=email, password_hash="hashed")
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_connection_manager_buffers_and_flushes_pending_messages():
    manager = reminder_service.ConnectionManager()
    ws = FakeWebSocket()
    payload = {"type": "approaching_deadline", "task_id": 1}

    await manager.send_to_user(7, payload)
    assert manager.is_connected(7) is False

    await manager.connect(7, ws)

    assert ws.accepted is True
    assert ws.sent_messages == [payload]
    assert manager.is_connected(7) is True


def test_in_quiet_hours_supports_same_day_and_cross_midnight_windows():
    assert reminder_service._in_quiet_hours(23, 22, 8) is True
    assert reminder_service._in_quiet_hours(7, 22, 8) is True
    assert reminder_service._in_quiet_hours(12, 22, 8) is False
    assert reminder_service._in_quiet_hours(10, 9, 18) is True
    assert reminder_service._in_quiet_hours(20, 9, 18) is False


@pytest.mark.asyncio
async def test_check_and_send_reminders_sends_due_soon_once_and_deduplicates(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    user = await create_user(session, "reminder_user", "reminder@example.com")
    session.add(
        ReminderSetting(
            user_id=user.id,
            before_due_minutes=30,
            overdue_enabled=True,
            quiet_start_hour=22,
            quiet_end_hour=8,
        )
    )

    fixed_now = datetime(2026, 4, 24, 10, 0, tzinfo=timezone.utc)
    task = Task(
        user_id=user.id,
        title="整理错题",
        status="pending",
        due_date=fixed_now + timedelta(minutes=20),
    )
    session.add(task)
    await session.flush()

    sent_payloads: list[tuple[int, dict]] = []

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_now.replace(tzinfo=None)
            return fixed_now.astimezone(tz)

    async def fake_send_to_user(user_id: int, data: dict) -> None:
        sent_payloads.append((user_id, data))

    reminder_service._sent_reminders.clear()
    monkeypatch.setattr(reminder_service, "async_session_factory", SessionFactoryStub(session))
    monkeypatch.setattr(reminder_service, "datetime", FrozenDateTime)
    monkeypatch.setattr(reminder_service.manager, "send_to_user", fake_send_to_user)

    await reminder_service.check_and_send_reminders()
    await reminder_service.check_and_send_reminders()

    assert len(sent_payloads) == 1
    assert sent_payloads[0][0] == user.id
    assert sent_payloads[0][1]["type"] == "approaching_deadline"
    assert sent_payloads[0][1]["task_title"] == "整理错题"


@pytest.mark.asyncio
async def test_check_and_send_reminders_skips_notifications_during_quiet_hours(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    user = await create_user(session, "quiet_user", "quiet@example.com")
    session.add(
        ReminderSetting(
            user_id=user.id,
            before_due_minutes=60,
            overdue_enabled=True,
            quiet_start_hour=22,
            quiet_end_hour=8,
        )
    )

    fixed_now = datetime(2026, 4, 24, 23, 0, tzinfo=timezone.utc)
    session.add(
        Task(
            user_id=user.id,
            title="夜间任务",
            status="pending",
            due_date=fixed_now + timedelta(minutes=10),
        )
    )
    await session.flush()

    sent_payloads: list[tuple[int, dict]] = []

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_now.replace(tzinfo=None)
            return fixed_now.astimezone(tz)

    async def fake_send_to_user(user_id: int, data: dict) -> None:
        sent_payloads.append((user_id, data))

    reminder_service._sent_reminders.clear()
    monkeypatch.setattr(reminder_service, "async_session_factory", SessionFactoryStub(session))
    monkeypatch.setattr(reminder_service, "datetime", FrozenDateTime)
    monkeypatch.setattr(reminder_service.manager, "send_to_user", fake_send_to_user)

    await reminder_service.check_and_send_reminders()

    assert sent_payloads == []


@pytest.mark.asyncio
async def test_check_and_send_reminders_emits_phase_checkpoint(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    user = await create_user(session, "phase_reminder_user", "phase-reminder@example.com")
    session.add(
        ReminderSetting(
            user_id=user.id,
            before_start_minutes=180,
            before_due_minutes=60,
            overdue_enabled=True,
            quiet_start_hour=22,
            quiet_end_hour=8,
        )
    )
    plan = StudyPlan(
        user_id=user.id,
        title="高数冲刺",
        start_date=datetime(2026, 4, 24, tzinfo=timezone.utc).date(),
        end_date=datetime(2026, 4, 30, tzinfo=timezone.utc).date(),
        status="active",
    )
    session.add(plan)
    await session.flush()
    phase = PlanPhase(
        plan_id=plan.id,
        title="第二阶段",
        sequence=1,
        start_date=datetime(2026, 4, 24, tzinfo=timezone.utc).date(),
        end_date=datetime(2026, 4, 24, tzinfo=timezone.utc).date(),
    )
    session.add(phase)
    await session.flush()
    session.add(
        Task(
            user_id=user.id,
            plan_id=plan.id,
            phase_id=phase.id,
            title="完成 20 道例题",
            status="in_progress",
        )
    )
    await session.flush()

    fixed_now = datetime(2026, 4, 24, 21, 30, tzinfo=timezone.utc)
    sent_payloads: list[tuple[int, dict]] = []

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_now.replace(tzinfo=None)
            return fixed_now.astimezone(tz)

    async def fake_send_to_user(user_id: int, data: dict) -> None:
        sent_payloads.append((user_id, data))

    reminder_service._sent_reminders.clear()
    monkeypatch.setattr(reminder_service, "async_session_factory", SessionFactoryStub(session))
    monkeypatch.setattr(reminder_service, "datetime", FrozenDateTime)
    monkeypatch.setattr(reminder_service.manager, "send_to_user", fake_send_to_user)

    await reminder_service.check_and_send_reminders()

    assert sent_payloads
    assert sent_payloads[0][1]["type"] == "phase_checkpoint"
    assert sent_payloads[0][1]["remaining_task_count"] == 1
