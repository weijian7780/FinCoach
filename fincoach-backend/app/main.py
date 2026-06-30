"""FastAPI app exposing the AI coaching endpoint.

    POST /coach   { "question": "...", "user_id": "optional-uuid" }  -> { answer, sources }
    GET  /health  -> { status: "ok" }
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.rag import coach

app = FastAPI(title="FinCoach AI Backend", version="0.1.0")

# Open during development. Before production, restrict to your app's origin and add
# auth (verify the caller's Supabase JWT) so only logged-in users can spend LLM calls.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class CoachRequest(BaseModel):
    question: str
    user_id: str | None = None


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/coach")
def coach_endpoint(req: CoachRequest) -> dict:
    return coach(req.question, req.user_id)
