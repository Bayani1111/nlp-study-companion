from datetime import date, timedelta

import pytest
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatMessage, ChatSession, StudyPlan, Task, User
from app.schemas.plans import PlanQuickCreate, PlanStatusUpdate, PlanUpdate
from app.schemas.reminders import ReminderSettingUpdate
from app.services import (
    chat_session_service,
    plan_service,
    reminder_settings_service,
    stats_service,
    task_service,
)


async def create_user(
    session: AsyncSession,
    username: str,
    email: str,
) -> User:
    user = User(username=username, email=email, password_hash="hashed")
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_get_owned_plan_returns_only_owner_plan(session: AsyncSession):
    owner = await create_user(session, "owner", "owner@example.com")
    intruder = await create_user(session, "intruder", "intruder@example.com")

    plan = StudyPlan(
        user_id=owner.id,
        title="考研复习",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
    )
    session.add(plan)
    await session.flush()

    fetched = await plan_service.get_owned_plan(plan.id, owner.id, session)
    assert fetched.id == plan.id

    with pytest.raises(HTTPException) as exc_info:
        await plan_service.get_owned_plan(plan.id, intruder.id, session)
    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_update_plan_rejects_start_date_after_existing_end_date(session: AsyncSession):
    owner = await create_user(session, "planner", "planner@example.com")
    plan = StudyPlan(
        user_id=owner.id,
        title="英语专项",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 10),
    )
    session.add(plan)
    await session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await plan_service.update_plan(
            plan,
            PlanUpdate(start_date=date(2026, 4, 11)),
            session,
        )
    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_update_plan_status_persists_new_status(session: AsyncSession):
    owner = await create_user(session, "status_user", "status@example.com")
    plan = StudyPlan(
        user_id=owner.id,
        title="刷题计划",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 20),
    )
    session.add(plan)
    await session.flush()

    updated = await plan_service.update_plan_status(
        plan,
        PlanStatusUpdate(status="completed"),
        session,
    )

    assert updated.status == "completed"


@pytest.mark.asyncio
async def test_serialize_plan_list_includes_progress_and_task_counts(session: AsyncSession):
    owner = await create_user(session, "plan_stats_user", "plan-stats@example.com")
    plan = StudyPlan(
        user_id=owner.id,
        title="英语冲刺计划",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 7),
    )
    session.add(plan)
    await session.flush()

    session.add_all(
        [
            Task(user_id=owner.id, plan_id=plan.id, title="任务1", status="completed"),
            Task(user_id=owner.id, plan_id=plan.id, title="任务2", status="pending"),
        ]
    )
    await session.flush()

    serialized = await plan_service.serialize_plan_list([plan], session)

    assert serialized[0]["task_count"] == 2
    assert serialized[0]["completed_task_count"] == 1
    assert serialized[0]["progress_percent"] == 50.0


@pytest.mark.asyncio
async def test_create_plan_from_template_generates_phases_and_tasks(session: AsyncSession):
    owner = await create_user(session, "template_user", "template@example.com")

    plan = await plan_service.create_plan_from_template(
        owner.id,
        PlanQuickCreate(template_key="exam_sprint", start_date=date(2026, 5, 5)),
        session,
    )

    serialized = await plan_service.serialize_plan(plan, session)

    assert plan.template_key == "exam_sprint"
    assert len(plan.phases) == 3
    assert serialized["task_count"] >= 3
    assert len(serialized["day_schedule"]) >= 1
    assert serialized["phases"][0]["title"] == "知识梳理"


@pytest.mark.asyncio
async def test_serialize_plan_includes_phase_and_schedule_views(session: AsyncSession):
    owner = await create_user(session, "phase_user", "phase@example.com")
    plan = StudyPlan(
        user_id=owner.id,
        title="周复习",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 7),
    )
    session.add(plan)
    await session.flush()

    await plan_service.update_plan(
        plan,
        PlanUpdate(
            phases=[
                {
                    "title": "输入",
                    "description": "看笔记",
                    "sequence": 0,
                    "start_date": date(2026, 5, 1),
                    "end_date": date(2026, 5, 2),
                },
                {
                    "title": "练习",
                    "description": "刷题",
                    "sequence": 1,
                    "start_date": date(2026, 5, 3),
                    "end_date": date(2026, 5, 5),
                },
            ]
        ),
        session,
    )

    phase_ids = [phase.id for phase in plan.phases]
    session.add_all(
        [
            Task(
                user_id=owner.id,
                plan_id=plan.id,
                phase_id=phase_ids[0],
                title="看第一章",
                status="completed",
                scheduled_date=date(2026, 5, 1),
                sort_order=0,
            ),
            Task(
                user_id=owner.id,
                plan_id=plan.id,
                phase_id=phase_ids[1],
                title="刷 20 题",
                status="pending",
                scheduled_date=date(2026, 5, 3),
                sort_order=1,
            ),
        ]
    )
    await session.flush()

    serialized = await plan_service.serialize_plan(plan, session)

    assert len(serialized["phases"]) == 2
    assert serialized["phases"][0]["completed_task_count"] == 1
    assert serialized["day_schedule"][0]["task_titles"] == ["看第一章"]
    assert serialized["week_schedule"][0]["task_count"] == 2


@pytest.mark.asyncio
async def test_get_or_create_session_creates_new_session_from_message(session: AsyncSession):
    user = await create_user(session, "chat_user", "chat_user@example.com")
    long_message = "今天帮我整理一下这周的高数和英语复习安排，并且把练习题也一起列出来"

    created = await chat_session_service.get_or_create_session(
        user.id,
        None,
        long_message,
        session,
    )

    assert created.user_id == user.id
    assert created.title == long_message[:50]


@pytest.mark.asyncio
async def test_get_or_create_session_rejects_other_users_session(session: AsyncSession):
    owner = await create_user(session, "owner2", "owner2@example.com")
    stranger = await create_user(session, "stranger", "stranger@example.com")
    existing = ChatSession(user_id=owner.id, title="我的会话")
    session.add(existing)
    await session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await chat_session_service.get_or_create_session(
            stranger.id,
            existing.id,
            "无关消息",
            session,
        )
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_load_history_returns_messages_in_chronological_order(session: AsyncSession):
    user = await create_user(session, "history_user", "history@example.com")
    chat_session = ChatSession(user_id=user.id, title="历史会话")
    session.add(chat_session)
    await session.flush()

    session.add_all(
        [
            ChatMessage(session_id=chat_session.id, role="user", content="第一句"),
            ChatMessage(session_id=chat_session.id, role="assistant", content="第二句"),
            ChatMessage(session_id=chat_session.id, role="user", content="第三句"),
        ]
    )
    await session.flush()

    history = await chat_session_service.load_history(chat_session.id, session)

    assert [item["content"] for item in history] == ["第一句", "第二句", "第三句"]


@pytest.mark.asyncio
async def test_save_message_persists_intent_and_entities(session: AsyncSession):
    user = await create_user(session, "save_user", "save@example.com")
    chat_session = ChatSession(user_id=user.id, title="保存消息")
    session.add(chat_session)
    await session.flush()

    message = await chat_session_service.save_message(
        chat_session.id,
        "assistant",
        "已经帮你创建任务",
        session,
        intent="create_task",
        entities_json='{"title":"整理错题"}',
    )

    assert message.intent == "create_task"
    assert message.entities_json == '{"title":"整理错题"}'


@pytest.mark.asyncio
async def test_get_or_create_settings_creates_defaults_once(session: AsyncSession):
    user = await create_user(session, "reminder_user", "reminder@example.com")

    first = await reminder_settings_service.get_or_create_settings(user.id, session)
    second = await reminder_settings_service.get_or_create_settings(user.id, session)

    assert first.id == second.id
    assert first.before_due_minutes == 60
    assert first.quiet_start_hour == 22


@pytest.mark.asyncio
async def test_update_settings_applies_partial_changes(session: AsyncSession):
    user = await create_user(session, "partial_user", "partial@example.com")
    setting = await reminder_settings_service.get_or_create_settings(user.id, session)

    updated = await reminder_settings_service.update_settings(
        setting,
        ReminderSettingUpdate(before_due_minutes=15, overdue_enabled=False),
        session,
    )

    assert updated.before_due_minutes == 15
    assert updated.overdue_enabled is False
    assert updated.quiet_start_hour == 22


@pytest.mark.asyncio
async def test_get_task_stats_aggregates_statuses_and_priorities(session: AsyncSession):
    user = await create_user(session, "stats_user", "stats@example.com")
    session.add_all(
        [
            Task(user_id=user.id, title="任务1", status="pending", priority="high"),
            Task(user_id=user.id, title="任务2", status="completed", priority="medium"),
            Task(user_id=user.id, title="任务3", status="in_progress", priority="medium"),
            Task(user_id=user.id, title="任务4", status="overdue", priority="low"),
        ]
    )
    await session.flush()

    stats = await stats_service.get_task_stats(user.id, session)

    assert stats["total_tasks"] == 4
    assert stats["completed_tasks"] == 1
    assert stats["pending_tasks"] == 1
    assert stats["in_progress_tasks"] == 1
    assert stats["overdue_tasks"] == 1
    assert stats["priority_distribution"] == {"high": 1, "medium": 2, "low": 1}
    assert stats["completion_rate"] == 0.25


@pytest.mark.asyncio
async def test_record_study_session_updates_daily_stats_and_overview(session: AsyncSession):
    user = await create_user(session, "study_user", "study@example.com")

    first_record = await stats_service.record_study_session(
        user.id,
        session,
        duration_minutes=25,
        source="focus_timer",
    )
    second_record = await stats_service.record_study_session(
        user.id,
        session,
        duration_minutes=15,
        source="focus_timer",
    )

    record_day = (second_record.recorded_at or first_record.recorded_at).date()
    daily = await stats_service.get_daily_stats(user.id, record_day, session)
    overview = await stats_service.aggregate_learning_stats(
        user.id,
        record_day - timedelta(days=1),
        record_day,
        session,
    )

    assert daily["study_minutes"] == 40
    assert daily["session_count"] == 2
    assert overview["total_study_minutes"] == 40
    assert overview["total_sessions"] == 2
    assert overview["streak_days"] >= 1


@pytest.mark.asyncio
async def test_task_stats_include_phase_completion_rate(session: AsyncSession):
    owner = await create_user(session, "phase_rate_user", "phase-rate@example.com")
    await plan_service.create_plan_from_template(
        owner.id,
        PlanQuickCreate(template_key="exam_sprint", start_date=date(2026, 5, 1)),
        session,
    )

    tasks = await task_service.list_tasks(owner.id, session)
    await task_service.update_task(owner.id, tasks[0].id, {"status": "completed"}, session)

    stats = await stats_service.get_task_stats(owner.id, session)

    assert stats["phase_completion_rate"] > 0


@pytest.mark.asyncio
async def test_aggregate_learning_stats_includes_chat_diagnostics(session: AsyncSession):
    user = await create_user(session, "diag_user", "diag@example.com")
    chat_session = ChatSession(user_id=user.id, title="诊断会话")
    session.add(chat_session)
    await session.flush()

    session.add_all(
        [
            ChatMessage(
                session_id=chat_session.id,
                role="assistant",
                content="澄清一下",
                entities_json='{"orchestration_diagnostics":{"event":"force_clarify_initial"}}',
            ),
            ChatMessage(
                session_id=chat_session.id,
                role="assistant",
                content="已根据偏好跳步",
                entities_json='{"orchestration_diagnostics":{"event":"force_clarify_seeded"}}',
            ),
            ChatMessage(
                session_id=chat_session.id,
                role="assistant",
                content="动作完成",
                entities_json='{"orchestration_diagnostics":{"event":"action_completed"}}',
            ),
        ]
    )
    await session.flush()

    today = date.today()
    stats = await stats_service.aggregate_learning_stats(
        user.id,
        today - timedelta(days=1),
        today,
        session,
    )

    assert stats["chat_diagnostic_total"] == 3
    assert stats["clarify_reason_distribution"]["force_clarify_initial"] == 1
    assert stats["clarify_reason_distribution"]["force_clarify_seeded"] == 1
    assert stats["orchestration_event_distribution"]["action_completed"] == 1
    assert stats["clarify_path_switch_hit_rate"] == 0.5
    assert stats["action_completion_rate"] == round(1 / 3, 4)


@pytest.mark.asyncio
async def test_complete_all_subtasks_marks_parent_completed(session: AsyncSession):
    user = await create_user(session, "task_tree_user", "task-tree@example.com")
    parent = await task_service.create_task(user.id, {"title": "复习高数"}, session)
    child_one = await task_service.create_task(
        user.id,
        {"title": "刷第一章例题", "parent_task_id": parent.id},
        session,
    )
    child_two = await task_service.create_task(
        user.id,
        {"title": "整理错题", "parent_task_id": parent.id},
        session,
    )

    await task_service.update_task(user.id, child_one.id, {"status": "completed"}, session)
    refreshed_parent = await task_service.get_task(user.id, parent.id, session)
    assert refreshed_parent.status == "in_progress"

    await task_service.update_task(user.id, child_two.id, {"status": "completed"}, session)
    refreshed_parent = await task_service.get_task(user.id, parent.id, session)
    assert refreshed_parent.status == "completed"


@pytest.mark.asyncio
async def test_reopening_subtask_reopens_parent(session: AsyncSession):
    user = await create_user(session, "reopen_user", "reopen@example.com")
    parent = await task_service.create_task(user.id, {"title": "英语冲刺"}, session)
    child = await task_service.create_task(
        user.id,
        {"title": "背诵单词", "parent_task_id": parent.id},
        session,
    )

    await task_service.update_task(user.id, child.id, {"status": "completed"}, session)
    await task_service.update_task(user.id, child.id, {"status": "pending"}, session)

    refreshed_parent = await task_service.get_task(user.id, parent.id, session)
    assert refreshed_parent.status == "pending"


@pytest.mark.asyncio
async def test_parent_task_cannot_complete_before_all_subtasks_done(session: AsyncSession):
    user = await create_user(session, "parent_guard", "parent-guard@example.com")
    parent = await task_service.create_task(user.id, {"title": "周末复盘"}, session)
    await task_service.create_task(
        user.id,
        {"title": "写总结", "parent_task_id": parent.id},
        session,
    )

    with pytest.raises(HTTPException) as exc_info:
        await task_service.update_task(user.id, parent.id, {"status": "completed"}, session)

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
