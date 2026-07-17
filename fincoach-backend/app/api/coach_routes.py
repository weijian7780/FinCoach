"""Authenticated REST API for saved financial-coaching conversations."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from app.auth import AuthenticatedUser, require_authenticated_user
from app.coaching_history import (
    CoachingHistoryRepository,
    CoachingRateLimitExceeded,
    ConversationNotFound,
)
from app.models import (
    CoachTurnResponse,
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
    MessageCreate,
    MessageResponse,
)
from app.rag.service import CoachingConflict, CoachingService
from app.supabase_client import get_supabase, get_user_supabase


router = APIRouter(prefix="/coach", tags=["AI Financial Coaching"])


def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> AuthenticatedUser:
    return require_authenticated_user(authorization)


def get_coaching_repository(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> CoachingHistoryRepository:
    admin_client = get_supabase()
    return CoachingHistoryRepository(
        user_client=get_user_supabase(user.token),
        admin_client=admin_client,
        user_id=user.user_id,
    )


def get_coaching_service(
    repository: Annotated[CoachingHistoryRepository, Depends(get_coaching_repository)],
) -> CoachingService:
    return CoachingService(repository, repository.admin_client)


Repository = Annotated[CoachingHistoryRepository, Depends(get_coaching_repository)]
Service = Annotated[CoachingService, Depends(get_coaching_service)]


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Conversation not found.")


@router.get("/conversations", response_model=list[ConversationResponse])
def list_conversations(repository: Repository):
    return repository.list_sessions(50)


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(payload: ConversationCreate, repository: Repository):
    return repository.create_session(payload.title)


@router.patch("/conversations/{session_id}", response_model=ConversationResponse)
def rename_conversation(session_id: str, payload: ConversationUpdate, repository: Repository):
    try:
        return repository.rename_session(session_id, payload.title)
    except ConversationNotFound as exc:
        raise _not_found() from exc


@router.delete("/conversations/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(session_id: str, repository: Repository):
    try:
        repository.delete_session(session_id)
    except ConversationNotFound as exc:
        raise _not_found() from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/conversations/{session_id}/messages", response_model=list[MessageResponse])
def list_messages(session_id: str, repository: Repository):
    try:
        messages = repository.list_messages(session_id, 100)
    except ConversationNotFound as exc:
        raise _not_found() from exc
    result = []
    for message in messages:
        item = dict(message)
        item["sources"] = (
            repository.list_retrievals(item["id"])
            if item.get("role") == "assistant"
            else []
        )
        result.append(item)
    return result


@router.post(
    "/conversations/{session_id}/messages",
    response_model=CoachTurnResponse,
    status_code=status.HTTP_201_CREATED,
)
def send_message(session_id: str, payload: MessageCreate, service: Service):
    try:
        return service.send_message(session_id, str(payload.message_id), payload.content)
    except ConversationNotFound as exc:
        raise _not_found() from exc
    except CoachingConflict as exc:
        raise HTTPException(409, "Message is already being processed.") from exc
    except CoachingRateLimitExceeded as exc:
        raise HTTPException(429, "Coaching message limit reached.") from exc
    except TimeoutError as exc:
        raise HTTPException(504, "Coaching provider timed out.") from exc
    except Exception as exc:
        if "timeout" in type(exc).__name__.lower():
            raise HTTPException(504, "Coaching provider timed out.") from exc
        raise HTTPException(502, "Coaching provider is unavailable.") from exc
