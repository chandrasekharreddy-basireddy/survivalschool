from __future__ import annotations

import base64
import os
import uuid

import magic
from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import NotFoundError, ServiceUnavailableError, ValidationAppError
from app.database import get_db
from app.dependencies import get_current_verified_user
from app.models.ai import AIConversation, AIMessage
from app.models.system import FileObject
from app.models.user import User
from app.services import storage_service
from app.services.ai_provider import get_ai_provider
from app.services.rate_limit_service import enforce_rate_limit

router = APIRouter(prefix="/ai", tags=["ai"])
settings = get_settings()

_TUTOR_SYSTEM_PROMPT = (
    "You are the Survival School AI tutor. Help the student with questions across coding, software, "
    "coursework, mathematics, science, study skills, general knowledge, and other educational topics. "
    "Be clear, accurate, friendly, and practical. For academic questions, explain the reasoning and "
    "guide learning instead of helping a student bypass an assessment. Keep answers appropriate for a "
    "school learning environment. When the student attaches an image, look at it carefully and answer "
    "based on what it actually shows."
)

_ALLOWED_IMAGE_MIME_TO_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    provider: str
    image_url: str | None = None

    model_config = {"from_attributes": True}


class SendMessageRequest(BaseModel):
    content: str


class SendMessageResponse(BaseModel):
    conversation_id: uuid.UUID
    reply: MessageOut


def _image_url(file_id: uuid.UUID | None) -> str | None:
    # Deliberately WITHOUT API_V1_PREFIX — see files.py::_file_url's comment;
    # the frontend appends this to API_BASE, which already ends in /api/v1.
    return f"/files/{file_id}" if file_id else None


def _to_message_out(message: AIMessage) -> MessageOut:
    return MessageOut(
        id=message.id, role=message.role, content=message.content, provider=message.provider,
        image_url=_image_url(message.image_file_id),
    )


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
    result = await db.execute(
        select(AIMessage)
        .where(AIMessage.conversation_id == conversation_id)
        .order_by(AIMessage.created_at)
    )
    return [_to_message_out(m) for m in result.scalars().all()]


async def _get_owned_conversation(db: AsyncSession, conversation_id: uuid.UUID, user: User) -> AIConversation:
    convo = await db.get(AIConversation, conversation_id)
    if convo is None or convo.user_id != user.id:
        raise NotFoundError("Conversation not found.")
    return convo


async def _run_assistant_turn(db: AsyncSession, conversation_id: uuid.UUID, *, image_data_url: str | None = None) -> AIMessage:
    """Shared tail end of both send-message paths: load history, call the
    provider, persist and return the assistant's reply. Called after the
    caller has already added (and flushed) the user's own AIMessage."""
    history = (
        await db.execute(
            select(AIMessage)
            .where(AIMessage.conversation_id == conversation_id)
            .order_by(AIMessage.created_at)
        )
    ).scalars().all()

    provider = get_ai_provider()
    response = await provider.chat(
        [{"role": m.role, "content": m.content} for m in history if m.role in ("user", "assistant")],
        system_prompt=_TUTOR_SYSTEM_PROMPT,
        image_data_url=image_data_url,
    )

    if not response.content and image_data_url:
        # Confirmed in production logs: the vision model (SARVAM_VISION_MODEL
        # = gemma4) returns a hard 400 "This endpoint is currently in beta
        # and not available" for this account — an account-tier limitation,
        # not a transient failure, so "try again shortly" would be actively
        # misleading (it will keep failing every time until Sarvam grants
        # beta access). Tell the user what's actually true instead.
        fallback = "Image analysis isn't available on this account right now — try describing the problem in text instead."
    else:
        fallback = "Sorry, I couldn't generate a response right now — please try again shortly."

    assistant_message = AIMessage(
        conversation_id=conversation_id,
        role="assistant",
        content=response.content or fallback,
        provider=response.provider,
        tokens_used=response.tokens_used,
        latency_ms=response.latency_ms,
        error=response.error,
    )
    db.add(assistant_message)
    await db.commit()
    await db.refresh(assistant_message)
    return assistant_message


@router.post("/conversations/{conversation_id}/messages", response_model=SendMessageResponse)
async def send_message(
    conversation_id: uuid.UUID,
    payload: SendMessageRequest,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_conversation(db, conversation_id, user)

    content = payload.content.strip()
    if not content:
        return SendMessageResponse(
            conversation_id=conversation_id,
            reply=MessageOut(
                id=uuid.uuid4(),
                role="assistant",
                content="Please enter a question or message so I can help.",
                provider="system",
            ),
        )

    await enforce_rate_limit(f"ai-daily:{user.id}", limit=settings.AI_DAILY_MESSAGE_LIMIT, window_seconds=86400)

    db.add(AIMessage(conversation_id=conversation_id, role="user", content=content))
    await db.flush()

    assistant_message = await _run_assistant_turn(db, conversation_id)
    return SendMessageResponse(conversation_id=conversation_id, reply=_to_message_out(assistant_message))


@router.post("/conversations/{conversation_id}/messages/image", response_model=SendMessageResponse)
async def send_message_with_image(
    conversation_id: uuid.UUID,
    content: str = Form(default=""),
    file: UploadFile = File(...),
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Same conversation turn as POST .../messages, but with an image
    attached — routed to Sarvam's vision-capable model (see
    ai_provider.py::SarvamAIProvider.chat). The image is stored the same way
    any other upload is (app/services/storage_service.py) so it survives a
    conversation reload, and separately base64-encoded straight into the
    request payload so the model doesn't depend on being able to reach back
    into this app's own storage."""
    await _get_owned_conversation(db, conversation_id, user)
    await enforce_rate_limit(f"ai-daily:{user.id}", limit=settings.AI_DAILY_MESSAGE_LIMIT, window_seconds=86400)

    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    raw = await file.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValidationAppError(f"Image exceeds the {settings.MAX_UPLOAD_MB}MB upload limit.")
    if not raw:
        raise ValidationAppError("Uploaded image is empty.")

    sniffed_mime = magic.from_buffer(raw, mime=True)
    if sniffed_mime not in _ALLOWED_IMAGE_MIME_TO_EXT:
        raise ValidationAppError(f"Image type '{sniffed_mime}' isn't supported. Allowed: PNG, JPEG, GIF, WEBP.")

    ext = _ALLOWED_IMAGE_MIME_TO_EXT[sniffed_mime]
    storage_key = f"{uuid.uuid4().hex}{ext}"
    if settings.STORAGE_BACKEND == "supabase":
        try:
            await storage_service.upload_object(storage_key, raw, sniffed_mime)
        except storage_service.StorageNotConfiguredError as exc:
            raise ServiceUnavailableError(str(exc)) from exc
        except Exception as exc:
            raise ServiceUnavailableError("Image storage is temporarily unavailable. Please try again.") from exc
    else:
        dest_path = os.path.join(settings.STORAGE_LOCAL_PATH, storage_key)
        os.makedirs(settings.STORAGE_LOCAL_PATH, exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(raw)

    file_record = FileObject(
        owner_id=user.id, storage_backend=settings.STORAGE_BACKEND, storage_key=storage_key,
        original_filename=os.path.basename(file.filename or "image")[:255], mime_type=sniffed_mime,
        size_bytes=len(raw), visibility="private", scan_status="pending",
    )
    db.add(file_record)
    await db.flush()

    text_content = content.strip() or "What can you tell me about this image?"
    db.add(AIMessage(conversation_id=conversation_id, role="user", content=text_content, image_file_id=file_record.id))
    await db.flush()

    image_data_url = f"data:{sniffed_mime};base64,{base64.b64encode(raw).decode('ascii')}"
    assistant_message = await _run_assistant_turn(db, conversation_id, image_data_url=image_data_url)
    return SendMessageResponse(conversation_id=conversation_id, reply=_to_message_out(assistant_message))
