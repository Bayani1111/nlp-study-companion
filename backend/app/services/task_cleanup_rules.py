from __future__ import annotations

from dataclasses import dataclass

ADVISORY_HINTS = (
    "目标",
    "建议",
    "学习内容",
    "精简版",
    "可拆为",
    "你可以",
    "如果你",
    "即使你",
    "推荐",
    "更建议",
)

ACTION_HINTS = (
    "复习",
    "练习",
    "刷题",
    "做题",
    "背",
    "写",
    "完成",
    "整理",
    "提交",
    "预习",
    "回顾",
    "总结",
    "打卡",
)

TIME_HINTS = (
    "上午",
    "下午",
    "晚上",
    "今晚",
    "明天",
    "今天",
    "下周",
    "点",
)


@dataclass(slots=True)
class CleanupDecision:
    should_delete: bool
    reason: str


def decide_advisory_subtask_cleanup(title: str, description: str | None = None) -> CleanupDecision:
    normalized_title = (title or "").strip()
    normalized_desc = (description or "").strip()
    combined = f"{normalized_title}\n{normalized_desc}"

    if not normalized_title:
        return CleanupDecision(False, "empty_title")

    advisory_hits = [hint for hint in ADVISORY_HINTS if hint in combined]
    action_hits = [hint for hint in ACTION_HINTS if hint in combined]
    has_time_hint = any(hint in combined for hint in TIME_HINTS)

    # 命中建议语且缺少动作/时间信号，判定为“建议型子任务”。
    if advisory_hits and (not action_hits or not has_time_hint):
        return CleanupDecision(True, f"advisory={','.join(advisory_hits[:3])}")

    # 以“目标/学习内容”开头的短句，通常是说明文字而非执行项。
    if normalized_title.startswith(("目标", "学习内容")) and not action_hits:
        return CleanupDecision(True, "title_starts_with_advisory_heading")

    return CleanupDecision(False, "looks_actionable")
