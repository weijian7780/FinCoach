"""Pydantic contracts for authenticated AI coaching APIs."""

from typing import Literal
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


class MessageCreate(StrictModel):
    message_id: UUID
    content: str = Field(min_length=1, max_length=1000)

    @field_validator("content")
    @classmethod
    def clean_content(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("content must not be empty")
        return cleaned


class SourceResponse(StrictModel):
    title: str | None = None
    source: str | None = None
    similarity: float
    rank: int


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
    created_at: str
    sources: list[SourceResponse] = Field(default_factory=list)


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
