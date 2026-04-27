import json
import sys
import types
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch

import pytest

if "dateparser" not in sys.modules:
    fake_dateparser = types.ModuleType("dateparser")
    fake_dateparser.parse = lambda *args, **kwargs: None
    sys.modules["dateparser"] = fake_dateparser

if "dateparser.search" not in sys.modules:
    fake_search = types.ModuleType("dateparser.search")
    fake_search.search_dates = lambda *args, **kwargs: None
    sys.modules["dateparser.search"] = fake_search

from app.services.chat_service import _pick_soft_preference, process_chat_message


@pytest.mark.asyncio
async def test_process_chat_message_falls_back_when_nlp_fails_but_llm_succeeds():
    session = SimpleNamespace(id=11)

    with (
        patch(
            "app.services.chat_service.get_or_create_session", new=AsyncMock(return_value=session)
        ),
        patch(
            "app.services.chat_service.load_history",
            new=AsyncMock(return_value=[{"role": "assistant", "content": "old reply"}]),
        ),
        patch("app.services.chat_service.load_structured_history", new=AsyncMock(return_value=[])),
        patch(
            "app.services.chat_service._hydrate_recent_action_context",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.services.chat_service.call_llm_for_intent",
            new=AsyncMock(side_effect=RuntimeError("nlp failed")),
        ),
        patch("app.services.chat_service.resolve_intent", return_value=("chat", {})),
        patch(
            "app.services.chat_service.execute_intent",
            new=AsyncMock(return_value=(None, None, None)),
        ),
        patch("app.services.chat_service.build_companion_prompt", return_value="system prompt"),
        patch("app.services.chat_service.call_llm_api", new=AsyncMock(return_value="LLM reply")),
        patch("app.services.chat_service.save_message", new=AsyncMock()) as save_message,
        patch(
            "app.services.chat_service.record_learning_activity", new=AsyncMock()
        ) as record_activity,
    ):
        result = await process_chat_message(
            user_id=7,
            session_id=None,
            message="hello there",
            db=AsyncMock(),
        )

    assert result == {
        "reply": "LLM reply",
        "intent": "chat",
        "session_id": 11,
        "extracted_tasks": None,
        "extracted_plans": None,
        "sync_summary": None,
        "next_prompt": None,
        "next_prompt_options": None,
        "proposal_id": None,
        "scenario_type": "general_learning",
        "scenario_label": "通用学习",
    }
    assert save_message.await_count == 2
    save_message.assert_any_await(
        11, "assistant", "LLM reply", ANY, intent="chat", entities_json=ANY
    )
    record_activity.assert_awaited_once_with(7, "chat", ANY)
    assistant_entities = json.loads(save_message.await_args_list[1].kwargs["entities_json"])
    assert assistant_entities["orchestration_diagnostics"]["event"] == "action_completed"


@pytest.mark.asyncio
async def test_process_chat_message_injects_preference_memory_into_system_prompt():
    session = SimpleNamespace(id=12)
    llm_mock = AsyncMock(return_value="LLM reply")

    with (
        patch(
            "app.services.chat_service.get_or_create_session", new=AsyncMock(return_value=session)
        ),
        patch("app.services.chat_service.load_history", new=AsyncMock(return_value=[])),
        patch("app.services.chat_service.load_structured_history", new=AsyncMock(return_value=[])),
        patch(
            "app.services.chat_service._load_user_preference_memory",
            new=AsyncMock(return_value={"time_budget": "每天一小时"}),
        ),
        patch(
            "app.services.chat_service._hydrate_recent_action_context",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.services.chat_service.call_llm_for_intent",
            new=AsyncMock(return_value={"intent": "chat", "entities": {}}),
        ),
        patch("app.services.chat_service.resolve_intent", return_value=("chat", {})),
        patch(
            "app.services.chat_service.execute_intent",
            new=AsyncMock(return_value=(None, None, None)),
        ),
        patch("app.services.chat_service.build_companion_prompt", return_value="system prompt"),
        patch("app.services.chat_service.call_llm_api", new=llm_mock),
        patch("app.services.chat_service.save_message", new=AsyncMock()),
        patch("app.services.chat_service.record_learning_activity", new=AsyncMock()),
    ):
        await process_chat_message(
            user_id=7,
            session_id=None,
            message="我今天想学一会儿",
            db=AsyncMock(),
        )

    llm_messages = llm_mock.await_args.args[0]
    assert "用户长期偏好" in llm_messages[0]["content"]
    assert "每天一小时" in llm_messages[0]["content"]


@pytest.mark.asyncio
async def test_process_chat_message_extracts_and_persists_tone_style_preference():
    session = SimpleNamespace(id=13)
    llm_mock = AsyncMock(return_value="收到，我会更直接推进。")

    with (
        patch(
            "app.services.chat_service.get_or_create_session", new=AsyncMock(return_value=session)
        ),
        patch("app.services.chat_service.load_history", new=AsyncMock(return_value=[])),
        patch("app.services.chat_service.load_structured_history", new=AsyncMock(return_value=[])),
        patch(
            "app.services.chat_service._load_user_preference_memory", new=AsyncMock(return_value={})
        ),
        patch(
            "app.services.chat_service._hydrate_recent_action_context",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.services.chat_service.call_llm_for_intent",
            new=AsyncMock(return_value={"intent": "chat", "entities": {}}),
        ),
        patch("app.services.chat_service.resolve_intent", return_value=("chat", {})),
        patch(
            "app.services.chat_service.execute_intent",
            new=AsyncMock(return_value=(None, None, None)),
        ),
        patch("app.services.chat_service.build_companion_prompt", return_value="system prompt"),
        patch("app.services.chat_service.call_llm_api", new=llm_mock),
        patch("app.services.chat_service.save_message", new=AsyncMock()) as save_message,
        patch("app.services.chat_service.record_learning_activity", new=AsyncMock()),
    ):
        await process_chat_message(
            user_id=12,
            session_id=None,
            message="之后你跟我说话直接点，少点鼓励",
            db=AsyncMock(),
        )

    llm_messages = llm_mock.await_args.args[0]
    assert "偏好对话语气：直接、务实、少寒暄" in llm_messages[0]["content"]

    user_entities_json = save_message.await_args_list[0].kwargs["entities_json"]
    payload = json.loads(user_entities_json)
    assert payload["user_preferences"]["tone_style"] == "direct"


@pytest.mark.asyncio
async def test_process_chat_message_continues_when_task_action_returns_empty_result():
    session = SimpleNamespace(id=22)

    with (
        patch(
            "app.services.chat_service.get_or_create_session", new=AsyncMock(return_value=session)
        ),
        patch("app.services.chat_service.load_history", new=AsyncMock(return_value=[])),
        patch("app.services.chat_service.load_structured_history", new=AsyncMock(return_value=[])),
        patch(
            "app.services.chat_service._hydrate_recent_action_context",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.services.chat_service.call_llm_for_intent",
            new=AsyncMock(
                return_value={"intent": "create_task", "entities": {"task_title": "Write notes"}}
            ),
        ),
        patch(
            "app.services.chat_service.resolve_intent",
            return_value=("create_task", {"task_title": "Write notes"}),
        ),
        patch(
            "app.services.chat_service.execute_intent",
            new=AsyncMock(return_value=(None, None, None)),
        ),
        patch("app.services.chat_service.build_companion_prompt", return_value="task prompt"),
        patch(
            "app.services.chat_service.call_llm_api",
            new=AsyncMock(return_value="I can still help you plan this."),
        ),
        patch("app.services.chat_service.save_message", new=AsyncMock()),
        patch("app.services.chat_service.record_learning_activity", new=AsyncMock()),
    ):
        result = await process_chat_message(
            user_id=3,
            session_id=22,
            message="create a task for me",
            db=AsyncMock(),
        )

    assert result["intent"] == "action_failed"
    assert "没能成功写入计划/任务模块" in result["reply"]
    assert result["extracted_tasks"] is None


@pytest.mark.asyncio
async def test_process_chat_message_prefixes_reply_when_task_created_successfully():
    session = SimpleNamespace(id=33)
    created_task = SimpleNamespace(id=5, title="Read chapter 3", children=[])

    with (
        patch(
            "app.services.chat_service.get_or_create_session", new=AsyncMock(return_value=session)
        ),
        patch("app.services.chat_service.load_history", new=AsyncMock(return_value=[])),
        patch("app.services.chat_service.load_structured_history", new=AsyncMock(return_value=[])),
        patch(
            "app.services.chat_service._hydrate_recent_action_context",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.services.chat_service.call_llm_for_intent",
            new=AsyncMock(
                return_value={"intent": "create_task", "entities": {"task_title": "Read chapter 3"}}
            ),
        ),
        patch(
            "app.services.chat_service.resolve_intent",
            return_value=("create_task", {"task_title": "Read chapter 3"}),
        ),
        patch(
            "app.services.chat_service.execute_intent",
            new=AsyncMock(
                return_value=(
                    created_task,
                    [{"id": 5, "title": "Read chapter 3", "parent_task_id": None}],
                    None,
                )
            ),
        ),
        patch(
            "app.services.chat_service.call_llm_api",
            new=AsyncMock(return_value="Finish it tonight."),
        ),
        patch("app.services.chat_service.save_message", new=AsyncMock()),
        patch("app.services.chat_service.record_learning_activity", new=AsyncMock()),
    ):
        result = await process_chat_message(
            user_id=9,
            session_id=None,
            message="read chapter three",
            db=AsyncMock(),
        )

    assert (
        result["reply"] == "已帮你创建任务：Read chapter 3\n\n主任务「Read chapter 3」已记入系统。"
    )
    assert result["next_prompt"] is not None
    assert result["next_prompt_options"] == ["今晚10点前完成并提醒我", "明晚20:00提醒我开始"]


@pytest.mark.asyncio
async def test_process_chat_message_does_not_generate_day_subtasks_during_initial_plan_creation():
    session = SimpleNamespace(id=55)
    created_plan = SimpleNamespace(
        id=6, title="高数复习计划", start_date=date(2026, 4, 28), phases=[]
    )
    created_task = SimpleNamespace(
        id=9,
        title="下周高数复习计划",
        plan_id=6,
        priority="medium",
        children=[],
        due_date=None,
    )
    refreshed_task_before = {
        "children": [],
    }
    refreshed_task_after = SimpleNamespace(
        id=9,
        title="下周高数复习计划",
        plan_id=6,
        priority="medium",
        children=[SimpleNamespace(id=10), SimpleNamespace(id=11)],
        due_date=None,
    )

    with (
        patch(
            "app.services.chat_service.get_or_create_session", new=AsyncMock(return_value=session)
        ),
        patch("app.services.chat_service.load_history", new=AsyncMock(return_value=[])),
        patch("app.services.chat_service.load_structured_history", new=AsyncMock(return_value=[])),
        patch(
            "app.services.chat_service._hydrate_recent_action_context",
            new=AsyncMock(return_value={}),
        ),
        patch("app.services.chat_service.call_llm_for_intent", new=AsyncMock(return_value=None)),
        patch(
            "app.services.chat_service.resolve_intent",
            return_value=("create_plan", {"plan_title": "高数复习计划"}),
        ),
        patch(
            "app.services.chat_service.execute_intent",
            new=AsyncMock(
                return_value=(
                    {"plan": created_plan, "task": created_task},
                    [{"id": 9, "title": "下周高数复习计划", "plan_id": 6, "parent_task_id": None}],
                    [{"id": 6, "title": "高数复习计划"}],
                )
            ),
        ),
        patch(
            "app.services.chat_service.call_llm_api",
            new=AsyncMock(
                return_value=(
                    "### 第1天：梳理知识点\n"
                    "- 目标：明确考试范围，整理知识结构\n"
                    "- 9:00 - 10:00 复习课本/笔记\n\n"
                    "### 第2天：开始刷题\n"
                    "- 15:30 - 16:30 刷 20 道例题"
                )
            ),
        ),
        patch(
            "app.services.chat_service.task_service.get_task",
            new=AsyncMock(
                side_effect=[SimpleNamespace(**refreshed_task_before), refreshed_task_after]
            ),
        ),
        patch(
            "app.services.chat_service.task_service.serialize_task",
            side_effect=[refreshed_task_before],
        ),
        patch(
            "app.services.chat_service.task_service.create_task",
            new=AsyncMock(
                side_effect=[
                    SimpleNamespace(
                        id=10, title="第1天·任务1 · 复习课本/笔记", plan_id=6, parent_task_id=9
                    ),
                    SimpleNamespace(
                        id=11, title="第2天·任务1 · 刷 20 道例题", plan_id=6, parent_task_id=9
                    ),
                ]
            ),
        ) as create_subtask,
        patch("app.services.chat_service.save_message", new=AsyncMock()),
        patch("app.services.chat_service.record_learning_activity", new=AsyncMock()),
    ):
        result = await process_chat_message(
            user_id=15,
            session_id=None,
            message="帮我做一个下周高数复习计划，并记录今天先做的第一项任务",
            db=AsyncMock(),
        )

    assert create_subtask.await_count == 0
    assert result["intent"] == "plan_proposal"
    assert result["extracted_tasks"] is None
    assert result["proposal_id"] is not None


@pytest.mark.asyncio
async def test_process_chat_message_refines_existing_plan_instead_of_creating_new_plan():
    session = SimpleNamespace(id=77)
    existing_plan = SimpleNamespace(
        id=21, title="下周高数复习计划", start_date=date(2026, 4, 28), phases=[]
    )
    existing_task = SimpleNamespace(
        id=31,
        title="下周高数复习",
        plan_id=21,
        priority="medium",
        children=[],
        due_date=None,
    )
    refreshed_parent = SimpleNamespace(
        id=31,
        title="下周高数复习",
        plan_id=21,
        priority="medium",
        children=[SimpleNamespace(id=32)],
        due_date=None,
    )

    with (
        patch(
            "app.services.chat_service.get_or_create_session", new=AsyncMock(return_value=session)
        ),
        patch("app.services.chat_service.load_history", new=AsyncMock(return_value=[])),
        patch(
            "app.services.chat_service.load_structured_history",
            new=AsyncMock(
                return_value=[
                    {
                        "role": "assistant",
                        "content": "之前已创建计划",
                        "intent": "create_plan",
                        "entities": {
                            "extracted_plans": [{"id": 21, "title": "下周高数复习计划"}],
                            "extracted_tasks": [{"id": 31, "title": "下周高数复习", "plan_id": 21}],
                        },
                    }
                ]
            ),
        ),
        patch(
            "app.services.chat_service._hydrate_recent_action_context",
            new=AsyncMock(
                return_value={
                    "plan_id": 21,
                    "plan_title": "下周高数复习计划",
                    "task_id": 31,
                    "task_title": "下周高数复习",
                }
            ),
        ),
        patch("app.services.chat_service.call_llm_for_intent", new=AsyncMock(return_value=None)),
        patch(
            "app.services.chat_service.execute_intent",
            new=AsyncMock(
                return_value=(
                    {"plan": existing_plan, "task": existing_task, "refinement_mode": True},
                    [{"id": 31, "title": "下周高数复习", "plan_id": 21, "parent_task_id": None}],
                    [{"id": 21, "title": "下周高数复习计划"}],
                )
            ),
        ),
        patch(
            "app.services.chat_service.call_llm_api",
            new=AsyncMock(
                return_value=(
                    "目标：明确考试范围，整理知识结构\n"
                    "任务安排：\n"
                    "- 9:00 - 10:00 复习课本/笔记\n"
                    "- 14:00 - 15:00 整理重点公式\n"
                )
            ),
        ),
        patch(
            "app.services.chat_service.task_service.get_task",
            new=AsyncMock(side_effect=[SimpleNamespace(children=[]), refreshed_parent]),
        ),
        patch(
            "app.services.chat_service.task_service.serialize_task",
            side_effect=[{"children": []}],
        ),
        patch(
            "app.services.chat_service.task_service.create_task",
            new=AsyncMock(
                side_effect=[
                    SimpleNamespace(
                        id=32,
                        title="第1天：明确考试范围，整理知识结构",
                        plan_id=21,
                        parent_task_id=31,
                    ),
                ]
            ),
        ) as create_subtask,
        patch("app.services.chat_service.save_message", new=AsyncMock()),
        patch("app.services.chat_service.record_learning_activity", new=AsyncMock()),
    ):
        result = await process_chat_message(
            user_id=8,
            session_id=77,
            message="那帮我把每天一天的任务具体化吧",
            db=AsyncMock(),
        )

    assert create_subtask.await_count == 1
    assert result["intent"] == "refine_plan"
    assert result["extracted_plans"][0]["id"] == 21
    assert result["extracted_tasks"][0]["id"] == 31
    assert "下周高数复习计划" in result["reply"] and "子项" in result["reply"]


@pytest.mark.asyncio
async def test_process_chat_message_refine_plan_falls_back_to_plan_title_when_task_context_missing():
    session = SimpleNamespace(id=88)
    existing_plan = SimpleNamespace(
        id=41, title="下周高数复习计划", start_date=date(2026, 4, 28), phases=[]
    )
    created_root_task = SimpleNamespace(
        id=51,
        title="下周高数复习计划",
        plan_id=41,
        priority="medium",
        parent_task_id=None,
        children=[],
        due_date=None,
    )

    with (
        patch(
            "app.services.chat_service.get_or_create_session", new=AsyncMock(return_value=session)
        ),
        patch("app.services.chat_service.load_history", new=AsyncMock(return_value=[])),
        patch(
            "app.services.chat_service.load_structured_history",
            new=AsyncMock(
                return_value=[
                    {
                        "role": "assistant",
                        "content": "之前已创建计划",
                        "intent": "create_plan",
                        "entities": {
                            "extracted_plans": [{"id": 41, "title": "下周高数复习计划"}],
                        },
                    }
                ]
            ),
        ),
        patch(
            "app.services.chat_service._hydrate_recent_action_context",
            new=AsyncMock(
                return_value={
                    "plan_id": 41,
                    "plan_title": "下周高数复习计划",
                }
            ),
        ),
        patch("app.services.chat_service.call_llm_for_intent", new=AsyncMock(return_value=None)),
        patch(
            "app.services.chat_service.execute_intent",
            new=AsyncMock(
                return_value=(
                    {"plan": existing_plan, "task": created_root_task, "refinement_mode": True},
                    [
                        {
                            "id": 51,
                            "title": "下周高数复习计划",
                            "plan_id": 41,
                            "parent_task_id": None,
                        }
                    ],
                    [{"id": 41, "title": "下周高数复习计划"}],
                )
            ),
        ),
        patch(
            "app.services.chat_service.call_llm_api",
            new=AsyncMock(return_value="我会继续细化这份计划。"),
        ),
        patch(
            "app.services.chat_service.task_service.get_task",
            new=AsyncMock(return_value=created_root_task),
        ),
        patch(
            "app.services.chat_service.task_service.serialize_task", return_value={"children": []}
        ),
        patch("app.services.chat_service.task_service.create_task", new=AsyncMock()),
        patch("app.services.chat_service.save_message", new=AsyncMock()),
        patch("app.services.chat_service.record_learning_activity", new=AsyncMock()),
    ):
        result = await process_chat_message(
            user_id=10,
            session_id=88,
            message="那帮我把每天一天的任务具体化吧",
            db=AsyncMock(),
        )

    assert result["intent"] == "refine_plan"
    assert "下周高数复习计划" in result["reply"]


@pytest.mark.asyncio
async def test_process_chat_message_clarifies_before_creating_plan_when_goal_is_still_broad():
    session = SimpleNamespace(id=101)

    with (
        patch(
            "app.services.chat_service.get_or_create_session", new=AsyncMock(return_value=session)
        ),
        patch("app.services.chat_service.load_history", new=AsyncMock(return_value=[])),
        patch("app.services.chat_service.load_structured_history", new=AsyncMock(return_value=[])),
        patch(
            "app.services.chat_service._hydrate_recent_action_context",
            new=AsyncMock(return_value={}),
        ),
        patch("app.services.chat_service.call_llm_for_intent", new=AsyncMock(return_value=None)),
        patch(
            "app.services.chat_service.save_message",
            new=AsyncMock(),
        ) as save_message,
        patch("app.services.chat_service.record_learning_activity", new=AsyncMock()),
        patch("app.services.chat_service.execute_intent", new=AsyncMock()) as execute_intent,
    ):
        result = await process_chat_message(
            user_id=3,
            session_id=None,
            message="现在开始一周内我想学习计算机专业的专业课内容",
            db=AsyncMock(),
        )

    assert result["intent"] == "clarify_plan"
    assert "我先不急着直接给你排完整计划" in result["reply"]
    assert result["extracted_tasks"] is None
    execute_intent.assert_not_awaited()
    assert save_message.await_count == 2


@pytest.mark.asyncio
async def test_process_chat_message_clarifies_for_natural_broad_learning_goal_phrase():
    session = SimpleNamespace(id=103)

    with (
        patch(
            "app.services.chat_service.get_or_create_session", new=AsyncMock(return_value=session)
        ),
        patch("app.services.chat_service.load_history", new=AsyncMock(return_value=[])),
        patch("app.services.chat_service.load_structured_history", new=AsyncMock(return_value=[])),
        patch(
            "app.services.chat_service._hydrate_recent_action_context",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.services.chat_service.call_llm_for_intent",
            new=AsyncMock(return_value={"intent": "create_plan", "entities": {}}),
        ),
        patch("app.services.chat_service.save_message", new=AsyncMock()),
        patch("app.services.chat_service.record_learning_activity", new=AsyncMock()),
        patch("app.services.chat_service.execute_intent", new=AsyncMock()) as execute_intent,
    ):
        result = await process_chat_message(
            user_id=4,
            session_id=None,
            message="我想一周内系统学一下计算机专业课",
            db=AsyncMock(),
        )

    assert result["intent"] == "clarify_plan"
    assert "先确认一个关键点" in result["reply"]
    execute_intent.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_chat_message_uses_exam_style_clarification_for_exam_goal():
    session = SimpleNamespace(id=104)

    with (
        patch(
            "app.services.chat_service.get_or_create_session", new=AsyncMock(return_value=session)
        ),
        patch("app.services.chat_service.load_history", new=AsyncMock(return_value=[])),
        patch("app.services.chat_service.load_structured_history", new=AsyncMock(return_value=[])),
        patch(
            "app.services.chat_service._hydrate_recent_action_context",
            new=AsyncMock(return_value={}),
        ),
        patch("app.services.chat_service.call_llm_for_intent", new=AsyncMock(return_value=None)),
        patch("app.services.chat_service.save_message", new=AsyncMock()),
        patch("app.services.chat_service.record_learning_activity", new=AsyncMock()),
        patch("app.services.chat_service.execute_intent", new=AsyncMock()) as execute_intent,
    ):
        result = await process_chat_message(
            user_id=4,
            session_id=None,
            message="我想准备下周的高数考试",
            db=AsyncMock(),
        )

    assert result["intent"] == "clarify_plan"
    assert "先帮你梳理考试范围" in result["reply"]
    execute_intent.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_chat_message_uses_skill_style_clarification_for_skill_goal():
    session = SimpleNamespace(id=105)

    with (
        patch(
            "app.services.chat_service.get_or_create_session", new=AsyncMock(return_value=session)
        ),
        patch("app.services.chat_service.load_history", new=AsyncMock(return_value=[])),
        patch("app.services.chat_service.load_structured_history", new=AsyncMock(return_value=[])),
        patch(
            "app.services.chat_service._hydrate_recent_action_context",
            new=AsyncMock(return_value={}),
        ),
        patch("app.services.chat_service.call_llm_for_intent", new=AsyncMock(return_value=None)),
        patch("app.services.chat_service.save_message", new=AsyncMock()),
        patch("app.services.chat_service.record_learning_activity", new=AsyncMock()),
        patch("app.services.chat_service.execute_intent", new=AsyncMock()) as execute_intent,
    ):
        result = await process_chat_message(
            user_id=4,
            session_id=None,
            message="我想系统学一下 Python 编程",
            db=AsyncMock(),
        )

    assert result["intent"] == "clarify_plan"
    assert "先确定学习路径" in result["reply"]
    assert result["next_prompt_options"] == ["先定学习路径", "直接排第一阶段"]
    execute_intent.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_chat_message_expires_stale_pending_plan_context_by_turn_count():
    session = SimpleNamespace(id=110)
    expired_pending = {
        "message": "我想系统学一下计算机专业课",
        "stage": "focus_topic",
        "answers": {"entry_choice": "schedule"},
        "entities": {"goal_type": "course_exploration"},
        "turn_count": 3,
        "created_at": datetime.utcnow().isoformat(),
    }
    with (
        patch(
            "app.services.chat_service.get_or_create_session", new=AsyncMock(return_value=session)
        ),
        patch("app.services.chat_service.load_history", new=AsyncMock(return_value=[])),
        patch("app.services.chat_service.load_structured_history", new=AsyncMock(return_value=[])),
        patch(
            "app.services.chat_service._hydrate_recent_action_context",
            new=AsyncMock(return_value={"pending_plan_request": expired_pending}),
        ),
        patch("app.services.chat_service.call_llm_for_intent", new=AsyncMock(return_value=None)),
        patch("app.services.chat_service.save_message", new=AsyncMock()),
        patch("app.services.chat_service.record_learning_activity", new=AsyncMock()),
        patch("app.services.chat_service.execute_intent", new=AsyncMock()) as execute_intent,
    ):
        result = await process_chat_message(
            user_id=6,
            session_id=None,
            message="我想系统学一下计算机专业课",
            db=AsyncMock(),
        )

    assert result["intent"] == "clarify_plan"
    assert "先不急着" in result["reply"]
    execute_intent.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_chat_message_uses_preference_seed_to_reduce_forced_clarify_steps():
    session = SimpleNamespace(id=111)
    preference_seed = {
        "time_budget": "每天1小时",
        "focus_topic": "计算机专业课核心课",
        "start_hint": None,
    }
    with (
        patch(
            "app.services.chat_service.get_or_create_session", new=AsyncMock(return_value=session)
        ),
        patch("app.services.chat_service.load_history", new=AsyncMock(return_value=[])),
        patch("app.services.chat_service.load_structured_history", new=AsyncMock(return_value=[])),
        patch(
            "app.services.chat_service._hydrate_recent_action_context",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.services.chat_service._load_user_preference_memory",
            new=AsyncMock(return_value=preference_seed),
        ),
        patch("app.services.chat_service.call_llm_for_intent", new=AsyncMock(return_value=None)),
        patch("app.services.chat_service.save_message", new=AsyncMock()),
        patch("app.services.chat_service.record_learning_activity", new=AsyncMock()),
        patch("app.services.chat_service.execute_intent", new=AsyncMock()) as execute_intent,
    ):
        result = await process_chat_message(
            user_id=6,
            session_id=None,
            message="我想一周内系统学一下计算机专业课，直接开始安排吧",
            db=AsyncMock(),
        )

    assert result["intent"] == "clarify_plan"
    assert "今天开始" in result["reply"]
    assert "先不急着直接给你整套计划" not in result["reply"]
    execute_intent.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_chat_message_passes_response_density_to_prompt_builder():
    session = SimpleNamespace(id=112)
    with (
        patch(
            "app.services.chat_service.get_or_create_session", new=AsyncMock(return_value=session)
        ),
        patch("app.services.chat_service.load_history", new=AsyncMock(return_value=[])),
        patch("app.services.chat_service.load_structured_history", new=AsyncMock(return_value=[])),
        patch(
            "app.services.chat_service._hydrate_recent_action_context",
            new=AsyncMock(return_value={}),
        ),
        patch("app.services.chat_service.call_llm_for_intent", new=AsyncMock(return_value=None)),
        patch("app.services.chat_service.resolve_intent", return_value=("chat", {})),
        patch(
            "app.services.chat_service.execute_intent",
            new=AsyncMock(return_value=(None, None, None)),
        ),
        patch(
            "app.services.chat_service.build_companion_prompt", return_value="prompt"
        ) as prompt_builder,
        patch(
            "app.services.chat_service.call_llm_api", new=AsyncMock(return_value="好的，已记下。")
        ),
        patch("app.services.chat_service.save_message", new=AsyncMock()),
        patch("app.services.chat_service.record_learning_activity", new=AsyncMock()),
    ):
        await process_chat_message(
            user_id=8,
            session_id=None,
            message="简短点，帮我看看今天先做什么",
            db=AsyncMock(),
        )

    prompt_builder.assert_called_once()
    assert prompt_builder.call_args.kwargs.get("response_density") == "concise"


def test_pick_soft_preference_ignores_stale_values():
    now = datetime.utcnow()
    selected = _pick_soft_preference(
        [
            ("concise", now - timedelta(days=20)),
            ("detailed", now - timedelta(days=20)),
        ]
    )
    assert selected is None


@pytest.mark.asyncio
async def test_process_chat_message_keeps_guiding_after_first_clarification_answer():
    session = SimpleNamespace(id=106)

    with (
        patch(
            "app.services.chat_service.get_or_create_session", new=AsyncMock(return_value=session)
        ),
        patch("app.services.chat_service.load_history", new=AsyncMock(return_value=[])),
        patch(
            "app.services.chat_service.load_structured_history",
            new=AsyncMock(
                return_value=[
                    {
                        "role": "assistant",
                        "content": "先别急着排计划。",
                        "intent": "clarify_plan",
                        "entities": {
                            "pending_plan_request": {
                                "message": "我想一周内系统学一下计算机专业课",
                                "stage": "initial_choice",
                                "answers": {},
                                "entities": {"goal_type": "course_exploration"},
                            }
                        },
                    }
                ]
            ),
        ),
        patch(
            "app.services.chat_service._hydrate_recent_action_context",
            new=AsyncMock(
                return_value={
                    "pending_plan_request": {
                        "message": "我想一周内系统学一下计算机专业课",
                        "stage": "initial_choice",
                        "answers": {},
                        "entities": {"goal_type": "course_exploration"},
                    }
                }
            ),
        ),
        patch("app.services.chat_service.save_message", new=AsyncMock()),
        patch("app.services.chat_service.record_learning_activity", new=AsyncMock()),
        patch("app.services.chat_service.execute_intent", new=AsyncMock()) as execute_intent,
    ):
        result = await process_chat_message(
            user_id=4,
            session_id=None,
            message="先理课程结构",
            db=AsyncMock(),
        )

    assert result["intent"] == "clarify_plan"
    assert "先选一个最关键科目或知识块起步" in result["reply"]
    execute_intent.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_chat_message_skips_time_budget_question_when_preference_known():
    session = SimpleNamespace(id=109)

    with (
        patch(
            "app.services.chat_service.get_or_create_session", new=AsyncMock(return_value=session)
        ),
        patch("app.services.chat_service.load_history", new=AsyncMock(return_value=[])),
        patch(
            "app.services.chat_service.load_structured_history",
            new=AsyncMock(
                return_value=[
                    {
                        "role": "assistant",
                        "content": "先别急着排计划。",
                        "intent": "clarify_plan",
                        "entities": {
                            "pending_plan_request": {
                                "message": "我想一周内系统学一下计算机专业课",
                                "stage": "focus_topic",
                                "answers": {},
                                "entities": {"goal_type": "course_exploration"},
                            }
                        },
                    }
                ]
            ),
        ),
        patch(
            "app.services.chat_service._load_user_preference_memory",
            new=AsyncMock(return_value={"time_budget": "每天晚上两小时"}),
        ),
        patch(
            "app.services.chat_service._hydrate_recent_action_context",
            new=AsyncMock(
                return_value={
                    "pending_plan_request": {
                        "message": "我想一周内系统学一下计算机专业课",
                        "stage": "focus_topic",
                        "answers": {},
                        "entities": {"goal_type": "course_exploration"},
                    }
                }
            ),
        ),
        patch("app.services.chat_service.save_message", new=AsyncMock()),
        patch("app.services.chat_service.record_learning_activity", new=AsyncMock()),
        patch("app.services.chat_service.execute_intent", new=AsyncMock()) as execute_intent,
    ):
        result = await process_chat_message(
            user_id=11,
            session_id=None,
            message="先从数据结构开始",
            db=AsyncMock(),
        )

    assert result["intent"] == "clarify_plan"
    assert "每天大概能投入多久" not in result["reply"]
    assert "最后确认一下" in result["reply"]
    execute_intent.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_chat_message_builds_plan_only_after_staged_answers_are_complete():
    session = SimpleNamespace(id=107)
    created_plan = SimpleNamespace(
        id=12, title="数据结构入门学习计划", start_date=date(2026, 4, 28), phases=[]
    )
    created_task = SimpleNamespace(
        id=18,
        title="数据结构",
        plan_id=12,
        priority="medium",
        children=[],
        due_date=None,
    )

    with (
        patch(
            "app.services.chat_service.get_or_create_session", new=AsyncMock(return_value=session)
        ),
        patch("app.services.chat_service.load_history", new=AsyncMock(return_value=[])),
        patch(
            "app.services.chat_service.load_structured_history",
            new=AsyncMock(
                return_value=[
                    {
                        "role": "assistant",
                        "content": "继续细化",
                        "intent": "clarify_plan",
                        "entities": {
                            "pending_plan_request": {
                                "message": "我想一周内系统学一下计算机专业课",
                                "stage": "start_time",
                                "answers": {
                                    "entry_choice": "schedule",
                                    "focus_topic": "数据结构",
                                    "time_budget": "每天晚上两小时",
                                },
                                "entities": {"goal_type": "course_exploration"},
                            }
                        },
                    }
                ]
            ),
        ),
        patch(
            "app.services.chat_service._hydrate_recent_action_context",
            new=AsyncMock(
                return_value={
                    "pending_plan_request": {
                        "message": "我想一周内系统学一下计算机专业课",
                        "stage": "start_time",
                        "answers": {
                            "entry_choice": "schedule",
                            "focus_topic": "数据结构",
                            "time_budget": "每天晚上两小时",
                        },
                        "entities": {"goal_type": "course_exploration"},
                    }
                }
            ),
        ),
        patch(
            "app.services.chat_service.execute_intent",
            new=AsyncMock(
                return_value=(
                    {"plan": created_plan, "task": created_task},
                    [{"id": 18, "title": "数据结构", "parent_task_id": None, "plan_id": 12}],
                    [{"id": 12, "title": "数据结构入门学习计划"}],
                )
            ),
        ) as execute_intent,
        patch(
            "app.services.chat_service.call_llm_api",
            new=AsyncMock(return_value="好的，我们就按这个节奏推进。"),
        ),
        patch("app.services.chat_service.save_message", new=AsyncMock()),
        patch("app.services.chat_service.record_learning_activity", new=AsyncMock()),
    ):
        result = await process_chat_message(
            user_id=4,
            session_id=None,
            message="明天开始",
            db=AsyncMock(),
        )

    assert result["intent"] == "plan_proposal"
    assert result["proposal_id"] is not None
    assert execute_intent.await_count == 0


@pytest.mark.asyncio
async def test_process_chat_message_treats_continuation_phrase_as_refine_plan():
    session = SimpleNamespace(id=108)
    existing_plan = SimpleNamespace(
        id=21, title="数据结构入门学习计划", start_date=date(2026, 4, 28), phases=[]
    )
    existing_task = SimpleNamespace(
        id=31,
        title="数据结构",
        plan_id=21,
        priority="medium",
        children=[],
        due_date=None,
    )

    with (
        patch(
            "app.services.chat_service.get_or_create_session", new=AsyncMock(return_value=session)
        ),
        patch("app.services.chat_service.load_history", new=AsyncMock(return_value=[])),
        patch(
            "app.services.chat_service.load_structured_history",
            new=AsyncMock(
                return_value=[
                    {
                        "role": "assistant",
                        "content": "已经创建学习计划",
                        "intent": "create_plan",
                        "entities": {
                            "extracted_plans": [{"id": 21, "title": "数据结构入门学习计划"}],
                            "extracted_tasks": [{"id": 31, "title": "数据结构", "plan_id": 21}],
                        },
                    }
                ]
            ),
        ),
        patch(
            "app.services.chat_service._hydrate_recent_action_context",
            new=AsyncMock(
                return_value={
                    "plan_id": 21,
                    "plan_title": "数据结构入门学习计划",
                    "task_id": 31,
                    "task_title": "数据结构",
                }
            ),
        ),
        patch("app.services.chat_service.call_llm_for_intent", new=AsyncMock(return_value=None)),
        patch(
            "app.services.chat_service.execute_intent",
            new=AsyncMock(
                return_value=(
                    {"plan": existing_plan, "task": existing_task, "refinement_mode": True},
                    [{"id": 31, "title": "数据结构", "plan_id": 21, "parent_task_id": None}],
                    [{"id": 21, "title": "数据结构入门学习计划"}],
                )
            ),
        ) as execute_intent,
        patch(
            "app.services.chat_service.call_llm_api",
            new=AsyncMock(return_value="好的，我继续沿着这个计划往下细化。"),
        ),
        patch("app.services.chat_service.save_message", new=AsyncMock()),
        patch("app.services.chat_service.record_learning_activity", new=AsyncMock()),
    ):
        result = await process_chat_message(
            user_id=6,
            session_id=108,
            message="好的，现在继续帮我列出其他的计划内容吧",
            db=AsyncMock(),
        )

    assert result["intent"] == "refine_plan"
    called_entities = execute_intent.await_args.kwargs["entities"]
    assert called_entities["refine_existing"] is True
    assert called_entities["plan_id"] == 21
    assert called_entities["plan_title"] == "数据结构入门学习计划"


@pytest.mark.asyncio
async def test_process_chat_message_uses_pending_plan_context_when_user_answers_clarification():
    session = SimpleNamespace(id=102)
    created_plan = SimpleNamespace(
        id=12, title="计算机专业课入门", start_date=date(2026, 4, 28), phases=[]
    )
    created_task = SimpleNamespace(
        id=18, title="计算机专业课入门", plan_id=12, priority="medium", children=[], due_date=None
    )

    with (
        patch(
            "app.services.chat_service.get_or_create_session", new=AsyncMock(return_value=session)
        ),
        patch("app.services.chat_service.load_history", new=AsyncMock(return_value=[])),
        patch(
            "app.services.chat_service.load_structured_history",
            new=AsyncMock(
                return_value=[
                    {
                        "role": "assistant",
                        "content": "先别急着排计划",
                        "intent": "clarify_plan",
                        "entities": {
                            "pending_plan_request": {
                                "message": "现在开始一周内我想学习计算机专业的专业课内容",
                                "entities": {
                                    "plan_title": "学习计算机专业的专业课内容",
                                    "plan_description": "现在开始一周内我想学习计算机专业的专业课内容",
                                    "task_title": "学习计算机专业的专业课内容",
                                },
                            }
                        },
                    }
                ]
            ),
        ),
        patch(
            "app.services.chat_service._hydrate_recent_action_context",
            new=AsyncMock(
                return_value={
                    "pending_plan_request": {
                        "message": "现在开始一周内我想学习计算机专业的专业课内容",
                        "entities": {
                            "plan_title": "学习计算机专业的专业课内容",
                            "plan_description": "现在开始一周内我想学习计算机专业的专业课内容",
                            "task_title": "学习计算机专业的专业课内容",
                        },
                    }
                }
            ),
        ),
        patch("app.services.chat_service.call_llm_for_intent", new=AsyncMock(return_value=None)),
        patch(
            "app.services.chat_service.execute_intent",
            new=AsyncMock(
                return_value=(
                    {"plan": created_plan, "task": created_task},
                    [
                        {
                            "id": 18,
                            "title": "计算机专业课入门",
                            "plan_id": 12,
                            "parent_task_id": None,
                        }
                    ],
                    [{"id": 12, "title": "计算机专业课入门"}],
                )
            ),
        ) as execute_intent,
        patch(
            "app.services.chat_service.call_llm_api",
            new=AsyncMock(return_value="好的，我会继续带你往下推进。"),
        ),
        patch("app.services.chat_service.save_message", new=AsyncMock()),
        patch("app.services.chat_service.record_learning_activity", new=AsyncMock()),
    ):
        result = await process_chat_message(
            user_id=5,
            session_id=102,
            message="直接从第一周安排开始，我每天晚上两小时，先从数据结构开始",
            db=AsyncMock(),
        )

    assert result["intent"] == "plan_proposal"
    assert result["proposal_id"] is not None
    assert execute_intent.await_count == 0


@pytest.mark.asyncio
async def test_process_chat_message_stages_plan_proposal_for_consultative_question():
    session = SimpleNamespace(id=201)
    with (
        patch(
            "app.services.chat_service.get_or_create_session", new=AsyncMock(return_value=session)
        ),
        patch("app.services.chat_service.load_history", new=AsyncMock(return_value=[])),
        patch("app.services.chat_service.load_structured_history", new=AsyncMock(return_value=[])),
        patch(
            "app.services.chat_service._hydrate_recent_action_context",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.services.chat_service.call_llm_for_intent",
            new=AsyncMock(
                return_value={"intent": "create_plan", "entities": {"plan_title": "计算机核心课程"}}
            ),
        ),
        patch(
            "app.services.chat_service.resolve_intent",
            return_value=("create_plan", {"plan_title": "计算机核心课程"}),
        ),
        patch("app.services.chat_service.execute_intent", new=AsyncMock()) as execute_intent_mock,
        patch(
            "app.services.chat_service.call_llm_api",
            new=AsyncMock(return_value="这是计划草案预览。"),
        ) as llm_mock,
        patch("app.services.chat_service.save_message", new=AsyncMock()) as save_message_mock,
        patch("app.services.chat_service.record_learning_activity", new=AsyncMock()),
    ):
        result = await process_chat_message(
            user_id=1,
            session_id=None,
            message="学几个核心课程，你推荐哪些？",
            db=AsyncMock(),
        )

    assert result["intent"] == "plan_proposal"
    assert result["proposal_id"] is not None
    assert result["extracted_tasks"] is None
    assert execute_intent_mock.await_count == 0
    assert llm_mock.await_count == 1
    assistant_entities = json.loads(save_message_mock.await_args_list[1].kwargs["entities_json"])
    assert assistant_entities["pending_action_proposal"]["intent"] == "create_plan"


@pytest.mark.asyncio
async def test_process_chat_message_commits_pending_plan_after_user_confirmation():
    session = SimpleNamespace(id=202)
    pending_entities = {
        "plan_title": "计算机核心课程学习计划",
        "task_title": "计算机核心课程学习计划",
    }
    with (
        patch(
            "app.services.chat_service.get_or_create_session", new=AsyncMock(return_value=session)
        ),
        patch("app.services.chat_service.load_history", new=AsyncMock(return_value=[])),
        patch(
            "app.services.chat_service.load_structured_history",
            new=AsyncMock(
                return_value=[
                    {
                        "role": "assistant",
                        "content": "这是草案",
                        "intent": "plan_proposal",
                        "entities": {
                            "pending_action_proposal": {
                                "proposal_id": "proposal-abc123",
                                "intent": "create_plan",
                                "entities": pending_entities,
                                "source_message": "学几个核心课程，你推荐哪些？",
                                "proposal_reply": "第1天：数据结构入门\n- 19:00-20:00 复习链表与队列",
                            }
                        },
                    }
                ]
            ),
        ),
        patch(
            "app.services.chat_service._hydrate_recent_action_context",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.services.chat_service.call_llm_for_intent",
            new=AsyncMock(return_value={"intent": "chat", "entities": {}}),
        ),
        patch("app.services.chat_service.resolve_intent", return_value=("chat", {})),
        patch(
            "app.services.chat_service.execute_intent",
            new=AsyncMock(
                return_value=(
                    {
                        "plan": SimpleNamespace(id=1, title="计划"),
                        "task": SimpleNamespace(title="主任务", children=[]),
                    },
                    [],
                    [],
                )
            ),
        ) as execute_intent_mock,
        patch("app.services.chat_service.call_llm_api", new=AsyncMock(return_value="已加入计划。")),
        patch("app.services.chat_service.save_message", new=AsyncMock()),
        patch("app.services.chat_service.record_learning_activity", new=AsyncMock()),
    ):
        await process_chat_message(
            user_id=1,
            session_id=None,
            message="按这个计划加入任务",
            db=AsyncMock(),
            proposal_id="proposal-abc123",
        )

    assert execute_intent_mock.await_count == 1
    assert execute_intent_mock.await_args.kwargs["intent"] == "create_plan"
    assert "数据结构入门" in execute_intent_mock.await_args.kwargs["message"]
    commit_entities = execute_intent_mock.await_args.kwargs["entities"]
    assert commit_entities["plan_title"].endswith("（一周版）")
    assert commit_entities["should_create_task"] is True


@pytest.mark.asyncio
async def test_process_chat_message_commit_uses_two_week_suffix_when_detected():
    session = SimpleNamespace(id=303)
    with (
        patch(
            "app.services.chat_service.get_or_create_session", new=AsyncMock(return_value=session)
        ),
        patch("app.services.chat_service.load_history", new=AsyncMock(return_value=[])),
        patch(
            "app.services.chat_service.load_structured_history",
            new=AsyncMock(
                return_value=[
                    {
                        "role": "assistant",
                        "content": "这是草案",
                        "intent": "plan_proposal",
                        "entities": {
                            "pending_action_proposal": {
                                "proposal_id": "p-two-weeks",
                                "intent": "create_plan",
                                "entities": {},
                                "source_message": "帮我规划一下",
                                "proposal_reply": "两周冲刺安排：Day1-14 复习与练习",
                            }
                        },
                    }
                ]
            ),
        ),
        patch(
            "app.services.chat_service._hydrate_recent_action_context",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.services.chat_service.call_llm_for_intent",
            new=AsyncMock(return_value={"intent": "chat", "entities": {}}),
        ),
        patch("app.services.chat_service.resolve_intent", return_value=("chat", {})),
        patch(
            "app.services.chat_service.execute_intent",
            new=AsyncMock(
                return_value=(
                    {
                        "plan": SimpleNamespace(id=1, title="两周冲刺"),
                        "task": SimpleNamespace(title="主任务", children=[]),
                    },
                    [],
                    [],
                )
            ),
        ) as execute_intent_mock,
        patch("app.services.chat_service.call_llm_api", new=AsyncMock(return_value="ok")),
        patch("app.services.chat_service.save_message", new=AsyncMock()),
        patch("app.services.chat_service.record_learning_activity", new=AsyncMock()),
    ):
        await process_chat_message(
            user_id=1,
            session_id=None,
            message="加入计划",
            db=AsyncMock(),
            proposal_id="p-two-weeks",
        )

    entities = execute_intent_mock.await_args.kwargs["entities"]
    assert entities["plan_title"].endswith("（两周版）")


def test_extract_explicit_plan_title_prefers_bracket_over_day_header():
    from app.services.chat_service import (
        _build_commit_entities_from_proposal,
        _extract_explicit_plan_title,
    )

    draft = (
        "### 周计划草案\n"
        "🗓️ 第1天（今晚）| 建立整体认知\n"
        "- 浏览考纲\n"
        "若你确认，我将正式创建主任务【公务员备考第一阶段：认知启动】，并把每日任务挂入计划。"
    )
    explicit = _extract_explicit_plan_title(draft)
    assert explicit is not None
    assert "公务员" in explicit
    assert "第1天" not in explicit
    assert "今晚" not in explicit

    entities, _ = _build_commit_entities_from_proposal(
        proposal={
            "entities": {},
            "proposal_reply": draft,
            "source_message": "加入计划",
        },
        fallback_message="加入计划",
    )
    assert "公务员" in entities["task_title"]
    assert "第1天" not in entities["task_title"]


def test_build_commit_entities_prefers_source_goal_and_filters_question_subtasks():
    from app.services.chat_service import _build_commit_entities_from_proposal

    proposal_reply = (
        "好的，我们先确认两点：\n"
        "- 你每天能抽出多久来背？15分钟还是30分钟以上？\n"
        "- 第1天：你每天能抽出多久来背？\n"
    )
    entities, _ = _build_commit_entities_from_proposal(
        proposal={
            "entities": {},
            "proposal_reply": proposal_reply,
            "source_message": "下周有个英语测试，想列个背单词计划",
        },
        fallback_message="加入计划",
    )

    assert "英语" in entities["plan_title"] or "背单词" in entities["plan_title"]
    assert "多少" not in entities["plan_title"]
    assert "subtasks" not in entities or all(
        "？" not in item["title"] for item in entities["subtasks"]
    )


def test_build_commit_entities_avoids_generic_plan_wording_as_title():
    from app.services.chat_service import _build_commit_entities_from_proposal

    entities, _ = _build_commit_entities_from_proposal(
        proposal={
            "entities": {},
            "proposal_reply": "好的，先确认时间投入。我会给你一版计划草案。",
            "source_message": "下周英语测试，想背单词，就帮我列个计划吧",
        },
        fallback_message="加入计划",
    )

    assert "就帮我列个计划" not in entities["plan_title"]
    assert "英语" in entities["plan_title"] or "背单词" in entities["plan_title"]


def test_build_commit_entities_standardizes_plan_title_and_task_title():
    from app.services.chat_service import _build_commit_entities_from_proposal

    entities, _ = _build_commit_entities_from_proposal(
        proposal={
            "entities": {},
            "proposal_reply": "可以，先明确词量和每天时长，再推进背词与复习。",
            "source_message": "下周英语测试，想列个背单词计划",
        },
        fallback_message="加入计划",
    )

    assert entities["plan_title"].endswith("（一周版）")
    assert "英语" in entities["plan_title"] or "背单词" in entities["plan_title"]
    assert "计划计划" not in entities["plan_title"]
    assert not entities["task_title"].endswith("计划")
