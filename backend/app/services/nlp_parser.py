"""NLP 意图识别与实体提取模块。

通过调用大模型 API 分析用户消息，返回意图和实体信息。
无效意图或 JSON 解析失败时降级为 general_chat。
"""

import json
import logging
from typing import Any

from app.config import settings
from app.services.llm_adapter import call_llm_api

logger = logging.getLogger(__name__)

VALID_INTENTS = frozenset(
    [
        "create_task",
        "query_task",
        "update_task",
        "complete_task",
        "create_plan",
        "query_stats",
        "general_chat",
    ]
)

_INTENT_SYSTEM_PROMPT = (
    "你是一个意图识别助手。分析用户消息，返回严格的 JSON 格式结果。\n"
    "可能的意图（intent）：create_task, query_task, update_task, "
    "complete_task, create_plan, query_stats, general_chat。\n"
    "需要提取的实体（entities）：task_title, due_date, priority, task_id, "
    "date_range, description, status。\n"
    '返回格式：{"intent": "...", "entities": {...}}\n'
    "只返回 JSON，不要包含其他文字。"
)


def _format_history(messages: list[dict]) -> list[dict]:
    """将对话历史格式化为 OpenAI messages 格式。"""
    formatted = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role in ("user", "assistant"):
            formatted.append({"role": role, "content": content})
    return formatted


async def call_llm_for_intent(
    message: str,
    history: list[dict] | None = None,
) -> dict[str, Any]:
    """调用大模型识别用户意图并提取实体。

    Parameters
    ----------
    message:
        当前用户消息。
    history:
        对话历史列表，每条包含 role 和 content。

    Returns
    -------
    dict
        ``{"intent": str, "entities": dict}``，intent 保证属于 VALID_INTENTS。
    """
    if history is None:
        history = []

    # 仅取最近 6 条消息（3 轮对话）作为上下文
    recent_context = history[-6:] if len(history) > 6 else history

    messages: list[dict] = [
        {"role": "system", "content": _INTENT_SYSTEM_PROMPT},
        *_format_history(recent_context),
        {"role": "user", "content": message},
    ]

    try:
        response = await call_llm_api(
            messages,
            response_format="json",
            model=settings.LLM_EXTRACTION_MODEL,
        )
        result = json.loads(response)
    except (json.JSONDecodeError, TypeError, KeyError) as exc:
        logger.warning("意图识别 JSON 解析失败，降级为 general_chat: %s", exc)
        return {"intent": "general_chat", "entities": {}}

    # 验证意图有效性
    intent = result.get("intent", "general_chat")
    if intent not in VALID_INTENTS:
        logger.warning("无效意图 '%s'，降级为 general_chat", intent)
        intent = "general_chat"

    entities = result.get("entities", {})
    if not isinstance(entities, dict):
        entities = {}

    return {"intent": intent, "entities": entities}
