"""Authenticated financial context and persistent coaching orchestration."""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.coaching_history import CoachingHistoryRepository
from app.config import COACH_HISTORY_LIMIT, COACH_RATE_LIMIT_DAY, COACH_RATE_LIMIT_MINUTE
from app.llm import generate_result
from app.rag.prompts import build_coach_prompt
from app.rag.retrieval import RetrievedChunk, retrieve


class CoachingConflict(RuntimeError):
    pass


def _money(value: Any) -> str:
    return f"RM{Decimal(str(value or 0)):.2f}"


def format_financial_context(
    profile: dict | None,
    transactions: list[dict],
    monthly_budget: dict | None,
    category_limits: list[dict],
    savings_goals: list[dict],
) -> str:
    profile = profile or {}
    parts = ["All figures below are recorded in FinCoach; no bank balance is assumed."]
    if profile.get("monthly_allowance") is not None:
        parts.append(f"Monthly allowance: {_money(profile['monthly_allowance'])}")
    if profile.get("coaching_style"):
        parts.append(f"Preferred coaching style: {profile['coaching_style']}")
    if monthly_budget and monthly_budget.get("limit_amount") is not None:
        parts.append(f"Monthly budget limit: {_money(monthly_budget['limit_amount'])}")

    spending: dict[str, Decimal] = defaultdict(Decimal)
    expenses = Decimal("0")
    for transaction in transactions:
        category = transaction.get("category") or {}
        if category.get("type") != "expense":
            continue
        amount = Decimal(str(transaction.get("amount") or 0))
        expenses += amount
        spending[category.get("name") or "Uncategorised"] += amount
    parts.append(f"Recorded expense total: {_money(expenses)}")
    limits = {(item.get("category") or {}).get("name"): item.get("amount") for item in category_limits}
    for name in sorted(spending):
        suffix = f" / {_money(limits[name])} limit" if name in limits else ""
        parts.append(f"{name}: {_money(spending[name])} spent{suffix}")
    for goal in savings_goals:
        parts.append(
            f"Savings goal {goal.get('name')}: {_money(goal.get('current_amount'))} / "
            f"{_money(goal.get('target_amount'))}"
        )
    if transactions:
        parts.append("Recent recorded transactions: " + "; ".join(
            f"{item.get('source') or 'Transaction'} {_money(item.get('amount'))}"
            for item in transactions[:8]
        ))
    return "\n".join(parts)


def fetch_financial_context(admin_client: Any, user_id: str, today: date | None = None) -> str:
    today = today or date.today()
    month_start = today.replace(day=1)
    next_month = date(today.year + (today.month == 12), 1 if today.month == 12 else today.month + 1, 1)

    def execute(query: Any) -> Any:
        return query.execute().data

    profile = execute(admin_client.table("profiles").select(
        "monthly_allowance, financial_status, coaching_style, university"
    ).eq("id", user_id).maybe_single())
    transactions = execute(admin_client.table("transactions").select(
        "amount, source, transaction_date, category:categories(name,type)"
    ).eq("user_id", user_id).gte("transaction_date", month_start.isoformat()).lt(
        "transaction_date", next_month.isoformat()
    ).order("transaction_date", desc=True).limit(100)) or []
    monthly_budget = execute(admin_client.table("monthly_budgets").select("limit_amount").eq(
        "user_id", user_id
    ).eq("month", month_start.isoformat()).maybe_single())
    category_limits = execute(admin_client.table("budgets").select(
        "amount, category:categories(name)"
    ).eq("user_id", user_id).eq("month", month_start.isoformat())) or []
    goals = execute(admin_client.table("savings_goals").select(
        "name, target_amount, current_amount, deadline"
    ).eq("user_id", user_id).order("created_at", desc=False)) or []
    return format_financial_context(profile, transactions, monthly_budget, category_limits, goals)


def source_rows(chunks: list[RetrievedChunk]) -> list[dict]:
    return [
        {"title": chunk.title, "source": chunk.source, "similarity": chunk.similarity, "rank": index}
        for index, chunk in enumerate(chunks, start=1)
    ]


class CoachingService:
    def __init__(self, repository: CoachingHistoryRepository, admin_client: Any):
        self.repository = repository
        self.admin_client = admin_client

    def send_message(self, session_id: str, message_id: str, content: str) -> dict:
        session = self.repository.require_session(session_id)
        user_message = self.repository.find_user_message(message_id)
        if user_message and (
            user_message.get("session_id") != session_id or user_message.get("content") != content
        ):
            raise CoachingConflict("Message identifier is already in use.")
        if user_message:
            reply = self.repository.find_reply(message_id)
            if reply:
                return {
                    "user_message": user_message,
                    "assistant_message": reply,
                    "sources": self.repository.list_retrievals(reply["id"]),
                }
            raise CoachingConflict("Message is already being processed.")
        else:
            self.repository.enforce_usage_limits(COACH_RATE_LIMIT_MINUTE, COACH_RATE_LIMIT_DAY)
            user_message = self.repository.insert_user_message(session_id, message_id, content)

        history = self.repository.list_messages(session_id, COACH_HISTORY_LIMIT)
        context = fetch_financial_context(self.admin_client, self.repository.user_id)
        chunks = retrieve(content)
        result = generate_result(build_coach_prompt(content, chunks, context, history, COACH_HISTORY_LIMIT))
        assistant = self.repository.insert_assistant_reply({
            "id": str(uuid4()),
            "session_id": session_id,
            "user_id": self.repository.user_id,
            "role": "assistant",
            "content": result.content,
            "reply_to_message_id": message_id,
            "status": "completed",
            "model": result.model,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
        })
        sources = source_rows(chunks)
        self.repository.insert_retrievals([
            {
                "user_id": self.repository.user_id,
                "assistant_message_id": assistant["id"],
                "knowledge_document_id": chunk.id,
                "rank": source["rank"],
                "similarity": chunk.similarity,
                "title": chunk.title,
                "source": chunk.source,
            }
            for chunk, source in zip(chunks, sources)
        ])
        self.repository.update_session_after_message(
            session_id,
            content if session.get("title") == "New conversation" else None,
        )
        return {"user_message": user_message, "assistant_message": assistant, "sources": sources}
