from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import forbidden
from app.models import ChatMessage, ChatSession

HistoryMessage = dict[str, str]
StructuredHistoryMessage = dict[str, Any]


def _parse_entities(raw_value: str | None) -> dict[str, Any]:
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def get_or_create_session(
    user_id: int,
    session_id: int | None,
    message: str,
    db: AsyncSession,
) -> ChatSession:
    if session_id is None:
        session = ChatSession(user_id=user_id, title=message[:50])
        db.add(session)
        await db.flush()
        await db.refresh(session)
        return session

    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )
    )
    existing_session = result.scalar_one_or_none()
    if existing_session is None:
        raise forbidden("无权访问该会话")
    return existing_session


async def load_structured_history(
    session_id: int,
    db: AsyncSession,
    limit: int = 20,
) -> list[StructuredHistoryMessage]:
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    messages = list(result.scalars().all())
    messages.reverse()
    return [
        {
            "role": message.role,
            "content": message.content,
            "intent": message.intent,
            "entities": _parse_entities(message.entities_json),
        }
        for message in messages
    ]


async def load_history(
    session_id: int,
    db: AsyncSession,
    limit: int = 20,
) -> list[HistoryMessage]:
    structured_history = await load_structured_history(session_id, db, limit=limit)
    return [
        {"role": message["role"], "content": message["content"]} for message in structured_history
    ]


async def save_message(
    session_id: int,
    role: str,
    content: str,
    db: AsyncSession,
    intent: str | None = None,
    entities_json: str | None = None,
) -> ChatMessage:
    message = ChatMessage(
        session_id=session_id,
        role=role,
        content=content,
        intent=intent,
        entities_json=entities_json,
    )
    db.add(message)
    await db.flush()
    return message
