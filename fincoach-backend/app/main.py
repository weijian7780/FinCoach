"""FastAPI application for authenticated FinCoach server features."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.coach_routes import router as coach_router
from app.config import CORS_ORIGINS
from app.observability import RequestContextMiddleware

app = FastAPI(title="FinCoach AI Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)
app.add_middleware(RequestContextMiddleware)
app.include_router(coach_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
