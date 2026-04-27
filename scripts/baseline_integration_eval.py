from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import get_db
from app.middleware import register_middleware
from app.models import Base
from app.routers import auth, chat

SCENARIO_KEYWORDS = {
    "exam_prep": ("考试", "复习", "冲刺", "刷题", "备考"),
    "skill_building": ("python", "java", "c++", "编程", "项目", "刷题"),
    "course_exploration": ("课程", "专业课", "数据结构", "操作系统", "计网", "数据库"),
}


def _auth_headers(client: AsyncClient) -> dict[str, str]:
    return {
        "origin": "http://localhost:8000",
        "x-csrf-token": client.cookies.get("study_companion_csrf", ""),
    }


def _classify_scenario(text: str) -> str:
    lowered = text.lower()
    for scenario, keywords in SCENARIO_KEYWORDS.items():
        if any(keyword in text or keyword in lowered for keyword in keywords):
            return scenario
    return "general"


async def _build_test_app() -> tuple[FastAPI, async_sessionmaker[AsyncSession], object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app = FastAPI()
    register_middleware(app)
    app.include_router(auth.router, prefix="/api/auth")
    app.include_router(chat.router, prefix="/api/chat")
    app.dependency_overrides[get_db] = override_get_db
    return app, session_factory, engine


async def main() -> None:
    os.environ.setdefault("APP_ENV", "testing")
    os.environ.setdefault("SECRET_KEY", "baseline-integration-secret")
    samples = json.loads(Path("docs/baseline_samples.json").read_text(encoding="utf-8"))
    sample_subset = samples[:30]

    app, _, engine = await _build_test_app()
    with (
        patch(
            "app.services.chat_service.call_llm_for_intent",
            new=AsyncMock(return_value={"intent": "general_chat", "entities": {}}),
        ),
        patch(
            "app.services.chat_service.call_llm_api",
            new=AsyncMock(return_value="好的，我帮你安排好了。"),
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            register_resp = await client.post(
                "/api/auth/register",
                json={
                    "username": "integration_user",
                    "email": "integration@example.com",
                    "password": "Password123",
                },
            )
            if register_resp.status_code != 201:
                raise RuntimeError(f"register failed: {register_resp.status_code} {register_resp.text}")

            success_count = 0
            clarify_count = 0
            fallback_count = 0
            by_scenario: dict[str, dict[str, int]] = {}

            for sample in sample_subset:
                scenario = _classify_scenario(sample["text"])
                if scenario not in by_scenario:
                    by_scenario[scenario] = {
                        "total": 0,
                        "success_count": 0,
                        "clarify_count": 0,
                        "fallback_count": 0,
                    }
                by_scenario[scenario]["total"] += 1
                resp = await client.post(
                    "/api/chat",
                    json={"message": sample["text"], "session_id": None},
                    headers=_auth_headers(client),
                )
                if resp.status_code != 200:
                    continue
                payload = resp.json()
                extracted_tasks = payload.get("extracted_tasks") or []
                extracted_plans = payload.get("extracted_plans") or []
                if extracted_tasks or extracted_plans:
                    success_count += 1
                    by_scenario[scenario]["success_count"] += 1
                if payload.get("intent") == "clarify_plan":
                    clarify_count += 1
                    by_scenario[scenario]["clarify_count"] += 1
                if payload.get("reply") == "抱歉，我暂时无法回复，请稍后再试":
                    fallback_count += 1
                    by_scenario[scenario]["fallback_count"] += 1

    await engine.dispose()

    total = len(sample_subset)
    result = {
        "sample_count": total,
        "conversation_success_rate": round(success_count / total, 4) if total else 0.0,
        "clarification_rate": round(clarify_count / total, 4) if total else 0.0,
        "llm_fallback_degradation_rate": round(fallback_count / total, 4) if total else 0.0,
        "counts": {
            "success_count": success_count,
            "clarify_count": clarify_count,
            "fallback_count": fallback_count,
        },
        "notes": "路由级集成评估：通过 /api/chat 真实链路评估，LLM/NLP 采用固定 mock。",
    }
    result["by_scenario"] = {
        scenario: {
            "total": values["total"],
            "conversation_success_rate": round(values["success_count"] / values["total"], 4) if values["total"] else 0.0,
            "clarification_rate": round(values["clarify_count"] / values["total"], 4) if values["total"] else 0.0,
            "llm_fallback_degradation_rate": round(values["fallback_count"] / values["total"], 4) if values["total"] else 0.0,
            "counts": {
                "success_count": values["success_count"],
                "clarify_count": values["clarify_count"],
                "fallback_count": values["fallback_count"],
            },
        }
        for scenario, values in sorted(by_scenario.items())
    }
    output = Path("docs/baseline_integration_metrics.json")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Wrote integration metrics to {output}")


if __name__ == "__main__":
    asyncio.run(main())
