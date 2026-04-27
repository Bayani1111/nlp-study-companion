from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import date, datetime, time, timedelta, timezone
from inspect import isawaitable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatMessage, ChatSession, User
from app.services import plan_service, task_service
from app.services.chat_guidance_templates import (
    build_clarify_quick_replies,
    build_force_clarify_next_prompt,
    build_force_clarify_reply,
    build_initial_choice_prompt,
)
from app.services.chat_prompts import build_companion_prompt
from app.services.chat_rule_parser import extract_structured_subtasks_from_reply
from app.services.chat_session_service import (
    get_or_create_session,
    load_history,
    load_structured_history,
    save_message,
)
from app.services.chat_task_orchestrator import (
    execute_intent,
    resolve_intent,
    should_clarify_before_action,
)
from app.services.llm_adapter import call_llm_api
from app.services.nlp_parser import call_llm_for_intent
from app.services.stats_service import record_learning_activity

logger = logging.getLogger(__name__)

PLAN_CLARIFY_PATTERNS = (
    re.compile(r"我想.*学"),
    re.compile(r"想在.+内.*学"),
    re.compile(r"系统学"),
    re.compile(r"开始学"),
    re.compile(r"开始.*学"),
    re.compile(r"学一下"),
    re.compile(r"准备.*考试"),
    re.compile(r".+考试"),
    re.compile(r"入门"),
)

PLAN_DIRECT_BUILD_HINTS = (
    "学习计划",
    "复习计划",
    "第1天",
    "第一天",
    "每天",
    "上午",
    "下午",
    "晚上",
    "提醒",
    "截止",
    "到几点",
)

PENDING_PLAN_MAX_TURNS = 3
PENDING_PLAN_MAX_MINUTES = 20

LEARNING_GOAL_TYPE_PATTERNS = {
    "exam_prep": (
        "考试",
        "测验",
        "期中",
        "期末",
        "冲刺",
        "复习",
        "刷题",
        "备考",
    ),
    "course_exploration": (
        "课程",
        "科目",
        "学科",
        "章节",
        "课程结构",
        "知识点",
        "大纲",
    ),
    "skill_building": (
        "技能",
        "项目",
        "实战",
        "练习",
        "作品集",
        "论文",
        "科研",
        "实验",
        "报告",
        "写作",
        "演讲",
        "口语",
        "英语",
        "求职",
        "面试",
        "简历",
        "实习",
        "竞赛",
        "编程",
        "写代码",
        "python",
        "java",
        "c++",
        "算法",
        "开发",
    ),
}

PLAN_COMMIT_HINTS = (
    "加入计划",
    "保存计划",
    "按这个计划",
    "就按这个",
    "确认计划",
    "开始执行这个计划",
    "生成对应任务",
    "落到任务",
)

PLAN_PROPOSAL_QUERY_HINTS = (
    "推荐",
    "推荐哪些",
    "有哪些",
    "怎么学",
    "怎么安排",
    "先学哪门",
    "哪个好",
    "是否",
)

PLAN_CYCLE_SUFFIX_CONFIG: list[tuple[tuple[str, ...], str]] = [
    (("14天", "两周", "2周", "两星期", "14-day"), "两周版"),
    (("冲刺", "考前", "临考", "最后", "压轴"), "冲刺版"),
]
PLAN_CYCLE_DEFAULT_SUFFIX = "一周版"


def _build_action_prefix(intent: str, action_result: Any) -> str:
    if intent == "create_task" and action_result:
        child_count = len(getattr(action_result, "children", []) or [])
        if child_count:
            return f"已帮你创建主任务：{action_result.title}，并拆成了 {child_count} 个子任务。"
        return f"已帮你创建任务：{action_result.title}"

    if intent in {"create_plan", "refine_plan"} and isinstance(action_result, dict):
        plan = action_result.get("plan")
        task = action_result.get("task")
        if plan and task:
            child_count = len(getattr(task, "children", []) or [])
            pt = _display_title_short(getattr(plan, "title", None))
            tt = _display_title_short(getattr(task, "title", None))
            if intent == "refine_plan":
                if child_count:
                    return (
                        f"已在「{pt}」下继续细化主任务「{tt}」，"
                        f"并生成了 {child_count} 个子项（按天或阶段汇总在子任务中）。"
                    )
                return f"已在「{pt}」下继续细化主任务「{tt}」。"

            if child_count:
                return (
                    f"已创建计划「{pt}」，主任务「{tt}」已挂到该计划，"
                    f"并拆出 {child_count} 条子项；每日细节在子任务中查看即可。"
                )
            return f"已创建计划「{pt}」，主任务「{tt}」已挂进该计划。"
        if plan:
            return f"已创建计划「{_display_title_short(getattr(plan, 'title', None))}」。"

    return ""


def _log_chat_orchestration(event: str, **payload: Any) -> None:
    safe_payload = {
        key: value
        for key, value in payload.items()
        if isinstance(value, (str, int, float, bool, type(None), list, dict))
    }
    logger.info(
        "chat_orchestration_event=%s payload=%s",
        event,
        json.dumps(safe_payload, ensure_ascii=False),
    )


def _attach_orchestration_diagnostics(
    base_entities: dict[str, Any],
    *,
    event: str,
    summary: str,
    **details: Any,
) -> dict[str, Any]:
    payload = dict(base_entities)
    payload["orchestration_diagnostics"] = {
        "event": event,
        "summary": summary,
        "details": {key: value for key, value in details.items() if value is not None},
        "recorded_at": datetime.utcnow().isoformat(),
    }
    return payload


def _extract_recent_action_context(structured_history: list[dict[str, Any]]) -> dict[str, Any]:
    context: dict[str, Any] = {}
    for item in reversed(structured_history):
        entities = item.get("entities") or {}

        if not context.get("pending_plan_request") and entities.get("pending_plan_request"):
            context["pending_plan_request"] = entities["pending_plan_request"]

        if not context.get("plan_id"):
            extracted_plans = entities.get("extracted_plans") or []
            if extracted_plans:
                context["plan_id"] = extracted_plans[0].get("id")
                context["plan_title"] = extracted_plans[0].get("title")
            elif entities.get("plan_id"):
                context["plan_id"] = entities.get("plan_id")
                context["plan_title"] = entities.get("plan_title")

        if not context.get("task_id"):
            extracted_tasks = entities.get("extracted_tasks") or []
            root_task = next(
                (task for task in extracted_tasks if not task.get("parent_task_id")),
                None,
            )
            if root_task:
                context["task_id"] = root_task.get("id")
                context["task_title"] = root_task.get("title")
                context["plan_id"] = context.get("plan_id") or root_task.get("plan_id")
            elif entities.get("task_id"):
                context["task_id"] = entities.get("task_id")
                context["task_title"] = entities.get("task_title")

        if context.get("plan_id") and context.get("task_id"):
            break
    return context


def _extract_pending_action_proposal(
    structured_history: list[dict[str, Any]],
    proposal_id: str | None = None,
) -> dict[str, Any] | None:
    for item in reversed(structured_history):
        entities = item.get("entities") or {}
        if "pending_action_proposal" not in entities:
            continue
        proposal = entities.get("pending_action_proposal")
        if not isinstance(proposal, dict):
            return None
        if proposal_id and str(proposal.get("proposal_id")) != proposal_id:
            continue
        return proposal
        return None
    return None


async def _load_pending_action_proposal_from_db(
    session_id: int,
    db: AsyncSession,
    proposal_id: str | None = None,
) -> dict[str, Any] | None:
    stmt = (
        select(ChatMessage.entities_json)
        .where(ChatMessage.session_id == session_id, ChatMessage.role == "assistant")
        .order_by(ChatMessage.id.desc())
        .limit(200)
    )
    result = await db.execute(stmt)
    scalar_result = result.scalars()
    if isawaitable(scalar_result):
        scalar_result = await scalar_result
    raw_rows = scalar_result.all() if hasattr(scalar_result, "all") else []
    if isawaitable(raw_rows):
        raw_rows = await raw_rows
    if not isinstance(raw_rows, list):
        return None
    for raw_entities in raw_rows:
        if not raw_entities:
            continue
        try:
            parsed = json.loads(raw_entities)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        proposal = parsed.get("pending_action_proposal")
        if not isinstance(proposal, dict):
            continue
        if proposal_id and str(proposal.get("proposal_id")) != proposal_id:
            continue
        return proposal
    return None


def _is_plan_commit_request(message: str) -> bool:
    normalized = message.strip()
    return any(hint in normalized for hint in PLAN_COMMIT_HINTS)


def _should_stage_plan_proposal(intent: str, message: str) -> bool:
    if intent not in {"create_plan", "refine_plan"}:
        return False
    normalized = message.strip()
    if _is_plan_commit_request(normalized):
        return False
    if intent == "create_plan":
        # 新计划统一先走草案预览，避免未经确认直接落库。
        return True
    # refine_plan 仅在明显咨询/问句时先预览，明确执行意图可直接细化。
    if "?" in normalized or "？" in normalized:
        return True
    return any(hint in normalized for hint in PLAN_PROPOSAL_QUERY_HINTS)


async def _hydrate_recent_action_context(
    user_id: int,
    raw_context: dict[str, Any],
    db: AsyncSession,
) -> dict[str, Any]:
    context = dict(raw_context)
    pending_plan_request = context.get("pending_plan_request")

    if context.get("task_id") and not context.get("task_title"):
        task = await task_service.get_task(user_id, int(context["task_id"]), db)
        context["task_title"] = task.title
        context["plan_id"] = context.get("plan_id") or task.plan_id

    if context.get("plan_id") and not context.get("plan_title"):
        plan = await plan_service.get_owned_plan(int(context["plan_id"]), user_id, db)
        context["plan_title"] = plan.title

    if pending_plan_request:
        return {key: value for key, value in context.items() if value is not None}

    if not context.get("plan_id"):
        plans = await plan_service.list_plans(user_id, db)
        if plans:
            context["plan_id"] = plans[0].id
            context["plan_title"] = plans[0].title

    if context.get("plan_id") and not context.get("task_id"):
        tasks = await task_service.list_tasks(user_id, db)
        matching_task = next((task for task in tasks if task.plan_id == context["plan_id"]), None)
        if matching_task:
            context["task_id"] = matching_task.id
            context["task_title"] = matching_task.title

    return {key: value for key, value in context.items() if value is not None}


def _build_subtask_due_datetime(
    *,
    base_date: datetime,
    day_offset: int,
    hour: int | None,
    minute: int | None,
) -> tuple[datetime, date]:
    target_date = (base_date + timedelta(days=day_offset)).date()
    target_hour = hour if hour is not None else 20
    target_minute = minute if minute is not None else 0
    due_date = datetime.combine(target_date, time(hour=target_hour, minute=target_minute))
    return due_date, target_date


def _pick_phase_id(
    plan: Any | None,
    *,
    step: dict[str, Any],
    target_date: date,
) -> int | None:
    if plan is None:
        return None

    phases = getattr(plan, "phases", []) or []
    for phase in phases:
        if (
            phase.start_date
            and phase.end_date
            and phase.start_date <= target_date <= phase.end_date
        ):
            return int(phase.id)

    phase_title_hint = (step.get("phase_title_hint") or "").strip()
    if phase_title_hint:
        for phase in phases:
            if phase.title and phase.title in phase_title_hint:
                return int(phase.id)
    return None


def _count_root_and_child_tasks(extracted_tasks: list[dict[str, Any]] | None) -> tuple[int, int]:
    tasks = extracted_tasks or []
    root_count = len([task for task in tasks if not task.get("parent_task_id")])
    child_count = len([task for task in tasks if task.get("parent_task_id")])
    return root_count, child_count


def _build_sync_summary(
    extracted_tasks: list[dict[str, Any]] | None,
    extracted_plans: list[dict[str, Any]] | None,
) -> str | None:
    plan_count = len(extracted_plans or [])
    root_count, child_count = _count_root_and_child_tasks(extracted_tasks)

    parts: list[str] = []
    if plan_count:
        parts.append(f"{plan_count} 个学习计划")
    if root_count:
        parts.append(f"{root_count} 个主任务")
    if child_count:
        parts.append(f"{child_count} 个子任务")

    if not parts:
        return None
    return f"这轮已经同步到任务系统：{'、'.join(parts)}。"


def _build_pending_plan_entities(
    *,
    message: str,
    entities: dict[str, Any],
    stage: str = "initial_choice",
    answers: dict[str, Any] | None = None,
    turn_count: int | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    now_iso = datetime.utcnow().isoformat()
    return {
        "pending_plan_request": {
            "message": message,
            "stage": stage,
            "answers": answers or {},
            "turn_count": turn_count if isinstance(turn_count, int) and turn_count >= 0 else 0,
            "created_at": created_at or now_iso,
            "entities": {
                "plan_title": entities.get("plan_title"),
                "plan_description": entities.get("plan_description")
                or entities.get("description")
                or message,
                "task_title": entities.get("task_title") or entities.get("plan_title"),
                "priority": entities.get("priority"),
                "should_create_task": entities.get("should_create_task"),
                "goal_type": entities.get("goal_type"),
            },
        }
    }


GUIDANCE_OVERVIEW_HINTS = (
    "先了解",
    "先理清",
    "先梳理",
    "先看看",
    "先认识一下",
    "先介绍",
    "先弄清",
    "先摸清",
    "课程结构",
    "考试范围",
    "学习路径",
    "有哪些课",
    "学什么",
    "从哪里开始",
)

GUIDANCE_SCHEDULE_HINTS = (
    "直接开始",
    "直接安排",
    "开始安排",
    "排计划",
    "排一下",
    "第一周",
    "这周",
    "本周",
    "先做计划",
    "先排",
    "可以开始",
    "直接学",
)

COURSE_FOCUS_KEYWORDS = (
    "数学",
    "英语",
    "语文",
    "政治",
    "历史",
    "物理",
    "化学",
    "生物",
    "经济",
    "管理",
    "写作",
    "阅读",
    "听力",
    "口语",
)

SKILL_DIRECTION_KEYWORDS = (
    "基础",
    "刷题",
    "做题",
    "项目",
    "实战",
    "小项目",
    "案例",
    "练习",
)

TIME_BUDGET_PATTERN = re.compile(
    r"((?:每天|每晚|晚上|周末)?[^，。；\n]{0,8}(?:半小时|\d+(?:\.\d+)?小时|\d+分钟|一小时|两小时|三小时|四小时))"
)


def _should_force_clarify_plan(message: str, recent_context: dict[str, Any]) -> bool:
    if recent_context.get("pending_plan_request"):
        return False
    if any(hint in message for hint in PLAN_DIRECT_BUILD_HINTS):
        return False
    return any(pattern.search(message) for pattern in PLAN_CLARIFY_PATTERNS)


def _should_reset_recent_context(message: str) -> bool:
    normalized = (message or "").strip().lower()
    if not normalized:
        return False
    reset_markers = (
        "换个",
        "另外",
        "重新",
        "改成",
        "不要这个",
        "不是这个",
        "新计划",
        "新的计划",
        "另一个",
    )
    return any(marker in normalized for marker in reset_markers)
    if any(hint in message for hint in PLAN_DIRECT_BUILD_HINTS):
        return False
    goal_type = _classify_learning_goal(message)
    if goal_type in {"course_exploration", "exam_prep", "skill_building"}:
        return True
    return any(pattern.search(message) for pattern in PLAN_CLARIFY_PATTERNS)


def _classify_learning_goal(message: str) -> str:
    lowered = message.lower()
    for goal_type, hints in LEARNING_GOAL_TYPE_PATTERNS.items():
        if any(hint in lowered or hint in message for hint in hints):
            return goal_type
    return "general_learning"


def _scenario_label(goal_type: str) -> str:
    mapping = {
        "exam_prep": "考试备考",
        "course_exploration": "课程学习",
        "skill_building": "技能提升",
        "general_learning": "通用学习",
    }
    return mapping.get(goal_type, "通用学习")


def _normalize_title_text(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", (value or "")).strip("，。！？?!：:;；- ")
    return cleaned[:36]


# Strip conversational openers that should never become plan/task titles
_TITLE_LEADING_JUNK = re.compile(
    r"^(?:好的|嗯|对|行|ok|OK|那|我们|你|我|可以|如果|所以|"
    r"关于|针对|这版|这|这个|这回合|来|来，|来,|来：|"
    r"明白了|知道啦|好哒|当然|收到)[，,。！？!?\s：:\"'「」*【】\d]*"
)
_EXPLICIT_ACK_PREFIX = re.compile(r"^明白了[！!。…,，\s]+")


def _strip_chinese_filler_leading(value: str) -> str:
    t = (value or "").replace("\n", " ").strip()
    for _ in range(8):
        m = _TITLE_LEADING_JUNK.match(t)
        if m:
            t = t[m.end() :].lstrip(" ，。、…\t")
            continue
        m2 = _EXPLICIT_ACK_PREFIX.match(t)
        if m2:
            t = t[m2.end() :].lstrip(" ，。、…\t")
            continue
        break
    return t


def _clean_title_candidate(value: str) -> str:
    t = _strip_chinese_filler_leading(value or "")
    return _normalize_title_text(t) or (t[:40] if t else "")


def _is_question_like_text(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    if "？" in text or "?" in text:
        return True
    return bool(re.search(r"(还是|多少|是否|怎么|如何|能否|可否|行吗|好吗|可以吗|要不要)", text))


def _extract_goal_title_from_source_message(message: str) -> str | None:
    normalized = re.sub(r"\s+", " ", (message or "").strip())
    if not normalized:
        return None
    chunks = [x.strip() for x in re.split(r"[，。；;！!\n]", normalized) if x.strip()]
    generic_blacklist = (
        "列个计划",
        "做个计划",
        "安排计划",
        "帮我计划",
        "就帮我",
        "给我一个计划",
        "来个计划",
        "一个计划吧",
        "计划吧",
    )
    best: str | None = None
    best_score = -1
    for raw in chunks:
        clause = _strip_chinese_filler_leading(raw)
        clause = re.sub(
            r"^(?:我想|我想要|我要|想要|想|希望|准备|打算|计划|请|帮我|麻烦你|能不能|可不可以|下周有个)\s*",
            "",
            clause,
        )
        clause = re.sub(r"^(?:列个|做个|做一份|安排一个|安排一份)\s*", "", clause)
        clause = clause.strip("：:，。 ")
        if len(clause) < 3 or _is_question_like_text(clause):
            continue
        if any(token in clause for token in generic_blacklist):
            continue
        if re.fullmatch(r"(?:学习|复习|备考)?计划", clause):
            continue
        score = 0
        # Prefer clauses with concrete domain objects and outcomes.
        if re.search(
            r"(英语|高数|数学|线代|概率|物理|化学|生物|历史|政治|经济|管理|论文|实验|报告|项目|实习|面试|简历|口语|听力|阅读|背单词|考试|测试|期中|期末)",
            clause,
        ):
            score += 5
        if re.search(r"(准备|冲刺|提升|通过|完成|入门|强化|复习|背|训练|练习)", clause):
            score += 2
        if re.search(r"(计划|复习|备考|课程|项目|论文|实习|面试|英语|考试|测试)", clause):
            score += 3
        if re.search(r"(第[一二三四五六七八九十0-9]+天|Day\s*\d)", clause, re.I):
            score -= 2
        if re.search(r"(帮我|给我|你|我们|一下|吧)$", clause):
            score -= 3
        if len(clause) <= 24:
            score += 1
        # Generic fallback-like wording should lose to concrete goals.
        if re.search(r"(就|先)?(?:列|做|安排).{0,4}计划", clause):
            score -= 4
        if score > best_score:
            best_score = score
            best = clause
    if not best:
        return None
    compact = _clean_title_candidate(best)
    if compact and not _is_question_like_text(compact) and not _is_day_scoped_title(compact):
        return compact
    return None


def _standardize_plan_title_core(title: str, source_message: str) -> str:
    core = _clean_title_candidate(title or "")
    if not core or _is_question_like_text(core) or _is_day_scoped_title(core):
        core = _extract_goal_title_from_source_message(source_message) or "学习任务"

    core = re.sub(r"\s+", " ", core).strip("，。；;：: ")
    core = re.sub(r"(?:方案草案|草案|安排)$", "", core).strip()
    core = re.sub(r"(?:学习)?计划计划$", "学习计划", core)

    # Prefer "对象+目标" wording; if too generic, fallback to source-derived goal.
    if core in {"学习任务", "学习", "计划", "学习计划"}:
        fallback = _extract_goal_title_from_source_message(source_message)
        if fallback:
            core = fallback

    has_goal_word = bool(re.search(r"(计划|备考|复习|冲刺|准备|提升|训练|学习)", core))
    if not has_goal_word:
        core = f"{core}学习计划"
    elif not re.search(r"计划$", core) and re.search(
        r"(备考|复习|冲刺|准备|提升|训练|学习)$", core
    ):
        core = f"{core}计划"

    return _clip_for_storage(core, 36) or "学习计划"


def _standardize_task_title_from_plan_core(plan_core: str) -> str:
    task = (plan_core or "").strip()
    task = re.sub(r"(学习)?计划$", "", task).strip("：:，。 ")
    task = re.sub(r"(?:方案|草案)$", "", task).strip("：:，。 ")
    if len(task) < 2:
        task = (plan_core or "学习任务").strip()
    return _clip_for_storage(task, 28) or "学习任务"


def _clip_for_storage(value: str, max_len: int) -> str:
    s = (value or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def _first_brief_line_for_plan_stored_text(block: str) -> str | None:
    """首段概要：给计划/主任务用，不要整段贴成对话复制品。"""
    for raw in (block or "").splitlines():
        line = _strip_chinese_filler_leading(raw.strip())
        if not line or line in {"---", "——", "---"}:
            continue
        if re.match(r"^#{1,4}\s", line) or re.match(r"^第[一二三四五六七八九十0-9０-９]+天", line):
            continue
        if re.match(r"^Day\s*\d", line, re.I):
            continue
        if re.match(r"^好[，,。!！]", line) or "我已经" in line[:16] or "按你" in line[:5]:
            continue
        if "以下为你" in line or "草案" in line[:4]:
            continue
        if any(x in line for x in ("复习总", "总策略", "如果你", "需要我", "下一步", "本计划已按")):
            continue
        if len(line) < 5:
            continue
        if _is_day_scoped_title(line):
            continue
        return _clip_for_storage(line, 220)
    return None


def _build_root_plan_and_task_brief(
    full_text: str,
    *,
    day_count: int,
) -> str:
    """主任务/计划卡片上只放要点；按天细项在子任务里。"""
    line = _first_brief_line_for_plan_stored_text(full_text)
    if day_count and day_count >= 1:
        head = f"本计划已按 {day_count} 天拆成子任务。每天只保留一条主条目，时间轴与细项在对应子任务中查看；下方为总览。"
    else:
        head = "学习安排概要。更细的拆步见子任务或聊天原文。"
    body = (
        line
        or _clip_for_storage((full_text or "").strip().replace("\n", " "), 400)
        or "（可回到对话中查看完整稿。）"
    )
    return _clip_for_storage(f"{head}\n{body}", 2000) or (body or "")


def _display_title_short(name: str | None, max_len: int = 24) -> str:
    t = (name or "").strip() or "当前任务"
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def _strip_title_emojis(value: str) -> str:
    t = re.sub(r"^[\s🗓️📅✅📝📚⭐]+", "", (value or "").strip())
    t = t.lstrip("|-:： ")
    return t


def _is_day_scoped_title(name: str) -> bool:
    """「第N天|…」等应作为子任务/按天项，不能当作整段计划/主任务总标题。"""
    t = _strip_title_emojis(name)
    t = t.replace(" ", "")
    if re.search(r"第[一二三四五六七八九十0-9０-９]+天", t):
        return True
    if re.match(r"^Day\d", t, re.I) or re.match(r"^Day\s*\d", t, re.I):
        return True
    if "今晚" in t and "天" in t and len(t) < 28:
        return True
    if "｜" in t or "|" in t:
        if "第" in t or ("天" in t and "周" not in t):
            return True
    return False


def _finalize_extracted_name_fragment(raw: str) -> str | None:
    s = re.sub(r"[*_`#]+", "", (raw or "").strip())
    s = s.strip(" ·•")
    s = _strip_chinese_filler_leading(s)
    if s:
        s = _clip_for_storage(s, 64)
    if not s or len(s) < 2:
        return None
    return _clean_title_candidate(s) or s[:36]


def _score_bracket_title_candidate(
    name: str,
    *,
    context_before: str,
) -> int:
    s = (name or "").strip()
    if not s or _is_day_scoped_title(s):
        return -100
    score = 0
    if re.search(
        r"(阶段|备考|计划|复习|周次|模考|基础|强化|冲刺|课程|项目|论文|实习|求职|语言)", s
    ):
        score += 4
    if "主任务" in context_before[-30:]:
        score += 5
    if "计划" in context_before[-20:]:
        score += 2
    if 3 <= len(s) <= 40:
        score += 1
    if re.match(r"^第[一二三四五六七八九十]+[章节回轮]", s):
        score += 2
    return score


def _extract_explicit_plan_title(proposal_text: str) -> str | None:
    """
    从方案全文抽取「要落库时用的计划/主任务名」：显式书名号【】、「」及「主任务」后的命名优先于首行泛读。
    适用于各场景，不依赖某类考试关键词。
    """
    text = re.sub(r"\*+", "", (proposal_text or "").replace("\r", ""))
    if not text.strip():
        return None

    priority_patterns = (
        r"主任务\s*[：:是为]?\s*【\s*([^】\n]+)】",
        r"主任务\s*[：:是为]?\s*「\s*([^」\n]+)」",
        r"(?:学习)?计划\s*[：:名为是为]?\s*【\s*([^】\n]+)】",
        r"(?:正式)?\s*帮?\s*你\s*(?:创建|生成)\s*[：:是为]?\s*主任务\s*[：:是为]?\s*【\s*([^】\n]+)】",
        r"创建\s*主任务\s*【\s*([^】\n]+)】",
    )
    for pat in priority_patterns:
        m = re.search(pat, text)
        if m:
            cand = _finalize_extracted_name_fragment(m.group(1))
            if cand and not _is_day_scoped_title(cand):
                return cand

    matches = list(re.finditer(r"【([^】\n]+)】", text))
    best: str | None = None
    best_score = 0
    for m in matches:
        start = m.start()
        before = text[max(0, start - 50) : start]
        cand = _finalize_extracted_name_fragment(m.group(1))
        if not cand:
            continue
        sc = _score_bracket_title_candidate(cand, context_before=before)
        if sc > best_score:
            best_score, best = sc, cand

    if best and best_score > 0:
        return best

    for m in reversed(matches):
        cand = _finalize_extracted_name_fragment(m.group(1))
        if cand and not _is_day_scoped_title(cand) and not re.search(r"^(?:草案|下|版)$", cand):
            return cand

    m = re.search(r"主任务[：:是为]?\s*「\s*([^」\n]{2,48})」", text)
    if m:
        cand = _finalize_extracted_name_fragment(m.group(1))
        if cand and not _is_day_scoped_title(cand):
            return cand
    return None


def _extract_plan_summary_from_proposal(proposal_text: str) -> str | None:
    lines = [line.strip(" -*•") for line in (proposal_text or "").splitlines() if line.strip()]
    for raw in lines:
        line = _strip_chinese_filler_leading(raw)
        if re.match(r"^好[，,。!！]", line) or "我已经按" in line[:20] or "按你" in line[:6]:
            continue
        if "以下为你" in line or "以下这份" in line or line.strip().startswith("草案"):
            continue
        line = _strip_title_emojis(line)
        if re.match(r"^第[一二三四五六七八九十0-9０-９]+天", line) or re.match(
            r"^Day\s*\d", line, re.I
        ):
            continue
        if _is_day_scoped_title(line):
            continue
        if line.startswith(("目标", "任务", "🗓", "D1", "D2")):
            continue
        if len(line) < 4:
            continue
        if any(
            marker in line
            for marker in (
                "学习计划",
                "学习方案",
                "详细计划",
                "下一步",
                "如果你觉得",
                "我们可以",
                "已确认",
                "确认方向",
            )
        ):
            continue
        cleaned = _clean_title_candidate(line)
        if len(cleaned) >= 3:
            return cleaned
    return None


def _build_commit_entities_from_proposal(
    *,
    proposal: dict[str, Any],
    fallback_message: str,
) -> tuple[dict[str, Any], str]:
    entities = dict(proposal.get("entities") or {})
    proposal_text = str(proposal.get("proposal_reply") or "").strip()
    source_message = str(proposal.get("source_message") or fallback_message).strip()
    effective_message = proposal_text or source_message

    summary_title = (
        _extract_explicit_plan_title(effective_message)
        or _extract_goal_title_from_source_message(source_message)
        or _extract_plan_summary_from_proposal(effective_message)
        or _clean_title_candidate(source_message)
    )
    if _is_question_like_text(summary_title or ""):
        summary_title = _extract_goal_title_from_source_message(source_message) or "学习任务"
    cycle_suffix = _detect_cycle_suffix(effective_message)
    if summary_title:
        plan_core = _standardize_plan_title_core(summary_title, source_message)
        task_core = _standardize_task_title_from_plan_core(plan_core)
        has_version_suffix = bool(re.search(r"[（(][^）)]*版[^）)]*[)）]", summary_title))
        if not has_version_suffix:
            entities["plan_title"] = f"{plan_core}（{cycle_suffix}）"
        else:
            entities["plan_title"] = plan_core
        entities["task_title"] = task_core
    elif source_message:
        fallback_core = _standardize_plan_title_core(source_message, source_message)
        entities["plan_title"] = f"{fallback_core}（{cycle_suffix}）"
        entities["task_title"] = _standardize_task_title_from_plan_core(fallback_core)

    steps = extract_structured_subtasks_from_reply(effective_message)
    day_count = len(steps) if steps else 0
    if day_count:
        entities["plan_day_span"] = day_count
    root_brief = _build_root_plan_and_task_brief(effective_message, day_count=day_count)
    entities["plan_description"] = root_brief
    entities["description"] = root_brief
    entities["should_create_task"] = True

    if steps:
        cleaned_subtasks: list[dict[str, str]] = []
        for step in steps[:14]:
            title = str(step.get("title") or "").strip()
            description = str(step.get("description") or "").strip()
            if not title or _is_question_like_text(title):
                continue
            if _is_day_scoped_title(title) and _is_question_like_text(description):
                continue
            cleaned_subtasks.append({"title": title, "description": description})
        if cleaned_subtasks:
            entities["subtasks"] = cleaned_subtasks

    return entities, effective_message


def _detect_cycle_suffix(text: str) -> str:
    normalized = (text or "").lower()
    for hints, suffix in PLAN_CYCLE_SUFFIX_CONFIG:
        if any(hint.lower() in normalized for hint in hints):
            return suffix
    return PLAN_CYCLE_DEFAULT_SUFFIX


def _build_force_clarify_reply(message: str, goal_type: str) -> str:
    return build_force_clarify_reply(goal_type)


def _build_force_clarify_next_prompt(goal_type: str) -> str:
    return build_force_clarify_next_prompt(goal_type)


def _interpret_guidance_choice(message: str) -> str | None:
    if any(hint in message for hint in GUIDANCE_OVERVIEW_HINTS):
        return "overview"
    if any(hint in message for hint in GUIDANCE_SCHEDULE_HINTS):
        return "schedule"
    return None


def _extract_focus_topic(message: str, goal_type: str) -> str | None:
    keyword_pool = (
        COURSE_FOCUS_KEYWORDS if goal_type == "course_exploration" else SKILL_DIRECTION_KEYWORDS
    )
    for keyword in keyword_pool:
        if keyword.lower() in message.lower() or keyword in message:
            return keyword

    cleaned = re.sub(r"[，。！？；,.!?\s]+", " ", message).strip()
    if not cleaned:
        return None
    if len(cleaned) > 24:
        return cleaned[:24]
    return cleaned


def _extract_time_budget_hint(message: str) -> str | None:
    match = TIME_BUDGET_PATTERN.search(message)
    if not match:
        return None
    return match.group(1).strip()


def _extract_start_hint(message: str) -> str | None:
    for hint in ("今天", "今晚", "明天", "明晚", "下周", "周末", "本周"):
        if hint in message:
            return hint
    return None


def _extract_preference_snapshot(message: str) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    time_budget = _extract_time_budget_hint(message)
    if time_budget:
        snapshot["time_budget"] = time_budget
    start_hint = _extract_start_hint(message)
    if start_hint:
        snapshot["start_hint"] = start_hint
    period_hint = next(
        (
            word
            for word in ("早上", "上午", "中午", "下午", "晚上", "今晚", "明晚")
            if word in message
        ),
        None,
    )
    if period_hint:
        snapshot["preferred_period"] = period_hint
    focus_hint = _extract_focus_topic(message, _classify_learning_goal(message))
    if focus_hint:
        snapshot["focus_topic"] = focus_hint
    tone_style = _extract_tone_style_hint(message)
    if tone_style:
        snapshot["tone_style"] = tone_style
    response_density = _extract_response_density_hint(message)
    if response_density:
        snapshot["response_density"] = response_density
    return snapshot


def _extract_tone_style_hint(message: str) -> str | None:
    lowered = message.lower()
    direct_hints = ("直接点", "严格点", "狠一点", "别太温柔", "少点鼓励", "务实一点", "干脆点")
    gentle_hints = ("温柔点", "慢一点", "耐心点", "别太凶", "轻松一点")
    motivational_hints = ("多鼓励", "打打气", "激励我", "严格督促", "push我", "push 我")

    if any(hint in message or hint in lowered for hint in direct_hints):
        return "direct"
    if any(hint in message or hint in lowered for hint in motivational_hints):
        return "motivational"
    if any(hint in message or hint in lowered for hint in gentle_hints):
        return "gentle"
    return None


def _extract_response_density_hint(message: str) -> str | None:
    lowered = message.lower()
    concise_hints = ("简短点", "简洁点", "一句话", "直接说重点", "少说点", "精简一点")
    detailed_hints = ("详细点", "展开讲", "讲细一点", "多解释", "说具体点", "完整一点")
    if any(hint in message or hint in lowered for hint in concise_hints):
        return "concise"
    if any(hint in message or hint in lowered for hint in detailed_hints):
        return "detailed"
    return None


def _merge_user_preferences(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    merged.update({key: value for key, value in updates.items() if value})
    return merged


def _sanitize_preference_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.startswith("<") and "Mock" in normalized:
        return None
    return normalized


def _extract_preference_seed(preferences: dict[str, Any]) -> dict[str, str]:
    seed: dict[str, str] = {}
    time_budget = _sanitize_preference_text(preferences.get("time_budget"))
    if time_budget:
        seed["time_budget"] = time_budget
    start_hint = _sanitize_preference_text(preferences.get("start_hint"))
    if start_hint:
        seed["start_hint"] = start_hint
    focus_topic = _sanitize_preference_text(preferences.get("focus_topic"))
    if focus_topic:
        seed["focus_topic"] = focus_topic
    return seed


def _is_pending_plan_expired(pending_plan_request: dict[str, Any] | None) -> bool:
    if not pending_plan_request:
        return False
    turn_count = pending_plan_request.get("turn_count", 0)
    if isinstance(turn_count, int) and turn_count >= PENDING_PLAN_MAX_TURNS:
        return True
    created_at = pending_plan_request.get("created_at")
    if not isinstance(created_at, str) or not created_at.strip():
        return False
    try:
        created_dt = datetime.fromisoformat(created_at)
    except ValueError:
        return False
    age = datetime.utcnow() - created_dt
    return age > timedelta(minutes=PENDING_PLAN_MAX_MINUTES)


def _build_preference_prompt_fragment(preferences: dict[str, Any]) -> str:
    if not preferences:
        return ""
    parts: list[str] = []
    if preferences.get("time_budget"):
        parts.append(f"常见可投入时长：{preferences['time_budget']}")
    if preferences.get("preferred_period"):
        parts.append(f"偏好学习时段：{preferences['preferred_period']}")
    if preferences.get("start_hint"):
        parts.append(f"常见开始偏好：{preferences['start_hint']}")
    if preferences.get("focus_topic"):
        parts.append(f"近期关注方向：{preferences['focus_topic']}")
    tone_style = preferences.get("tone_style")
    if tone_style == "direct":
        parts.append("偏好对话语气：直接、务实、少寒暄")
    elif tone_style == "motivational":
        parts.append("偏好对话语气：更有激励感，适度打气")
    elif tone_style == "gentle":
        parts.append("偏好对话语气：温和、耐心、循序推进")
    response_density = preferences.get("response_density")
    if response_density == "concise":
        parts.append("偏好信息密度：简洁，先说重点")
    elif response_density == "detailed":
        parts.append("偏好信息密度：详细，适当展开解释")
    elif response_density == "standard":
        parts.append("偏好信息密度：标准")
    return "；".join(parts)


def _build_clarify_quick_replies(goal_type: str, stage: str) -> list[str]:
    return build_clarify_quick_replies(goal_type, stage)


def _soft_preference_weight(now: datetime, created_at: datetime | None) -> float:
    if created_at is None:
        return 0.5
    if created_at.tzinfo is not None:
        created_at = created_at.astimezone(timezone.utc).replace(tzinfo=None)
    age = now - created_at
    if age > timedelta(days=14):
        return 0.0
    if age <= timedelta(days=2):
        return 1.0
    if age <= timedelta(days=7):
        return 0.65
    return 0.35


def _pick_soft_preference(values: list[tuple[str, datetime | None]]) -> str | None:
    if not values:
        return None
    now = datetime.utcnow()
    score_map: dict[str, float] = {}
    for value, created_at in values:
        if not isinstance(value, str) or not value.strip():
            continue
        normalized = value.strip()
        score_map[normalized] = score_map.get(normalized, 0.0) + _soft_preference_weight(
            now, created_at
        )
    if not score_map:
        return None
    selected, score = max(score_map.items(), key=lambda item: item[1])
    if score < 0.8:
        return None
    return selected


async def _load_user_preference_memory(user_id: int, db: AsyncSession) -> dict[str, Any]:
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    memory: dict[str, Any] = {"preference_sources": {}}
    tone_style = getattr(user, "companion_tone_style", None) if user else None
    tone_locked = bool(getattr(user, "companion_tone_locked", False)) if user else False
    memory["tone_locked"] = tone_locked
    if isinstance(tone_style, str) and tone_style:
        memory["tone_style"] = tone_style
        memory["preference_sources"]["tone_style"] = "hard"
    if tone_locked and memory.get("tone_style"):
        return memory

    result = await db.execute(
        select(ChatMessage.entities_json, ChatMessage.created_at)
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .where(ChatSession.user_id == user_id, ChatMessage.entities_json.is_not(None))
        .order_by(ChatMessage.created_at.desc())
        .limit(200)
    )
    scalars_result = result.scalars()
    if hasattr(scalars_result, "__await__"):
        scalars_result = await scalars_result
    rows = scalars_result.all()
    if hasattr(rows, "__await__"):
        rows = await rows

    soft_candidates: dict[str, list[tuple[str, datetime | None]]] = {
        "tone_style": [],
        "response_density": [],
        "time_budget": [],
        "start_hint": [],
        "focus_topic": [],
    }

    for row in rows:
        entities_json = row[0] if isinstance(row, tuple) else getattr(row, "entities_json", None)
        created_at = row[1] if isinstance(row, tuple) else getattr(row, "created_at", None)
        if not entities_json:
            continue
        try:
            payload = json.loads(entities_json)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        prefs = payload.get("user_preferences")
        if isinstance(prefs, dict):
            for key in soft_candidates:
                value = prefs.get(key)
                if isinstance(value, str) and value.strip():
                    soft_candidates[key].append((value.strip(), created_at))
            continue
        pending = payload.get("pending_plan_request")
        if isinstance(pending, dict):
            answers = pending.get("answers")
            if isinstance(answers, dict):
                inferred = {
                    "time_budget": answers.get("time_budget"),
                    "start_hint": answers.get("start_hint"),
                    "focus_topic": answers.get("focus_topic"),
                }
                for key, value in inferred.items():
                    if isinstance(value, str) and value.strip():
                        soft_candidates[key].append((value.strip(), created_at))

    for key, values in soft_candidates.items():
        if key == "tone_style" and memory.get("tone_style"):
            continue
        selected = _pick_soft_preference(values)
        if selected:
            memory[key] = selected
            memory["preference_sources"][key] = "soft"

    if "response_density" not in memory:
        memory["response_density"] = "standard"
        memory["preference_sources"]["response_density"] = "default"
    return memory


def _suggest_plan_title(
    *,
    original_message: str,
    goal_type: str,
    answers: dict[str, Any],
) -> str:
    focus = (answers.get("focus_topic") or "").strip()
    if goal_type == "course_exploration":
        if focus:
            return f"{focus}入门学习计划"
        return "阶段学习计划"
    if goal_type == "exam_prep":
        if focus:
            return f"{focus}考试复习计划"
        return "考试复习计划"
    if goal_type == "skill_building":
        if focus:
            return f"{focus}阶段学习计划"
        return "技能学习计划"
    return original_message[:40]


def _build_pending_plan_description(
    *,
    original_message: str,
    answers: dict[str, Any],
) -> str:
    parts = [original_message.strip()]
    if answers.get("focus_topic"):
        parts.append(f"当前优先方向：{answers['focus_topic']}")
    if answers.get("time_budget"):
        parts.append(f"可投入时间：{answers['time_budget']}")
    if answers.get("start_hint"):
        parts.append(f"开始时间：{answers['start_hint']}")
    return "；".join(part for part in parts if part)


def _build_followup_plan_entities(
    *,
    pending_request: dict[str, Any],
    answers: dict[str, Any],
) -> dict[str, Any]:
    original_message = pending_request.get("message", "").strip()
    base_entities = dict((pending_request.get("entities") or {}))
    goal_type = base_entities.get("goal_type") or "general_learning"
    plan_title = _suggest_plan_title(
        original_message=original_message,
        goal_type=goal_type,
        answers=answers,
    )
    plan_description = _build_pending_plan_description(
        original_message=original_message,
        answers=answers,
    )
    return {
        **base_entities,
        "plan_title": plan_title,
        "task_title": answers.get("focus_topic") or plan_title,
        "plan_description": plan_description,
        "description": plan_description,
    }


def _build_pending_guidance_response(
    *,
    goal_type: str,
    stage: str,
    message: str,
    answers: dict[str, Any],
) -> tuple[str, str | None, str, dict[str, Any]] | tuple[None, None, str, dict[str, Any]]:
    updated_answers = dict(answers)

    if stage == "initial_choice":
        choice = _interpret_guidance_choice(message)
        if choice is None:
            reply, next_prompt = build_initial_choice_prompt(goal_type)
            return (
                reply,
                next_prompt,
                "initial_choice",
                updated_answers,
            )

        updated_answers["entry_choice"] = choice
        if goal_type == "course_exploration":
            if choice == "overview":
                return (
                    "如果你是刚开始系统学，我们先抓主线会更稳：先选一个最关键科目或知识块起步，再逐步扩展。你现在最想先从哪一块开始？",
                    "比如可以直接回我“先从高数开始”，或者“先整体过一遍考试范围”。",
                    "focus_topic",
                    updated_answers,
                )
            focus_topic = _extract_focus_topic(message, goal_type)
            time_budget = _extract_time_budget_hint(message)
            time_from_message = bool(time_budget)
            if not time_budget:
                time_budget = updated_answers.get("time_budget")
            if focus_topic and time_budget:
                updated_answers["focus_topic"] = focus_topic
                updated_answers["time_budget"] = time_budget
                if _extract_start_hint(message):
                    updated_answers["start_hint"] = _extract_start_hint(message)
                if updated_answers.get("start_hint"):
                    return None, None, "ready_to_build", updated_answers
                if not time_from_message:
                    return (
                        f"好，那我们就先围绕“{focus_topic}”推进，并按“{time_budget}”安排节奏。最后确认一下：你想从今天开始，还是明天/下周开始？",
                        "你可以直接回我“今晚开始”“明天开始”或“下周一开始”。",
                        "start_time",
                        updated_answers,
                    )
                return None, None, "ready_to_build", updated_answers
            return (
                "好，那我们先不排太满，只先搭第一步。你这周最想先从哪门科目或哪块知识开始？",
                "你可以直接回我“先从高数开始”，或者“先整体过一遍范围”。",
                "focus_topic",
                updated_answers,
            )

        if goal_type == "exam_prep":
            focus_topic = _extract_focus_topic(message, goal_type)
            time_budget = _extract_time_budget_hint(message)
            time_from_message = bool(time_budget)
            if not time_budget:
                time_budget = updated_answers.get("time_budget")
            if focus_topic and time_budget:
                updated_answers["focus_topic"] = focus_topic
                updated_answers["time_budget"] = time_budget
                if _extract_start_hint(message):
                    updated_answers["start_hint"] = _extract_start_hint(message)
                if updated_answers.get("start_hint"):
                    return None, None, "ready_to_build", updated_answers
                if not time_from_message:
                    return (
                        f"明白，我们先聚焦“{focus_topic}”，并按“{time_budget}”推进。最后确认开始时间：今天开始，还是明天/下周开始？",
                        "你可以直接回我“今晚开始”“明天开始”或“下周一开始”。",
                        "start_time",
                        updated_answers,
                    )
                return None, None, "ready_to_build", updated_answers
            return (
                "好，我们先抓最关键的一点。你这次主要是哪门考试，或者你现在最没底的是哪一块？",
                "比如可以直接回我“高数，积分和微分方程比较弱”。",
                "focus_topic",
                updated_answers,
            )

        if goal_type == "skill_building":
            focus_topic = _extract_focus_topic(message, goal_type)
            time_budget = _extract_time_budget_hint(message)
            time_from_message = bool(time_budget)
            if not time_budget:
                time_budget = updated_answers.get("time_budget")
            if focus_topic and time_budget:
                updated_answers["focus_topic"] = focus_topic
                updated_answers["time_budget"] = time_budget
                if _extract_start_hint(message):
                    updated_answers["start_hint"] = _extract_start_hint(message)
                if updated_answers.get("start_hint"):
                    return None, None, "ready_to_build", updated_answers
                if not time_from_message:
                    return (
                        f"好，我们先围绕“{focus_topic}”练起，并按“{time_budget}”节奏推进。最后确认开始时间：今天开始，还是明天/下周开始？",
                        "你可以直接回我“今晚开始”“明天开始”或“下周一开始”。",
                        "start_time",
                        updated_answers,
                    )
                return None, None, "ready_to_build", updated_answers
            return (
                "好，那我们先把第一阶段的目标说清楚。你现在更想先练基础语法、刷题，还是直接做一个小项目？",
                "比如可以直接回我“先把基础打牢”，或者“我想直接做个小项目”。",
                "focus_topic",
                updated_answers,
            )

        focus_topic = _extract_focus_topic(message, "course_exploration")
        time_budget = _extract_time_budget_hint(message)
        time_from_message = bool(time_budget)
        if not time_budget:
            time_budget = updated_answers.get("time_budget")
        if focus_topic and time_budget:
            updated_answers["focus_topic"] = focus_topic
            updated_answers["time_budget"] = time_budget
            if _extract_start_hint(message):
                updated_answers["start_hint"] = _extract_start_hint(message)
            if updated_answers.get("start_hint"):
                return None, None, "ready_to_build", updated_answers
            if not time_from_message:
                return (
                    f"好，那我们先围绕“{focus_topic}”推进，并按“{time_budget}”安排节奏。最后确认开始时间：今天开始，还是明天/下周开始？",
                    "你可以直接回我“今晚开始”“明天开始”或“下周一开始”。",
                    "start_time",
                    updated_answers,
                )
            return None, None, "ready_to_build", updated_answers

    if stage == "focus_topic":
        focus_topic = _extract_focus_topic(message, goal_type)
        if not focus_topic:
            return (
                "我先顺着你这条线继续带，不过我还想确认得再具体一点。你最想先推进的对象是什么？是一门课、一个知识块，还是一个项目方向？",
                "你可以直接回我一个很短的答案，比如“高数积分”“英语阅读”“数据分析项目”。",
                "focus_topic",
                updated_answers,
            )
        updated_answers["focus_topic"] = focus_topic
        existing_time_budget = updated_answers.get("time_budget")
        if existing_time_budget:
            if updated_answers.get("start_hint"):
                return None, None, "ready_to_build", updated_answers
            return (
                f"好，那我们就先围绕“{focus_topic}”来推进，并按“{existing_time_budget}”这个节奏安排。最后确认一下：你想从今天开始，还是从明天/下周开始？",
                "比如可以直接回我“今晚开始”“明天开始”或者“下周一开始”。",
                "start_time",
                updated_answers,
            )
        return (
            f"好，那我们就先围绕“{focus_topic}”来推进。接下来我只确认一个最关键的现实条件：你每天大概能投入多久？",
            "比如可以直接回我“每天晚上两小时”，或者“工作日一小时，周末三小时”。",
            "time_budget",
            updated_answers,
        )

    if stage == "time_budget":
        time_budget = _extract_time_budget_hint(message)
        if not time_budget:
            return (
                "这个信息我还没完全抓到，我想先把节奏定实一点。你每天大概能稳定拿出多久来学？",
                "你可以直接回我“每天一小时”“每天晚上两小时”或者“周末半天”。",
                "time_budget",
                updated_answers,
            )
        updated_answers["time_budget"] = time_budget
        return (
            f"明白了，那我会按“{time_budget}”这个节奏来给你搭。最后再确认一个小点：你想从今天开始，还是从明天/下周开始？",
            "比如可以直接回我“今晚开始”“明天开始”或者“下周一开始”。",
            "start_time",
            updated_answers,
        )

    if stage == "start_time":
        updated_answers["start_hint"] = _extract_start_hint(message) or message.strip()
        return None, None, "ready_to_build", updated_answers

    return None, None, "ready_to_build", updated_answers


def _build_next_step_guidance(
    intent: str,
    action_result: Any,
    recent_context: dict[str, Any],
) -> tuple[str | None, list[str] | None]:
    if intent in {"create_plan", "refine_plan"}:
        has_plan = bool(getattr(action_result, "id", None))
        if isinstance(action_result, dict):
            has_plan = has_plan or bool(action_result.get("plan"))
        if has_plan:
            return (
                "我们可以顺着这条计划再往前走一步：先把每天可投入时长和提醒节点补上，我就能把节奏排得更贴合你。",
                ["每天晚上两小时，下周一开始", "先给我加三个提醒节点"],
            )
        return (
            "如果你愿意，我可以接着把这条学习线落成一份更好执行的周节奏。",
            ["继续细化成第一周安排", "先补提醒再细化"],
        )
    if intent == "create_task":
        has_due_date = bool(getattr(action_result, "due_date", None))
        if not has_due_date:
            return (
                "这一步先补上截止和提醒会更稳，后面执行时不容易漏掉。",
                ["今晚10点前完成并提醒我", "明晚20:00提醒我开始"],
            )
        return (
            "要继续推进的话，我可以把这项任务再拆成按天可执行的小步骤。",
            ["拆成3个子步骤", "按今晚和明晚拆两步"],
        )
    if intent == "update_task":
        return (
            "如果你想一口气理顺，我可以顺手帮你调优先级、截止时间，或者挂进学习计划。",
            ["设为高优先级并明晚截止", "挂到当前学习计划里"],
        )
    if intent == "complete_task":
        return (
            "你现在状态不错，可以直接衔接下一步，我来帮你把节奏接上。",
            ["基于它安排下一步任务", "根据今天进度排明天任务"],
        )
    if intent == "query_task":
        return (
            "如果你愿意，我可以直接从当前任务里挑出今天最值得先做的 1-3 项，省得你来回权衡。",
            ["帮我选今天最先做的3项", "只给我1项最高优先级"],
        )
    if intent == "query_stats":
        recent_activity = bool(recent_context.get("last_activity_type"))
        if recent_activity:
            return (
                "我可以基于这份统计给你一版更具体的节奏调整建议，直接能落地。",
                ["给我一个本周节奏优化方案", "找出我最近效率最低的时段"],
            )
        return (
            "如果你愿意，我可以把这份统计继续转成一份可执行的调整建议。",
            ["给我两条最重要的改进建议", "按任务完成率给我建议"],
        )
    return None, None


def _build_guided_reply(
    *,
    intent: str,
    action_result: Any,
    extracted_tasks: list[dict[str, Any]] | None,
    extracted_plans: list[dict[str, Any]] | None,
    fallback_reply: str,
) -> str:
    root_count, child_count = _count_root_and_child_tasks(extracted_tasks)

    if intent == "create_task" and action_result is not None:
        title = _display_title_short(getattr(action_result, "title", "这项学习任务"))
        if child_count:
            return f"主任务「{title}」已进任务树，并补了 {child_count} 条子项；子项里可写具体步骤。"
        return f"主任务「{title}」已记入系统。"

    if intent in {"create_plan", "refine_plan"} and isinstance(action_result, dict):
        plan = action_result.get("plan")
        task = action_result.get("task")
        plan_title = _display_title_short(getattr(plan, "title", "当前计划"))
        task_title = _display_title_short(getattr(task, "title", "主任务"))

        if intent == "create_plan":
            if child_count:
                return (
                    f"已保存为计划「{plan_title}」；主任务「{task_title}」下共 {child_count} 条子项，"
                    f"按天/阶段的详细步骤在子任务里，不必再和聊天长文一一对照。"
                )
            return f"计划「{plan_title}」和主任务「{task_title}」已建好了；要补细节可继续在子任务中展开。"

        if child_count:
            return f"已在「{plan_title}」上继续细化了「{task_title}」，本轮回补了 {child_count} 条子项。"
        return f"已更新「{plan_title}」相关安排，主任务「{task_title}」仍挂在同一条主线上。"

    if intent == "update_task" and action_result is not None:
        return f"已帮你更新任务“{getattr(action_result, 'title', '当前任务')}”，现在状态是最新的。"

    if intent == "complete_task" and action_result is not None:
        return f"很好，这项任务“{getattr(action_result, 'title', '当前任务')}”已经为你标记完成。"

    if intent == "query_task" and isinstance(action_result, list):
        return f"我先把你当前相关的任务梳理好了，这次一共找到 {len(action_result)} 条。"

    if intent == "query_stats" and action_result is not None:
        return "我已经把你最近的学习状态整理出来了，接下来我们可以一起看节奏、连续性和薄弱点。"

    return fallback_reply


async def _maybe_generate_subtasks_from_reply(
    *,
    user_id: int,
    intent: str,
    action_result: Any,
    extracted_tasks: list[dict[str, Any]] | None,
    ai_reply: str,
    db: AsyncSession,
) -> tuple[Any, list[dict[str, Any]] | None]:
    if intent not in {"refine_plan"} or not action_result:
        return action_result, extracted_tasks

    parent_task = action_result.get("task") if isinstance(action_result, dict) else None
    plan = action_result.get("plan") if isinstance(action_result, dict) else None

    if parent_task is None:
        return action_result, extracted_tasks

    generated_steps = extract_structured_subtasks_from_reply(ai_reply)
    if not generated_steps:
        return action_result, extracted_tasks

    refreshed_parent_before = await task_service.get_task(user_id, parent_task.id, db)
    serialized_parent_before = task_service.serialize_task(refreshed_parent_before)
    existing_children = serialized_parent_before.get("children", [])
    existing_titles = {child["title"] for child in existing_children}
    next_sort_order = (
        max((child.get("sort_order", -1) for child in existing_children), default=-1) + 1
    )

    if plan is not None:
        base_date = datetime.combine(plan.start_date, time(hour=20, minute=0))
    else:
        base_date = parent_task.due_date or datetime.now()

    created_tasks = list(extracted_tasks or [])
    for step in generated_steps:
        if step["title"] in existing_titles:
            continue

        due_date, scheduled_date = _build_subtask_due_datetime(
            base_date=base_date,
            day_offset=int(step["day_offset"]),
            hour=step.get("hour"),
            minute=step.get("minute"),
        )
        phase_id = _pick_phase_id(plan, step=step, target_date=scheduled_date)

        child = await task_service.create_task(
            user_id,
            {
                "title": step["title"],
                "description": step["description"],
                "priority": parent_task.priority,
                "plan_id": parent_task.plan_id,
                "phase_id": phase_id,
                "parent_task_id": parent_task.id,
                "due_date": due_date,
                "scheduled_date": scheduled_date,
                "sort_order": next_sort_order,
            },
            db,
        )
        next_sort_order += 1
        existing_titles.add(child.title)
        created_tasks.append(
            {
                "id": child.id,
                "title": child.title,
                "plan_id": child.plan_id,
                "parent_task_id": child.parent_task_id,
            }
        )

    refreshed_parent = await task_service.get_task(user_id, parent_task.id, db)
    updated_payload = dict(action_result)
    updated_payload["task"] = refreshed_parent
    return updated_payload, created_tasks


async def process_chat_message(
    user_id: int,
    session_id: int | None,
    message: str,
    db: AsyncSession,
    proposal_id: str | None = None,
) -> dict[str, Any]:
    session = await get_or_create_session(user_id, session_id, message, db)
    history = await load_history(session.id, db, limit=20)
    structured_history = await load_structured_history(session.id, db, limit=20)
    preference_memory = await _load_user_preference_memory(user_id, db)
    current_preference = _extract_preference_snapshot(message)
    merged_preferences = _merge_user_preferences(preference_memory, current_preference)
    recent_context = await _hydrate_recent_action_context(
        user_id,
        _extract_recent_action_context(structured_history),
        db,
    )
    pending_action_proposal = _extract_pending_action_proposal(
        structured_history, proposal_id=proposal_id
    )
    if pending_action_proposal is None:
        pending_action_proposal = await _load_pending_action_proposal_from_db(
            session.id,
            db,
            proposal_id=proposal_id,
        )
    if _should_reset_recent_context(message):
        recent_context.pop("pending_plan_request", None)
        recent_context.pop("plan_id", None)
        recent_context.pop("task_id", None)
    pending_plan_request = recent_context.get("pending_plan_request")
    if _is_pending_plan_expired(pending_plan_request):
        _log_chat_orchestration(
            "pending_plan_expired",
            user_id=user_id,
            turn_count=(pending_plan_request or {}).get("turn_count"),
            created_at=(pending_plan_request or {}).get("created_at"),
        )
        recent_context.pop("pending_plan_request", None)
        pending_plan_request = None

    execution_message = message
    proposal_commit_confirmed = False

    if pending_plan_request and not recent_context.get("plan_id"):
        pending_goal_type = (pending_plan_request.get("entities") or {}).get(
            "goal_type"
        ) or "general_learning"
        pending_stage = pending_plan_request.get("stage") or "initial_choice"
        pending_answers = dict(pending_plan_request.get("answers") or {})
        preference_time_budget = _sanitize_preference_text(merged_preferences.get("time_budget"))
        if not pending_answers.get("time_budget") and preference_time_budget:
            pending_answers["time_budget"] = preference_time_budget
        preference_start_hint = _sanitize_preference_text(merged_preferences.get("start_hint"))
        if not pending_answers.get("start_hint") and preference_start_hint:
            pending_answers["start_hint"] = preference_start_hint
        preference_focus_topic = _sanitize_preference_text(merged_preferences.get("focus_topic"))
        if (
            pending_stage in {"initial_choice", "focus_topic"}
            and not pending_answers.get("focus_topic")
            and preference_focus_topic
        ):
            pending_answers["focus_topic"] = preference_focus_topic
        clarify_reply, clarify_next_prompt, next_stage, updated_answers = (
            _build_pending_guidance_response(
                goal_type=pending_goal_type,
                stage=pending_stage,
                message=message,
                answers=pending_answers,
            )
        )

        if next_stage != "ready_to_build":
            assert clarify_reply is not None
            clarify_user_entities_str = json.dumps(
                {"user_preferences": merged_preferences},
                ensure_ascii=False,
            )
            clarify_assistant_entities_str = json.dumps(
                _attach_orchestration_diagnostics(
                    _build_pending_plan_entities(
                        message=pending_plan_request.get("message", message),
                        entities=pending_plan_request.get("entities") or {},
                        stage=next_stage,
                        answers=updated_answers,
                        turn_count=(pending_plan_request.get("turn_count") or 0) + 1,
                        created_at=pending_plan_request.get("created_at"),
                    ),
                    event="pending_clarify_continue",
                    summary="沿用未完成的澄清链路，继续补关键缺失字段。",
                    stage=next_stage,
                    goal_type=pending_goal_type,
                ),
                ensure_ascii=False,
            )

            await save_message(
                session.id,
                "user",
                message,
                db,
                intent="clarify_plan",
                entities_json=clarify_user_entities_str,
            )
            await save_message(
                session.id,
                "assistant",
                clarify_reply,
                db,
                intent="clarify_plan",
                entities_json=clarify_assistant_entities_str,
            )
            await record_learning_activity(user_id, "chat", db)

            return {
                "reply": clarify_reply,
                "intent": "clarify_plan",
                "session_id": session.id,
                "extracted_tasks": None,
                "extracted_plans": None,
                "sync_summary": None,
                "next_prompt": clarify_next_prompt,
                "next_prompt_options": _build_clarify_quick_replies(pending_goal_type, next_stage),
                "proposal_id": None,
                "scenario_type": pending_goal_type,
                "scenario_label": _scenario_label(pending_goal_type),
            }

        intent = "create_plan"
        entities = _build_followup_plan_entities(
            pending_request=pending_plan_request,
            answers=updated_answers,
        )
        nlp_result = None
    else:
        try:
            nlp_result = await call_llm_for_intent(message, history)
        except Exception as exc:
            _log_chat_orchestration(
                "nlp_intent_failed",
                user_id=user_id,
                session_id=session.id,
                error=str(exc),
            )
            nlp_result = None

    if pending_plan_request and not recent_context.get("plan_id"):
        pass
    elif _should_force_clarify_plan(message, recent_context):
        goal_type = _classify_learning_goal(message)
        _log_chat_orchestration(
            "force_clarify_triggered",
            user_id=user_id,
            session_id=session.id,
            goal_type=goal_type,
        )
        seeded_answers = _extract_preference_seed(preference_memory)
        if seeded_answers:
            _log_chat_orchestration(
                "force_clarify_seeded_from_preferences",
                user_id=user_id,
                session_id=session.id,
                seeded_keys=sorted(seeded_answers.keys()),
            )
            (
                clarification_reply,
                clarification_next_prompt,
                next_stage,
                updated_answers,
            ) = _build_pending_guidance_response(
                goal_type=goal_type,
                stage="initial_choice",
                message=message,
                answers=seeded_answers,
            )
            if next_stage == "ready_to_build":
                _log_chat_orchestration(
                    "force_clarify_seeded_ready_to_build",
                    user_id=user_id,
                    session_id=session.id,
                    goal_type=goal_type,
                )
                intent = "create_plan"
                entities = _build_followup_plan_entities(
                    pending_request={
                        "message": message,
                        "entities": {
                            "plan_title": message[:60],
                            "plan_description": message,
                            "task_title": message[:60],
                            "goal_type": goal_type,
                        },
                    },
                    answers=updated_answers,
                )
                nlp_result = None
            elif clarification_reply:
                forced_user_entities_str = json.dumps(
                    {"user_preferences": merged_preferences},
                    ensure_ascii=False,
                )
                forced_assistant_entities_str = json.dumps(
                    _attach_orchestration_diagnostics(
                        _build_pending_plan_entities(
                            message=message,
                            entities={
                                "plan_title": message[:60],
                                "plan_description": message,
                                "task_title": message[:60],
                                "goal_type": goal_type,
                            },
                            stage=next_stage,
                            answers=updated_answers,
                            turn_count=1,
                        ),
                        event="force_clarify_seeded",
                        summary="强制澄清触发后，已基于历史偏好自动补全并跳步。",
                        stage=next_stage,
                        goal_type=goal_type,
                    ),
                    ensure_ascii=False,
                )
                await save_message(
                    session.id,
                    "user",
                    message,
                    db,
                    intent="create_plan",
                    entities_json=forced_user_entities_str,
                )
                await save_message(
                    session.id,
                    "assistant",
                    clarification_reply,
                    db,
                    intent="clarify_plan",
                    entities_json=forced_assistant_entities_str,
                )
                await record_learning_activity(user_id, "chat", db)
                return {
                    "reply": clarification_reply,
                    "intent": "clarify_plan",
                    "session_id": session.id,
                    "extracted_tasks": None,
                    "extracted_plans": None,
                    "sync_summary": None,
                    "next_prompt": clarification_next_prompt
                    or _build_force_clarify_next_prompt(goal_type),
                    "next_prompt_options": _build_clarify_quick_replies(goal_type, next_stage),
                    "proposal_id": None,
                    "scenario_type": goal_type,
                    "scenario_label": _scenario_label(goal_type),
                }
        clarification_reply = _build_force_clarify_reply(message, goal_type)
        forced_user_entities_str = json.dumps(
            {"user_preferences": merged_preferences},
            ensure_ascii=False,
        )
        forced_assistant_entities_str = json.dumps(
            _attach_orchestration_diagnostics(
                _build_pending_plan_entities(
                    message=message,
                    entities={
                        "plan_title": message[:60],
                        "plan_description": message,
                        "task_title": message[:60],
                        "goal_type": goal_type,
                    },
                    stage="initial_choice",
                ),
                event="force_clarify_initial",
                summary="检测到宽泛目标，先进入澄清模式再继续执行。",
                stage="initial_choice",
                goal_type=goal_type,
            ),
            ensure_ascii=False,
        )

        await save_message(
            session.id,
            "user",
            message,
            db,
            intent="create_plan",
            entities_json=forced_user_entities_str,
        )
        await save_message(
            session.id,
            "assistant",
            clarification_reply,
            db,
            intent="clarify_plan",
            entities_json=forced_assistant_entities_str,
        )
        await record_learning_activity(user_id, "chat", db)

        return {
            "reply": clarification_reply,
            "intent": "clarify_plan",
            "session_id": session.id,
            "extracted_tasks": None,
            "extracted_plans": None,
            "sync_summary": None,
            "next_prompt": _build_force_clarify_next_prompt(goal_type),
            "next_prompt_options": _build_clarify_quick_replies(goal_type, "initial_choice"),
            "proposal_id": None,
            "scenario_type": goal_type,
            "scenario_label": _scenario_label(goal_type),
        }
    else:
        intent, entities = resolve_intent(message, nlp_result, recent_context)
        if proposal_id:
            if (
                pending_action_proposal
                and str(pending_action_proposal.get("proposal_id")) == proposal_id
            ):
                intent = str(pending_action_proposal.get("intent") or "create_plan")
                entities, execution_message = _build_commit_entities_from_proposal(
                    proposal=pending_action_proposal,
                    fallback_message=message,
                )
                proposal_commit_confirmed = True
            else:
                user_entities_payload = {"user_preferences": merged_preferences}
                user_entities_str = json.dumps(user_entities_payload, ensure_ascii=False)
                assistant_entities_str = json.dumps(
                    _attach_orchestration_diagnostics(
                        {"pending_action_proposal": pending_action_proposal},
                        event="plan_proposal_commit_rejected",
                        summary="草案确认失败：proposal_id 不存在或已过期。",
                        provided_proposal_id=proposal_id,
                    ),
                    ensure_ascii=False,
                )
                rejection_reply = "这份草案可能已经过期或不匹配当前会话。你可以先让我重新生成一版，再点击“加入计划”。"
                await save_message(
                    session.id,
                    "user",
                    message,
                    db,
                    intent="plan_proposal_commit",
                    entities_json=user_entities_str,
                )
                await save_message(
                    session.id,
                    "assistant",
                    rejection_reply,
                    db,
                    intent="plan_proposal",
                    entities_json=assistant_entities_str,
                )
                await record_learning_activity(user_id, "chat", db)
                return {
                    "reply": rejection_reply,
                    "intent": "plan_proposal",
                    "session_id": session.id,
                    "extracted_tasks": None,
                    "extracted_plans": None,
                    "sync_summary": None,
                    "next_prompt": "请先让我重新给你一版草案，然后再点“加入计划”。",
                    "next_prompt_options": ["重新给我一版计划草案"],
                    "proposal_id": None,
                    "scenario_type": "general_learning",
                    "scenario_label": _scenario_label("general_learning"),
                }
        elif pending_action_proposal and _is_plan_commit_request(message):
            intent = str(pending_action_proposal.get("intent") or "create_plan")
            entities = dict(pending_action_proposal.get("entities") or {})
            execution_message = str(pending_action_proposal.get("source_message") or message)
        should_clarify, clarification_reply_opt = should_clarify_before_action(
            intent=intent,
            message=message,
            entities=entities,
            recent_context=recent_context,
        )
        if proposal_commit_confirmed and intent in {"create_plan", "refine_plan"}:
            should_clarify = False
            clarification_reply_opt = None

        if should_clarify and clarification_reply_opt:
            _log_chat_orchestration(
                "clarify_before_action_triggered",
                user_id=user_id,
                session_id=session.id,
                intent=intent,
            )
            clarification_reply = clarification_reply_opt
            clarify_user_entities_payload = dict(entities or {})
            clarify_user_entities_payload["user_preferences"] = merged_preferences
            clarify_user_entities_json = json.dumps(
                clarify_user_entities_payload, ensure_ascii=False
            )
            clarify_assistant_entities_str = json.dumps(
                _attach_orchestration_diagnostics(
                    _build_pending_plan_entities(
                        message=message,
                        entities=entities,
                        stage="initial_choice",
                    ),
                    event="clarify_before_action",
                    summary="动作执行前关键信息不足，先发起一次澄清。",
                    stage="initial_choice",
                    goal_type=entities.get("goal_type") or _classify_learning_goal(message),
                ),
                ensure_ascii=False,
            )

            await save_message(
                session.id,
                "user",
                message,
                db,
                intent=intent,
                entities_json=clarify_user_entities_json,
            )
            await save_message(
                session.id,
                "assistant",
                clarification_reply,
                db,
                intent="clarify_plan",
                entities_json=clarify_assistant_entities_str,
            )
            await record_learning_activity(user_id, "chat", db)

            return {
                "reply": clarification_reply,
                "intent": "clarify_plan",
                "session_id": session.id,
                "extracted_tasks": None,
                "extracted_plans": None,
                "sync_summary": None,
                "next_prompt": "你可以回：先了解课程结构；或直接排第一周（例如每天晚上两小时）。",
                "next_prompt_options": _build_clarify_quick_replies(
                    entities.get("goal_type") or _classify_learning_goal(message),
                    "initial_choice",
                ),
                "proposal_id": None,
                "scenario_type": entities.get("goal_type") or _classify_learning_goal(message),
                "scenario_label": _scenario_label(
                    entities.get("goal_type") or _classify_learning_goal(message)
                ),
            }

    if _should_stage_plan_proposal(intent, message):
        proposal_uid = uuid.uuid4().hex[:16]
        response_density = merged_preferences.get("response_density") or "standard"
        if response_density not in {"concise", "standard", "detailed"}:
            response_density = "standard"
        proposal_prompt = (
            f"{build_companion_prompt(intent, None, response_density=response_density)}\n\n"
            "你当前处于“方案预览”阶段：\n"
            "1. 先给出引导式、简洁、可执行的计划草案。\n"
            "2. 不要声称已创建任务/计划，不要使用“已帮你记录/创建”措辞。\n"
            "3. 结尾明确提示：若用户确认，再由你落库生成任务。"
        )
        proposal_messages: list[dict[str, str]] = [{"role": "system", "content": proposal_prompt}]
        for item in history:
            proposal_messages.append({"role": item["role"], "content": item["content"]})
        proposal_messages.append({"role": "user", "content": message})
        proposal_reply = await call_llm_api(proposal_messages)

        user_entities_payload = dict(entities or {})
        user_entities_payload["user_preferences"] = merged_preferences
        user_entities_str = json.dumps(user_entities_payload, ensure_ascii=False)
        assistant_entities_str = json.dumps(
            _attach_orchestration_diagnostics(
                {
                    "pending_action_proposal": {
                        "proposal_id": proposal_uid,
                        "intent": intent,
                        "entities": entities,
                        "source_message": message,
                        "proposal_reply": proposal_reply,
                        "created_at": datetime.utcnow().isoformat(),
                    }
                },
                event="plan_proposal_generated",
                summary="已生成计划草案，等待用户确认后再落库。",
                intent=intent,
            ),
            ensure_ascii=False,
        )
        await save_message(
            session.id,
            "user",
            message,
            db,
            intent=intent,
            entities_json=user_entities_str,
        )
        await save_message(
            session.id,
            "assistant",
            proposal_reply,
            db,
            intent="plan_proposal",
            entities_json=assistant_entities_str,
        )
        await record_learning_activity(user_id, "chat", db)
        return {
            "reply": proposal_reply,
            "intent": "plan_proposal",
            "session_id": session.id,
            "extracted_tasks": None,
            "extracted_plans": None,
            "sync_summary": None,
            "next_prompt": "如果你觉得这版合理，可以直接回“按这个计划加入任务”。",
            "next_prompt_options": ["按这个计划加入任务", "先改一下再加入计划"],
            "proposal_id": proposal_uid,
            "scenario_type": entities.get("goal_type") or _classify_learning_goal(message),
            "scenario_label": _scenario_label(
                entities.get("goal_type") or _classify_learning_goal(message)
            ),
        }

    action_result, extracted_tasks, extracted_plans = await execute_intent(
        user_id=user_id,
        message=execution_message,
        intent=intent,
        entities=entities,
        db=db,
    )

    if intent in {"create_task", "create_plan", "refine_plan"} and not action_result:
        failure_reply = "这次我没能成功写入计划/任务模块。你可以点一次“加入计划”重试，或让我先精简草案后再提交。"
        user_entities_payload = dict(entities or {})
        user_entities_payload["user_preferences"] = merged_preferences
        user_entities_str = json.dumps(user_entities_payload, ensure_ascii=False)
        failed_proposal_id: str | None = None
        if isinstance(pending_action_proposal, dict):
            failed_proposal_id = str(pending_action_proposal.get("proposal_id") or "") or None
        assistant_entities_str = json.dumps(
            _attach_orchestration_diagnostics(
                {
                    "pending_action_proposal": None,
                    "failed_proposal_id": failed_proposal_id,
                },
                event="action_commit_failed",
                summary="动作执行失败，已阻止成功态话术返回。",
                intent=intent,
            ),
            ensure_ascii=False,
        )
        await save_message(
            session.id,
            "user",
            message,
            db,
            intent=intent,
            entities_json=user_entities_str,
        )
        await save_message(
            session.id,
            "assistant",
            failure_reply,
            db,
            intent="action_failed",
            entities_json=assistant_entities_str,
        )
        await record_learning_activity(user_id, "chat", db)
        return {
            "reply": failure_reply,
            "intent": "action_failed",
            "session_id": session.id,
            "extracted_tasks": None,
            "extracted_plans": None,
            "sync_summary": None,
            "next_prompt": "你可以点下方「重试加入计划」，或发一句：先精简为一周3个关键任务。",
            "next_prompt_options": ["重试加入计划", "先精简为一周3个关键任务"],
            "proposal_id": failed_proposal_id,
            "scenario_type": entities.get("goal_type") or _classify_learning_goal(message),
            "scenario_label": _scenario_label(
                entities.get("goal_type") or _classify_learning_goal(message)
            ),
        }

    response_density = merged_preferences.get("response_density") or "standard"
    if response_density not in {"concise", "standard", "detailed"}:
        response_density = "standard"
    system_prompt = build_companion_prompt(intent, action_result, response_density=response_density)
    preference_fragment = _build_preference_prompt_fragment(merged_preferences)
    if preference_fragment:
        system_prompt = f"{system_prompt}\n\n用户长期偏好：{preference_fragment}"
    llm_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for item in history:
        llm_messages.append({"role": item["role"], "content": item["content"]})
    llm_messages.append({"role": "user", "content": message})

    ai_reply = await call_llm_api(llm_messages)
    action_result, extracted_tasks = await _maybe_generate_subtasks_from_reply(
        user_id=user_id,
        intent=intent,
        action_result=action_result,
        extracted_tasks=extracted_tasks,
        ai_reply=ai_reply,
        db=db,
    )

    sync_summary = _build_sync_summary(extracted_tasks, extracted_plans)
    next_prompt, next_prompt_options = _build_next_step_guidance(
        intent, action_result, recent_context
    )
    _log_chat_orchestration(
        "action_completed",
        user_id=user_id,
        session_id=session.id,
        intent=intent,
        has_tasks=bool(extracted_tasks),
        has_plans=bool(extracted_plans),
        next_prompt=bool(next_prompt),
        next_prompt_options_count=len(next_prompt_options or []),
    )
    guided_reply = _build_guided_reply(
        intent=intent,
        action_result=action_result,
        extracted_tasks=extracted_tasks,
        extracted_plans=extracted_plans,
        fallback_reply=ai_reply,
    )

    prefix = _build_action_prefix(intent, action_result)
    if prefix and prefix not in guided_reply:
        guided_reply = f"{prefix}\n\n{guided_reply}"

    user_entities_payload = dict(entities or {})
    user_entities_payload["user_preferences"] = merged_preferences
    user_entities_str = json.dumps(user_entities_payload, ensure_ascii=False)
    assistant_entities = _attach_orchestration_diagnostics(
        {
            "extracted_tasks": extracted_tasks or [],
            "extracted_plans": extracted_plans or [],
            "pending_action_proposal": None,
        },
        event="action_completed",
        summary="动作已执行并生成回复，返回下一步建议。",
        intent=intent,
        has_tasks=bool(extracted_tasks),
        has_plans=bool(extracted_plans),
        next_prompt=bool(next_prompt),
        next_prompt_options_count=len(next_prompt_options or []),
    )
    assistant_entities_str = json.dumps(assistant_entities, ensure_ascii=False)

    await save_message(
        session.id,
        "user",
        message,
        db,
        intent=intent,
        entities_json=user_entities_str,
    )
    await save_message(
        session.id,
        "assistant",
        guided_reply,
        db,
        intent=intent,
        entities_json=assistant_entities_str,
    )
    await record_learning_activity(user_id, "chat", db)

    return {
        "reply": guided_reply,
        "intent": intent,
        "session_id": session.id,
        "extracted_tasks": extracted_tasks,
        "extracted_plans": extracted_plans,
        "sync_summary": sync_summary,
        "next_prompt": next_prompt,
        "next_prompt_options": next_prompt_options,
        "proposal_id": None,
        "scenario_type": entities.get("goal_type") or _classify_learning_goal(message),
        "scenario_label": _scenario_label(
            entities.get("goal_type") or _classify_learning_goal(message)
        ),
    }
