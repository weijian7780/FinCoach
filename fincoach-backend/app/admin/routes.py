"""Admin website API. No endpoint returns students' financial records."""
from collections import defaultdict, deque
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from time import monotonic
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field, SecretStr
from starlette.concurrency import run_in_threadpool
from supabase import ClientOptions, create_client

from app import config
from app.admin.documents import MAX_UPLOAD_BYTES, RevisionInput, build_revision_chunks, extract_document
from app.admin.service import admin_read, admin_rpc, require_administrator
from app.auth import AuthenticatedUser, require_authenticated_user
from app.supabase_client import get_supabase

router = APIRouter(prefix="/api/admin", tags=["administration"])
_login_attempts: dict[str, deque] = defaultdict(deque)


def require_enabled() -> None:
    if not config.ADMIN_PANEL_ENABLED or not config.ACCOUNT_ACCESS_ENFORCED:
        raise HTTPException(503, "Admin panel is not enabled. Complete database and access-control setup first.")


def administrator(authorization: str | None = Header(default=None)) -> AuthenticatedUser:
    require_enabled()
    return require_administrator(require_authenticated_user(authorization))


@router.get("/config")
def public_configuration():
    # These two settings are public client configuration, never service secrets.
    return dict(supabase_url=config.SUPABASE_URL, publishable_key=config.SUPABASE_PUBLISHABLE_KEY,
                enabled=config.ADMIN_PANEL_ENABLED and config.ACCOUNT_ACCESS_ENFORCED)


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=256)


@router.post("/login")
def login(body: LoginInput, request: Request):
    require_enabled()
    # In-process protection complements Supabase Auth's rate limits. Production
    # uses a single worker; never trust arbitrary X-Forwarded-For values here.
    key = request.client.host if request.client else "unknown"
    now = monotonic()
    if len(_login_attempts) > 1000:
        _login_attempts.clear()
    attempts = _login_attempts[key]
    while attempts and attempts[0] < now - 60:
        attempts.popleft()
    if len(attempts) >= 10:
        raise HTTPException(429, "Too many sign-in attempts. Wait a minute.")
    attempts.append(now)
    username = body.username.strip()
    email = config.ADMIN_LOGIN_EMAIL if username.lower() == "admin" else username
    if "@" not in email:
        raise HTTPException(401, "Sign-in failed.")
    try:
        client = create_client(config.SUPABASE_URL, config.SUPABASE_PUBLISHABLE_KEY,
                               options=ClientOptions(auto_refresh_token=False, persist_session=False))
        result = client.auth.sign_in_with_password({"email": email, "password": body.password.get_secret_value()})
        if not result.user or not result.session:
            raise ValueError("Missing session")
        require_administrator(AuthenticatedUser(str(result.user.id), result.session.access_token))
        return dict(access_token=result.session.access_token, refresh_token=result.session.refresh_token)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(401, "Sign-in failed.") from exc


@router.get("/me")
def me(user=Depends(administrator)):
    return dict(user_id=user.user_id, role="admin")


@router.get("/accounts")
def accounts(user=Depends(administrator), offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100), search: str = Query("", max_length=200)):
    query = get_supabase().table("account_access").select("user_id,role,status,email,display_name,created_at,last_sign_in_at", count="exact")
    if search:
        # A single ilike parameter avoids interpolating arbitrary PostgREST filter
        # expressions; search by email, with status/role visible in the result.
        query = query.ilike("email", "%" + search.replace("%", "\\%").replace("_", "\\_") + "%")
    response = admin_read(query.order("created_at", desc=True).range(offset, offset + limit - 1))
    return dict(items=response.data, total=response.count)


class AccountAction(BaseModel):
    status: str = Field(pattern="^(active|suspended)$")
    expected_status: str = Field(pattern="^(active|suspended)$")
    reason: str = Field(min_length=1, max_length=300)


@router.patch("/accounts/{user_id}")
def account_action(user_id: UUID, body: AccountAction, user=Depends(administrator)):
    return admin_rpc("admin_set_account_status", dict(p_actor=user.user_id, p_user=str(user_id), p_status=body.status, p_reason=body.reason.strip(), p_expected=body.expected_status))


@router.get("/dashboard")
def dashboard(request: Request, user=Depends(administrator)):
    client = get_supabase()
    counts = {}
    for name in ("account_access", "knowledge_sources", "coaching_sessions", "coaching_messages"):
        counts[name] = admin_read(client.table(name).select("user_id" if name == "account_access" else "id", count="exact", head=True)).count or 0
    counts["suspended_accounts"] = admin_read(client.table("account_access").select("user_id", count="exact", head=True).eq("status", "suspended")).count or 0
    counts["failed_revisions"] = admin_read(client.table("knowledge_revisions").select("id", count="exact", head=True).eq("status", "failed")).count or 0
    return dict(counts=counts, components=getattr(request.app.state, "model_warmup", {"ocr": "unknown", "embeddings": "unknown"}),
                providers={"llm_configured": bool(config.LLM_API_KEY or config.LLM_PRIMARY_API_KEY), "tavily_configured": bool(config.TAVILY_API_KEY)})


@router.get("/audit")
def audit(user=Depends(administrator), offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
    response = admin_read(get_supabase().table("admin_audit_logs").select("id,actor_id,action,target_type,target_id,details,created_at", count="exact").order("id", desc=True).range(offset, offset + limit - 1))
    items = response.data or []
    client = get_supabase()

    def lookup(table, key, columns, values):
        # Batch only this audit page's identifiers; never fetch financial data.
        ids = set()
        for value in values:
            try:
                ids.add(str(UUID(str(value))))
            except (ValueError, TypeError, AttributeError):
                continue
        if not ids:
            return {}
        rows = admin_read(client.table(table).select(columns).in_(key, sorted(ids))).data or []
        return {str(row[key]): row for row in rows}

    accounts = lookup("account_access", "user_id", "user_id,email,display_name",
                      [row.get("actor_id") for row in items] +
                      [row.get("target_id") for row in items if row.get("target_type") == "account"])
    sources = lookup("knowledge_sources", "id", "id,title",
                     [row.get("target_id") for row in items if row.get("target_type") == "knowledge_source"])
    revisions = lookup("knowledge_revisions", "id", "id,source_id,title",
                       [(row.get("details") or {}).get("revision_id") for row in items])
    for row in items:
        actor = accounts.get(str(row.get("actor_id")), {})
        row["actor_name"] = actor.get("email") or actor.get("display_name") or "Administrator unavailable"
        target = str(row.get("target_id"))
        if row.get("target_type") == "knowledge_source":
            revision = revisions.get(str((row.get("details") or {}).get("revision_id")), {})
            # Prefer the title of the recorded version, not a later renamed source.
            title = revision.get("title") if str(revision.get("source_id")) == target else None
            row["target_name"] = title or sources.get(target, {}).get("title") or "Document unavailable"
        elif row.get("target_type") == "account":
            account = accounts.get(target, {})
            row["target_name"] = account.get("email") or account.get("display_name") or "Account unavailable"
        else:
            row["target_name"] = "Record unavailable"
    return dict(items=items, total=response.count)


@router.get("/knowledge")
def knowledge(user=Depends(administrator), offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
    result = admin_read(get_supabase().table("knowledge_sources").select("*", count="exact").order("updated_at", desc=True).range(offset, offset + limit - 1))
    return dict(items=result.data, total=result.count)


def source_record(source_id: UUID):
    row = admin_read(get_supabase().table("knowledge_sources").select("*").eq("id", str(source_id)).maybe_single()).data
    if not row:
        raise HTTPException(404, "Knowledge document not found.")
    return row


@router.get("/knowledge/{source_id}")
def knowledge_detail(source_id: UUID, user=Depends(administrator)):
    client = get_supabase()
    source = source_record(source_id)
    revisions = admin_read(client.table("knowledge_revisions").select("id,title,status,checked_at,created_at,chunk_count,error_message,file_path").eq("source_id", str(source_id)).order("created_at", desc=True).order("id", desc=True).limit(50)).data
    latest = admin_read(client.table("knowledge_revisions").select("*").eq("id", source["latest_revision_id"]).maybe_single()).data if source["latest_revision_id"] else None
    return dict(source=source, revisions=revisions, latest=latest)


@router.post("/uploads")
async def upload(file: UploadFile = File(...), user=Depends(administrator)):
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    try:
        content = await run_in_threadpool(extract_document, file.filename or "", data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        await file.close()
    upload_id = uuid4()
    suffix = Path(file.filename or "").suffix.lower()
    mime = {".md": "text/markdown", ".txt": "text/plain", ".pdf": "application/pdf"}[suffix]
    path = f"{user.user_id}/{upload_id}/original{suffix}"
    await run_in_threadpool(lambda: get_supabase().storage.from_("knowledge-originals").upload(path, data, {"content-type": mime}))
    return dict(upload_id=str(upload_id), content=content, filename=Path(file.filename or "Document").name)


@router.get("/knowledge/{source_id}/revisions")
def revision_history(source_id: UUID, user=Depends(administrator), offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    source_record(source_id)
    result = admin_read(get_supabase().table("knowledge_revisions").select("id,title,status,checked_at,created_at,chunk_count,error_message,file_path", count="exact").eq("source_id", str(source_id)).order("created_at", desc=True).order("id", desc=True).range(offset, offset + limit - 1))
    return dict(items=result.data, total=result.count)


def save_revision(body: RevisionInput, user, source_id: UUID | None):
    path = None
    if body.upload_id:
        prefix = f"{user.user_id}/{body.upload_id}"
        objects = get_supabase().storage.from_("knowledge-originals").list(prefix)
        names = [obj["name"] for obj in objects if obj["name"] in {"original.md", "original.txt", "original.pdf"}]
        if len(names) != 1:
            raise HTTPException(422, "Uploaded original was not found.")
        path = prefix + "/" + names[0]
    return admin_rpc("admin_save_knowledge_revision", dict(p_actor=user.user_id, p_source=str(source_id) if source_id else None,
        p_title=body.title, p_content=body.content, p_urls=body.source_urls, p_checked=str(body.checked_at) if body.checked_at else None, p_file_path=path,
        p_expected=str(body.expected_revision_id) if body.expected_revision_id else None))


@router.post("/knowledge")
def create_knowledge(body: RevisionInput, user=Depends(administrator)):
    return save_revision(body, user, None)


@router.post("/knowledge/{source_id}/revisions")
def revise_knowledge(source_id: UUID, body: RevisionInput, user=Depends(administrator)):
    return save_revision(body, user, source_id)


@router.post("/preview")
def preview(body: RevisionInput, user=Depends(administrator)):
    chunks = build_revision_chunks(body.model_dump(mode="json"), "preview.md")
    return dict(chunk_count=len(chunks), excerpts=[chunk.content for chunk in chunks[:5]], stale=bool(body.checked_at and (datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).date() - body.checked_at).days > 90))


class LinkInput(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


@router.post("/imports/link")
def import_link(body: LinkInput, user=Depends(administrator)):
    from app.admin.link_import import extract_link
    try:
        return extract_link(body.url.strip(), config.TAVILY_API_KEY)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


class KnowledgeAction(BaseModel):
    action: str = Field(pattern="^(prepare|publish|archive|restore)$")
    revision_id: UUID | None = None
    expected_revision_id: UUID | None = None


@router.post("/knowledge/{source_id}/actions")
def knowledge_action(source_id: UUID, body: KnowledgeAction, user=Depends(administrator)):
    return admin_rpc("admin_knowledge_action", dict(p_actor=user.user_id, p_source=str(source_id), p_revision=str(body.revision_id) if body.revision_id else None,
                    p_action=body.action, p_expected=str(body.expected_revision_id) if body.expected_revision_id else None))


@router.get("/knowledge/{source_id}/revisions/{revision_id}/original")
def original(source_id: UUID, revision_id: UUID, user=Depends(administrator)):
    row = admin_read(get_supabase().table("knowledge_revisions").select("file_path").eq("id", str(revision_id)).eq("source_id", str(source_id)).maybe_single()).data
    if not row or not row.get("file_path"):
        raise HTTPException(404, "No uploaded original for this revision.")
    value = get_supabase().storage.from_("knowledge-originals").create_signed_url(row["file_path"], 60)
    return dict(url=value.get("signedURL") or value.get("signedUrl"))


class SearchInput(BaseModel):
    question: str = Field(min_length=1, max_length=500)


@router.post("/search")
def search(body: SearchInput, user=Depends(administrator)):
    # Search the corpus directly, without coaching routes, private tools, or an
    # external LLM/Tavily call. Include newly uploaded topics as well as aliases.
    from app.embeddings import embed_query
    from app.rag.retrieval import _chunk_from_row, _rank_subquery_candidates
    rows = get_supabase().rpc("match_knowledge_documents_hybrid", dict(query_text=body.question, query_embedding=embed_query(body.question), match_count=5)).execute().data
    chunks = _rank_subquery_candidates([_chunk_from_row(row, None) for row in rows or []])
    return dict(items=[dict(id=c.id, title=c.title, source=c.source, content=c.content, similarity=c.similarity) for c in chunks[:5]])
