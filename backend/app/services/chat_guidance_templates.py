from __future__ import annotations

from typing import Literal, cast

GoalType = Literal["course_exploration", "exam_prep", "skill_building", "general_learning"]


def normalize_goal_type(goal_type: str) -> GoalType:
    if goal_type in {"course_exploration", "exam_prep", "skill_building"}:
        return cast(GoalType, goal_type)
    return "general_learning"


def build_force_clarify_reply(goal_type: str) -> str:
    normalized = normalize_goal_type(goal_type)
    if normalized == "course_exploration":
        return (
            "我先问这个，是为了避免一上来排满导致计划不贴合你当前阶段。"
            "这件事我可以陪你一步步来，不过我先不急着直接给你整套计划。"
            "你现在更想先做哪一步：先理清当前学习范围，还是直接开始安排第一周学习？"
        )
    if normalized == "exam_prep":
        return (
            "我先问这个，是为了先抓住提分杠杆，再安排节奏。"
            "我们先别急着把整套复习计划铺开。"
            "先确认最关键的一点：你现在更需要我先帮你梳理考试范围，还是直接开始安排这一周的复习节奏？"
        )
    if normalized == "skill_building":
        return (
            "我先问这个，是为了先定路径，避免后面反复返工。"
            "这类目标更适合一步一步搭起来。"
            "你现在更想先确定学习路径，还是直接开始安排第一阶段要练的内容？"
        )
    return (
        "我先问这个，是为了先定方向再定节奏。"
        "我先不急着直接给你排完整计划。"
        "先确认一个关键点：你现在是想先理清学习范围，还是已经准备好直接开始安排第一周任务？"
    )


def build_force_clarify_next_prompt(goal_type: str) -> str:
    normalized = normalize_goal_type(goal_type)
    if normalized == "course_exploration":
        return "你可以回：先理课程结构；或直接排第一周（附每天可投入时长）。"
    if normalized == "exam_prep":
        return "你可以回：先梳理考试范围；或直接排本周复习（附每天可投入时长）。"
    if normalized == "skill_building":
        return "你可以回：先定学习路径；或直接排第一阶段（附每天可投入时长）。"
    return "你可以回：先理清范围；或直接排第一周安排。"


def build_initial_choice_prompt(goal_type: str) -> tuple[str, str]:
    normalized = normalize_goal_type(goal_type)
    if normalized == "course_exploration":
        return (
            "我们先别急着往下排计划，我想先把方向陪你定清楚。你现在更希望我先带你理一遍学习范围，还是直接开始给你搭第一周安排？",
            "你可以直接回我“先理课程结构”，或者“直接安排第一周”。",
        )
    if normalized == "exam_prep":
        return (
            "这类复习目标我更想陪你先抓住重点，再去排日程。你现在更想先梳理考试范围，还是直接开始安排这一周的复习节奏？",
            "你可以直接回我“先梳理范围”，或者“直接安排这一周”。",
        )
    if normalized == "skill_building":
        return (
            "这种学习目标更适合一步步搭起来。你是想先把学习路径定清楚，还是直接开始安排第一阶段练什么？",
            "你可以直接回我“先定学习路径”，或者“直接开始第一阶段”。",
        )
    return (
        "我先不急着直接排计划，我们先把方向说清楚。你更想先理范围，还是直接开始安排第一周？",
        "你可以直接回我“先理范围”，或者“直接安排第一周”。",
    )


def build_clarify_quick_replies(goal_type: str, stage: str) -> list[str]:
    normalized = normalize_goal_type(goal_type)
    if stage == "initial_choice":
        if normalized == "course_exploration":
            return ["先理课程结构", "直接排第一周"]
        if normalized == "exam_prep":
            return ["先梳理考试范围", "直接排本周复习"]
        if normalized == "skill_building":
            return ["先定学习路径", "直接排第一阶段"]
        return ["先理清范围", "直接排第一周"]
    if stage == "focus_topic":
        return ["先从最薄弱的一块开始", "先整体过一遍范围"]
    if stage == "time_budget":
        return ["每天一小时", "工作日一小时，周末三小时"]
    if stage == "start_time":
        return ["今晚开始", "下周一开始"]
    return []
