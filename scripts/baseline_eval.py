from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from app.services.chat_rule_parser import build_fallback_entities, infer_priority
from app.services.chat_service import process_chat_message
from app.services.chat_time_parser import parse_natural_due_date
from app.services.llm_adapter import FALLBACK_REPLY

SCENARIO_KEYWORDS = {
    "exam_prep": ("考试", "复习", "冲刺", "刷题", "备考"),
    "skill_building": ("python", "java", "c++", "编程", "项目", "刷题"),
    "course_exploration": ("课程", "专业课", "数据结构", "操作系统", "计网", "数据库"),
}


@dataclass
class ExtractionMetrics:
    total: int = 0
    title_correct: int = 0
    time_correct: int = 0
    priority_correct: int = 0
    all_fields_correct: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "title_accuracy": _rate(self.title_correct, self.total),
            "time_accuracy": _rate(self.time_correct, self.total),
            "priority_accuracy": _rate(self.priority_correct, self.total),
            "all_fields_accuracy": _rate(self.all_fields_correct, self.total),
            "counts": {
                "title_correct": self.title_correct,
                "time_correct": self.time_correct,
                "priority_correct": self.priority_correct,
                "all_fields_correct": self.all_fields_correct,
            },
        }


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def load_samples(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("baseline samples must be a list")
    return raw


def classify_scenario(text: str) -> str:
    lowered = text.lower()
    for scenario, keywords in SCENARIO_KEYWORDS.items():
        if any(keyword in text or keyword in lowered for keyword in keywords):
            return scenario
    return "general"


def evaluate_extraction(samples: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    metrics = ExtractionMetrics()
    issues: list[dict[str, Any]] = []
    scenario_metrics: dict[str, ExtractionMetrics] = {}

    for sample in samples:
        text = sample["text"]
        expected = sample["expected"]
        scenario = classify_scenario(text)
        metrics.total += 1
        if scenario not in scenario_metrics:
            scenario_metrics[scenario] = ExtractionMetrics()
        scenario_metrics[scenario].total += 1

        entities = build_fallback_entities(text)
        title = (entities.get("task_title") or entities.get("plan_title") or "").strip()
        parsed_due = parse_natural_due_date(None, text)
        parsed_priority = entities.get("priority") or infer_priority(text)

        title_ok = all(keyword in title for keyword in expected["title_keywords"])
        time_ok = bool(parsed_due) == bool(expected["has_due_date"])
        priority_ok = parsed_priority == expected["priority"]

        if title_ok:
            metrics.title_correct += 1
            scenario_metrics[scenario].title_correct += 1
        if time_ok:
            metrics.time_correct += 1
            scenario_metrics[scenario].time_correct += 1
        if priority_ok:
            metrics.priority_correct += 1
            scenario_metrics[scenario].priority_correct += 1
        if title_ok and time_ok and priority_ok:
            metrics.all_fields_correct += 1
            scenario_metrics[scenario].all_fields_correct += 1

        if not (title_ok and time_ok and priority_ok):
            issues.append(
                {
                    "id": sample["id"],
                    "text": text,
                    "predicted": {
                        "title": title,
                        "has_due_date": bool(parsed_due),
                        "priority": parsed_priority,
                    },
                    "expected": expected,
                    "failed_fields": [
                        name
                        for name, ok in (
                            ("title", title_ok),
                            ("time", time_ok),
                            ("priority", priority_ok),
                        )
                        if not ok
                    ],
                }
            )

    payload = metrics.to_dict()
    payload["by_scenario"] = {
        scenario: scenario_data.to_dict() for scenario, scenario_data in sorted(scenario_metrics.items())
    }
    return payload, issues


async def _run_single_chat(
    *,
    text: str,
    force_fallback_reply: bool,
) -> dict[str, Any]:
    session = SimpleNamespace(id=1)
    default_action = (
        SimpleNamespace(id=100, title="auto task", children=[]),
        [{"id": 100, "title": "auto task", "parent_task_id": None}],
        None,
    )

    async def execute_intent_stub(**kwargs):
        intent = kwargs["intent"]
        if intent == "create_plan":
            return (
                {"plan": SimpleNamespace(id=200, title="auto plan"), "task": SimpleNamespace(id=201, title="auto task", children=[])},
                [{"id": 201, "title": "auto task", "parent_task_id": None}],
                [{"id": 200, "title": "auto plan"}],
            )
        if intent in {"create_task", "refine_plan"}:
            return default_action
        return (None, None, None)

    llm_reply = FALLBACK_REPLY if force_fallback_reply else "这是一个正常回复。"
    with (
        patch("app.services.chat_service.get_or_create_session", new=AsyncMock(return_value=session)),
        patch("app.services.chat_service.load_history", new=AsyncMock(return_value=[])),
        patch("app.services.chat_service.load_structured_history", new=AsyncMock(return_value=[])),
        patch("app.services.chat_service._hydrate_recent_action_context", new=AsyncMock(return_value={})),
        patch("app.services.chat_service.call_llm_for_intent", new=AsyncMock(return_value={"intent": "general_chat", "entities": {}})),
        patch("app.services.chat_service.execute_intent", new=AsyncMock(side_effect=execute_intent_stub)),
        patch("app.services.chat_service.call_llm_api", new=AsyncMock(return_value=llm_reply)),
        patch("app.services.chat_service.save_message", new=AsyncMock()),
        patch("app.services.chat_service.record_learning_activity", new=AsyncMock()),
    ):
        return await process_chat_message(
            user_id=1,
            session_id=None,
            message=text,
            db=AsyncMock(),
        )


async def evaluate_chat_metrics(samples: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(samples)
    clarify_count = 0
    success_count = 0
    fallback_count = 0
    by_scenario: dict[str, dict[str, int]] = {}

    for sample in samples:
        force_fallback = sample["id"] % 5 == 0
        result = await _run_single_chat(text=sample["text"], force_fallback_reply=force_fallback)
        scenario = classify_scenario(sample["text"])
        if scenario not in by_scenario:
            by_scenario[scenario] = {
                "total": 0,
                "success_count": 0,
                "clarify_count": 0,
                "fallback_count": 0,
            }
        by_scenario[scenario]["total"] += 1
        intent = result.get("intent")
        reply = result.get("reply", "")
        extracted_tasks = result.get("extracted_tasks") or []
        extracted_plans = result.get("extracted_plans") or []

        if intent == "clarify_plan":
            clarify_count += 1
            by_scenario[scenario]["clarify_count"] += 1
        if extracted_tasks or extracted_plans:
            success_count += 1
            by_scenario[scenario]["success_count"] += 1
        if reply == FALLBACK_REPLY:
            fallback_count += 1
            by_scenario[scenario]["fallback_count"] += 1

    payload = {
        "total": total,
        "conversation_success_rate": _rate(success_count, total),
        "clarification_rate": _rate(clarify_count, total),
        "llm_fallback_degradation_rate": _rate(fallback_count, total),
        "counts": {
            "success_count": success_count,
            "clarify_count": clarify_count,
            "fallback_count": fallback_count,
        },
        "notes": "对话指标通过模拟链路评估：NLP 固定为 general_chat，依赖当前规则兜底与编排逻辑。",
    }
    payload["by_scenario"] = {
        scenario: {
            "total": values["total"],
            "conversation_success_rate": _rate(values["success_count"], values["total"]),
            "clarification_rate": _rate(values["clarify_count"], values["total"]),
            "llm_fallback_degradation_rate": _rate(values["fallback_count"], values["total"]),
            "counts": {
                "success_count": values["success_count"],
                "clarify_count": values["clarify_count"],
                "fallback_count": values["fallback_count"],
            },
        }
        for scenario, values in sorted(by_scenario.items())
    }
    return payload


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run baseline evaluation")
    parser.add_argument(
        "--samples",
        type=Path,
        default=Path("docs/baseline_samples.json"),
        help="Path to baseline sample file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/baseline_metrics.json"),
        help="Path to output metrics JSON",
    )
    args = parser.parse_args()

    samples = load_samples(args.samples)
    extraction_metrics, extraction_issues = evaluate_extraction(samples)
    chat_metrics = await evaluate_chat_metrics(samples)

    payload = {
        "sample_count": len(samples),
        "extraction_metrics": extraction_metrics,
        "chat_metrics": chat_metrics,
        "top_issues": extraction_issues[:15],
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote baseline metrics to {args.output}")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
