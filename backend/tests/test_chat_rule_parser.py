from datetime import date, timedelta

from app.services.chat_rule_parser import (
    build_fallback_entities,
    determine_fallback_intent,
    extract_bullet_subtasks_from_reply,
    extract_day_subtasks_from_reply,
    extract_goal_sections_from_reply,
    extract_structured_subtasks_from_reply,
    extract_subtasks_from_message,
    infer_plan_date_range,
    infer_time_of_day,
    looks_like_refinement_request,
    looks_like_task_request,
    needs_plan_clarification,
)


def test_extract_subtasks_from_message_splits_learning_arrangement():
    message = "帮我做一个下周高数复习计划，先看第一章笔记，然后刷20道例题，最后整理错题"

    subtasks = extract_subtasks_from_message(message, "下周高数复习计划")

    assert "看第一章笔记" in subtasks
    assert "刷20道例题" in subtasks
    assert "整理错题" in subtasks


def test_build_fallback_entities_includes_subtasks_for_plan_request():
    message = "帮我安排一个英语复习计划，并记录背单词任务，然后复习阅读，最后做一套听力"

    entities = build_fallback_entities(message)

    assert entities["should_create_task"] is True
    assert entities["subtasks"] == ["背单词任务", "复习阅读", "做一套听力"]


def test_build_fallback_entities_defaults_priority_to_medium_for_task_request():
    entities = build_fallback_entities("明天下午三点要交机器学习作业，帮我记个任务")
    assert entities["priority"] == "medium"


def test_build_fallback_entities_extracts_title_for_actionable_sentence():
    entities = build_fallback_entities("这周末把NLP课程实验报告写完")
    assert "NLP" in entities["task_title"]
    assert "实验报告" in entities["task_title"]


def test_build_fallback_entities_marks_must_sentence_as_high_priority():
    entities = build_fallback_entities("今天晚上必须完成测试用例编写")
    assert entities["priority"] == "high"


def test_build_fallback_entities_extracts_title_from_relaxed_prefix_sentence():
    entities = build_fallback_entities("有空的时候把简历项目经历润色一下")
    assert "简历" in entities["task_title"]
    assert "项目经历" in entities["task_title"]


def test_build_fallback_entities_extracts_title_for_backup_action():
    entities = build_fallback_entities("立刻把实验数据备份一下")
    assert "实验数据" in entities["task_title"]


def test_build_fallback_entities_extracts_title_for_checkin_action():
    entities = build_fallback_entities("之后把考研政治每日打卡加上")
    assert "考研政治" in entities["task_title"]


def test_infer_plan_date_range_supports_next_week():
    start_date, end_date = infer_plan_date_range("帮我做一个下周高数复习计划", None)

    assert start_date.weekday() == 0
    assert end_date - start_date == timedelta(days=6)
    assert start_date >= date.today()


def test_infer_time_of_day_supports_period_and_explicit_time():
    assert infer_time_of_day("上午复习英语") == (9, 0)
    assert infer_time_of_day("下午3点半刷题") == (15, 30)
    assert infer_time_of_day("晚上8点整理错题") == (20, 0)
    assert infer_time_of_day("9:00-10:00 复习高数") == (9, 0)


def test_looks_like_refinement_request_detects_follow_up_phrase():
    assert looks_like_refinement_request("那帮我把每天一天的任务具体化吧")


def test_looks_like_task_request_detects_actionable_sentence_without_task_keyword():
    assert looks_like_task_request("尽快把AI导论ppt过一遍")


def test_looks_like_task_request_ignores_exploration_only_question():
    assert not looks_like_task_request("我想先了解一下这门课有哪些内容")


def test_determine_fallback_intent_keeps_consultation_question_as_chat():
    assert determine_fallback_intent("学几个核心课程，你推荐哪些？") == "chat"


def test_build_fallback_entities_does_not_force_titles_for_consultation_question():
    entities = build_fallback_entities("学几个核心课程，你推荐哪些？")
    assert "task_title" not in entities
    assert "plan_title" not in entities


def test_build_fallback_entities_compacts_overlong_plan_title():
    entities = build_fallback_entities(
        "我想在一个月内学完计算机专业的主要课程，帮我列个合理的学习计划吧"
    )
    assert entities["plan_title"] == "我想在一个月内学完计算机专业的主要课程"


def test_needs_plan_clarification_skips_when_actionable_task_intent_is_obvious():
    entities = build_fallback_entities("我想系统学一下Python，先做一个学习计划")
    assert not needs_plan_clarification("我想系统学一下Python，先做一个学习计划", entities)


def test_extract_day_subtasks_from_reply_parses_day_schedule_into_multiple_tasks():
    reply = """
### 第1天：梳理知识点
- 目标：明确考试范围，整理知识结构
- 任务安排：
- 9:00 - 10:00 复习课本/笔记，整理重点公式和概念
- 10:30 - 11:00 做5道基础题（如极限、导数）
- 14:00 - 15:00 整理知识清单或画思维导图

### 第2天：专项刷题
- 目标：提升计算速度和准确度
- 任务安排：
- 9:00 - 10:30 做10道例题（如求导、积分、极值问题）
"""

    subtasks = extract_day_subtasks_from_reply(reply)

    assert len(subtasks) == 2
    assert subtasks[0]["day_offset"] == 0
    assert "梳理知识点" in subtasks[0]["title"] or "第1天" in subtasks[0]["title"]
    assert "9:00" in (subtasks[0].get("description") or "")
    assert subtasks[1]["day_offset"] == 1
    assert "提升计算速度和准确度" in (subtasks[1].get("description") or "")


def test_extract_goal_sections_from_reply_parses_goal_and_schedule_blocks():
    reply = """
目标：明确考试范围，整理知识结构
任务安排：
- 9:00 - 10:00 复习课本/笔记
- 14:00 - 15:00 整理重点公式

目标：提升计算速度和准确度
任务安排：
- 9:00 - 10:30 做10道例题
"""

    subtasks = extract_goal_sections_from_reply(reply)

    assert len(subtasks) == 2
    assert subtasks[0]["day_offset"] == 0
    assert subtasks[1]["day_offset"] == 1
    assert "10:00" in (subtasks[0].get("description") or "")
    assert "提升计算速度和准确度" in (
        subtasks[1].get("description") or subtasks[1].get("title", "")
    )


def test_extract_bullet_subtasks_from_reply_parses_bullet_plan():
    reply = """
- 上午看第一章笔记
- 下午刷 20 道例题
- 晚上整理错题
"""

    subtasks = extract_bullet_subtasks_from_reply(reply)

    assert len(subtasks) == 3
    assert subtasks[0]["title"].startswith("步骤1")
    assert subtasks[0]["hour"] == 9
    assert subtasks[1]["hour"] == 15
    assert subtasks[2]["hour"] == 20


def test_extract_structured_subtasks_prefers_day_sections_over_bullets():
    reply = """
### 第1天：梳理
- 上午看笔记
- 晚上整理错题
"""

    subtasks = extract_structured_subtasks_from_reply(reply)

    assert len(subtasks) == 1
    assert "第1天" in subtasks[0]["title"]
    assert "看笔记" in (subtasks[0].get("description") or "") and "整理错题" in (
        subtasks[0].get("description") or ""
    )


def test_extract_structured_subtasks_ignores_conversational_reply():
    reply = "好的，我已经把你的学习节奏记下来了：每天晚上两小时，从下周一开始。你可以先看课程结构。"
    subtasks = extract_structured_subtasks_from_reply(reply)
    assert subtasks == []


def test_extract_structured_subtasks_ignores_advisory_lines_in_plan_reply():
    reply = """
### 第1天：
- 目标：能写出清晰、模块化的代码
- > 即使你有基础，也建议用一周做结构化梳理 + 实战强化
- 学习内容（精简版）
- 19:00-20:00 复习数据结构数组和链表
"""
    subtasks = extract_structured_subtasks_from_reply(reply)
    assert len(subtasks) == 1
    assert "清晰" in subtasks[0]["title"] or "第1天" in subtasks[0]["title"]
    assert "复习数据结构数组和链表" in (subtasks[0].get("description") or "")


def test_extract_subtasks_ignores_question_sentences():
    message = "帮我做计划。你每天能抽出多久？先背单词，再复习阅读"
    subtasks = extract_subtasks_from_message(message, "英语计划")
    assert all("?" not in item and "？" not in item for item in subtasks)
    assert any("背单词" in item for item in subtasks)
