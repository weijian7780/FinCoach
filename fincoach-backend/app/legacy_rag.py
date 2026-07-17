"""Legacy RAG orchestration kept temporarily during the package split."""

from app.config import RETRIEVE_K
from app.embeddings import embed_query
from app.llm import generate
from app.supabase_client import get_supabase


def retrieve(question: str, k: int = RETRIEVE_K) -> list[dict]:
    query_embedding = embed_query(question)
    response = get_supabase().rpc(
        "match_knowledge_documents",
        {"query_embedding": query_embedding, "match_count": k},
    ).execute()
    return response.data or []


def fetch_user_context(user_id: str) -> str:
    sb = get_supabase()
    parts: list[str] = []
    profile = sb.table("profiles").select(
        "monthly_allowance, financial_status, coaching_style, university"
    ).eq("id", user_id).maybe_single().execute()
    if profile.data:
        data = profile.data
        if data.get("monthly_allowance") is not None:
            parts.append(f"Monthly allowance: RM{data['monthly_allowance']}")
        if data.get("financial_status"):
            parts.append(f"Financial status: {data['financial_status']}")
        if data.get("coaching_style"):
            parts.append(f"Preferred coaching style: {data['coaching_style']}")
    goals = sb.table("savings_goals").select(
        "name, target_amount, current_amount"
    ).eq("user_id", user_id).execute()
    for goal in goals.data or []:
        parts.append(
            f"Savings goal '{goal['name']}': saved RM{goal['current_amount']} "
            f"of RM{goal['target_amount']}"
        )
    return "\n".join(parts) if parts else "No financial profile data provided."


def build_prompt(question: str, chunks: list[dict], user_context: str) -> str:
    knowledge = "\n\n".join(
        f"[Source: {chunk.get('source') or 'unknown'}]\n{chunk['content']}"
        for chunk in chunks
    ) or "No relevant knowledge was found in the knowledge base."
    return (
        f"### Retrieved Malaysian finance knowledge\n{knowledge}\n\n"
        f"### Student's financial profile\n{user_context}\n\n"
        f"### Student's question\n{question}\n\n"
        "### Your advice:\n"
    )


def coach(question: str, user_id: str | None = None) -> dict:
    chunks = retrieve(question)
    context = fetch_user_context(user_id) if user_id else "No financial profile data provided."
    answer = generate(build_prompt(question, chunks, context))
    return {
        "answer": answer,
        "sources": [
            {
                "title": chunk.get("title"),
                "source": chunk.get("source"),
                "similarity": chunk.get("similarity"),
            }
            for chunk in chunks
        ],
    }
