from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

TASK_HINT_WORDS = (
    "任务",
    "待办",
    "提醒",
    "记录",
    "记得",
    "安排",
    "复习",
    "背",
    "考试",
    "测试",
    "测验",
    "提交",
    "截止",
    "完成",
)

PLAN_HINT_WORDS = (
    "计划",
    "学习计划",
    "复习计划",
    "安排一个",
    "帮我列个计划",
    "阶段目标",
    "每日安排",
    "每天安排",
)

REFINEMENT_HINT_WORDS = (
    "具体化",
    "细化",
    "拆分",
    "拆成",
    "展开",
    "按天",
    "按周",
    "每天",
    "每日",
    "具体到",
    "任务树",
    "细到",
)

TIME_HINT_WORDS = (
    "今天",
    "明天",
    "后天",
    "今晚",
    "下午",
    "晚上",
    "早上",
    "上午",
    "中午",
    "下周",
    "月底",
)

ACTIONABLE_HINT_WORDS = (
    "复习",
    "整理",
    "刷",
    "看",
    "背",
    "做",
    "复盘",
    "总结",
    "检查",
    "练习",
    "学习",
    "记忆",
    "默写",
    "预习",
    "记录",
    "订正",
    "梳理",
    "回顾",
    "写",
    "跑",
    "补齐",
    "润色",
    "备份",
    "打卡",
    "加上",
)

CONVERSATIONAL_NOISE_HINTS = (
    "好的",
    "我已经",
    "我先",
    "你可以",
    "如果你愿意",
    "下面我们",
    "我会",
    "我可以",
    "这次一共",
    "帮你",
)

NON_TASK_ADVISORY_HINTS = (
    "目标",
    "建议",
    "学习内容",
    "精简版",
    "可拆为",
    "你可以",
    "如果你",
    "即使你",
    "更建议",
    "推荐",
)

PRIORITY_HINTS = {
    "high": ("紧急", "尽快", "马上", "立刻", "今天必须", "必须", "务必", "马上要用"),
    "medium": ("尽量", "安排一个", "这几天"),
    "low": ("有空", "之后", "回头"),
}

EXPLORATION_ONLY_HINTS = (
    "有哪些",
    "学什么",
    "怎么学",
    "介绍",
    "先了解",
    "先看看",
    "是什么",
)

CONSULTATION_HINT_WORDS = (
    "推荐",
    "推荐哪些",
    "哪个好",
    "哪门",
    "怎么选",
    "有必要",
    "值不值得",
)

TASK_INTENT_EXTRA_HINTS = (
    "过一遍",
    "推进",
    "写完",
    "跑通",
    "补齐",
    "备份",
    "打卡",
    "加上",
)

TASK_TITLE_TRIGGER_WORDS = (
    *TASK_HINT_WORDS,
    *ACTIONABLE_HINT_WORDS,
    "提交",
    "上交",
    "复盘",
    "写",
    "补",
    "推进",
    "过一遍",
)

STEP_SPLIT_PATTERN = re.compile(r"(?:\n+|[，。！？；;]|(?:然后|再|接着|最后|并且|并|同时|之后|先))")
STEP_PREFIX_PATTERN = re.compile(
    r"^(?:先|然后|再|接着|最后|并且|并|同时|之后|先把|把|请|帮我|给我|记录|安排|完成)\s*"
)
DAY_HEADER_PATTERN = re.compile(
    r"^(?:[#>*\-\s]*)?(第\s*([0-9一二三四五六七八九十两]+)\s*(?:天|日)|周[一二三四五六日天]|星期[一二三四五六日天]|Day\s*([0-9]+))(?:\s*[:：]\s*(.*))?$",
    re.IGNORECASE,
)
BULLET_PATTERN = re.compile(r"^(?:[-*•]|\d+[.)、])\s*(.+)$")
GOAL_HEADER_PATTERN = re.compile(r"^目标[:：]\s*(.+)$")
TASK_HEADER_PATTERN = re.compile(r"^(?:任务安排|安排|执行安排|今日安排|学习安排)[:：]?\s*$")
TIME_EXPLICIT_PATTERN = re.compile(r"(?<!\d)(\d{1,2})\s*(?:点|:|：)\s*(半|[0-5]?\d分?)?")
TIME_RANGE_PREFIX_PATTERN = re.compile(
    r"^(\d{1,2})\s*(?::|：|点)\s*([0-5]?\d)?\s*(?:分)?\s*[-~—到至]\s*(\d{1,2})\s*(?::|：|点)\s*([0-5]?\d)?\s*(?:分)?"
)

CHINESE_NUMERAL_MAP = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def looks_like_task_request(message: str) -> bool:
    normalized = message.strip()
    if looks_like_consultation_question(normalized):
        return False
    if any(hint in normalized for hint in EXPLORATION_ONLY_HINTS):
        return False
    if any(word in message for word in TASK_HINT_WORDS):
        return True
    if any(word in message for word in TASK_INTENT_EXTRA_HINTS):
        return True
    if any(word in message for word in ACTIONABLE_HINT_WORDS):
        return True
    return any(word in message for word in TIME_HINT_WORDS) and any(
        word in message for word in ("要", "需要", "准备", "背", "复习", "完成")
    )


def looks_like_plan_request(message: str) -> bool:
    if looks_like_consultation_question(message):
        return False
    return any(word in message for word in PLAN_HINT_WORDS)


def looks_like_refinement_request(message: str) -> bool:
    return any(word in message for word in REFINEMENT_HINT_WORDS)


RESOURCE_ENRICHMENT_HINTS = (
    "学习资源",
    "资料",
    "视频",
    "题库",
    "练习题",
    "链接",
    "配上资源",
    "补充资源",
    "推荐资料",
)


def looks_like_resource_enrichment_request(message: str) -> bool:
    normalized = (message or "").strip()
    if not normalized:
        return False
    return any(hint in normalized for hint in RESOURCE_ENRICHMENT_HINTS)


CONTINUATION_HINT_WORDS = (
    "继续",
    "继续帮我",
    "接着",
    "接下来",
    "往下",
    "下一步",
    "再往下",
    "补充",
    "补完",
    "列出其他",
    "其他内容",
    "剩下的内容",
    "后面的内容",
)


def looks_like_continuation_request(message: str) -> bool:
    return any(word in message for word in CONTINUATION_HINT_WORDS)


def infer_priority(message: str) -> str | None:
    for priority, hints in PRIORITY_HINTS.items():
        if any(hint in message for hint in hints):
            return priority
    if looks_like_task_request(message) or looks_like_plan_request(message):
        # 对学习任务场景给出稳定默认值，避免大量空优先级。
        return "medium"
    return None


def determine_fallback_intent(message: str) -> str:
    if looks_like_consultation_question(message):
        return "chat"
    if looks_like_refinement_request(message):
        return "refine_plan"
    if looks_like_plan_request(message):
        return "create_plan"
    if looks_like_task_request(message):
        return "create_task"
    return "chat"


def _clean_fragment(fragment: str) -> str:
    cleaned = re.sub(r"\s+", " ", fragment).strip("，。！？；;:：- ")
    cleaned = STEP_PREFIX_PATTERN.sub("", cleaned).strip()
    return cleaned


def _looks_like_question_sentence(fragment: str) -> bool:
    normalized = (fragment or "").strip()
    if not normalized:
        return False
    if "？" in normalized or "?" in normalized:
        return True
    return bool(
        re.search(
            r"(还是|多少|是否|怎么|如何|能否|可否|行吗|好吗|可以吗|要不要|要么)",
            normalized,
        )
    )


def _should_keep_subtask(fragment: str, title: str | None = None) -> bool:
    if len(fragment) < 2:
        return False
    if _looks_like_question_sentence(fragment):
        return False
    lowered = fragment.lower()
    if any(hint in fragment or hint in lowered for hint in CONVERSATIONAL_NOISE_HINTS):
        return False
    if title and (fragment == title or title in fragment):
        return False
    if fragment in {"学习计划", "复习计划", "任务", "待办", "任务安排"}:
        return False
    return any(word in fragment for word in ACTIONABLE_HINT_WORDS) or bool(
        infer_time_of_day(fragment)
    )


def extract_subtasks_from_message(message: str, title: str | None = None) -> list[str]:
    normalized = message.replace("：", "，").replace(":", "，")
    parts = STEP_SPLIT_PATTERN.split(normalized)
    subtasks: list[str] = []

    for raw_part in parts:
        cleaned = _clean_fragment(raw_part)
        if not _should_keep_subtask(cleaned, title):
            continue
        if cleaned not in subtasks:
            subtasks.append(cleaned[:120])

    return subtasks[:8]


def _parse_day_number(raw_value: str | None) -> int | None:
    if not raw_value:
        return None
    raw_value = raw_value.strip()
    if raw_value.isdigit():
        return int(raw_value)
    if raw_value == "十":
        return 10
    if raw_value.startswith("十"):
        return 10 + CHINESE_NUMERAL_MAP.get(raw_value[1:], 0)
    if raw_value.endswith("十"):
        return CHINESE_NUMERAL_MAP.get(raw_value[0], 0) * 10
    total = 0
    for char in raw_value:
        total += CHINESE_NUMERAL_MAP.get(char, 0)
    return total or None


def infer_plan_date_range(message: str, due_date: datetime | None) -> tuple[date, date]:
    today = date.today()
    if due_date is not None:
        end_date = due_date.date()
        start_date = today if end_date >= today else end_date
        return start_date, end_date

    if "下周" in message:
        days_until_next_monday = (7 - today.weekday()) % 7
        days_until_next_monday = 7 if days_until_next_monday == 0 else days_until_next_monday
        start_date = today + timedelta(days=days_until_next_monday)
        return start_date, start_date + timedelta(days=6)

    if "本周" in message or "这周" in message:
        return today, today + timedelta(days=max(0, 6 - today.weekday()))

    if "明天" in message:
        target = today + timedelta(days=1)
        return target, target

    if "后天" in message:
        target = today + timedelta(days=2)
        return target, target

    return today, today


def infer_time_of_day(text: str) -> tuple[int, int] | None:
    if not text:
        return None

    range_match = TIME_RANGE_PREFIX_PATTERN.search(text)
    if range_match:
        hour = int(range_match.group(1))
        minute = int(range_match.group(2) or "0")
        return _normalize_hour_with_period(text, hour), minute

    match = TIME_EXPLICIT_PATTERN.search(text)
    if match:
        hour = int(match.group(1))
        minute_token = match.group(2) or ""
        minute = 30 if minute_token == "半" else int(re.sub(r"\D", "", minute_token) or "0")
        return _normalize_hour_with_period(text, hour), minute

    if any(word in text for word in ("清晨", "早上", "上午")):
        return 9, 0
    if "中午" in text:
        return 12, 0
    if "下午" in text:
        return 15, 0
    if any(word in text for word in ("晚上", "今晚")):
        return 20, 0
    return None


def _normalize_hour_with_period(text: str, hour: int) -> int:
    if any(word in text for word in ("下午", "晚上", "今晚")) and hour < 12:
        return hour + 12
    if "中午" in text and hour < 11:
        return hour + 12
    return hour


def _strip_time_prefix(line: str) -> str:
    line = TIME_RANGE_PREFIX_PATTERN.sub("", line).strip()
    return re.sub(r"^(?:上午|下午|晚上|今晚|早上|中午)\s*", "", line).strip()


def _is_action_line(line: str) -> bool:
    cleaned = _clean_fragment(line)
    if not cleaned:
        return False
    if TASK_HEADER_PATTERN.match(cleaned):
        return False
    if GOAL_HEADER_PATTERN.match(cleaned):
        return False
    if any(hint in cleaned for hint in NON_TASK_ADVISORY_HINTS):
        return False
    return _should_keep_subtask(cleaned)


def _build_step_payload(
    *,
    title_prefix: str,
    summary_line: str,
    description_lines: list[str],
    day_offset: int,
    time_hint: str,
    phase_title_hint: str | None = None,
) -> dict[str, Any]:
    clean_summary = _clean_fragment(summary_line) or title_prefix
    description = "\n".join(description_lines) if description_lines else clean_summary
    time_value = infer_time_of_day(time_hint or description)
    return {
        "title": f"{title_prefix} · {clean_summary[:48]}"[:80],
        "description": description[:600],
        "day_offset": max(0, day_offset),
        "time_hint": time_hint,
        "hour": time_value[0] if time_value else None,
        "minute": time_value[1] if time_value else None,
        "phase_title_hint": phase_title_hint,
    }


def _clip_subtask_title_theme(text: str, max_len: int = 28) -> str:
    s = re.sub(r"\s+", " ", (text or "").strip())
    s = re.sub(r"^目标[:：]\s*", "", s)
    if not s:
        return ""
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def _theme_for_day_block(goal: str, items: list[str]) -> str:
    g = _clean_fragment(goal) if goal else ""
    g = re.sub(r"^目标[:：]\s*", "", g)
    if g:
        return _clip_subtask_title_theme(g, 28) or "当日安排"
    for raw in items:
        it = _clean_fragment(raw)
        if it and _is_action_line(it):
            return _clip_subtask_title_theme(it, 28)
    return "当日安排"


def _description_for_day_block(goal: str, items: list[str]) -> str:
    parts: list[str] = []
    g = _clean_fragment(goal) if goal else ""
    g = re.sub(r"^目标[:：]\s*", "", g)
    if g:
        parts.append(f"【重点】{g}")
    for raw in items:
        it = _clean_fragment(raw)
        if it and _is_action_line(it):
            parts.append(f"· {it}")
    if not parts and g:
        parts.append(g)
    body = "\n".join(parts) if parts else "（更细的时间与步骤可对照对话。）"
    return body[:2000]


def _day_subtask_title(label: str, goal: str, items: list[str]) -> str:
    theme = _theme_for_day_block(goal, items)
    if theme in {"当日安排", ""}:
        return f"{label}：{theme}"[:80] if theme else f"{label}：学习安排"[:80]
    return f"{label}：{theme}"[:80]


def _ensure_section(
    sections: list[dict[str, Any]],
    current: dict[str, Any] | None,
    *,
    label: str | None = None,
    day_number: int | None = None,
) -> dict[str, Any]:
    if current is not None:
        return current
    sequence = len(sections) + 1
    return {
        "label": label or f"第{sequence}天",
        "day_number": day_number or sequence,
        "goal": "",
        "items": [],
        "time_hint": "",
    }


def extract_day_subtasks_from_reply(reply: str) -> list[dict[str, Any]]:
    normalized = reply.replace("\r\n", "\n")
    lines = [re.sub(r"[*`_]+", "", line).strip() for line in normalized.split("\n")]
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for raw_line in lines:
        line = raw_line.strip(" -•")
        if not line or line in {"---", "——"}:
            continue

        day_match = DAY_HEADER_PATTERN.match(line)
        if day_match:
            if current and (current["goal"] or current["items"]):
                sections.append(current)
            day_number = _parse_day_number(day_match.group(2) or day_match.group(3)) or len(sections) + 1
            current = {
                "label": f"第{day_number}天",
                "day_number": day_number,
                "goal": _clean_fragment(day_match.group(4) or ""),
                "items": [],
                "time_hint": "",
            }
            continue

        goal_match = GOAL_HEADER_PATTERN.match(line)
        if goal_match:
            if current and current["items"]:
                sections.append(current)
                current = None
            current = _ensure_section(sections, current)
            current["goal"] = _clean_fragment(goal_match.group(1))
            continue

        if TASK_HEADER_PATTERN.match(line):
            current = _ensure_section(sections, current)
            continue

        bullet_match = BULLET_PATTERN.match(line)
        content = bullet_match.group(1) if bullet_match else line
        cleaned = _clean_fragment(content)
        if not cleaned:
            continue

        current = _ensure_section(sections, current)
        if cleaned.startswith(("时间", "开始时间", "截止时间")):
            current["time_hint"] = cleaned
            continue

        if _is_action_line(cleaned):
            current["items"].append(cleaned)

    if current and (current["goal"] or current["items"]):
        sections.append(current)

    # One subtask per day; detailed bullets go into the child task's description.
    subtasks: list[dict[str, Any]] = []
    for section in sections:
        day_offset = max(0, int(section["day_number"]) - 1)
        goal = (section.get("goal") or "").strip()
        action_items = [x for x in (section.get("items") or []) if x]
        title = _day_subtask_title(section["label"], goal, action_items)
        description = _description_for_day_block(goal, action_items)
        th = next((x for x in action_items if infer_time_of_day(x)), None) or (section.get("time_hint") or "")
        tval = infer_time_of_day(th or description) if th else None
        subtasks.append(
            {
                "title": title,
                "description": description,
                "day_offset": day_offset,
                "time_hint": th or "",
                "hour": tval[0] if tval else None,
                "minute": tval[1] if tval else None,
                "phase_title_hint": _clean_fragment(goal) or None,
            }
        )

    return subtasks[:14]


def extract_goal_sections_from_reply(reply: str) -> list[dict[str, Any]]:
    normalized = reply.replace("\r\n", "\n")
    lines = [re.sub(r"[*`_]+", "", line).strip() for line in normalized.split("\n")]
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for raw_line in lines:
        line = raw_line.strip(" -•")
        if not line or line in {"---", "——"}:
            continue

        goal_match = GOAL_HEADER_PATTERN.match(line)
        if goal_match:
            if current and (current["goal"] or current["items"]):
                sections.append(current)
            current = {
                "label": f"第{len(sections) + 1}天",
                "day_number": len(sections) + 1,
                "goal": _clean_fragment(goal_match.group(1)),
                "items": [],
                "time_hint": "",
            }
            continue

        if current is None:
            continue

        if TASK_HEADER_PATTERN.match(line):
            continue

        bullet_match = BULLET_PATTERN.match(line)
        content = bullet_match.group(1) if bullet_match else line
        cleaned = _clean_fragment(content)
        if not cleaned:
            continue
        if cleaned.startswith(("时间", "开始时间", "截止时间")):
            current["time_hint"] = cleaned
            continue
        if _is_action_line(cleaned):
            current["items"].append(cleaned)

    if current and (current["goal"] or current["items"]):
        sections.append(current)

    # One subtask per 目标/阶段块；条目汇总到子任务说明里
    subtasks: list[dict[str, Any]] = []
    for section in sections:
        goal = (section.get("goal") or "").strip()
        action_items = [x for x in (section.get("items") or []) if x]
        title = _day_subtask_title(section["label"], goal, action_items)
        description = _description_for_day_block(goal, action_items)
        th = next((x for x in action_items if infer_time_of_day(x)), None) or (section.get("time_hint") or "")
        tval = infer_time_of_day(th or description) if th else None
        subtasks.append(
            {
                "title": title,
                "description": description,
                "day_offset": max(0, int(section["day_number"]) - 1),
                "time_hint": th or "",
                "hour": tval[0] if tval else None,
                "minute": tval[1] if tval else None,
                "phase_title_hint": _clean_fragment(goal) or None,
            }
        )
    return subtasks[:14]


def extract_bullet_subtasks_from_reply(reply: str) -> list[dict[str, Any]]:
    normalized = reply.replace("\r\n", "\n")
    lines = [re.sub(r"[*`_]+", "", line).strip() for line in normalized.split("\n")]
    subtasks: list[dict[str, Any]] = []

    for line in lines:
        bullet_match = BULLET_PATTERN.match(line)
        if not bullet_match:
            continue

        content = _clean_fragment(bullet_match.group(1))
        if not _should_keep_subtask(content):
            continue

        subtasks.append(
            _build_step_payload(
                title_prefix=f"步骤{len(subtasks) + 1}",
                summary_line=_strip_time_prefix(content),
                description_lines=[content],
                day_offset=len(subtasks),
                time_hint=content,
            )
        )

    return subtasks[:20]


def extract_structured_subtasks_from_reply(reply: str) -> list[dict[str, Any]]:
    if not _looks_like_structured_plan_reply(reply):
        return []
    for extractor in (
        extract_day_subtasks_from_reply,
        extract_goal_sections_from_reply,
        extract_bullet_subtasks_from_reply,
    ):
        steps = extractor(reply)
        if steps:
            return steps
    return []


def _looks_like_structured_plan_reply(reply: str) -> bool:
    normalized = (reply or "").strip()
    if not normalized:
        return False
    if DAY_HEADER_PATTERN.search(normalized):
        return True
    if GOAL_HEADER_PATTERN.search(normalized) or TASK_HEADER_PATTERN.search(normalized):
        return True
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    bullet_lines = sum(1 for line in lines if BULLET_PATTERN.match(line))
    if bullet_lines >= 2:
        return True
    # 至少两条“时间 + 动作”行才允许抽取，避免把普通对话句误当任务。
    timed_action_lines = sum(
        1
        for line in lines
        if infer_time_of_day(line) and any(word in line for word in ACTIONABLE_HINT_WORDS)
    )
    return timed_action_lines >= 2


def build_fallback_entities(message: str) -> dict[str, Any]:
    cleaned = re.sub(r"\s+", " ", message).strip("，。！？?! ")
    title = cleaned

    fragments = re.split(r"[，。！？]", cleaned, maxsplit=1)
    if fragments and fragments[0].strip():
        title = fragments[0].strip()

    title = re.sub(r"^(帮我|请|麻烦你|记得|提醒我|帮忙|给我)", "", title).strip()
    title = re.sub(r"^(有空(?:的时候)?|回头|之后)\s*(?:把)?", "", title).strip()
    title = re.sub(r"^(?:今天|明天|后天|今晚|今早|明晚|晚上|下午|上午|早上)\s*(?:把)?", "", title).strip()
    title = re.sub(r"(然后|并且).*$", "", title).strip()
    title = _compact_entity_title(title) or _compact_entity_title(cleaned)
    title = title[:36].strip() or cleaned[:36].strip()

    entities: dict[str, Any] = {
        "description": message.strip(),
    }

    if looks_like_plan_request(message):
        plan_title = title.replace("计划", "").strip()
        entities["plan_title"] = (plan_title or title)[:60]
        entities["plan_description"] = message.strip()

    if (
        looks_like_task_request(message)
        or "记录" in message
        or "任务" in message
        or any(word in message for word in TASK_TITLE_TRIGGER_WORDS)
    ):
        entities["task_title"] = title[:60]

    priority = infer_priority(message)
    if priority:
        entities["priority"] = priority

    subtasks = extract_subtasks_from_message(
        message,
        entities.get("task_title") or entities.get("plan_title"),
    )
    if subtasks:
        entities["subtasks"] = subtasks

    entities["should_create_task"] = looks_like_task_request(message) and looks_like_plan_request(
        message
    )
    entities["wants_refinement"] = looks_like_refinement_request(message)
    return entities


def _compact_entity_title(raw: str) -> str:
    title = (raw or "").strip()
    if not title:
        return ""
    if _looks_like_question_sentence(title):
        return ""
    title = re.sub(r"(你推荐哪些|推荐哪些|有哪些|怎么学|怎么安排|可以吗|行吗|好吗|吧)$", "", title).strip()
    title = re.sub(r"(一起|帮我一起|顺便|先|再|然后).*$", "", title).strip()
    title = re.sub(r"[？?！!。,.，；;：:]+$", "", title).strip()
    return title


PLAN_CLARIFICATION_ANSWER_HINTS = (
    "每天",
    "每周",
    "小时",
    "分钟",
    "先从",
    "先学",
    "优先",
    "晚上",
    "上午",
    "下午",
    "周末",
    "工作日",
    "提醒",
    "开始",
    "投入",
)

PLAN_EXPLORATION_HINTS = (
    "有哪些课程",
    "学什么",
    "怎么学",
    "从哪里开始",
    "先了解",
    "先看看",
    "介绍一下",
    "课程有哪些",
)

BROAD_LEARNING_GOAL_PATTERNS = (
    re.compile(r"我想.*学"),
    re.compile(r"想在.+内.*学"),
    re.compile(r"系统学"),
    re.compile(r"开始学"),
    re.compile(r"入门"),
)


def needs_plan_clarification(
    message: str,
    entities: dict[str, Any],
    recent_context: dict[str, Any] | None = None,
) -> bool:
    if recent_context and recent_context.get("plan_id"):
        return False
    if entities.get("refine_existing"):
        return False
    if entities.get("subtasks"):
        return False
    if entities.get("should_create_task"):
        return False
    if looks_like_task_request(message):
        # 明确包含可执行动作时优先直接落地任务/计划，减少无效澄清。
        return False
    if any(hint in message for hint in PLAN_CLARIFICATION_ANSWER_HINTS):
        return False
    if any(word in message for word in TIME_HINT_WORDS):
        return False
    if any(word in message for word in ("今天", "明天", "后天", "下周", "本周", "这周")):
        return False
    if any(word in message for word in ("第1天", "第2天", "第一天", "第二天")):
        return False
    if looks_like_plan_request(message) or "想学" in message or "学习" in message:
        return True
    return any(pattern.search(message) for pattern in BROAD_LEARNING_GOAL_PATTERNS)


def build_plan_clarification_question(message: str, entities: dict[str, Any]) -> str:
    topic = entities.get("plan_title") or entities.get("task_title") or "这次学习目标"
    if any(hint in message for hint in PLAN_EXPLORATION_HINTS):
        return (
            f"可以，我们先别急着直接排计划。围绕“{topic}”，你现在更想先解决哪一步："
            "先了解课程结构，还是直接开始做第一周学习安排？"
        )
    return (
        f"这件事我可以陪你一起往下做，不过我先不急着直接给整套计划。"
        f"先确认一个关键点：围绕“{topic}”，你是想先理清学习范围，还是直接开始安排第一周任务？"
    )


def looks_like_plan_follow_up_answer(message: str) -> bool:
    if any(hint in message for hint in PLAN_CLARIFICATION_ANSWER_HINTS):
        return True
    return bool(infer_time_of_day(message))


def looks_like_consultation_question(message: str) -> bool:
    normalized = (message or "").strip()
    if not normalized:
        return False
    if any(hint in normalized for hint in EXPLORATION_ONLY_HINTS):
        return True
    if any(hint in normalized for hint in CONSULTATION_HINT_WORDS):
        return True
    return "？" in normalized or "?" in normalized
