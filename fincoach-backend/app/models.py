"""Pydantic contracts for authenticated AI coaching APIs."""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConversationCreate(StrictModel):
    title: str = Field(default="New conversation", min_length=1, max_length=80)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("title must not be empty")
        return cleaned


class ConversationUpdate(StrictModel):
    title: str = Field(min_length=1, max_length=80)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("title must not be empty")
        return cleaned


class CoachInteractionReply(StrictModel):
    assistant_message_id: UUID
    value: str = Field(min_length=1, max_length=1000)

    @field_validator("value")
    @classmethod
    def clean_value(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value must not be empty")
        return cleaned


class MessageCreate(StrictModel):
    message_id: UUID
    content: str = Field(min_length=1, max_length=1000)
    interaction_reply: CoachInteractionReply | None = None

    @field_validator("content")
    @classmethod
    def clean_content(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("content must not be empty")
        return cleaned


class MessageFeedbackUpdate(StrictModel):
    feedback: Literal["helpful", "not_helpful"] | None


class CoachActionDecision(StrictModel):
    action_id: UUID


class CoachActionCompletion(CoachActionDecision):
    success: bool
    result: dict[str, Any] = Field(default_factory=dict)


class SourceResponse(StrictModel):
    title: str | None = None
    source: str | None = None
    similarity: float
    rank: int
    # Web-research fallback fields. Corpus sources keep the defaults, so the
    # existing contract is unchanged for callers that only read corpus results.
    url: str | None = None
    source_type: Literal["corpus", "web"] = "corpus"
    tier: int | None = None
    confidence: Literal["established", "reported", "anecdotal", "insufficient"] | None = None


class MessageResponse(StrictModel):
    id: UUID
    session_id: UUID
    user_id: UUID
    role: Literal["user", "assistant"]
    content: str
    reply_to_message_id: UUID | None = None
    status: Literal["completed", "failed"] = "completed"
    error_code: str | None = None
    model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    feedback: Literal["helpful", "not_helpful"] | None = None
    ui_payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    sources: list[SourceResponse] = Field(default_factory=list)


class MessagePageResponse(StrictModel):
    messages: list[MessageResponse] = Field(default_factory=list)
    next_before: str | None = None


class ConversationResponse(StrictModel):
    id: UUID
    user_id: UUID
    title: str
    created_at: str
    updated_at: str
    last_message_at: str


class CoachTurnResponse(StrictModel):
    user_message: MessageResponse
    assistant_message: MessageResponse
    sources: list[SourceResponse] = Field(default_factory=list)


class CoachActionResponse(StrictModel):
    message: MessageResponse
    effect: dict[str, Any] | None = None
