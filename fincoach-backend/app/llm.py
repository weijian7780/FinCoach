"""LLM call via an OpenAI-compatible API (NVIDIA NIM / Gemini / Groq / OpenAI).

If no provider is configured in .env, generate() returns a stub that echoes the
prompt — so the RAG pipeline (retrieval + prompt building) is fully testable before
you pick a provider.
"""
from app.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

SYSTEM_PROMPT = (
    "You are FinCoach, a friendly financial coach for Malaysian university students. "
    "Answer using ONLY the provided knowledge context and the student's financial "
    "profile. If the context does not contain the answer, say you are not sure rather "
    "than inventing figures. Keep advice practical and specific to the Malaysian "
    "context (e.g. PTPTN, EPF, SOCSO). End with a one-line reminder that this is "
    "educational guidance, not licensed financial advice."
)


def _configured() -> bool:
    return bool(LLM_BASE_URL and LLM_API_KEY and LLM_MODEL)


def generate(prompt: str) -> str:
    if not _configured():
        return (
            "[LLM not configured yet — set LLM_BASE_URL / LLM_API_KEY / LLM_MODEL in "
            ".env. Below is the prompt the model WOULD receive, so you can verify that "
            "retrieval works:]\n\n" + prompt
        )

    from openai import OpenAI

    client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content or ""
