"""The RAG pipeline (DIY — written by hand so it's fully yours to defend).

    question -> embed -> search pgvector -> + user's Supabase data -> prompt -> LLM
"""
from app.config import RETRIEVE_K
from app.embeddings import embed_query
from app.llm import generate
from app.supabase_client import get_supabase


def retrieve(question: str, k: int = RETRIEVE_K) -> list[dict]:
    """Vector search over knowledge_documents via the Postgres RPC."""
    query_embedding = embed_query(question)
    response = (
        get_supabase()
        .rpc(
            "match_knowledge_documents",
            {"query_embedding": query_embedding, "match_count": k},
        )
        .execute()
    )
    return response.data or []


def fetch_user_context(user_id: str) -> str:
    """Pull the student's own numbers so the advice is personalised, not generic."""
    sb = get_supabase()
    parts: list[str] = []

    profile = (
        sb.table("profiles")
        .select("monthly_allowance, financial_status, coaching_style, university")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    if profile.data:
        p = profile.data
        if p.get("monthly_allowance") is not None:
            parts.append(f"Monthly allowance: RM{p['monthly_allowance']}")
        if p.get("financial_status"):
            parts.append(f"Financial status: {p['financial_status']}")
        if p.get("coaching_style"):
            parts.append(f"Preferred coaching style: {p['coaching_style']}")

    goals = (
        sb.table("savings_goals")
        .select("name, target_amount, current_amount")
        .eq("user_id", user_id)
        .execute()
    )
    for g in goals.data or []:
        parts.append(
            f"Savings goal '{g['name']}': saved RM{g['current_amount']} of RM{g['target_amount']}"
        )

    return "\n".join(parts) if parts else "No financial profile data provided."


def build_prompt(question: str, chunks: list[dict], user_context: str) -> str:
    knowledge = "\n\n".join(
        f"[Source: {c.get('source') or 'unknown'}]\n{c['content']}" for c in chunks
    ) or "No relevant knowledge was found in the knowledge base."

    return (
        f"### Retrieved Malaysian finance knowledge\n{knowledge}\n\n"
        f"### Student's financial profile\n{user_context}\n\n"
        f"### Student's question\n{question}\n\n"
        f"### Your advice:\n"
    )


def coach(question: str, user_id: str | None = None) -> dict:
    chunks = retrieve(question)
    user_context = fetch_user_context(user_id) if user_id else "No financial profile data provided."
    prompt = build_prompt(question, chunks, user_context)
    answer = generate(prompt)
    sources = [
        {
            "title": c.get("title"),
            "source": c.get("source"),
            "similarity": c.get("similarity"),
        }
        for c in chunks
    ]
    return {"answer": answer, "sources": sources}
