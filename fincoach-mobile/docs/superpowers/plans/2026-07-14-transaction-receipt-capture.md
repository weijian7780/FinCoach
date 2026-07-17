# Transaction and Receipt Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build prototype-aligned manual transaction CRUD and real PaddleOCR receipt capture for the FinCoach Android app.

**Architecture:** The Expo app owns transaction UI, validation, Supabase CRUD, private receipt upload, and editable receipt drafts. The existing FastAPI service exposes one authenticated multipart OCR endpoint backed by a lazy PaddleOCR service and deterministic receipt parser. PostgreSQL keeps one ERD-aligned `transactions` table; receipt items remain temporary review data.

**Tech Stack:** Expo SDK 56, React Native 0.85, Expo Router, Expo Camera, Expo ImagePicker, TypeScript, Vitest, Supabase PostgreSQL/Storage/RLS, FastAPI, pytest, Pillow, PaddleOCR.

## Global Constraints

- Follow only the root prototype files in `G:\My Drive\FYP 1 & 2\FinCoach UI`; ignore nested folders.
- Use `expo-camera` for the live in-app preview and direct capture; keep `expo-image-picker` for gallery selection only.
- Use real PaddleOCR through FastAPI; do not require an LLM for receipt structuring.
- Keep one ERD-aligned `transactions` table; do not add persisted receipt or receipt-item tables.
- Store confirmed receipt images in a private `receipts` bucket under `<user_id>/<transaction_id>.<extension>`.
- Require explicit user review before saving an OCR result.
- Do not add `react-native-svg`, `@react-native-community/datetimepicker`, or another native date picker.
- Preserve the existing Hanken Grotesk and FinCoach indigo UI tokens.
- Do not create branches, commits, worktrees, or push changes; the user handles GitHub.

---

### Task 1: Transaction schema, private receipt storage, and verification

**Files:**
- Create: `supabase/migrations/20260714000000_complete_transaction_receipt_capture.sql`
- Create: `scripts/verify-transaction-schema.mjs`
- Modify: `supabase/schema.sql`

**Interfaces:**
- Produces table `public.transactions` and private bucket `receipts`.
- Produces columns consumed by the mobile client: `id`, `user_id`, `category_id`, `amount`, `transaction_date`, `description`, `source`, `receipt_image_path`, `created_at`, `updated_at`.

- [ ] Write a failing schema verification script asserting the migration contains the table, constraints, indexes, explicit grants, four owner-scoped RLS policies, private bucket limits, and owner-folder Storage policies.
- [ ] Run `node scripts/verify-transaction-schema.mjs`; expect failure because the migration does not exist.
- [ ] Create the idempotent migration. Seed a system `Income` category, create `transactions`, validate category visibility/type through a private trigger, add indexes, RLS, grants, and a private `receipts` bucket restricted to JPEG/PNG/WebP and 5 MB.
- [ ] Mirror the final migration in `supabase/schema.sql` so fresh-project setup and incremental setup stay aligned.
- [ ] Run `node scripts/verify-transaction-schema.mjs`; expect all assertions to pass.

### Task 2: Transaction domain model and Supabase data client

**Files:**
- Create: `src/lib/transaction-domain.test.ts`
- Create: `src/lib/transaction-domain.ts`
- Create: `src/lib/transactions.test.ts`
- Create: `src/lib/transactions.ts`
- Modify: `src/lib/types.ts`

**Interfaces:**
- Produces `Transaction`, `TransactionWriteInput`, `TransactionDraft`, and `ReceiptItemDraft` types.
- Produces `validateTransactionInput`, `groupTransactionsByDate`, `filterTransactions`, `formatTransactionAmount`, and `transactionTypeForCategory`.
- Produces `fetchTransactions`, `fetchTransaction`, `createTransaction`, `updateTransaction`, `deleteTransaction`, `uploadReceiptImage`, `deleteReceiptImage`, and `createReceiptSignedUrl`.

- [ ] Write failing domain tests for positive RM parsing, future-date rejection, source/note limits, income/expense category matching, date grouping, category filtering, and signed display amounts.
- [ ] Run `npm.cmd test -- src/lib/transaction-domain.test.ts`; expect missing-module failure.
- [ ] Implement the pure domain functions with date-only and two-decimal money handling.
- [ ] Run the domain tests; expect pass.
- [ ] Write failing injected-client tests covering ordered owner reads, CRUD filters, Storage upload as `ArrayBuffer`, signed URL creation, cleanup, and error propagation.
- [ ] Implement the typed Supabase client boundary and add transaction types.
- [ ] Run `npm.cmd test -- src/lib/transactions.test.ts src/lib/transaction-domain.test.ts`; expect pass.

### Task 3: Authenticated PaddleOCR backend and deterministic parser

**Files:**
- Create: `fincoach-backend/tests/test_receipt_parser.py`
- Create: `fincoach-backend/tests/test_receipt_api.py`
- Create: `fincoach-backend/app/receipt_parser.py`
- Create: `fincoach-backend/app/receipt_ocr.py`
- Create: `fincoach-backend/app/auth.py`
- Modify: `fincoach-backend/app/main.py`
- Modify: `fincoach-backend/app/config.py`
- Modify: `fincoach-backend/requirements.txt`
- Modify: `fincoach-backend/.env.example`

**Interfaces:**
- Produces `parse_receipt(lines: list[OCRLine]) -> ReceiptExtraction`.
- Produces lazy `extract_lines(image_bytes: bytes) -> list[OCRLine]`.
- Produces authenticated `POST /receipts/extract` multipart endpoint returning merchant, transaction date, total, items, category suggestion, confidences, and sanitized lines.

- [ ] Write failing parser tests using Malaysian-style receipt text fixtures for merchant, `DD/MM/YYYY`, ISO/text dates, `TOTAL` precedence, subtotal/tax exclusion, item pairs, and Food/Transport/Education/Entertainment/Others category scoring.
- [ ] Run the backend pytest command; expect import failure.
- [ ] Implement Pydantic parser models and deterministic parsing functions.
- [ ] Run parser tests; expect pass.
- [ ] Write failing API tests for missing/invalid bearer token, unsupported MIME, over-5-MB image, undecodable image, mocked OCR success, and OCR failure translation.
- [ ] Add Supabase JWT verification, lazy PaddleOCR loading, bounded inference concurrency, multipart endpoint, configuration, and pinned dependency ranges compatible with the active Python runtime.
- [ ] Run backend tests with OCR mocked; expect pass without downloading models.

### Task 4: Prototype transaction history and detail management

**Files:**
- Create: `src/components/transactions/transaction-row.tsx`
- Create: `src/components/transactions/transaction-detail-sheet.tsx`
- Create: `src/lib/transaction-ui.test.ts`
- Modify: `src/app/(app)/transactions.tsx`

**Interfaces:**
- Consumes transaction domain/client interfaces from Task 2.
- Produces the main Transactions tab with route links to `/transactions/manage` and detail callbacks.

- [ ] Write a failing structural UI test asserting the prototype title, add action, category chips, date groups, empty/error states, detail sheet, Edit, and Delete flows.
- [ ] Run `npm.cmd test -- src/lib/transaction-ui.test.ts`; expect failure against the placeholder.
- [ ] Build the prototype-aligned list, filter chips, grouped cards, category avatars, loading/retry/empty states, and owner CRUD detail sheet.
- [ ] Run the structural and transaction tests; expect pass.

### Task 5: Prototype manual create/edit transaction form

**Files:**
- Create: `src/app/transactions/manage.tsx`
- Create: `src/components/transactions/category-picker.tsx`
- Create: `src/components/transactions/transaction-form.tsx`
- Modify: `src/app/_layout.tsx`
- Modify: `src/lib/transaction-ui.test.ts`

**Interfaces:**
- Consumes categories from `src/lib/budget.ts`, validation from Task 2, and CRUD from Task 2.
- Produces one reusable form for create, edit, and prefilled receipt drafts.

- [ ] Extend the failing UI test for Manual/Scan Receipt tabs, Income/Expense selector, RM amount card, type-filtered category picker, source, date, note, create/edit labels, and root route registration.
- [ ] Run the focused UI test; expect failure.
- [ ] Implement the prototype-aligned keyboard-safe form and route. Link Scan Receipt to `/receipts/scan`; fetch existing records in edit mode; preserve input on errors.
- [ ] Run focused UI, domain, and client tests; expect pass.

### Task 6: Receipt capture, OCR draft, editable review, upload, and compensation

**Files:**
- Create: `src/lib/receipt-api.test.ts`
- Create: `src/lib/receipt-api.ts`
- Create: `src/lib/receipt-draft-context.tsx`
- Create: `src/app/receipts/scan.tsx`
- Create: `src/app/receipts/review.tsx`
- Create: `src/components/receipts/receipt-item-editor.tsx`
- Modify: `src/app/_layout.tsx`
- Modify: `src/app.json`
- Modify: `src/lib/transaction-ui.test.ts`

**Interfaces:**
- Produces `extractReceipt(image, accessToken, signal) -> ReceiptExtractionDraft`.
- Produces receipt draft context storing image URI/MIME/extension, extracted fields, items, and confidence.
- Consumes transaction and Storage operations from Task 2.

- [ ] Write failing API tests for multipart request construction, bearer token, timeout/abort, success decoding, and friendly error translation.
- [ ] Implement the receipt API client using `EXPO_PUBLIC_OCR_API_URL` and a bounded timeout.
- [ ] Write failing structural tests for prototype dark scan frame, camera/gallery actions, selected-image preview, OCR loading/retry/manual actions, editable Review Receipt fields/items, Rescan, and Save.
- [ ] Implement the draft context, prototype scan screen using Expo Camera with Retake/Use Photo confirmation and ImagePicker gallery fallback, and editable review screen.
- [ ] Implement confirmed save: client-generated UUID, base64-to-ArrayBuffer private upload, transaction insert, uploaded-object deletion if insert fails, and draft clearing on success.
- [ ] Update ImagePicker permission copy to cover private receipt images.
- [ ] Run receipt API/UI/transaction tests; expect pass.

### Task 7: Connect transactions to Budget/Home and complete verification

**Files:**
- Modify: `src/lib/budget.ts`
- Modify: `src/app/(app)/budget.tsx`
- Modify: `src/app/(app)/index.tsx`
- Modify: `src/lib/budget.test.ts`
- Modify: `docs/acceptance-tests.md`
- Modify: `design-qa.md`

**Interfaces:**
- Consumes expense transactions by month/category.
- Produces real recorded-spending totals for existing budget progress and Home preview.

- [ ] Write failing budget tests asserting only expense-category transactions count toward spending, grouped by selected month/category.
- [ ] Implement transaction aggregation in the budget data load and current-month Home preview without adding report or alert behavior.
- [ ] Run the complete mobile test suite and backend test suite; expect pass.
- [ ] Run `npm.cmd run typecheck`, focused/full ESLint, `node scripts/verify-transaction-schema.mjs`, Python compilation, and `npx.cmd expo install --check`; expect pass.
- [ ] Run `npx.cmd expo export --platform android` to a temporary output directory; expect a successful Android bundle.
- [ ] Record source-level design QA and mark device comparison blocked unless the Honor 200 is connected through ADB for same-state screenshots.
- [ ] Update acceptance instructions for manual CRUD, camera/gallery OCR, review correction, private image access, retry, edit/delete, budget totals, and reload persistence.

## Plan self-review

- Every approved UI, database, OCR, security, compensation, testing, and acceptance requirement maps to a task.
- The plan contains no deferred functionality or placeholder requirements.
- Transaction, draft, parser, endpoint, and Storage interfaces use consistent names across tasks.
- The work remains one cohesive module; later AI, reporting, export, backup, and alert modules remain out of scope.
