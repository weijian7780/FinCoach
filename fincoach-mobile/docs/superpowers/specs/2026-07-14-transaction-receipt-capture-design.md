# Transaction and Receipt Capture Management Design

Date: 2026-07-14

## Objective

Complete the FinCoach Transaction and Receipt Capture Management module while preserving the existing Expo, Supabase, FastAPI, current ERD, and root FinCoach UI prototype architecture.

## Approved scope

The module will provide:

- manual creation of income and expense transactions;
- transaction history grouped by date and filtered by category;
- retrieval, editing, and deletion of user-owned transactions;
- receipt capture through an embedded `expo-camera` live preview, with `expo-image-picker` retained for the photo library;
- real receipt OCR through PaddleOCR hosted by the existing FastAPI backend;
- extraction of merchant, date, total amount, receipt items, and a suggested category;
- an editable Review Receipt screen before any record is saved;
- private receipt-image storage in Supabase Storage;
- transaction persistence in Supabase PostgreSQL with owner-based Row Level Security.

The selected implementation uses `expo-camera` for an in-app rear-camera preview and direct capture. `expo-image-picker` remains the gallery-only fallback. This removes the misleading static scanner frame and the extra Honor system-camera handoff.

## UI source of truth

The root files in `G:\My Drive\FYP 1 & 2\FinCoach UI` are the visual authority. Nested folders are not used.

The implementation follows these prototype screens:

- `Transactions` from `screens_app.jsx`;
- `AddTransaction` from `screens_app.jsx`;
- `ScanReceipt` from `screens_extra.jsx`;
- `ReceiptReview` from `screens_extra.jsx`;
- the transaction detail sheet from `app.jsx`.

Necessary additions remain within the prototype style:

- an Income/Expense selector because the thesis scope requires both transaction types;
- an Edit action because the module requires full CRUD;
- explicit loading, retry, permission, empty, validation, and low-confidence states;
- editable receipt fields and receipt items rather than static review content.

The visual system remains Hanken Grotesk, FinCoach indigo, warm off-white background, rounded white cards, tonal category icons, compact chips, prototype spacing, and the current bottom navigation.

## Explicit non-goals

- No bank or external account integration.
- No automatic transaction import.
- No background receipt scanning.
- No handoff to the Honor system-camera application for receipt capture.
- No LLM-dependent receipt structuring in this module. PaddleOCR plus deterministic parsing is the approved low-cost path.
- No AI financial advice, report generation, export, backup, or alert delivery.
- No separate persisted receipt-item or raw-OCR table because the current ERD has one `TRANSACTION` entity.
- No automatic transaction save. User confirmation is always required.

## Existing-state findings

The current application has:

- a Transactions tab containing only a `ComingSoon` placeholder;
- no transaction client, domain model, routes, or tests;
- no `transactions` table in the active schema or migrations;
- shared `categories` with `bigint` IDs and expense/income type support;
- `expo-image-picker` already installed and registered in `app.json`;
- a separate FastAPI backend with `/health` and `/coach`, but no OCR dependencies or endpoint;
- no PaddleOCR implementation in either repository;
- no receipt Storage bucket or receipt-specific policies.

The current ERD defines one `TRANSACTION` entity with `TRANS_ID`, `USR_ID`, `CATEGORY_ID`, `TRANS_Amount`, `TRANS_Date`, `TRANS_Description`, `TRANS_Source`, and `TRANS_ReceiptImageURL`. The database design retains this single-entity structure.

## Data architecture

### `transactions`

One table stores manual and receipt-derived transaction records:

- `id uuid primary key default gen_random_uuid()`;
- `user_id uuid not null references auth.users(id) on delete cascade`;
- `category_id bigint not null references categories(id)`;
- `amount numeric(12,2) not null check (amount > 0)`;
- `transaction_date date not null`;
- `description text null`;
- `source text not null`;
- `receipt_image_path text null`;
- `created_at timestamptz not null default now()`;
- `updated_at timestamptz not null default now()`.

The category relationship determines whether a transaction is income or expense through `categories.type`. Amounts remain positive in storage, avoiding mixed sign semantics. Expense totals subtract expense-category amounts; income totals add income-category amounts.

`source` stores the merchant or income source and maps to ERD `TRANS_Source`. `description` stores the optional note and maps to `TRANS_Description`. `receipt_image_path` stores the private Storage object path and maps to `TRANS_ReceiptImageURL`; a short-lived signed URL is generated only when the client needs to display the image.

Manual transactions use `receipt_image_path = null`. Receipt items and raw OCR lines exist only in the extraction draft returned to the Review Receipt screen. The confirmed transaction stores the total, source, date, description, category, and image path required by the ERD.

### System income category

The migration ensures one system `Income` category exists with `type = 'income'`, a suitable icon, and the FinCoach success colour. User-created categories remain expense-only under the existing Budget module rules.

### Constraints and indexes

- Amount must be greater than zero.
- Source must contain 1 to 120 trimmed characters.
- Description is optional and limited to 300 characters.
- Transaction date cannot be unreasonably far in the future; the mobile client rejects future dates and the database enforces `transaction_date <= current_date`.
- Receipt paths, when present, must begin with the authenticated user's folder prefix at the Storage policy boundary.
- `(user_id, transaction_date desc, created_at desc)` supports history queries.
- `(user_id, category_id, transaction_date desc)` supports budget and report aggregation.

### RLS and Data API access

- RLS is enabled on `transactions`.
- Authenticated users can select, insert, update, and delete only rows where `user_id = auth.uid()`.
- Update uses both `USING` and `WITH CHECK`.
- Category references must resolve to a visible system category or a category owned by the same user.
- Explicit authenticated-role grants expose only required operations.
- The client includes the user ID in write filters as defense in depth.

### Receipt Storage

A private `receipts` bucket accepts JPEG, PNG, and WebP images with a 5 MB limit. Object paths use:

`<user_id>/<transaction_id>.<extension>`

Storage policies permit authenticated users to select, insert, and delete only objects in their own first-level folder. No public URL is created. Display uses authenticated download or a short-lived signed URL.

The mobile application never contains a Supabase service-role key. The FastAPI service-role key remains server-only.

## Mobile application architecture

### Routes

- `src/app/(app)/transactions.tsx`: transaction history tab.
- `src/app/transactions/manage.tsx`: create and edit manual transactions.
- `src/app/receipts/scan.tsx`: prototype-styled receipt capture/gallery entry screen.
- `src/app/receipts/review.tsx`: editable OCR review and confirmation.

The root stack registers the management, scan, and review routes with hidden native headers to preserve the prototype page bars. The Transactions tab remains the main module entry.

### Transactions screen

- title and indigo circular add button;
- horizontal category filter chips;
- transaction rows grouped by local calendar date;
- category avatar, source, category/date metadata, and RM amount;
- green amount treatment for income;
- explicit loading, empty-filter, first-transaction, and retry states;
- detail sheet with category, date, note, receipt preview when present, Edit, and confirmed Delete.

### Add/Edit Transaction screen

- prototype page bar and Manual/Scan Receipt tabs;
- Income/Expense segmented selector;
- large RM amount card;
- category selector filtered by transaction type;
- merchant or income-source field;
- transaction date field using the existing pure React Native date component;
- optional note;
- keyboard-safe scrolling, inline field errors, and disabled saving state;
- create and edit use the same validated form.

### Scan Receipt screen

The screen follows the dark prototype scanner visual with a live embedded camera view:

- back button and PaddleOCR capability chip;
- receipt alignment frame with instruction text;
- gallery button and central capture button;
- the receipt frame contains the rear-camera preview through `CameraView`;
- capture takes the photo directly, then shows Retake and Use Photo controls;
- gallery launches the system photo library;
- after selection, the image appears inside the frame and OCR processing starts;
- processing, retry, permission-denied, and invalid-image states remain on this screen;
- successful extraction routes to Review Receipt with a temporary draft.

A functional torch button is shown while the live camera is active. Permission denial and camera mount failures provide recovery states inside the frame.

### Review Receipt screen

- prototype page bar and receipt thumbnail;
- suggested-category chip with confidence indication;
- editable source, amount, date, category, and note;
- editable receipt item rows with add and remove controls;
- field-level low-confidence indicators;
- Save Transaction primary action;
- Rescan Receipt secondary action;
- no persistence before user confirmation.

Receipt item edits help the user validate the total but are not stored separately under the current ERD.

### State transfer

The selected image URI and OCR draft are short-lived navigation state managed by a focused receipt-draft context. Large base64 image data is not passed through Expo Router parameters. Leaving the flow clears the draft after confirmation or explicit cancellation.

## FastAPI OCR architecture

### Endpoint

`POST /receipts/extract`

Input:

- multipart image file;
- `Authorization: Bearer <Supabase access token>`.

Output:

- `merchant`;
- `transaction_date`;
- `total_amount`;
- `items[]` with description and amount;
- `suggested_category`;
- per-field confidence;
- sanitized raw OCR lines for debugging and review.

The endpoint verifies the Supabase access token and rejects unauthenticated callers. It validates MIME type, decoded image format, image dimensions, and the 5 MB size limit before inference.

### PaddleOCR service

PaddleOCR loads once through a lazy singleton rather than once per request. The initial configuration prioritizes CPU compatibility and receipt accuracy using current Latin/English-capable mobile OCR models. The device can be changed through backend environment configuration without altering the API.

The OCR service receives bytes in memory, performs recognition, returns ordered text lines with confidence, and does not persist the image.

### Deterministic receipt parser

Pure parsing functions transform OCR lines into an editable draft:

- merchant: highest-confidence plausible heading near the top;
- date: Malaysian and common numeric/text receipt-date patterns;
- total: values associated with `TOTAL`, `GRAND TOTAL`, `NETT`, or `AMOUNT DUE`, with a safe fallback to the strongest final amount;
- items: description/price line pairs excluding subtotal, tax, change, and payment rows;
- category: keyword scoring across merchant and item descriptions against visible FinCoach categories.

The parser never claims certainty when evidence is weak. Missing or low-confidence fields are returned as empty or flagged values for user correction.

## End-to-end data flow

### Manual transaction

1. User opens Add Transaction.
2. User selects Income or Expense and enters the validated form.
3. Client inserts one owner-scoped `transactions` row.
4. Transactions history reloads and shows the new record.

### Receipt transaction

1. User opens Scan Receipt and selects camera or gallery.
2. Mobile sends the image to authenticated `POST /receipts/extract`.
3. FastAPI validates the token and image, runs PaddleOCR, parses fields, and returns an extraction draft.
4. Mobile opens Review Receipt and the user corrects the draft.
5. Client generates a transaction UUID and uploads the image to the private user folder using that UUID.
6. Client inserts the confirmed `transactions` row with the same UUID and Storage path.
7. If insertion fails, the client deletes the newly uploaded object.
8. On success, the draft is cleared and the Transactions history reloads.

### Update and delete

- Updating changes validated transaction fields but does not overwrite the receipt object unless the user rescans.
- Deleting a manual transaction deletes only its database row.
- Deleting a receipt transaction first records the path, deletes the row, then attempts Storage cleanup. Cleanup failure is retryable and logged without restoring a deleted financial record.

## Validation and error handling

- Amount must be valid RM greater than zero.
- Source is required and trimmed.
- Category must match the selected Income/Expense type.
- Date must be valid and not in the future.
- Note length is limited to 300 characters.
- Camera/gallery permission denial shows a clear retry action.
- Unsupported, corrupted, oversized, or undecodable images are rejected before OCR.
- FastAPI timeout or PaddleOCR failure preserves the selected photo for Retry or Manual Entry.
- Low-confidence and missing fields are visibly marked on Review Receipt.
- Save is disabled during submission to prevent duplicate transactions.
- Upload-success/insert-failure removes the uploaded image.
- Failed creates or updates preserve user input.
- Raw database, Storage, Paddle, and Python errors are translated into concise user-facing messages.
- OCR requests use a bounded timeout and the backend limits concurrent inference to avoid memory exhaustion.

## Security and privacy

- Every OCR request requires a verified Supabase user token.
- Receipt bytes are processed in memory and are not retained by FastAPI.
- Confirmed receipt images use a private Storage bucket.
- RLS isolates transaction rows and Storage paths by authenticated owner.
- Service-role and model/backend secrets never enter the mobile bundle.
- MIME type is not trusted alone; decoded image validation is required.
- File size, dimensions, and OCR concurrency are bounded.
- API logs exclude receipt text and image contents.

## Testing strategy

Implementation follows red-green-refactor.

### Mobile tests

- transaction form validation for income and expense;
- date, money, description, and source validation;
- transaction grouping, filtering, display amount, and category-type rules;
- Supabase query construction, ordering, owner filters, CRUD, and error propagation through an injected data-client boundary;
- receipt draft transitions and cleanup;
- upload/insert compensation when insertion fails;
- structural route and prototype-content regression tests;
- regression checks for `CameraView`, direct capture, torch control, gallery fallback, and the continued absence of `RNCDatePicker` and `react-native-svg`.

### Backend tests

- parser fixtures for Malaysian/common receipt dates, totals, tax/subtotal exclusion, items, and category scoring;
- endpoint authentication, MIME, size, decode, timeout, and success responses;
- mocked PaddleOCR inference so normal tests do not download models;
- OCR-service singleton and error translation;
- representative real-receipt smoke test after model installation.

### SQL verification

- table fields, types, foreign keys, constraints, and indexes;
- explicit grants for current Supabase Data API exposure behavior;
- user A cannot read or mutate user B transactions;
- category visibility and type enforcement;
- private receipt upload/read/delete isolation;
- manual rows accept null receipt paths;
- cascaded user deletion removes transaction rows.

### Build verification

- mobile unit tests;
- backend tests;
- TypeScript typecheck;
- focused ESLint;
- Python compilation/static import check;
- Supabase schema verification script;
- Expo dependency check;
- Android production export;
- Honor 200 acceptance test with one manual expense, one income, one camera receipt, one gallery receipt, edit, delete, reload, permission denial, and OCR retry.

## Acceptance criteria

- A signed-in user can create manual income and expense transactions.
- The user can view history grouped by date and filter it by category.
- The user can open, edit, and delete only their own transactions.
- The Scan Receipt screen visually follows the approved root prototype.
- Camera capture works through the embedded Expo Camera preview; gallery selection works through Expo ImagePicker.
- A selected image is processed by real PaddleOCR through FastAPI.
- Merchant, date, total, items, and a category suggestion appear in Review Receipt.
- Every extracted field can be corrected before saving.
- Nothing is saved automatically after OCR.
- Confirmed receipt images are private and accessible only to their owner.
- Receipt transactions persist with the ERD-aligned transaction fields and Storage path.
- Manual transactions persist without a receipt path.
- OCR/backend failures preserve the photo and offer Retry or Manual Entry.
- Duplicate saves are prevented.
- Failed database insertion after upload removes the uploaded object.
- Transaction totals are immediately available to the existing Budget and Home calculations without implementing later Report, Alert, Export, Backup, or AI modules.
- No new live-camera, SVG, or native date-picker dependency is introduced.

## Requirement traceability

| Requirement | Design evidence |
|---|---|
| Manual income and expense records | Shared Add/Edit Transaction form and `transactions` table |
| Receipt capture | Embedded Expo Camera preview plus Expo ImagePicker gallery fallback |
| Smart extraction | Authenticated FastAPI PaddleOCR endpoint and deterministic parser |
| Merchant, date, amount, category extraction | Structured OCR response and editable Review Receipt fields |
| Receipt items | Temporary editable review items derived from OCR |
| Review before save | No persistence until explicit Save Transaction |
| Transaction retrieval | Date-grouped history with category filters and detail sheet |
| Transaction update/delete | Shared edit form and confirmed deletion with receipt cleanup |
| ERD alignment | One `transactions` table with nullable receipt Storage path |
| User-data isolation | Transaction RLS, private Storage policies, JWT-verified OCR endpoint |
