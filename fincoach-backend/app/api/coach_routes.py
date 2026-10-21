"""Authenticated REST API for saved financial-coaching conversations."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status

from app.agent_actions import (
    AgentActionConflict,
    AgentActionNotFound,
    AgentActionService,
)
from app.auth import AuthenticatedUser, require_authenticated_user
from app.coaching_history import (
    ActionProtocolError,
    ActionStateConflict,
    CoachingHistoryRepository,
    CoachingRateLimitExceeded,
    ConversationNotFound,
    MessageNotFound,
)
from app.config import COACH_PROVIDER_CONSENT_VERSION, COACH_WRITE_ACTIONS_ENABLED
from app.models import (
    CoachActionCompletion,
    CoachActionDecision,
    CoachActionResponse,
    CoachReportAttemptResponse,
    CoachTurnResponse,
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
    MessageCreate,
    MessageFeedbackUpdate,
    MessagePageResponse,
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


def get_agent_action_service(
    repository: Annotated[CoachingHistoryRepository, Depends(get_coaching_repository)],
) -> AgentActionService:
    return AgentActionService(
        repository,
        repository.admin_client,
        writes_enabled=COACH_WRITE_ACTIONS_ENABLED,
    )


Repository = Annotated[CoachingHistoryRepository, Depends(get_coaching_repository)]
Service = Annotated[CoachingService, Depends(get_coaching_service)]
ActionService = Annotated[AgentActionService, Depends(get_agent_action_service)]


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Conversation not found.")


def _message_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Message not found.")


def require_current_provider_consent(
    x_fincoach_provider_consent: Annotated[str | None, Header()] = None,
) -> None:
    """Block new provider-bound messages until this app version disclosed routing."""
    if x_fincoach_provider_consent != COACH_PROVIDER_CONSENT_VERSION:
        raise HTTPException(status_code=403, detail="AI provider consent is required.")


ProviderConsent = Annotated[None, Depends(require_current_provider_consent)]


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


@router.get("/conversations/{session_id}/messages", response_model=MessagePageResponse)
def list_messages(
    session_id: str,
    repository: Repository,
    limit: int = Query(default=30, ge=1, le=30),
    before: str | None = None,
):
    try:
        page = repository.list_message_page(session_id, limit=limit, before=before)
    except ConversationNotFound as exc:
        raise _not_found() from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail='Invalid history cursor.') from exc

    messages = page["messages"]
    assistant_ids = [
        str(message["id"])
        for message in messages
        if message.get("role") == "assistant"
    ]
    sources_by_message_id: dict[str, list[dict]] = {}
    for source in repository.list_retrievals_for_messages(assistant_ids):
        message_id = str(source.get("assistant_message_id", ""))
        if not message_id:
            continue
        source_payload = {
            key: value
            for key, value in source.items()
            if key != "assistant_message_id"
        }
        sources_by_message_id.setdefault(message_id, []).append(source_payload)

    result: list[dict] = []
    for message in messages:
        item = dict(message)
        snapshot = (item.get("ui_payload") or {}).get("source_snapshot")
        item["sources"] = (
            snapshot if isinstance(snapshot, list) and len(snapshot) <= 10
            else sources_by_message_id.get(str(item["id"]), [])
        )
        result.append(item)
    return {"messages": result, "next_before": page.get("next_before")}


@router.patch("/messages/{message_id}/feedback", response_model=MessageResponse)
def set_message_feedback(
    message_id: str,
    payload: MessageFeedbackUpdate,
    repository: Repository,
):
    try:
        return repository.set_message_feedback(message_id, payload.feedback)
    except MessageNotFound as exc:
        raise _message_not_found() from exc


def _run_action(operation):
    try:
        return operation()
    except ActionProtocolError as exc:
        # A protocol refusal carries a stable code the mobile reconciles by;
        # the optional lease detail never widens what the client may do.
        detail: dict[str, Any] = {"code": exc.code, "message": str(exc)}
        if exc.lease_expires_at:
            detail["lease_expires_at"] = exc.lease_expires_at
        raise HTTPException(exc.status_code, detail) from exc
    except (AgentActionNotFound, MessageNotFound) as exc:
        raise HTTPException(404, "Action not found.") from exc
    except AgentActionConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ActionStateConflict as exc:
        raise HTTPException(409, {
            'code': 'report_state_conflict',
            'message': 'This report action changed or its category is unavailable. Reopen the chat or ask for a new report.',
        }) from exc


def _required_uuid(value: str, detail: str) -> str:
    try:
        return str(UUID(value))
    except (TypeError, ValueError) as exc:
        raise HTTPException(404, detail) from exc


def _attempt_id(payload: CoachActionDecision) -> str | None:
    return str(payload.attempt_id) if payload.attempt_id else None


@router.post(
    "/messages/{message_id}/actions/confirm",
    response_model=CoachActionResponse,
)
def confirm_action(
    message_id: str,
    payload: CoachActionDecision,
    service: ActionService,
):
    return _run_action(
        lambda: service.confirm(
            message_id, str(payload.action_id), attempt_id=_attempt_id(payload),
        )
    )


@router.post(
    "/messages/{message_id}/actions/cancel",
    response_model=CoachActionResponse,
)
def cancel_action(
    message_id: str,
    payload: CoachActionDecision,
    service: ActionService,
):
    return _run_action(lambda: service.cancel(message_id, str(payload.action_id)))


@router.post(
    "/messages/{message_id}/actions/complete",
    response_model=CoachActionResponse,
)
def complete_action(
    message_id: str,
    payload: CoachActionCompletion,
    service: ActionService,
):
    return _run_action(
        lambda: service.complete(
            message_id,
            str(payload.action_id),
            success=payload.success,
            result=payload.result,
            attempt_id=_attempt_id(payload),
        )
    )


@router.get(
    "/messages/{message_id}/actions/report-attempt/{attempt_id}",
    response_model=CoachReportAttemptResponse,
)
def get_report_attempt(
    message_id: str,
    attempt_id: str,
    repository: Repository,
):
    """Owner-scoped attempt status so a device can reconcile a lost response."""
    attempt = repository.find_report_attempt(
        message_id, _required_uuid(attempt_id, "Report attempt not found."),
    )
    if not attempt:
        raise HTTPException(404, "Report attempt not found.")
    return attempt


@router.post(
    "/messages/{message_id}/actions/report-attempt/{attempt_id}/renew",
    response_model=CoachReportAttemptResponse,
)
def renew_report_attempt(
    message_id: str,
    attempt_id: str,
    repository: Repository,
):
    """Extend the caller's live report lease while the PDF is still rendering."""
    try:
        return repository.renew_report_attempt(
            message_id, _required_uuid(attempt_id, "Report attempt not found."),
        )
    except MessageNotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post(
    "/conversations/{session_id}/messages",
    response_model=CoachTurnResponse,
    status_code=status.HTTP_201_CREATED,
)
def send_message(
    session_id: str,
    payload: MessageCreate,
    service: Service,
    _: ProviderConsent,
):
    try:
        interaction_reply = (
            payload.interaction_reply.model_dump(mode="json")
            if payload.interaction_reply
            else None
        )
        if interaction_reply:
            return service.send_message(
                session_id,
                str(payload.message_id),
                payload.content,
                interaction_reply=interaction_reply,
            )
        return service.send_message(
            session_id,
            str(payload.message_id),
            payload.content,
        )
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
