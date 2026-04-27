import secrets
import json
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.errors import conflict, not_found, unauthorized
from app.models import ChatMessage, ChatSession, User
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    UserPreference,
    UserProfile,
    UserProfileUpdate,
)

router = APIRouter()


def _soft_preference_weight(now: datetime, created_at: datetime | None) -> float:
    if created_at is None:
        return 0.5
    if created_at.tzinfo is not None:
        created_at = created_at.astimezone(timezone.utc).replace(tzinfo=None)
    age = now.replace(tzinfo=None) - created_at
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
    now = datetime.now(timezone.utc)
    score_map: dict[str, float] = {}
    for value, created_at in values:
        if not isinstance(value, str) or not value.strip():
            continue
        normalized = value.strip().lower()
        score_map[normalized] = score_map.get(normalized, 0.0) + _soft_preference_weight(now, created_at)
    if not score_map:
        return None
    selected, score = max(score_map.items(), key=lambda item: item[1])
    if score < 0.8:
        return None
    return selected


async def _resolve_tone_preference(user: User, db: AsyncSession) -> UserPreference:
    manual_tone = (user.companion_tone_style or "").strip().lower()
    is_locked = bool(user.companion_tone_locked)
    if manual_tone in {"gentle", "direct", "motivational"} and is_locked:
        return UserPreference(
            companion_tone_style=manual_tone,
            companion_tone_source="manual",
            companion_tone_locked=True,
            companion_tone_manual_style=manual_tone,
            companion_tone_effective_style=manual_tone,
            companion_tone_source_detail="hard",
            response_density="standard",
            response_density_source="default",
        )

    result = await db.execute(
        select(ChatMessage.entities_json, ChatMessage.created_at)
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .where(ChatSession.user_id == user.id, ChatMessage.entities_json.is_not(None))
        .order_by(ChatMessage.created_at.desc())
        .limit(100)
    )
    soft_tone_candidates: list[tuple[str, datetime | None]] = []
    soft_density_candidates: list[tuple[str, datetime | None]] = []
    for row in result.all():
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
        preferences = payload.get("user_preferences")
        if not isinstance(preferences, dict):
            continue
        tone_style = (preferences.get("tone_style") or "").strip().lower()
        response_density = (preferences.get("response_density") or "").strip().lower()
        if tone_style in {"gentle", "direct", "motivational"}:
            soft_tone_candidates.append((tone_style, created_at))
        if response_density in {"concise", "standard", "detailed"}:
            soft_density_candidates.append((response_density, created_at))

    soft_tone = _pick_soft_preference(soft_tone_candidates)
    soft_density = _pick_soft_preference(soft_density_candidates)

    if manual_tone in {"gentle", "direct", "motivational"}:
        return UserPreference(
            companion_tone_style=manual_tone,
            companion_tone_source="manual",
            companion_tone_locked=is_locked,
            companion_tone_manual_style=manual_tone,
            companion_tone_effective_style=manual_tone,
            companion_tone_source_detail="hard",
            response_density=soft_density or "standard",
            response_density_source="soft" if soft_density else "default",
        )

    if soft_tone:
        return UserPreference(
            companion_tone_style=soft_tone,
            companion_tone_source="auto",
            companion_tone_locked=is_locked,
            companion_tone_manual_style=None,
            companion_tone_effective_style=soft_tone,
            companion_tone_source_detail="soft",
            response_density=soft_density or "standard",
            response_density_source="soft" if soft_density else "default",
        )

    return UserPreference(
        companion_tone_style="gentle",
        companion_tone_source="default",
        companion_tone_locked=is_locked,
        companion_tone_manual_style=None,
        companion_tone_effective_style="gentle",
        companion_tone_source_detail="default",
        response_density=soft_density or "standard",
        response_density_source="soft" if soft_density else "default",
    )


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def _create_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "exp": now + timedelta(hours=settings.JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _create_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=token,
        max_age=settings.AUTH_COOKIE_MAX_AGE_SECONDS,
        expires=settings.AUTH_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        path="/",
    )


def _set_csrf_cookie(response: Response, csrf_token: str) -> None:
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=settings.AUTH_COOKIE_MAX_AGE_SECONDS,
        expires=settings.AUTH_COOKIE_MAX_AGE_SECONDS,
        httponly=False,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.CSRF_COOKIE_SAMESITE,
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.AUTH_COOKIE_NAME,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        path="/",
    )


def _clear_csrf_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.CSRF_COOKIE_NAME,
        httponly=False,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.CSRF_COOKIE_SAMESITE,
        path="/",
    )


def _set_session_cookies(response: Response, token: str) -> None:
    _set_auth_cookie(response, token)
    _set_csrf_cookie(response, _create_csrf_token())


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none() is not None:
        raise conflict("用户名已被占用")

    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise conflict("邮箱已被注册")

    user = User(
        username=body.username,
        email=body.email,
        password_hash=_hash_password(body.password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    token = _create_token(user.id)
    _set_session_cookies(response, token)
    return AuthResponse(user=UserProfile.model_validate(user))


@router.post("/login", response_model=AuthResponse)
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()

    if user is None or not _verify_password(body.password, user.password_hash):
        raise unauthorized("用户名或密码错误")

    token = _create_token(user.id)
    _set_session_cookies(response, token)
    return AuthResponse(user=UserProfile.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response):
    _clear_auth_cookie(response)
    _clear_csrf_cookie(response)


@router.get("/profile", response_model=UserProfile)
async def get_profile(
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise not_found("用户不存在")
    return UserProfile.model_validate(user)


@router.put("/profile", response_model=UserProfile)
async def update_profile(
    body: UserProfileUpdate,
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise not_found("用户不存在")

    if body.nickname is not None:
        user.nickname = body.nickname
    if body.avatar_url is not None:
        user.avatar_url = body.avatar_url

    await db.flush()
    await db.refresh(user)
    return UserProfile.model_validate(user)


@router.get("/preferences", response_model=UserPreference)
async def get_preferences(
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise not_found("用户不存在")
    return await _resolve_tone_preference(user, db)


@router.put("/preferences", response_model=UserPreference)
async def update_preferences(
    body: UserPreference,
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise not_found("用户不存在")
    user.companion_tone_style = body.companion_tone_style
    user.companion_tone_locked = bool(body.companion_tone_locked)
    await db.flush()
    await db.refresh(user)
    return UserPreference(
        companion_tone_style=user.companion_tone_style or "gentle",
        companion_tone_source="manual",
        companion_tone_locked=bool(user.companion_tone_locked),
        companion_tone_manual_style=user.companion_tone_style or "gentle",
        companion_tone_effective_style=user.companion_tone_style or "gentle",
        companion_tone_source_detail="hard",
        response_density="standard",
        response_density_source="default",
    )
