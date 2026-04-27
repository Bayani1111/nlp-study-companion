from app.services.chat_guidance_templates import (
    build_clarify_quick_replies,
    build_force_clarify_next_prompt,
    build_force_clarify_reply,
    build_initial_choice_prompt,
)


def test_force_clarify_reply_contains_explanation_prefix():
    reply = build_force_clarify_reply("skill_building")
    assert "我先问这个，是为了" in reply
    assert "先确定学习路径" in reply


def test_initial_choice_prompt_is_structured():
    reply, next_prompt = build_initial_choice_prompt("exam_prep")
    assert "梳理考试范围" in reply
    assert "你可以直接回我" in next_prompt


def test_clarify_quick_replies_follow_goal_and_stage():
    assert build_clarify_quick_replies("course_exploration", "initial_choice") == [
        "先理课程结构",
        "直接排第一周",
    ]
    assert build_clarify_quick_replies("general_learning", "start_time") == [
        "今晚开始",
        "下周一开始",
    ]
    assert "附每天可投入时长" in build_force_clarify_next_prompt("course_exploration")
