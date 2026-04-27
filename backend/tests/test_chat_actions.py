from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch

import pytest

from app.services.chat_actions import ChatActionResult, execute_chat_action


@pytest.mark.asyncio
async def test_execute_chat_action_creates_task_and_records_activity():
    fake_task = SimpleNamespace(id=101, title="Read NLP paper", plan_id=None, parent_task_id=None)

    with (
        patch(
            "app.services.chat_actions.task_service.create_task",
            new=AsyncMock(return_value=fake_task),
        ) as create_task,
        patch(
            "app.services.chat_actions.task_service.get_task",
            new=AsyncMock(return_value=fake_task),
        ) as get_task,
        patch(
            "app.services.chat_actions.record_learning_activity", new=AsyncMock()
        ) as record_activity,
    ):
        result = await execute_chat_action(
            user_id=1,
            intent="create_task",
            entities={"task_title": "Read NLP paper", "priority": "high"},
            fallback_message="read nlp paper tomorrow",
            db=AsyncMock(),
            due_date="fake-due-date",
        )

    assert isinstance(result, ChatActionResult)
    assert result.payload is fake_task
    assert result.extracted_tasks == [
        {"id": 101, "title": "Read NLP paper", "plan_id": None, "parent_task_id": None}
    ]
    create_task.assert_awaited_once()
    get_task.assert_awaited_once_with(1, 101, ANY)
    record_activity.assert_awaited_once_with(1, "task_create", ANY, task_id=101)


@pytest.mark.asyncio
async def test_execute_chat_action_creates_plan_and_bound_task():
    fake_plan = SimpleNamespace(
        id=3, title="英语计划", start_date=date(2026, 4, 24), end_date=date(2026, 4, 25)
    )
    fake_task = SimpleNamespace(id=7, title="背单词", plan_id=3, parent_task_id=None, children=[])

    with (
        patch(
            "app.services.chat_actions.plan_service.create_plan",
            new=AsyncMock(return_value=fake_plan),
        ) as create_plan,
        patch(
            "app.services.chat_actions.task_service.create_task",
            new=AsyncMock(return_value=fake_task),
        ) as create_task,
        patch(
            "app.services.chat_actions.task_service.get_task",
            new=AsyncMock(return_value=fake_task),
        ) as get_task,
        patch(
            "app.services.chat_actions.record_learning_activity", new=AsyncMock()
        ) as record_activity,
    ):
        result = await execute_chat_action(
            user_id=1,
            intent="create_plan",
            entities={
                "plan_title": "英语计划",
                "task_title": "背单词",
                "description": "明天中午前背完 100 个单词",
                "should_create_task": True,
            },
            fallback_message="帮我做个英语计划并记录任务",
            db=AsyncMock(),
            due_date=datetime(2026, 4, 25, 12, 0, 0),
        )

    assert result.extracted_plans == [{"id": 3, "title": "英语计划"}]
    assert result.extracted_tasks == [
        {"id": 7, "title": "背单词", "plan_id": 3, "parent_task_id": None}
    ]
    create_plan.assert_awaited_once()
    create_task.assert_awaited_once()
    get_task.assert_awaited_once_with(1, 7, ANY)
    record_activity.assert_awaited_once_with(1, "task_create", ANY, task_id=7)


@pytest.mark.asyncio
async def test_execute_chat_action_creates_plan_when_description_exceeds_schema_max():
    """Lengthy plan drafts (LLM) must be clipped so PlanCreate validation does not fail."""
    long_desc = "段" * 5000
    fake_plan = SimpleNamespace(
        id=9, title="长文计划", start_date=date(2026, 4, 1), end_date=date(2026, 4, 2)
    )
    fake_task = SimpleNamespace(
        id=12, title="长文计划", plan_id=9, parent_task_id=None, children=[]
    )

    with (
        patch(
            "app.services.chat_actions.plan_service.create_plan",
            new=AsyncMock(return_value=fake_plan),
        ) as create_plan,
        patch(
            "app.services.chat_actions.task_service.create_task",
            new=AsyncMock(return_value=fake_task),
        ),
        patch(
            "app.services.chat_actions.task_service.get_task",
            new=AsyncMock(return_value=fake_task),
        ),
        patch("app.services.chat_actions.record_learning_activity", new=AsyncMock()),
    ):
        result = await execute_chat_action(
            user_id=1,
            intent="create_plan",
            entities={
                "plan_title": "长文计划",
                "task_title": "长文计划",
                "plan_description": long_desc,
                "description": long_desc,
                "should_create_task": True,
            },
            fallback_message="加入计划",
            db=AsyncMock(),
            due_date=None,
        )

    assert result.payload is not None
    assert result.extracted_plans
    data = create_plan.call_args[0][1]
    assert data.description is not None
    assert len(data.description) == 2000
    assert data.title == "长文计划"


@pytest.mark.asyncio
async def test_execute_chat_action_creates_subtasks_under_parent_task():
    fake_parent = SimpleNamespace(
        id=10,
        title="高数复习",
        plan_id=4,
        parent_task_id=None,
        priority="medium",
        children=[SimpleNamespace(id=11), SimpleNamespace(id=12)],
    )
    fake_child_one = SimpleNamespace(id=11, title="看第一章笔记", plan_id=4, parent_task_id=10)
    fake_child_two = SimpleNamespace(id=12, title="刷例题", plan_id=4, parent_task_id=10)

    with (
        patch(
            "app.services.chat_actions.task_service.create_task",
            new=AsyncMock(side_effect=[fake_parent, fake_child_one, fake_child_two]),
        ) as create_task,
        patch(
            "app.services.chat_actions.task_service.get_task",
            new=AsyncMock(return_value=fake_parent),
        ) as get_task,
        patch(
            "app.services.chat_actions.record_learning_activity", new=AsyncMock()
        ) as record_activity,
    ):
        result = await execute_chat_action(
            user_id=3,
            intent="create_task",
            entities={
                "task_title": "高数复习",
                "subtasks": ["看第一章笔记", "刷例题"],
            },
            fallback_message="帮我安排高数复习",
            db=AsyncMock(),
            due_date=None,
        )

    assert result.payload is fake_parent
    assert result.extracted_tasks == [
        {"id": 10, "title": "高数复习", "plan_id": 4, "parent_task_id": None},
        {"id": 11, "title": "看第一章笔记", "plan_id": 4, "parent_task_id": 10},
        {"id": 12, "title": "刷例题", "plan_id": 4, "parent_task_id": 10},
    ]
    assert create_task.await_count == 3
    get_task.assert_awaited_once_with(3, 10, ANY)
    record_activity.assert_awaited_once_with(3, "task_create", ANY, task_id=10)


@pytest.mark.asyncio
async def test_execute_chat_action_returns_empty_when_update_task_id_missing():
    result = await execute_chat_action(
        user_id=1,
        intent="update_task",
        entities={},
        fallback_message="update something",
        db=AsyncMock(),
    )

    assert result.payload is None
    assert result.extracted_tasks is None


@pytest.mark.asyncio
async def test_execute_chat_action_completes_task_and_records_activity():
    fake_task = SimpleNamespace(id=9, title="Finish quiz")

    with (
        patch(
            "app.services.chat_actions.task_service.complete_task",
            new=AsyncMock(return_value=fake_task),
        ) as complete_task,
        patch(
            "app.services.chat_actions.record_learning_activity", new=AsyncMock()
        ) as record_activity,
    ):
        result = await execute_chat_action(
            user_id=2,
            intent="complete_task",
            entities={"task_id": 9},
            fallback_message="done",
            db=AsyncMock(),
        )

    assert result.payload is fake_task
    assert result.extracted_tasks is None
    complete_task.assert_awaited_once_with(2, 9, ANY)
    record_activity.assert_awaited_once_with(2, "task_complete", ANY, task_id=9)


@pytest.mark.asyncio
async def test_execute_chat_action_swallows_create_errors_for_chat_flow():
    with (
        patch(
            "app.services.chat_actions.task_service.create_task",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch(
            "app.services.chat_actions.record_learning_activity", new=AsyncMock()
        ) as record_activity,
    ):
        result = await execute_chat_action(
            user_id=1,
            intent="create_task",
            entities={},
            fallback_message="fallback",
            db=AsyncMock(),
        )

    assert result.payload is None
    assert result.extracted_tasks is None
    record_activity.assert_not_awaited()
