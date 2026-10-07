"""FastAPI application for authenticated FinCoach server features."""
from contextlib import asynccontextmanager
import asyncio
from pathlib import Path
import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from app.api.coach_routes import router as coach_router
from app.config import CORS_ORIGINS
from app.embeddings import warm_embeddings
from app.observability import RequestContextMiddleware
from app.receipt_ocr import get_ocr_engine
from app.receipt_routes import router as receipt_router
from app.admin.routes import router as admin_router
from app.admin.worker import run_worker
from app.config import ADMIN_PANEL_ENABLED, ACCOUNT_ACCESS_ENFORCED, ADMIN_STATIC_DIR
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

logger = logging.getLogger("uvicorn.error")


async def _warm_optional_component(app: FastAPI, name: str, loader) -> None:
    """Warm a local model without making the authenticated API unavailable.

    Receipt OCR and Coach embeddings are optional at process startup: a failure
    must be visible through `/ready`, while login and the unaffected module
    routes remain available. Their own request handlers still return safe
    errors until the underlying model problem is fixed.
    """
    try:
        await run_in_threadpool(loader)
    except Exception:
        app.state.model_warmup[name] = "unavailable"
        logger.exception("fincoach_model_warmup_failed component=%s", name)
    else:
        app.state.model_warmup[name] = "ready"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _app.state.model_warmup = {"ocr": "starting", "embeddings": "starting"}
    # Pay PaddleOCR's model initialization cost once during server startup,
    # rather than making the first phone scan wait for it. Failure is isolated
    # so the rest of FinCoach can still serve authenticated requests.
    await _warm_optional_component(_app, "ocr", get_ocr_engine)
    # Do the same for BGE-M3 so the first coaching request stays inside the
    # mobile client's timeout budget.
    await _warm_optional_component(_app, "embeddings", warm_embeddings)
    stop = asyncio.Event()
    worker = asyncio.create_task(run_worker(stop)) if ADMIN_PANEL_ENABLED and ACCOUNT_ACCESS_ENFORCED else None
    try:
        yield
    finally:
        stop.set()
        if worker:
            await worker


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
app.include_router(admin_router)

# Serve the separate browser application without adding a Node backend. API
# routes are registered first so SPA fallback cannot swallow admin API errors.
_admin_dist = Path(ADMIN_STATIC_DIR) if ADMIN_STATIC_DIR else Path(__file__).resolve().parents[2] / "fincoach-admin" / "dist"
if _admin_dist.is_dir() and (_admin_dist / "index.html").is_file():
    app.mount("/admin/assets", StaticFiles(directory=_admin_dist / "assets"), name="admin-assets")

    @app.get("/admin")
    @app.get("/admin/{path:path}")
    def admin_page(path: str = ""):
        return FileResponse(_admin_dist / "index.html", headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"})


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
def readiness() -> JSONResponse:
    """Report whether optional local model dependencies completed warm-up."""
    components = dict(
        getattr(
            app.state,
            "model_warmup",
            {"ocr": "starting", "embeddings": "starting"},
        )
    )
    status_code = 200 if all(value == "ready" for value in components.values()) else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if status_code == 200 else "degraded",
            "components": components,
        },
    )
