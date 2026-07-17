# FinCoach AI Backend (FastAPI + RAG)

The AI coaching service for FinCoach. It is **separate** from the mobile app — the app
talks to Supabase directly for normal data, and calls **this** service only for AI advice.

```
question -> bge-m3 embed -> search Supabase pgvector -> + user's data -> prompt -> LLM -> answer
```

- **No LangChain or LlamaIndex** — loading, chunking, retrieval, prompting, and orchestration are native Python.
- **Embedding model:** `BAAI/bge-m3` creates 1024-dimensional vectors for pgvector retrieval. It does not write the chat answer.
- **Response model:** the configurable OpenAI-compatible `LLM_MODEL` generates the coaching reply. The current local configuration uses NVIDIA's compatible API boundary.
- Missing provider configuration fails safely; FinCoach never returns the constructed prompt or private financial context as a stub response.

## Layout
```
fincoach-backend/
├── app/
│   ├── main.py            # FastAPI app, restrictive CORS, request logging
│   ├── api/coach_routes.py # authenticated conversation/message routes
│   ├── rag/               # native ingestion, chunking, retrieval, prompts, service
│   ├── coaching_history.py # owner-scoped persistence and usage limits
│   ├── auth.py            # verified Supabase bearer identity
│   ├── embeddings.py      # bge-m3 (local, GPU if available)
│   ├── llm.py             # bounded OpenAI-compatible provider call
│   ├── supabase_client.py # service-role client
│   ├── observability.py   # request IDs and privacy-safe JSON logs
│   └── config.py          # provider, retrieval, rate, timeout, and CORS config
├── ingest.py              # native corpus -> chunks -> embeddings -> Supabase
├── sql/knowledge.sql      # knowledge_documents table + match function (run in Supabase)
├── corpus/                # put your Malaysian finance docs here (.md/.txt/.pdf)
└── .env.example
```

## Receipt extraction

The receipt module uses a privacy-conscious two-stage pipeline:

```text
receipt image -> PaddleOCR locally on FastAPI -> OCR text -> Gemini structured cleanup
              -> confidence/missing-field warnings -> editable mobile review -> Supabase
```

Only PaddleOCR text is sent to Gemini. The receipt image is never included in the Gemini
request. If Gemini is not configured or temporarily fails, the endpoint returns the
deterministic PaddleOCR result with a review warning instead of blocking receipt scanning.

## Setup (one time)

**1. Deploy the Supabase migration**
Deploy `fincoach-mobile/supabase/migrations/20260717021519_complete_ai_financial_coaching.sql`
through the project's normal migration workflow. It creates owner-scoped conversations,
messages, retrieval provenance, RLS policies, indexes, and the service-only pgvector RPC.
Do not expose the service-role key to the mobile bundle.

**2. Python environment**
```bash
cd "fincoach-backend"
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```
> For GPU (your RTX 4050), install the CUDA build of PyTorch from https://pytorch.org
> before/after the requirements, otherwise embeddings run on CPU (slower but works).

**3. Configure secrets**
```bash
copy .env.example .env          # Windows
```
Fill in `SUPABASE_SERVICE_ROLE_KEY` (Supabase → Project Settings → API → service_role).
Also set `SUPABASE_PUBLISHABLE_KEY`, `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL`.
Coaching returns a safe `502` when the provider is not configured. Optional bounds include
`RETRIEVE_THRESHOLD`, `COACH_HISTORY_LIMIT`, `COACH_RATE_LIMIT_MINUTE`,
`COACH_RATE_LIMIT_DAY`, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_TOKENS`, and comma-separated
`CORS_ORIGINS`.

For Gemini receipt cleanup, add a server-side Google AI Studio key:

```text
GEMINI_API_KEY=your-google-ai-studio-key
GEMINI_RECEIPT_MODEL=gemini-3.1-flash-lite
```

## Run

**A. Build the knowledge base** (uses the sample doc in `corpus/`; replace it with real ones)
```bash
python ingest.py
# -> Stored N chunks in knowledge_documents.
```

**B. Start the API**
```bash
uvicorn app.main:app --reload --port 8000
```

**C. Test authenticated conversation routes**
```bash
curl http://localhost:8000/health
# {"status":"ok"}

curl -X POST http://localhost:8000/coach/conversations ^
  -H "Authorization: Bearer <access-token>" ^
  -H "Content-Type: application/json" ^
  -d "{\"title\": \"New conversation\"}"

curl -X POST http://localhost:8000/coach/conversations/<conversation-id>/messages ^
  -H "Authorization: Bearer <access-token>" ^
  -H "Content-Type: application/json" ^
  -d "{\"message_id\": \"<new-uuid>\", \"content\": \"How can I save on RM800?\"}"
```

Available routes are `GET/POST /coach/conversations`,
`PATCH/DELETE /coach/conversations/{id}`, `GET .../{id}/messages`, and
`POST .../{id}/messages`. Identity always comes from the verified JWT `sub`; request
bodies never accept a `user_id`.

## Going live with a real LLM
Pick a provider, set the three `LLM_*` values in `.env`, restart `uvicorn`. No code changes.
Example (NVIDIA-compatible endpoint):
```
LLM_BASE_URL=https://integrate.api.nvidia.com/v1
LLM_API_KEY=nvapi-...
LLM_MODEL=z-ai/glm-5.2
```

## Connecting the mobile app
Set `EXPO_PUBLIC_FINCOACH_API_URL` in `fincoach-mobile/.env`. The mobile client sends
the current Supabase access token, refreshes once after `401`, and supports saved
conversation list/create/rename/delete plus message history. It never sends `user_id`.
On the Honor 200 over Wi-Fi, use your PC's LAN IP (e.g. `http://192.168.1.x:8000`),
not `localhost`.

## Implemented safeguards

- Verified Supabase bearer claims and owner-scoped RLS.
- Persistent multiple-conversation history with idempotent client message IDs.
- Service-only knowledge retrieval, similarity filtering, bounded history/output, and prompt-injection boundaries.
- Persisted per-minute/daily limits, provider timeout, safe errors, restrictive CORS, and privacy-safe request logs.

## Deployment still required

Local code is complete, but the migration must be deployed, backend secrets and hosting
or LAN access must be configured, the corpus must be ingested, and the Honor 200
acceptance checklist must pass. ERD and DFD redesign remains later documentation work.
