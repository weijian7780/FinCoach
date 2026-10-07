# FinCoach AI Backend (FastAPI + RAG)

Administrator website setup, rollout order and local validation:
[fincoach-admin/README.md](../fincoach-admin/README.md). Admin features default
to disabled until the reviewed database migration and administrator provisioning
are complete. After enabling versioned knowledge management, maintain documents
through `/admin`; do not rerun the legacy knowledge bootstrap or global pruning.

The AI coaching service for FinCoach. It is **separate** from the mobile app — the app
talks to Supabase directly for normal data, and calls **this** service only for AI advice.

```
question -> route -> allowlisted owner-scoped tools and/or pgvector retrieval
         -> bounded LLM synthesis -> answer or clarification/confirmation card
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
Deploy all pending migrations through the project's normal migration workflow, including
`20260717021519_complete_ai_financial_coaching.sql` and
`20260724090000_add_coach_agent_interactions.sql`. They create owner-scoped conversations,
messages, durable interaction payloads, retrieval provenance, RLS policies, indexes, and
the service-only pgvector RPC.
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
Coaching returns a safe `502` when the provider is not configured. Retrieval uses five
candidates, a `0.45` similarity floor, a `0.10` best-score margin, and returns at most
three sources. Optional bounds include `RETRIEVE_CANDIDATES`, `RETRIEVE_K`,
`RETRIEVE_THRESHOLD`, `RETRIEVE_SCORE_MARGIN`, `COACH_HISTORY_LIMIT`, `COACH_RATE_LIMIT_MINUTE`,
`COACH_RATE_LIMIT_DAY`, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_TOKENS`, and comma-separated
`CORS_ORIGINS`.

For Gemini receipt cleanup, add a server-side Google AI Studio key:

```text
GEMINI_API_KEY=your-google-ai-studio-key
GEMINI_RECEIPT_MODEL=gemini-3.1-flash-lite
```

## Run

**A. Build the knowledge base** (the included documents summarize dated official
KWSP, PTPTN, and PERKESO sources; add your own `.md`, `.txt`, or `.pdf` files)
```bash
python ingest.py --validate
python ingest.py --prune --verify
# -> Stored N chunks in knowledge_documents.
```

`--validate` checks dated official-source evidence and shows the future chunk count without
database writes. `--prune --verify` first confirms all replacement chunks were stored, then
removes stale chunks and verifies the final database state. Run without `--prune` when you
only want to upsert.

See [RAG evaluation protocol](docs/rag-evaluation-protocol.md) for document-level
precision/recall/F1, dense versus production-hybrid retrieval, label review,
CSV/JSON reports, and candidate held-out FYP questions. Existing labels are not
independently validated; do not present unit-test results as retrieval scores.

Run the labelled English/Malay/informal retrieval benchmark before deployment:

```bash
python rag_evaluation.py
```

**B. Start the API**
```bash
uvicorn app.main:app --reload --port 8000
```

**C. Test authenticated conversation routes**
```bash
curl http://localhost:8000/health
# {"status":"ok"}

curl http://localhost:8000/ready
# {"status":"ok","components":{"ocr":"ready","embeddings":"ready"}}

curl -X POST http://localhost:8000/coach/conversations ^
  -H "Authorization: Bearer <access-token>" ^
  -H "Content-Type: application/json" ^
  -d "{\"title\": \"New conversation\"}"

curl -X POST http://localhost:8000/coach/conversations/<conversation-id>/messages ^
  -H "Authorization: Bearer <access-token>" ^
  -H "Content-Type: application/json" ^
  -d "{\"message_id\": \"<new-uuid>\", \"content\": \"How can I save on RM800?\"}"
```

`/health` confirms that the HTTP process is alive. `/ready` is `503` when PaddleOCR or Coach embeddings did not finish warm-up; inspect the backend log and fix the unavailable component before presenting that module.

Available routes are `GET/POST /coach/conversations`,
`PATCH/DELETE /coach/conversations/{id}`, `GET .../{id}/messages`, and
`POST .../{id}/messages`. Confirmation-gated actions use
`POST /coach/messages/{id}/actions/confirm|cancel|complete`. Identity always comes from
the verified JWT `sub`; request bodies never accept a `user_id`.

## Going live with real LLM failover

FinCoach attempts the `LLM_PRIMARY_*` provider first. If that provider times out,
returns an error, or produces an empty answer, the same bounded request is sent to
the existing `LLM_*` fallback provider. Configure OpenRouter Gemma 4 31B as
primary and direct DeepSeek V4 Flash as fallback:

```
LLM_PRIMARY_BASE_URL=https://openrouter.ai/api/v1
LLM_PRIMARY_API_KEY=sk-or-v1-...
LLM_PRIMARY_MODEL=google/gemma-4-31b-it:free
LLM_PRIMARY_MAX_TOKENS=1024

LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=<dedicated-server-side-DeepSeek-Coach-key>
LLM_MODEL=deepseek-v4-flash
LLM_MAX_TOKENS=4096
```

Keep the dedicated Coach keys separate from `GEMINI_API_KEY`, which is used only for
receipt OCR cleanup. OpenRouter requests disable hidden reasoning for short,
non-leaking responses, while DeepSeek receives its official
`thinking={"type":"enabled"}` control. `LLM_PRIMARY_MAX_TOKENS` bounds Gemma's
response independently from the fallback `LLM_MAX_TOKENS` ceiling.

Restart `uvicorn` after changing `.env`. Provider-failover logs contain provider
roles, model IDs, and error types, but never prompts or API keys.

## Connecting the mobile app
Set `EXPO_PUBLIC_FINCOACH_API_URL` in `fincoach-mobile/.env`. The mobile client sends
the current Supabase access token, refreshes once after `401`, and supports saved
conversation list/create/rename/delete plus message history. It never sends `user_id`.
On the Honor 200 over Wi-Fi, use your PC's LAN IP (e.g. `http://192.168.1.x:8000`),
not `localhost`.

## Implemented safeguards

- Verified Supabase bearer claims and owner-scoped RLS.
- Persistent multiple-conversation history with idempotent client message IDs.
- Allowlisted read tools for spending, budgets, savings, reminders, reports, and overview.
- Three tool-execution rounds plus one tool-disabled synthesis call; no arbitrary SQL or delete tools.
- Durable clarification/action cards with explicit confirmation before reminder creation or report generation.
- Spending consent is checked before transaction reads, report preparation, and report confirmation.
- Service-only knowledge retrieval, multilingual routing, calibrated similarity filtering, bounded history/output, and prompt-injection boundaries.
- Source-marked educational answers with deterministic numeric/product validation, one high-reasoning correction retry, and safe fallback when evidence is insufficient.
- Persisted per-minute/daily limits, provider timeout, safe errors, restrictive CORS, and privacy-safe request logs.

## Savings predictions and existing tools

Coaching already has ten read tools in `app/agent_tools.py`:

| Tools | Purpose |
| --- | --- |
| `predict_savings`, `get_cashflow_forecast` | Monthly savings projection and funds available after recorded expenses and upcoming reminders. |
| `get_financial_profile`, `get_financial_overview` | Coaching-safe profile fields and a combined financial overview. |
| `get_spending_summary`, `search_transactions` | Recorded totals, categories, comparisons, and matching transactions. |
| `get_budget_status`, `get_savings_goals` | Budget limits, remaining budget, and savings-goal progress. |
| `get_upcoming_reminders`, `get_report_summary` | Upcoming reminders and calculated report summaries. |

The registry also includes `prepare_reminder` and `prepare_report`; those preparation
tools are gated by `COACH_WRITE_ACTIONS_ENABLED` and confirmation before any write.

Questions such as "predict money saving" and "forecast my savings next month" reuse
`predict_savings`. It reads the authenticated user's data after checking spending
consent and calculates the estimate in Python. The model can explain the result.

- Spending pace uses expenses through today, excluding future-dated entries. A future
  target month uses observed spending, with the target and observation periods shown
  separately. If the current month has no expenses, the previous complete month is tried.
- With no expense history, a recorded monthly budget can support an explicitly labelled
  scenario. Missing income, spending history, or budget is never silently treated as zero.
- Recorded income and the profile allowance are alternative income bases, not added
  together. Savings goals are destinations for the estimated surplus; their entire
  unfinished targets are not deducted as monthly expenses. A deficit is shown as a shortfall.
- Numeric evidence preserves units such as `days_elapsed`. Unsupported model amounts
  recover to the successful tool calculation instead of asking the user to rephrase.
  Estimates assume complete records and unchanged income/spending, and are not guarantees.

Run the prediction regression tests with `python -m unittest tests.test_savings_prediction`.
This change is backend-only and needs no database migration or mobile response-contract change.

Run the live non-destructive provider smoke scenarios with:

```bash
python agent_live_smoke.py
```

The script uses synthetic records only and cannot access Supabase.

## Deployment still required

Local code is complete, but the migration must be deployed, backend secrets and hosting
or LAN access must be configured, the corpus must be ingested, and the Honor 200
acceptance checklist must pass. ERD and DFD redesign remains later documentation work.
