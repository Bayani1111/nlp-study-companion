from app.services.chat_task_orchestrator import resolve_intent


def test_resolve_intent_downgrades_consultation_question_from_create_plan():
    intent, entities = resolve_intent(
        message="学几个核心课程，你推荐哪些？",
        nlp_result={"intent": "create_plan", "entities": {"plan_title": "学几个核心课程"}},
        recent_context=None,
    )

    assert intent == "chat"
    assert entities == {}


def test_resolve_intent_downgrades_consultation_question_from_create_task():
    intent, entities = resolve_intent(
        message="计算机专业课先学哪门更好？",
        nlp_result={"intent": "create_task", "entities": {"task_title": "先学哪门"}},
        recent_context=None,
    )

    assert intent == "chat"
    assert entities == {}


def test_resolve_intent_routes_resource_request_to_refine_existing_plan():
    intent, entities = resolve_intent(
        message="帮我一起把学习资源配上吧",
        nlp_result={"intent": "create_plan", "entities": {"plan_title": "学习资源"}},
        recent_context={
            "plan_id": 12,
            "plan_title": "计算机核心课程学习计划",
            "task_id": 30,
            "task_title": "主任务",
        },
    )

    assert intent == "refine_plan"
    assert entities["refine_existing"] is True
    assert entities["plan_title"] == "计算机核心课程学习计划"
