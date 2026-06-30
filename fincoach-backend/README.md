# FinCoach AI Backend (FastAPI + RAG)

The AI coaching service for FinCoach. It is **separate** from the mobile app — the app
talks to Supabase directly for normal data, and calls **this** service only for AI advice.

```
question -> bge-m3 embed -> search Supabase pgvector -> + user's data -> prompt -> LLM -> answer
```

- **DIY RAG** — retrieval, prompt building, and the LLM call are written by hand (`app/rag.py`).
- **LangChain** is used in **one place only**: loading + chunking documents in `ingest.py`.
- **LLM is swappable** via `.env` (OpenAI-compatible: NVIDIA NIM / Gemini / Groq / OpenAI).
  With no provider set, it runs in **stub mode** so you can verify retrieval first.

## Layout
```
fincoach-backend/
├── app/
│   ├── main.py            # FastAPI: POST /coach, GET /health
│   ├── rag.py             # retrieve -> build_prompt -> coach
│   ├── embeddings.py      # bge-m3 (local, GPU if available)
│   ├── llm.py             # OpenAI-compatible LLM (or stub)
│   ├── supabase_client.py # service-role client
│   └── config.py          # reads .env
├── ingest.py              # Phase 1: corpus -> chunks -> embeddings -> Supabase
├── sql/knowledge.sql      # knowledge_documents table + match function (run in Supabase)
├── corpus/                # put your Malaysian finance docs here (.md/.txt/.pdf)
└── .env.example
```

## Setup (one time)

**1. Create the table in Supabase**
Open the Supabase SQL Editor (project `yqsyrzdpvtasldkthhfg`) and run the contents of
[`sql/knowledge.sql`](sql/knowledge.sql). This enables `pgvector`, creates
`knowledge_documents`, and the `match_knowledge_documents` search function.

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
Leave the `LLM_*` values blank for now (stub mode).

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

**C. Test it**
```bash
curl http://localhost:8000/health
# {"status":"ok"}

curl -X POST http://localhost:8000/coach ^
  -H "Content-Type: application/json" ^
  -d "{\"question\": \"How can I save on a RM800 monthly allowance?\"}"
```
In stub mode the response's `answer` echoes the built prompt (so you can confirm the
right chunks were retrieved). `sources` lists the matched documents + similarity scores.

## Going live with a real LLM
Pick a provider, set the three `LLM_*` values in `.env`, restart `uvicorn`. No code changes.
Example (NVIDIA NIM):
```
LLM_BASE_URL=https://integrate.api.nvidia.com/v1
LLM_API_KEY=nvapi-...
LLM_MODEL=nvidia/nemotron-3-ultra-550b-a55b
```

## Connecting the mobile app
Call `POST /coach` from the app's Coach screen (a `lib/coach.ts` client). Send the
logged-in user's id as `user_id` so advice is personalised.
On the Honor 200 over Wi-Fi, use your PC's LAN IP (e.g. `http://192.168.1.x:8000`),
not `localhost`.

## Before production (TODO, not needed for the demo)
- Add auth: verify the caller's Supabase JWT so only logged-in users can spend LLM calls.
- Restrict CORS to your app's origin.
- Add rate limiting + a provider spending cap.
- (ERD next step) Persist `coaching_sessions`, `messages`, and `retrievals` for history.
