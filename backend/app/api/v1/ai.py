from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import NotFoundError, ValidationAppError
from app.database import get_db
from app.dependencies import get_current_verified_user
from app.models.ai import AIConversation, AIMessage
from app.models.user import User
from app.services.ai_provider import get_ai_provider
from app.services.rate_limit_service import enforce_rate_limit

router = APIRouter(prefix="/ai", tags=["ai"])
settings = get_settings()

_CODING_HINTS = re.compile(
    r"\b(?:code|coding|program|programming|algorithm|debug|debugging|bug|error|exception|"
    r"python|javascript|typescript|java|c\+\+|c#|golang|go|rust|kotlin|swift|php|ruby|"
    r"html|css|sql|postgres|mysql|mongodb|react|next\.?js|node\.?js|fastapi|django|flask|"
    r"git|github|docker|api|rest|graphql|regex|function|class|object|variable|array|list|"
    r"tuple|dictionary|map|set|loop|recursion|pointer|query|database|terminal|shell|bash|"
    r"powershell|compiler|runtime|framework|library|package|dependency|syntax|stack trace)\b",
    re.IGNORECASE,
)


def _is_coding_question(content: str) -> bool:
    text = content.strip()
    if not text:
        return False
    if "```" in text or re.search(r"[{};]|=>|\bSELECT\b|\bdef\s+\w+\s*\(|\bimport\s+\w+", text, re.IGNORECASE):
        return True
    return bool(_CODING_HINTS.search(text))


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    provider: str

    model_config = {"from_attributes": True}


class SendMessageRequest(BaseModel):
    content: str


class SendMessageResponse(BaseModel):
    conversation_id: uuid.UUID
    reply: MessageOut


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AIConversation).where(AIConversation.user_id == user.id, AIConversation.archived_at.is_(None))
        .order_by(AIConversation.updated_at.desc())
    )
    return result.scalars().all()


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    convo = AIConversation(user_id=user.id)
    db.add(convo)
    await db.commit()
    await db.refresh(convo)
    return convo


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def get_messages(conversation_id: uuid.UUID, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    convo = await db.get(AIConversation, conversation_id)
    if convo is None or convo.user_id != user.id:
        raise NotFoundError("Conversation not found.")
    result = await db.execute(select(AIMessage).where(AIMessage.conversation_id == conversation_id).order_by(AIMessage.created_at))
    return result.scalars().all()


@router.post("/conversations/{conversation_id}/messages", response_model=SendMessageResponse)
async def send_message(conversation_id: uuid.UUID, payload: SendMessageRequest,
                       user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    convo = await db.get(AIConversation, conversation_id)
    if convo is None or convo.user_id != user.id:
        raise NotFoundError("Conversation not found.")

    content = payload.content.strip()
    if not _is_coding_question(content):
        raise ValidationAppError(
            "The AI Tutor is limited to coding and programming questions. Ask about code, debugging, algorithms, software development, or related technical topics."
        )

    await enforce_rate_limit(f"ai-daily:{user.id}", limit=settings.AI_DAILY_MESSAGE_LIMIT, window_seconds=86400)

    user_message = AIMessage(conversation_id=conversation_id, role="user", content=content)
    db.add(user_message)
    await db.flush()

    history = (await db.execute(select(AIMessage).where(AIMessage.conversation_id == conversation_id).order_by(AIMessage.created_at))).scalars().all()
    provider = get_ai_provider()
    response = await provider.chat(
        [{"role": m.role, "content": m.content} for m in history if m.role in ("user", "assistant")],
        system_prompt=(
            "You are the Survival School coding tutor. Answer ONLY coding and software-development questions. "
            "Be concise, accurate, educational, and practical. Explain concepts, code, debugging, algorithms, "
            "databases, APIs, developer tools, and related technical topics. Refuse unrelated questions briefly "
            "and redirect the student to a coding topic. Never provide non-coding content."
        ),
    )

    assistant_message = AIMessage(
        conversation_id=conversation_id, role="assistant",
        content=response.content or "Sorry, I couldn't generate a response right now — please try again shortly.",
        provider=response.provider, tokens_used=response.tokens_used, latency_ms=response.latency_ms, error=response.error,
    )
    db.add(assistant_message)
    await db.commit()
    await db.refresh(assistant_message)

    return SendMessageResponse(conversation_id=conversation_id, reply=MessageOut.model_validate(assistant_message))
