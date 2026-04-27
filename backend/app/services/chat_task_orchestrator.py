from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chat_actions import ChatActionResult, execute_chat_action
from app.services.chat_rule_parser import (
    build_fallback_entities,
    build_plan_clarification_question,
    determine_fallback_intent,
    looks_like_consultation_question,
    looks_like_continuation_request,
    looks_like_plan_follow_up_answer,
    looks_like_refinement_request,
    looks_like_resource_enrichment_request,
    needs_plan_clarification,
)
from app.services.chat_time_parser import parse_natural_due_date


def resolve_intent(
    message: str,
    nlp_result: dict[str, Any] | None,
    recent_context: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    if not nlp_result:
        intent = "chat"
        entities: dict[str, Any] = {}
    else:
        intent = nlp_result.get("intent", "chat")
        entities = nlp_result.get("entities") or {}

    if intent in {"create_plan", "create_task"} and looks_like_consultation_question(message):
        intent = "chat"
        entities = {}

    if intent in {"chat", "general_chat"}:
        fallback_intent = determine_fallback_intent(message)
        if fallback_intent != "chat":
            intent = fallback_intent
            fallback_entities = build_fallback_entities(message)
            entities = {**fallback_entities, **(recent_context or {}), **entities}

    if (
        (looks_like_refinement_request(message) or looks_like_continuation_request(message))
        and recent_context
        and (recent_context.get("plan_id") or recent_context.get("task_id"))
    ):
        intent = "refine_plan" if recent_context.get("plan_id") else "create_task"
        fallback_entities = build_fallback_entities(message)
        entities = {**fallback_entities, **recent_context, **entities}
        entities["refine_existing"] = True
        if recent_context.get("plan_title"):
            entities["plan_title"] = recent_context["plan_title"]
        if recent_context.get("task_title"):
            entities["task_title"] = recent_context["task_title"]
        elif recent_context.get("plan_title"):
            entities["task_title"] = recent_context["plan_title"]

    if (
        recent_context
        and recent_context.get("plan_id")
        and looks_like_resource_enrichment_request(message)
    ):
        intent = "refine_plan"
        fallback_entities = build_fallback_entities(message)
        entities = {**fallback_entities, **recent_context, **entities}
        entities["refine_existing"] = True
        if recent_context.get("plan_title"):
            entities["plan_title"] = recent_context["plan_title"]
            entities["task_title"] = entities.get("task_title") or recent_context["plan_title"]

    pending_plan_request = (recent_context or {}).get("pending_plan_request")
    if pending_plan_request and not (recent_context or {}).get("plan_id"):
        if intent in {
            "chat",
            "general_chat",
            "refine_plan",
            "create_plan",
        } and looks_like_plan_follow_up_answer(message):
            intent = "create_plan"
            fallback_entities = build_fallback_entities(message)
            pending_entities = pending_plan_request.get("entities") or {}
            entities = {
                **pending_entities,
                **fallback_entities,
                **entities,
            }
            entities["plan_description"] = (
                f"{pending_plan_request.get('message', '').strip()}；{message.strip()}".strip("；")
            )
            if not entities.get("task_title") and entities.get("plan_title"):
                entities["task_title"] = entities["plan_title"]

    return intent, entities


def should_clarify_before_action(
    intent: str,
    message: str,
    entities: dict[str, Any],
    recent_context: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    if intent not in {"create_plan", "chat", "general_chat"}:
        return False, None
    if not needs_plan_clarification(message, entities, recent_context):
        return False, None
    return True, build_plan_clarification_question(message, entities)


async def execute_intent(
    user_id: int,
    message: str,
    intent: str,
    entities: dict[str, Any],
    db: AsyncSession,
) -> tuple[Any, list[dict[str, Any]] | None, list[dict[str, Any]] | None]:
    due_date = None
    if intent in {"create_task", "create_plan"}:
        due_date = parse_natural_due_date(entities.get("due_date"), message)

    result: ChatActionResult = await execute_chat_action(
        user_id=user_id,
        intent=intent,
        entities=entities,
        fallback_message=message,
        db=db,
        due_date=due_date,
    )
    return result.payload, result.extracted_tasks, result.extracted_plans
