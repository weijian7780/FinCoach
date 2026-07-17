"""FastAPI application for authenticated FinCoach server features."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from app.api.coach_routes import router as coach_router
from app.config import CORS_ORIGINS
from app.observability import RequestContextMiddleware
from app.receipt_ocr import get_ocr_engine
from app.receipt_routes import router as receipt_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Pay PaddleOCR's model initialization cost once during server startup,
    # rather than making the first phone scan wait for it.
    await run_in_threadpool(get_ocr_engine)
    yield


app = FastAPI(title="FinCoach AI Backend", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)
app.add_middleware(RequestContextMiddleware)
app.include_router(coach_router)
app.include_router(receipt_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
