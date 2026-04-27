import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import get_db
from app.dependencies import get_current_user
from app.middleware import register_middleware
from app.models import Base
from app.routers.auth import router as auth_router


@pytest.fixture
async def auth_test_app():
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
    app.include_router(auth_router, prefix="/api/auth")

    @app.get("/api/me")
    async def read_me(user_id: int = Depends(get_current_user)):
        return {"user_id": user_id}

    app.dependency_overrides[get_db] = override_get_db

    try:
        yield app
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_register_sets_http_only_cookie(auth_test_app: FastAPI):
    async with AsyncClient(
        transport=ASGITransport(app=auth_test_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/auth/register",
            json={
                "username": "cookie_user",
                "email": "cookie@example.com",
                "password": "Password123",
            },
        )

    assert response.status_code == 201
    assert response.json()["access_token"] is None
    cookie_header = response.headers.get("set-cookie", "")
    assert "study_companion_session=" in cookie_header
    assert "HttpOnly" in cookie_header
    assert "study_companion_csrf=" in cookie_header


@pytest.mark.asyncio
async def test_cookie_auth_grants_access_to_protected_route(auth_test_app: FastAPI):
    async with AsyncClient(
        transport=ASGITransport(app=auth_test_app),
        base_url="http://testserver",
    ) as client:
        register_response = await client.post(
            "/api/auth/register",
            json={
                "username": "session_user",
                "email": "session@example.com",
                "password": "Password123",
            },
        )
        assert register_response.status_code == 201

        profile_response = await client.get("/api/auth/profile")
        me_response = await client.get("/api/me")

    assert profile_response.status_code == 200
    assert profile_response.json()["username"] == "session_user"
    assert me_response.status_code == 200
    assert me_response.json()["user_id"] > 0


@pytest.mark.asyncio
async def test_logout_clears_cookie_and_blocks_followup_requests(auth_test_app: FastAPI):
    async with AsyncClient(
        transport=ASGITransport(app=auth_test_app),
        base_url="http://testserver",
    ) as client:
        register_response = await client.post(
            "/api/auth/register",
            json={
                "username": "logout_user",
                "email": "logout@example.com",
                "password": "Password123",
            },
        )
        assert register_response.status_code == 201

        csrf_token = client.cookies.get("study_companion_csrf")
        logout_response = await client.post(
            "/api/auth/logout",
            headers={
                "origin": "http://localhost:8000",
                "x-csrf-token": csrf_token,
            },
        )
        profile_response = await client.get("/api/auth/profile")

    assert logout_response.status_code == 204
    cookie_header = logout_response.headers.get("set-cookie", "")
    assert "study_companion_session=" in cookie_header
    assert "Max-Age=0" in cookie_header or "expires=" in cookie_header.lower()
    assert profile_response.status_code == 401


@pytest.mark.asyncio
async def test_cookie_requests_require_trusted_origin_and_csrf_token(auth_test_app: FastAPI):
    async with AsyncClient(
        transport=ASGITransport(app=auth_test_app),
        base_url="http://testserver",
    ) as client:
        register_response = await client.post(
            "/api/auth/register",
            json={
                "username": "csrf_user",
                "email": "csrf@example.com",
                "password": "Password123",
            },
        )
        assert register_response.status_code == 201

        missing_headers_response = await client.put(
            "/api/auth/profile",
            json={"nickname": "unsafe"},
        )
        invalid_origin_response = await client.put(
            "/api/auth/profile",
            json={"nickname": "unsafe"},
            headers={
                "origin": "http://evil.example",
                "x-csrf-token": client.cookies.get("study_companion_csrf"),
            },
        )
        valid_response = await client.put(
            "/api/auth/profile",
            json={"nickname": "safe"},
            headers={
                "origin": "http://localhost:8000",
                "x-csrf-token": client.cookies.get("study_companion_csrf"),
            },
        )

    assert missing_headers_response.status_code == 403
    assert missing_headers_response.json()["detail"] == "不受信任的请求来源"
    assert invalid_origin_response.status_code == 403
    assert valid_response.status_code == 200
    assert valid_response.json()["nickname"] == "safe"


@pytest.mark.asyncio
async def test_cookie_requests_reject_missing_csrf_even_with_trusted_origin(auth_test_app: FastAPI):
    async with AsyncClient(
        transport=ASGITransport(app=auth_test_app),
        base_url="http://testserver",
    ) as client:
        register_response = await client.post(
            "/api/auth/register",
            json={
                "username": "csrf_only_user",
                "email": "csrf-only@example.com",
                "password": "Password123",
            },
        )
        assert register_response.status_code == 201

        response = await client.put(
            "/api/auth/profile",
            json={"nickname": "blocked"},
            headers={"origin": "http://localhost:8000"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF 校验失败"


@pytest.mark.asyncio
async def test_can_read_and_update_tone_style_preference(auth_test_app: FastAPI):
    async with AsyncClient(
        transport=ASGITransport(app=auth_test_app),
        base_url="http://testserver",
    ) as client:
        register_response = await client.post(
            "/api/auth/register",
            json={
                "username": "pref_user",
                "email": "pref@example.com",
                "password": "Password123",
            },
        )
        assert register_response.status_code == 201

        read_response = await client.get("/api/auth/preferences")
        update_response = await client.put(
            "/api/auth/preferences",
            json={"companion_tone_style": "direct", "companion_tone_locked": True},
            headers={
                "origin": "http://localhost:8000",
                "x-csrf-token": client.cookies.get("study_companion_csrf"),
            },
        )
        read_after_update_response = await client.get("/api/auth/preferences")

    assert read_response.status_code == 200
    assert read_response.json()["companion_tone_style"] == "gentle"
    assert read_response.json()["companion_tone_source"] == "default"
    assert read_response.json()["companion_tone_locked"] is False
    assert read_response.json()["companion_tone_source_detail"] == "default"
    assert read_response.json()["response_density"] == "standard"
    assert read_response.json()["response_density_source"] == "default"
    assert update_response.status_code == 200
    assert update_response.json()["companion_tone_style"] == "direct"
    assert update_response.json()["companion_tone_source"] == "manual"
    assert update_response.json()["companion_tone_locked"] is True
    assert update_response.json()["companion_tone_source_detail"] == "hard"
    assert read_after_update_response.status_code == 200
    assert read_after_update_response.json()["companion_tone_style"] == "direct"
    assert read_after_update_response.json()["companion_tone_source"] == "manual"
    assert read_after_update_response.json()["companion_tone_locked"] is True
    assert read_after_update_response.json()["companion_tone_source_detail"] == "hard"
