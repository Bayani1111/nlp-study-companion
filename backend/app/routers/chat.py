from fastapi import APIRouter, Depends, HTTPException, status
import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import ChatMessage, ChatSession
from app.schemas.chat import ChatRequest, ChatResponse, MessageInfo, SessionInfo
from app.services.chat_service import process_chat_message

router = APIRouter()


def _safe_parse_entities(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


@router.post("", response_model=ChatResponse)
async def send_message(
    body: ChatRequest,
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a message and return the AI reply."""
    result = await process_chat_message(
        user_id,
        body.session_id,
        body.message,
        db,
        proposal_id=body.proposal_id,
    )
    return ChatResponse(**result)


@router.get("/sessions", response_model=list[SessionInfo])
async def list_sessions(
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all chat sessions for the current user."""
    stmt = (
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.updated_at.desc())
    )
    result = await db.execute(stmt)
    sessions = result.scalars().all()
    return [SessionInfo.model_validate(session) for session in sessions]


@router.get("/sessions/{session_id}", response_model=list[MessageInfo])
async def get_session_history(
    session_id: int,
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the message history for a session owned by the current user."""
    session_result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )
    )
    if session_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在",
        )

    msg_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    messages = msg_result.scalars().all()
    return [
        MessageInfo(
            id=message.id,
            role=message.role,
            content=message.content,
            intent=message.intent,
            entities=_safe_parse_entities(message.entities_json),
            created_at=message.created_at,
        )
        for message in messages
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: int,
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a session owned by the current user."""
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在",
        )
    await db.delete(session)
    await db.flush()
