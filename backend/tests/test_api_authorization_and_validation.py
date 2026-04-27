from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import get_db
from app.middleware import register_middleware
from app.models import Base
from app.routers import auth, plans, tasks


@pytest.fixture
async def api_test_app():
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
    app.include_router(tasks.router, prefix="/api/tasks")
    app.include_router(plans.router, prefix="/api/plans")
    app.dependency_overrides[get_db] = override_get_db

    try:
        yield app
    finally:
        await engine.dispose()


async def register_user(client: AsyncClient, username: str, email: str) -> dict:
    response = await client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": email,
            "password": "Password123",
        },
    )
    assert response.status_code == 201
    return response.json()["user"]


def auth_headers(client: AsyncClient) -> dict[str, str]:
    return {
        "origin": "http://localhost:8000",
        "x-csrf-token": client.cookies.get("study_companion_csrf"),
    }


@pytest.mark.asyncio
async def test_register_rejects_duplicate_username(api_test_app: FastAPI):
    async with AsyncClient(
        transport=ASGITransport(app=api_test_app),
        base_url="http://testserver",
    ) as client:
        await register_user(client, "duplicate_user", "first@example.com")
        response = await client.post(
            "/api/auth/register",
            json={
                "username": "duplicate_user",
                "email": "second@example.com",
                "password": "Password123",
            },
            headers=auth_headers(client),
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "用户名已被占用"


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(api_test_app: FastAPI):
    async with AsyncClient(
        transport=ASGITransport(app=api_test_app),
        base_url="http://testserver",
    ) as client:
        await register_user(client, "first_user", "duplicate@example.com")
        response = await client.post(
            "/api/auth/register",
            json={
                "username": "second_user",
                "email": "duplicate@example.com",
                "password": "Password123",
            },
            headers=auth_headers(client),
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "邮箱已被注册"


@pytest.mark.asyncio
async def test_task_routes_require_authentication(api_test_app: FastAPI):
    async with AsyncClient(
        transport=ASGITransport(app=api_test_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/tasks")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_cannot_update_another_users_task(api_test_app: FastAPI):
    async with (
        AsyncClient(
            transport=ASGITransport(app=api_test_app),
            base_url="http://testserver",
        ) as owner_client,
        AsyncClient(
            transport=ASGITransport(app=api_test_app),
            base_url="http://testserver",
        ) as other_client,
    ):
        await register_user(owner_client, "owner_user", "owner@example.com")
        create_response = await owner_client.post(
            "/api/tasks",
            json={"title": "Owner Task"},
            headers=auth_headers(owner_client),
        )
        assert create_response.status_code == 201
        task_id = create_response.json()["id"]

        await register_user(other_client, "other_user", "other@example.com")
        update_response = await other_client.put(
            f"/api/tasks/{task_id}",
            json={"title": "Hijacked"},
            headers=auth_headers(other_client),
        )

    assert update_response.status_code == 404
    assert update_response.json()["detail"] == "任务不存在"


@pytest.mark.asyncio
async def test_user_cannot_delete_another_users_plan(api_test_app: FastAPI):
    async with (
        AsyncClient(
            transport=ASGITransport(app=api_test_app),
            base_url="http://testserver",
        ) as owner_client,
        AsyncClient(
            transport=ASGITransport(app=api_test_app),
            base_url="http://testserver",
        ) as other_client,
    ):
        await register_user(owner_client, "plan_owner", "plan-owner@example.com")
        create_response = await owner_client.post(
            "/api/plans",
            json={
                "title": "Owner Plan",
                "start_date": "2026-05-01",
                "end_date": "2026-05-10",
            },
            headers=auth_headers(owner_client),
        )
        assert create_response.status_code == 201
        plan_id = create_response.json()["id"]

        await register_user(other_client, "plan_other", "plan-other@example.com")
        delete_response = await other_client.delete(
            f"/api/plans/{plan_id}",
            headers=auth_headers(other_client),
        )

    assert delete_response.status_code == 404
    assert delete_response.json()["detail"] == "学习计划不存在"


@pytest.mark.asyncio
async def test_create_task_rejects_past_due_date(api_test_app: FastAPI):
    past_due = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

    async with AsyncClient(
        transport=ASGITransport(app=api_test_app),
        base_url="http://testserver",
    ) as client:
        await register_user(client, "task_user", "task@example.com")
        response = await client.post(
            "/api/tasks",
            json={"title": "Past Task", "due_date": past_due},
            headers=auth_headers(client),
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "截止时间不能早于当前时间"


@pytest.mark.asyncio
async def test_update_task_rejects_past_due_date(api_test_app: FastAPI):
    past_due = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

    async with AsyncClient(
        transport=ASGITransport(app=api_test_app),
        base_url="http://testserver",
    ) as client:
        await register_user(client, "task_update_user", "task-update@example.com")
        create_response = await client.post(
            "/api/tasks",
            json={"title": "Future Task"},
            headers=auth_headers(client),
        )
        task_id = create_response.json()["id"]

        response = await client.put(
            f"/api/tasks/{task_id}",
            json={"due_date": past_due},
            headers=auth_headers(client),
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "截止时间不能早于当前时间"


@pytest.mark.asyncio
async def test_create_task_rejects_other_users_plan(api_test_app: FastAPI):
    async with (
        AsyncClient(
            transport=ASGITransport(app=api_test_app),
            base_url="http://testserver",
        ) as owner_client,
        AsyncClient(
            transport=ASGITransport(app=api_test_app),
            base_url="http://testserver",
        ) as other_client,
    ):
        await register_user(owner_client, "plan_source", "plan-source@example.com")
        plan_response = await owner_client.post(
            "/api/plans",
            json={
                "title": "Private Plan",
                "start_date": "2026-06-01",
                "end_date": "2026-06-10",
            },
            headers=auth_headers(owner_client),
        )
        plan_id = plan_response.json()["id"]

        await register_user(other_client, "task_target", "task-target@example.com")
        task_response = await other_client.post(
            "/api/tasks",
            json={"title": "Cross-linked Task", "plan_id": plan_id},
            headers=auth_headers(other_client),
        )

    assert task_response.status_code == 404
    assert task_response.json()["detail"] == "学习计划不存在"


@pytest.mark.asyncio
async def test_update_task_rejects_other_users_plan(api_test_app: FastAPI):
    async with (
        AsyncClient(
            transport=ASGITransport(app=api_test_app),
            base_url="http://testserver",
        ) as owner_client,
        AsyncClient(
            transport=ASGITransport(app=api_test_app),
            base_url="http://testserver",
        ) as other_client,
    ):
        await register_user(owner_client, "shared_plan_owner", "shared-plan-owner@example.com")
        plan_response = await owner_client.post(
            "/api/plans",
            json={
                "title": "Owner Only Plan",
                "start_date": "2026-07-01",
                "end_date": "2026-07-15",
            },
            headers=auth_headers(owner_client),
        )
        plan_id = plan_response.json()["id"]

        await register_user(other_client, "task_owner", "task-owner@example.com")
        task_response = await other_client.post(
            "/api/tasks",
            json={"title": "Own Task"},
            headers=auth_headers(other_client),
        )
        task_id = task_response.json()["id"]

        update_response = await other_client.put(
            f"/api/tasks/{task_id}",
            json={"plan_id": plan_id},
            headers=auth_headers(other_client),
        )

    assert update_response.status_code == 404
    assert update_response.json()["detail"] == "学习计划不存在"


@pytest.mark.asyncio
async def test_plan_update_rejects_invalid_date_boundary(api_test_app: FastAPI):
    async with AsyncClient(
        transport=ASGITransport(app=api_test_app),
        base_url="http://testserver",
    ) as client:
        await register_user(client, "plan_user", "plan@example.com")
        create_response = await client.post(
            "/api/plans",
            json={
                "title": "Valid Plan",
                "start_date": "2026-08-01",
                "end_date": "2026-08-10",
            },
            headers=auth_headers(client),
        )
        plan_id = create_response.json()["id"]

        response = await client.put(
            f"/api/plans/{plan_id}",
            json={"end_date": "2026-07-31"},
            headers=auth_headers(client),
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "开始日期不能晚于结束日期"


@pytest.mark.asyncio
async def test_plan_and_task_list_only_return_owned_records(api_test_app: FastAPI):
    async with (
        AsyncClient(
            transport=ASGITransport(app=api_test_app),
            base_url="http://testserver",
        ) as first_client,
        AsyncClient(
            transport=ASGITransport(app=api_test_app),
            base_url="http://testserver",
        ) as second_client,
    ):
        await register_user(first_client, "list_owner", "list-owner@example.com")
        await first_client.post(
            "/api/plans",
            json={
                "title": "Owner Plan",
                "start_date": "2026-09-01",
                "end_date": "2026-09-05",
            },
            headers=auth_headers(first_client),
        )
        await first_client.post(
            "/api/tasks",
            json={"title": "Owner Task"},
            headers=auth_headers(first_client),
        )

        await register_user(second_client, "list_other", "list-other@example.com")
        plans_response = await second_client.get("/api/plans")
        tasks_response = await second_client.get("/api/tasks")

    assert plans_response.status_code == 200
    assert tasks_response.status_code == 200
    assert plans_response.json() == []
    assert tasks_response.json() == []


@pytest.mark.asyncio
async def test_create_subtask_rejects_other_users_parent(api_test_app: FastAPI):
    async with (
        AsyncClient(
            transport=ASGITransport(app=api_test_app),
            base_url="http://testserver",
        ) as owner_client,
        AsyncClient(
            transport=ASGITransport(app=api_test_app),
            base_url="http://testserver",
        ) as other_client,
    ):
        await register_user(owner_client, "parent_owner", "parent-owner@example.com")
        parent_response = await owner_client.post(
            "/api/tasks",
            json={"title": "Owner Parent Task"},
            headers=auth_headers(owner_client),
        )
        parent_id = parent_response.json()["id"]

        await register_user(other_client, "subtask_other", "subtask-other@example.com")
        child_response = await other_client.post(
            "/api/tasks",
            json={"title": "Illegal Child", "parent_task_id": parent_id},
            headers=auth_headers(other_client),
        )

    assert child_response.status_code == 404
    assert child_response.json()["detail"] == "任务不存在"


@pytest.mark.asyncio
async def test_create_subtask_returns_nested_children_in_task_list(api_test_app: FastAPI):
    async with AsyncClient(
        transport=ASGITransport(app=api_test_app),
        base_url="http://testserver",
    ) as client:
        await register_user(client, "nested_user", "nested@example.com")
        parent_response = await client.post(
            "/api/tasks",
            json={"title": "主任务"},
            headers=auth_headers(client),
        )
        parent_id = parent_response.json()["id"]

        child_response = await client.post(
            "/api/tasks",
            json={"title": "子任务", "parent_task_id": parent_id},
            headers=auth_headers(client),
        )
        assert child_response.status_code == 201

        list_response = await client.get("/api/tasks")

    payload = list_response.json()
    assert len(payload) == 1
    assert payload[0]["title"] == "主任务"
    assert payload[0]["subtask_count"] == 1
    assert payload[0]["children"][0]["title"] == "子任务"


@pytest.mark.asyncio
async def test_cleanup_advisory_subtasks_dry_run_returns_candidates_without_deleting(
    api_test_app: FastAPI,
):
    async with AsyncClient(
        transport=ASGITransport(app=api_test_app),
        base_url="http://testserver",
    ) as client:
        await register_user(client, "cleanup_preview_user", "cleanup-preview@example.com")
        parent_response = await client.post(
            "/api/tasks",
            json={"title": "主任务"},
            headers=auth_headers(client),
        )
        parent_id = parent_response.json()["id"]

        await client.post(
            "/api/tasks",
            json={
                "title": "第1天任务3 · 目标：能写出清晰、模块化的代码",
                "description": "目标：能写出清晰、模块化的代码，熟练使用函数、类。",
                "parent_task_id": parent_id,
            },
            headers=auth_headers(client),
        )
        await client.post(
            "/api/tasks",
            json={
                "title": "第1天任务1 · 19:00-20:00 复习数据结构数组和链表",
                "description": "晚上19:00-20:00完成复习并整理错题。",
                "parent_task_id": parent_id,
            },
            headers=auth_headers(client),
        )

        cleanup_response = await client.post(
            "/api/tasks/cleanup/advisory?dry_run=true",
            headers=auth_headers(client),
        )
        list_response = await client.get("/api/tasks")

    assert cleanup_response.status_code == 200
    payload = cleanup_response.json()
    assert payload["dry_run"] is True
    assert payload["matched_count"] == 1
    assert payload["deleted_count"] == 0
    assert len(payload["candidates"]) == 1
    assert "目标" in payload["candidates"][0]["title"]
    assert list_response.status_code == 200
    assert list_response.json()[0]["subtask_count"] == 2


@pytest.mark.asyncio
async def test_cleanup_advisory_subtasks_apply_deletes_candidates(api_test_app: FastAPI):
    async with AsyncClient(
        transport=ASGITransport(app=api_test_app),
        base_url="http://testserver",
    ) as client:
        await register_user(client, "cleanup_apply_user", "cleanup-apply@example.com")
        parent_response = await client.post(
            "/api/tasks",
            json={"title": "主任务"},
            headers=auth_headers(client),
        )
        parent_id = parent_response.json()["id"]

        await client.post(
            "/api/tasks",
            json={
                "title": "第1天任务4 · 学习内容（精简版）",
                "description": "学习内容（精简版）",
                "parent_task_id": parent_id,
            },
            headers=auth_headers(client),
        )
        await client.post(
            "/api/tasks",
            json={
                "title": "第1天任务1 · 19:00-20:00 复习数据结构数组和链表",
                "description": "晚上19:00-20:00完成复习并整理错题。",
                "parent_task_id": parent_id,
            },
            headers=auth_headers(client),
        )

        cleanup_response = await client.post(
            "/api/tasks/cleanup/advisory?dry_run=false",
            headers=auth_headers(client),
        )
        list_response = await client.get("/api/tasks")

    assert cleanup_response.status_code == 200
    payload = cleanup_response.json()
    assert payload["dry_run"] is False
    assert payload["matched_count"] == 1
    assert payload["deleted_count"] == 1
    assert list_response.status_code == 200
    root = list_response.json()[0]
    assert root["subtask_count"] == 1
    assert len(root["children"]) == 1
    assert "复习数据结构" in root["children"][0]["title"]
