# AI Financial Coaching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Coach ComingSoon screen with an authenticated, persistent, multi-conversation RAG chat backed by FastAPI, Supabase, pgvector, BGE-M3, and the configured NVIDIA NIM LLM.

**Architecture:** React Native sends the active Supabase bearer token to focused FastAPI coaching routes. FastAPI verifies the token, derives the user identity, loads owner-scoped financial and conversation context, retrieves shared knowledge with custom BGE-M3/pgvector code, calls the configured LLM, and persists the turn plus retrieval evidence. Supabase RLS protects all exposed coaching history.

**Tech Stack:** Python 3.13, FastAPI, Pydantic, Supabase Python 2.31, sentence-transformers BGE-M3, pypdf, OpenAI-compatible NVIDIA NIM, PostgreSQL/pgvector/RLS, React Native 0.85, Expo SDK 56, Expo Router, TypeScript 6, Vitest 4.

## Global Constraints

- Do not use LangChain or LlamaIndex; remove both LangChain ingestion dependencies.
- Keep `fincoach-mobile` as the canonical mobile source and do not edit `C:\fcb`.
- Preserve the root UI reference `G:\My Drive\FYP 1 & 2\FinCoach UI\screen_coach.jsx`.
- Support multiple owner-scoped saved conversations.
- Derive identity only from the verified Supabase JWT `sub`; never trust a request `user_id`.
- Keep AI Financial Coaching separate from Reports, Budget, Savings, Alerts, Export/Backup, and receipt OCR.
- Use non-streaming responses, a visible typing state, bounded prompts, and bounded provider output.
- Treat ERD and DFD redesign as later documentation work; implement the production physical schema now.
- Do not deploy the migration or backend service without a separate deployment action; create and verify deployable artifacts locally.
- Use test-driven development: observe every new behavior fail before implementing it.
- Preserve unrelated user changes in the dirty worktree and stage only files named by the active task.

---

## File Map

### Backend

- `fincoach-backend/app/auth.py`: shared bearer parsing and verified Supabase identity.
- `fincoach-backend/app/models.py`: coaching request/response models.
- `fincoach-backend/app/coaching_history.py`: owner-scoped session/message persistence and usage limits.
- `fincoach-backend/app/observability.py`: request IDs and privacy-safe structured logs.
- `fincoach-backend/app/rag/ingestion.py`: native TXT/Markdown/PDF loading.
- `fincoach-backend/app/rag/chunking.py`: deterministic overlap chunking and content hashes.
- `fincoach-backend/app/rag/retrieval.py`: pgvector RPC and threshold filtering.
- `fincoach-backend/app/rag/prompts.py`: grounded prompt construction and conversation bounds.
- `fincoach-backend/app/rag/service.py`: orchestration of context, retrieval, LLM, and persistence.
- `fincoach-backend/app/api/coach_routes.py`: authenticated conversation and message routes.
- `fincoach-backend/app/config.py`: validated coaching limits/provider configuration.
- `fincoach-backend/app/llm.py`: bounded provider call and usage result.
- `fincoach-backend/app/main.py`: router registration and restrictive CORS.
- `fincoach-backend/ingest.py`: thin CLI entry point.
- `fincoach-backend/tests/test_ingestion.py`: native ingestion/chunking tests.
- `fincoach-backend/tests/test_coach_auth.py`: JWT tests.
- `fincoach-backend/tests/test_coaching_history.py`: persistence/ownership/rate-limit tests.
- `fincoach-backend/tests/test_rag_pipeline.py`: retrieval/prompt/service tests.
- `fincoach-backend/tests/test_coach_routes.py`: HTTP contract tests.

### Supabase and mobile

- `fincoach-mobile/supabase/migrations/*_complete_ai_financial_coaching.sql`: coaching schema, grants, RLS, indexes, and knowledge lockdown.
- `fincoach-mobile/supabase/schema.sql`: canonical schema mirror.
- `fincoach-mobile/scripts/verify-coaching-schema.mjs`: static migration/schema assertions.
- `fincoach-mobile/src/lib/coach-domain.ts`: pure conversation/message state helpers.
- `fincoach-mobile/src/lib/coach-domain.test.ts`: domain behavior tests.
- `fincoach-mobile/src/lib/coach-api.ts`: authenticated FastAPI client with one refresh retry.
- `fincoach-mobile/src/lib/coach-api.test.ts`: API contract tests.
- `fincoach-mobile/src/components/coach/coach-message.tsx`: message/source presentation.
- `fincoach-mobile/src/components/coach/coach-screen.tsx`: main Coach experience.
- `fincoach-mobile/src/components/coach/conversation-history-screen.tsx`: history/rename/delete experience.
- `fincoach-mobile/src/app/(app)/coach.tsx`: tab route export.
- `fincoach-mobile/src/app/coach/history.tsx`: history route export.
- `fincoach-mobile/src/app/_layout.tsx`: history route registration.
- `fincoach-mobile/src/lib/types.ts`: coaching API/domain types.
- `fincoach-mobile/docs/acceptance-tests.md`: device and cross-account checklist.

---

### Task 1: Remove LangChain and Build Native Ingestion

**Files:**
- Create: `fincoach-backend/app/rag/__init__.py`
- Create: `fincoach-backend/app/rag/ingestion.py`
- Create: `fincoach-backend/app/rag/chunking.py`
- Create: `fincoach-backend/tests/test_ingestion.py`
- Modify: `fincoach-backend/ingest.py`
- Modify: `fincoach-backend/requirements.txt`

**Interfaces:**
- Produces: `LoadedDocument`, `DocumentChunk`, `load_documents(root: Path)`, `chunk_document(document, chunk_size, overlap)`, and `content_hash(text)`.
- Consumes: existing `embed_texts()` and `get_supabase()`.

- [ ] **Step 1: Write failing native loader and chunker tests**

```python
class NativeIngestionTests(unittest.TestCase):
    def test_loads_text_and_markdown_without_langchain(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "guide.txt").write_text("Student finance guide", encoding="utf-8")
            (root / "notes.md").write_text("# Budget notes", encoding="utf-8")
            documents = load_documents(root)
        self.assertEqual([item.title for item in documents], ["guide.txt", "notes.md"])

    def test_chunks_deterministically_with_overlap_and_metadata(self):
        document = LoadedDocument("abcdefghij", "guide.txt", "guide.txt")
        chunks = chunk_document(document, chunk_size=6, overlap=2)
        self.assertEqual([item.content for item in chunks], ["abcdef", "efghij"])
        self.assertEqual([item.chunk_index for item in chunks], [0, 1])

    def test_content_hash_is_stable_for_normalized_text(self):
        self.assertEqual(content_hash("A  budget\nplan"), content_hash("A budget plan"))
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m unittest tests.test_ingestion -v` from `fincoach-backend`  
Expected: import failure for `app.rag.ingestion` or missing interfaces.

- [ ] **Step 3: Implement the native document interfaces**

```python
@dataclass(frozen=True)
class LoadedDocument:
    content: str
    source: str
    title: str
    page: int | None = None

@dataclass(frozen=True)
class DocumentChunk:
    content: str
    source: str
    title: str
    page: int | None
    chunk_index: int
    content_hash: str
```

Use `Path.rglob`, `Path.read_text(encoding="utf-8")`, and `pypdf.PdfReader`. Split normalized text on paragraph/sentence boundaries, enforce `0 <= overlap < chunk_size`, and carry the final `overlap` characters into the next chunk.

- [ ] **Step 4: Replace the ingestion CLI implementation**

`ingest.py` must call the native loader/chunker, embed chunk content, and upsert rows containing `title`, `source`, `content`, `embedding`, `page_number`, `chunk_index`, and `content_hash` with `on_conflict="content_hash"`.

- [ ] **Step 5: Remove LangChain dependencies and verify GREEN**

Delete `langchain-community` and `langchain-text-splitters` from `requirements.txt`.  
Run: `python -m unittest tests.test_ingestion -v`  
Expected: all ingestion tests pass.

- [ ] **Step 6: Commit Task 1 files only**

```powershell
git add fincoach-backend/app/rag fincoach-backend/tests/test_ingestion.py fincoach-backend/ingest.py fincoach-backend/requirements.txt
git commit -m "refactor: replace LangChain ingestion with native RAG code"
```

### Task 2: Add Coaching Schema, RLS, and Knowledge Lockdown

**Files:**
- Create via CLI: `fincoach-mobile/supabase/migrations/*_complete_ai_financial_coaching.sql`
- Create: `fincoach-mobile/scripts/verify-coaching-schema.mjs`
- Modify: `fincoach-mobile/supabase/schema.sql`
- Modify: `fincoach-backend/sql/knowledge.sql`

**Interfaces:**
- Produces tables `coaching_sessions`, `coaching_messages`, `coaching_retrievals` and the extended `knowledge_documents` metadata columns.
- Produces owner policies and indexes consumed by FastAPI routes.

- [ ] **Step 1: Write the failing schema verifier**

The Node script must require exact SQL fragments for:

```javascript
const required = [
  'create table if not exists public.coaching_sessions',
  'create table if not exists public.coaching_messages',
  'create table if not exists public.coaching_retrievals',
  'alter table public.coaching_sessions enable row level security',
  'to authenticated',
  '(select auth.uid()) = user_id',
  "role = 'user'",
  'unique (reply_to_message_id)',
  'revoke execute on function public.match_knowledge_documents',
];
```

- [ ] **Step 2: Run verifier and verify RED**

Run: `node scripts/verify-coaching-schema.mjs` from `fincoach-mobile`  
Expected: non-zero exit with missing coaching schema fragments.

- [ ] **Step 3: Create the migration using the installed Supabase CLI**

Run: `npx.cmd supabase migration new complete_ai_financial_coaching`  
Expected: one new timestamped migration ending in `_complete_ai_financial_coaching.sql`.

- [ ] **Step 4: Implement normalized coaching tables**

Use UUID session/message keys, `auth.users(id) on delete cascade`, role/status checks, `reply_to_message_id`, provider metadata, and explicit timestamps. `coaching_retrievals` stores `assistant_message_id`, `knowledge_document_id`, rank, similarity, and source snapshots. Add a unique `(assistant_message_id, knowledge_document_id)` constraint even though the physical schema also uses a surrogate key.

- [ ] **Step 5: Implement grants and RLS**

Authenticated users may CRUD their sessions, select their messages/retrievals, and insert only their own `role='user'` messages. They cannot directly insert assistant messages or retrieval rows. Every owner policy uses `TO authenticated` and `(select auth.uid()) = user_id`; UPDATE includes `USING` and `WITH CHECK`.

- [ ] **Step 6: Lock shared knowledge behind FastAPI**

Revoke `anon`/`authenticated` table access and match-function execution; retain server access. Add `page_number`, `chunk_index`, and unique `content_hash` to knowledge rows.

- [ ] **Step 7: Mirror schema and verify GREEN**

Apply the exact migration schema to `supabase/schema.sql` and the knowledge portion to `fincoach-backend/sql/knowledge.sql`.  
Run: `node scripts/verify-coaching-schema.mjs`  
Expected: `COACHING_SCHEMA_VERIFIED`.

- [ ] **Step 8: Commit Task 2 files only**

```powershell
git add fincoach-mobile/supabase/migrations fincoach-mobile/supabase/schema.sql fincoach-mobile/scripts/verify-coaching-schema.mjs fincoach-backend/sql/knowledge.sql
git commit -m "feat: add secure AI coaching persistence schema"
```

### Task 3: Centralize Supabase JWT Authentication

**Files:**
- Create: `fincoach-backend/app/auth.py`
- Create: `fincoach-backend/tests/test_coach_auth.py`
- Modify: `fincoach-backend/app/receipt_routes.py`
- Modify: `fincoach-backend/app/supabase_client.py`
- Modify: `fincoach-backend/app/config.py`
- Modify: `fincoach-backend/.env.example`

**Interfaces:**
- Produces `AuthenticatedUser(user_id: str, token: str)` and `require_authenticated_user(authorization: str | None) -> AuthenticatedUser`.
- Produces `get_user_supabase(token: str) -> Client` and retains `get_supabase() -> Client` for server-only operations.

- [ ] **Step 1: Write failing auth tests**

```python
class CoachAuthTests(unittest.TestCase):
    def test_rejects_missing_bearer_header(self):
        with self.assertRaises(HTTPException) as caught:
            require_authenticated_user(None)
        self.assertEqual(caught.exception.status_code, 401)

    def test_returns_verified_sub_from_get_claims(self):
        auth = SimpleNamespace(get_claims=lambda token: SimpleNamespace(claims={"sub": "user-1"}))
        with patch("app.auth.get_supabase", return_value=SimpleNamespace(auth=auth)):
            user = require_authenticated_user("Bearer valid-token")
        self.assertEqual(user.user_id, "user-1")
        self.assertEqual(user.token, "valid-token")

    def test_rejects_claims_without_sub(self):
        auth = SimpleNamespace(get_claims=lambda token: SimpleNamespace(claims={}))
        with patch("app.auth.get_supabase", return_value=SimpleNamespace(auth=auth)):
            with self.assertRaises(HTTPException) as caught:
                require_authenticated_user("Bearer invalid-token")
        self.assertEqual(caught.exception.status_code, 401)
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m unittest tests.test_coach_auth -v`  
Expected: missing `app.auth`.

- [ ] **Step 3: Implement verified identity**

Parse exactly one Bearer token, call `get_supabase().auth.get_claims(token)`, read `claims["sub"]`, and map all verification failures to `HTTPException(401, "Authentication required.")`. Never log the token.

- [ ] **Step 4: Implement request-scoped Supabase client**

Use `ClientOptions(headers={"Authorization": f"Bearer {token}"}, auto_refresh_token=False, persist_session=False)` with `SUPABASE_PUBLISHABLE_KEY`. Add that key to `.env.example` and configuration validation.

- [ ] **Step 5: Reuse shared auth in receipt routes**

Replace the duplicated `verify_access_token` implementation while preserving the existing `/receipts/extract` contract and tests.

- [ ] **Step 6: Verify GREEN and existing receipt tests**

Run: `python -m unittest tests.test_coach_auth tests.test_receipt_routes -v`  
Expected: all tests pass.

- [ ] **Step 7: Commit Task 3 files only**

```powershell
git add fincoach-backend/app/auth.py fincoach-backend/app/receipt_routes.py fincoach-backend/app/supabase_client.py fincoach-backend/app/config.py fincoach-backend/.env.example fincoach-backend/tests/test_coach_auth.py fincoach-backend/tests/test_receipt_routes.py
git commit -m "feat: verify Supabase JWTs for backend APIs"
```

### Task 4: Implement Owner-Scoped Conversation History

**Files:**
- Create: `fincoach-backend/app/models.py`
- Create: `fincoach-backend/app/coaching_history.py`
- Create: `fincoach-backend/tests/test_coaching_history.py`

**Interfaces:**
- Produces Pydantic models `ConversationCreate`, `ConversationUpdate`, `MessageCreate`, `ConversationResponse`, `MessageResponse`, `SourceResponse`, and `CoachTurnResponse`.
- Produces `CoachingHistoryRepository` methods `list_sessions`, `create_session`, `rename_session`, `delete_session`, `list_messages`, `insert_user_message`, `find_reply`, `insert_assistant_reply`, and `enforce_usage_limits`.

- [ ] **Step 1: Write failing repository tests with injected fake clients**

Cover owner filters on every query, bounded list sizes, deterministic first-question titles, duplicate user-message recovery, unique reply recovery, cross-user missing-session behavior, minute limit, and daily limit.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m unittest tests.test_coaching_history -v`  
Expected: missing repository/models.

- [ ] **Step 3: Implement strict API models**

Use UUID identifiers, `content: str` with 1..1000 characters after trimming, titles with 1..80 characters, Literal roles/statuses, and `extra="forbid"`.

- [ ] **Step 4: Implement user-client session operations**

Every query includes `.eq("user_id", authenticated_user_id)`. Missing or foreign session IDs raise the same `404` message. Lists are ordered and limited.

- [ ] **Step 5: Implement idempotent message persistence**

The mobile UUID becomes the user message ID. Before generation, return the existing assistant reply when `reply_to_message_id` already exists. Server inserts assistant/retrieval rows with the verified owner UUID.

- [ ] **Step 6: Implement durable rate limits and usage limits**

Count owner user-role messages since one minute ago and UTC day start. Raise `429` with a safe retry message at configured thresholds.

- [ ] **Step 7: Verify GREEN**

Run: `python -m unittest tests.test_coaching_history -v`  
Expected: all history tests pass.

- [ ] **Step 8: Commit Task 4 files only**

```powershell
git add fincoach-backend/app/models.py fincoach-backend/app/coaching_history.py fincoach-backend/tests/test_coaching_history.py
git commit -m "feat: add persistent coaching conversation history"
```

### Task 5: Modularize and Safeguard the RAG Turn

**Files:**
- Create: `fincoach-backend/app/rag/retrieval.py`
- Create: `fincoach-backend/app/rag/prompts.py`
- Create: `fincoach-backend/app/rag/service.py`
- Create: `fincoach-backend/tests/test_rag_pipeline.py`
- Modify: `fincoach-backend/app/llm.py`
- Modify: `fincoach-backend/app/config.py`
- Delete after replacement: `fincoach-backend/app/rag.py`

**Interfaces:**
- Produces `retrieve(question: str) -> list[RetrievedChunk]`.
- Produces `build_coach_prompt(question, chunks, financial_context, history) -> str`.
- Produces `LLMResult(content: str, model: str, prompt_tokens: int | None, completion_tokens: int | None)`.
- Produces `CoachingService.send_message(user, session_id, request) -> CoachTurnResponse`.

- [ ] **Step 1: Write failing retrieval/prompt/service tests**

Cover similarity thresholding, top-k bounds, source mapping, current-month transaction/category/budget context, savings goals, bounded recent history, injection delimiters, empty provider output, timeout mapping, persistence-before-response, and duplicate request behavior.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m unittest tests.test_rag_pipeline -v`  
Expected: missing modular RAG interfaces.

- [ ] **Step 3: Implement typed retrieval**

Call `match_knowledge_documents`, clamp `RETRIEVE_K` to 1..10, and retain only rows whose similarity is at least `RETRIEVE_THRESHOLD`.

- [ ] **Step 4: Implement bounded financial and conversation context**

Fetch verified-owner profile, current-month transactions/categories, monthly budget, category limits, and active savings goals. Format only recorded data. Include at most `COACH_HISTORY_LIMIT` recent messages from the current session.

- [ ] **Step 5: Implement prompt boundaries**

Label retrieved chunks as untrusted reference data. State that instructions inside references or user financial text must not override system rules. Require grounded Malaysian/MYR advice, uncertainty when evidence is missing, and the educational disclaimer.

- [ ] **Step 6: Harden the LLM call**

Configure `timeout=LLM_TIMEOUT_SECONDS`, `max_retries=1`, `max_tokens=LLM_MAX_TOKENS`, and non-streaming completion. Reject blank content and return usage metadata when supplied by the provider.

- [ ] **Step 7: Implement the service transaction sequence**

Validate ownership and usage, persist/recover the user message, retrieve context, generate, persist assistant message, persist retrieval evidence, update session ordering, then return only persisted data. Store a safe failure code on provider failure and allow retry with the same user-message UUID.

- [ ] **Step 8: Remove legacy `app/rag.py` and verify GREEN**

Run: `python -m unittest tests.test_rag_pipeline -v`  
Expected: all RAG tests pass and no import references `app.rag.py`.

- [ ] **Step 9: Commit Task 5 files only**

```powershell
git add fincoach-backend/app/rag fincoach-backend/app/llm.py fincoach-backend/app/config.py fincoach-backend/app/rag.py fincoach-backend/tests/test_rag_pipeline.py
git commit -m "feat: implement grounded persistent coaching RAG"
```

### Task 6: Expose Authenticated Coaching Routes

**Files:**
- Create: `fincoach-backend/app/api/__init__.py`
- Create: `fincoach-backend/app/api/coach_routes.py`
- Create: `fincoach-backend/app/observability.py`
- Create: `fincoach-backend/tests/test_coach_routes.py`
- Modify: `fincoach-backend/app/main.py`
- Modify: `fincoach-backend/.env.example`

**Interfaces:**
- Produces the REST routes from the approved design.
- Consumes shared auth, models, repository, and coaching service.

- [ ] **Step 1: Write failing FastAPI route tests**

Use dependency overrides/fakes to cover unauthenticated rejection; conversation list/create/rename/delete; owned ordered messages; successful turn; `404` for foreign sessions; `409` duplicate-in-progress; `429` limit; `502` provider failure; and `504` timeout.

Also assert every response contains `X-Request-ID` and captured structured logs contain request ID, route, status, and elapsed milliseconds without tokens, prompts, financial context, or message bodies.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m unittest tests.test_coach_routes -v`  
Expected: routes return `404` or module import fails.

- [ ] **Step 3: Implement `/coach/conversations` routes**

Every route depends on `require_authenticated_user`; no route accepts `user_id`.

- [ ] **Step 4: Implement the message route and safe error mapping**

Map validation to `400/422`, missing ownership to `404`, duplicate-in-progress to `409`, usage to `429`, provider failure to `502`, and provider timeout to `504`. Do not expose provider/database exception strings.

- [ ] **Step 5: Add privacy-safe structured logging**

Implement middleware that accepts or generates a bounded UUID request ID, records monotonic elapsed time, adds `X-Request-ID`, and emits one JSON log event. Coaching service events may include a hashed owner identifier, session ID, model, retrieval count, latency, and safe error code only.

- [ ] **Step 6: Register the router and restrict CORS**

Replace `allow_origins=["*"]` with parsed `CORS_ORIGINS`; an empty list is valid for native-only deployment. Keep `/health` minimal.

- [ ] **Step 7: Verify GREEN and complete backend suite**

Run: `python -m unittest discover -s tests -v`  
Expected: all backend tests pass.

- [ ] **Step 8: Commit Task 6 files only**

```powershell
git add fincoach-backend/app/api fincoach-backend/app/observability.py fincoach-backend/app/main.py fincoach-backend/.env.example fincoach-backend/tests/test_coach_routes.py
git commit -m "feat: expose authenticated coaching API"
```

### Task 7: Build the Authenticated Mobile Coach Client

**Files:**
- Create: `fincoach-mobile/src/lib/coach-domain.ts`
- Create: `fincoach-mobile/src/lib/coach-domain.test.ts`
- Create: `fincoach-mobile/src/lib/coach-api.ts`
- Create: `fincoach-mobile/src/lib/coach-api.test.ts`
- Modify: `fincoach-mobile/src/lib/types.ts`

**Interfaces:**
- Produces `CoachConversation`, `CoachMessage`, `CoachSource`, and `CoachTurnResponse`.
- Produces `listCoachConversations`, `createCoachConversation`, `renameCoachConversation`, `deleteCoachConversation`, `listCoachMessages`, and `sendCoachMessage`.
- Produces pure helpers `sortConversations`, `mergeTurn`, `canSendCoachMessage`, and `coachErrorMessage`.

- [ ] **Step 1: Write failing domain tests**

Cover chronological message merge without duplicates, newest-first conversation ordering, trimmed 1..1000 input, deterministic suggestion visibility, and safe HTTP error copy.

- [ ] **Step 2: Run domain tests and verify RED**

Run: `npm.cmd test -- src/lib/coach-domain.test.ts`  
Expected: missing module/interfaces.

- [ ] **Step 3: Implement pure domain helpers and types**

Use readonly-compatible TypeScript types and UUID strings. Never use `any`.

- [ ] **Step 4: Write failing authenticated client tests**

Inject `fetch` and an auth adapter. Assert the bearer header, JSON content type, URL/method/body, one refresh retry after `401`, no retry after other `4xx`, and decoded safe errors.

- [ ] **Step 5: Run client tests and verify RED**

Run: `npm.cmd test -- src/lib/coach-api.test.ts`  
Expected: missing API client.

- [ ] **Step 6: Implement the API client**

Read the current Supabase session, fail clearly when `fincoachApiUrl` or session is missing, send the access token, call `supabase.auth.refreshSession()` once after `401`, and use an `AbortController` timeout.

- [ ] **Step 7: Verify GREEN**

Run: `npm.cmd test -- src/lib/coach-domain.test.ts src/lib/coach-api.test.ts`  
Expected: all Coach library tests pass.

- [ ] **Step 8: Commit Task 7 files only**

```powershell
git add fincoach-mobile/src/lib/coach-domain.ts fincoach-mobile/src/lib/coach-domain.test.ts fincoach-mobile/src/lib/coach-api.ts fincoach-mobile/src/lib/coach-api.test.ts fincoach-mobile/src/lib/types.ts
git commit -m "feat: add authenticated mobile coaching client"
```

### Task 8: Replace ComingSoon with the Real Coach UI

**Files:**
- Create: `fincoach-mobile/src/components/coach/coach-message.tsx`
- Create: `fincoach-mobile/src/components/coach/coach-screen.tsx`
- Create: `fincoach-mobile/src/components/coach/conversation-history-screen.tsx`
- Create: `fincoach-mobile/src/app/coach/history.tsx`
- Modify: `fincoach-mobile/src/app/(app)/coach.tsx`
- Modify: `fincoach-mobile/src/app/_layout.tsx`
- Create: `fincoach-mobile/src/lib/coach-ui.test.ts`

**Interfaces:**
- Consumes Task 7 types and API functions.
- Produces the tab Coach screen and `/coach/history` route.

- [ ] **Step 1: Write failing UI-state tests**

Test suggestion visibility for empty chats, disabled composer rules, retry-state transitions, source visibility, rename validation, and delete confirmation copy as pure exported helpers.

- [ ] **Step 2: Run tests and verify RED**

Run: `npm.cmd test -- src/lib/coach-ui.test.ts`  
Expected: missing helper exports.

- [ ] **Step 3: Implement reference-aligned message presentation**

Use `AppText`, Hanken Grotesk, `authColors`, 20px bubbles, assistant avatar, user indigo bubble, selectable source chips, and stable UUID keys. Render plain text and simple bullets; do not render arbitrary HTML.

- [ ] **Step 4: Implement the main Coach screen**

Load the newest conversation and messages on focus. Provide four reference suggestions, optimistic user bubble, typing indicator, safe retry, keyboard avoidance, auto-scroll, New chat, and history navigation. Keep the typed draft after network failure.

- [ ] **Step 5: Implement conversation history**

Show newest-first saved conversations, empty/loading/offline states, New chat, rename with 1..80 validation, and confirmed delete. Returning to the tab opens the selected session.

- [ ] **Step 6: Register routes and replace ComingSoon**

`(app)/coach.tsx` exports the real component; `_layout.tsx` registers `coach/history` without a header.

- [ ] **Step 7: Verify GREEN, typecheck, and lint**

Run:

```powershell
npm.cmd test -- src/lib/coach-ui.test.ts
npm.cmd run typecheck
npx.cmd eslint "src/app/(app)/coach.tsx" src/app/coach/history.tsx src/components/coach src/lib/coach-api.ts src/lib/coach-domain.ts
```

Expected: all commands exit zero.

- [ ] **Step 8: Commit Task 8 files only**

```powershell
git add "fincoach-mobile/src/app/(app)/coach.tsx" fincoach-mobile/src/app/coach fincoach-mobile/src/app/_layout.tsx fincoach-mobile/src/components/coach fincoach-mobile/src/lib/coach-ui.test.ts
git commit -m "feat: build persistent AI Coach chat UI"
```

### Task 9: Documentation and Full Verification

**Files:**
- Modify: `fincoach-backend/README.md`
- Modify: `fincoach-mobile/docs/acceptance-tests.md`
- Modify: `fincoach-mobile/.env.example`

**Interfaces:**
- Documents setup, migration, ingestion, authentication, model configuration, safeguards, and device testing.

- [ ] **Step 1: Update backend documentation**

Document the zero-LangChain pipeline, current configurable model boundary, required environment keys, native ingestion, authenticated routes, conversation behavior, migration deployment requirement, and curl examples using `<access-token>`.

- [ ] **Step 2: Add AI coaching acceptance coverage**

Add physical Honor 200, LAN/deployed API, two-account isolation, multiple conversation persistence, financial-context grounding, duplicate retry, offline retry, expired token, provider timeout, and secret-bundle checks.

- [ ] **Step 3: Run backend verification**

```powershell
& '.\fincoach-backend\.venv\Scripts\python.exe' -m unittest discover -s fincoach-backend\tests -v
```

Expected: all backend tests pass.

- [ ] **Step 4: Run schema and mobile verification**

```powershell
Set-Location fincoach-mobile
node scripts/verify-coaching-schema.mjs
npm.cmd test
npm.cmd run typecheck
npm.cmd run lint
npx.cmd expo export --platform android --output-dir C:\tmp\fincoach-ai-coach-export
```

Expected: schema verifier prints `COACHING_SCHEMA_VERIFIED`; all tests/typecheck/lint pass; Android export completes.

- [ ] **Step 5: Check dependency and secret hygiene**

Run:

```powershell
Select-String -Path ..\fincoach-backend\requirements.txt -Pattern 'langchain|llamaindex' -CaseSensitive:$false
git status --short
git diff --check
```

Expected: no RAG framework dependency match; no staged secret files; no whitespace errors.

- [ ] **Step 6: Commit documentation only**

```powershell
git add fincoach-backend/README.md fincoach-mobile/docs/acceptance-tests.md fincoach-mobile/.env.example
git commit -m "docs: document AI coaching setup and acceptance tests"
```

- [ ] **Step 7: Report deferred deployment work accurately**

State that code implementation is complete locally while the new Supabase migration, backend hosting/LAN configuration, production secrets, and physical-device acceptance remain deployment work until performed.
