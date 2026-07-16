# Financial Data Export and Backup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a real FinCoach module that exports owner-scoped financial data as CSV/PDF and creates, validates, restores, retains, and deletes private Supabase cloud backups.

**Architecture:** Pure TypeScript owns export selection, CSV/HTML generation, deterministic backup documents, validation, hashing inputs, and retention. A focused Supabase client owns normalized export metadata, full-data reads, private Storage operations, profile backup preference, and the atomic restore RPC. Expo-specific file generation and sharing stay behind an injected platform adapter, while Expo Router screens follow the approved FinCoach UI.

**Tech Stack:** React Native 0.85, Expo SDK 56, Expo Router, TypeScript 6, Supabase JS 2.108, PostgreSQL/RLS, Supabase Storage, Expo FileSystem, Expo Print, Expo Sharing, Expo Crypto, Vitest 4.

## Global Constraints

- Use real Supabase data and real files only; no mock production rows or simulated success.
- Preserve the normalized ERD: `USER 1:N DATA_EXPORT`, `DATA_EXPORT 1:N EXPORT_CONTENT`, and `USER 1:N BACKUP`.
- Store arbitrary export sections in `export_contents`; do not use arrays or comma-separated lists.
- Keep restore as a process and store only the latest restore state on `backups`.
- Use a private `financial-backups` bucket with owner-folder Storage RLS.
- Keep `profiles.auto_backup_enabled` outside backup payload restoration.
- Never expose a service-role key or signed public backup URL.
- Use a narrowly scoped `SECURITY DEFINER` restore function with a fixed `search_path`, explicit `auth.uid()` checks, revoked `PUBLIC` execution, and owner validation.
- Create the migration filename through `npx supabase migration new`; do not invent it.
- Preserve all unrelated dirty-worktree changes and do not stage them.
- Follow red-green-refactor: every production behavior starts with a focused failing test.

## File map

- Modify `package.json` and `package-lock.json`: add SDK-compatible `expo-print` and `expo-sharing`.
- Modify `src/lib/types.ts`: export, backup, source-document, and restore result types; add `Profile.auto_backup_enabled`.
- Create `src/lib/export-backup-domain.ts`: selection validation, local dates, CSV/HTML, backup serialization/validation, retention, filenames, and paths.
- Create `src/lib/export-backup-domain.test.ts`: pure domain coverage.
- Create `src/lib/export-backup.ts`: owner-scoped Supabase tables, Storage, preference, source retrieval, and restore RPC.
- Create `src/lib/export-backup.test.ts`: injected-client query and Storage behavior.
- Create `src/lib/export-files.ts`: Expo FileSystem/Print/Sharing adapter.
- Create `src/lib/export-files.test.ts`: injected platform behavior.
- Create `src/lib/export-backup-ui.test.ts`: route and UI regression checks.
- Create `src/components/export-backup/export-sheet.tsx`: format, date, and content selection.
- Create `src/components/export-backup/export-backup-components.tsx`: reusable rows, status, progress, and backup cards.
- Create `src/app/export-backup/index.tsx`: main export/backup orchestration.
- Create `src/app/export-backup/success.tsx`: completed export details and re-share.
- Create `src/app/export-backup/restore.tsx`: backup history, validation, deletion, and restore.
- Modify `src/app/profile/settings.tsx`: navigate to `/export-backup`.
- Modify `src/app/_layout.tsx`: register export/backup routes.
- Modify `src/lib/auth-context.tsx`: trigger eligible automatic backups after authenticated bootstrap/foreground without changing auth behavior.
- Modify `supabase/schema.sql`: normalized tables, profile preference, private bucket, RLS, and restore function.
- Create CLI-generated `supabase/migrations/*_complete_financial_data_export_backup.sql`.
- Create `scripts/verify-export-backup-schema.mjs`: static schema and migration verifier.
- Modify `docs/acceptance-tests.md`: real Android export, backup, corruption, retention, and restore checks.

---

### Task 1: Export and backup domain model

**Files:**
- Create: `src/lib/export-backup-domain.test.ts`
- Create: `src/lib/export-backup-domain.ts`
- Modify: `src/lib/types.ts`

**Interfaces:**
- Produces: `ExportFormat`, `ExportContentType`, `ExportSelection`, `ExportSourceData`, `DataExportRecord`, `BackupRecord`, `FinancialBackupDocumentV1`, `validateExportSelection()`, `createExportPreset()`, `buildExportCsv()`, `buildExportHtml()`, `serializeBackupDocument()`, `validateBackupDocument()`, `selectAutomaticBackupsForDeletion()`, `createExportFileName()`, and `createBackupObjectPath()`.

- [ ] **Step 1: Write failing selection and normalization tests**

```ts
test('requires at least one normalized export content row', () => {
  expect(validateExportSelection({
    format: 'csv',
    startDate: '2026-07-01',
    endDate: '2026-07-31',
    contents: [],
  })).toBe('Select at least one data section.');
});

test('rejects reversed dates', () => {
  expect(validateExportSelection({
    format: 'pdf',
    startDate: '2026-07-31',
    endDate: '2026-07-01',
    contents: ['transaction'],
  })).toBe('Start date must be on or before end date.');
});
```

- [ ] **Step 2: Run RED**

Run: `npm.cmd test -- src/lib/export-backup-domain.test.ts`

Expected: FAIL because `export-backup-domain.ts` does not exist.

- [ ] **Step 3: Add exact domain types**

Add types for:

```ts
export type ExportFormat = 'csv' | 'pdf';
export type ExportContentType = 'transaction' | 'budget' | 'savings' | 'report';
export type OperationStatus = 'pending' | 'processing' | 'completed' | 'failed';
export type BackupType = 'manual' | 'automatic';

export type ExportSelection = {
  format: ExportFormat;
  startDate: string;
  endDate: string;
  contents: ExportContentType[];
};
```

Add `DataExportRecord`, `ExportContentRecord`, `BackupRecord`, `ExportSourceData`, `BackupSourceData`, `FinancialBackupDocumentV1`, and `RestoreFinancialBackupResult`. Add `auto_backup_enabled: boolean` to `Profile` and its update pick.

- [ ] **Step 4: Implement selection and Malaysia-local preset helpers**

Use local date getters and strict `YYYY-MM-DD` round-trip validation. Return exact validation messages used in Step 1.

- [ ] **Step 5: Run GREEN**

Run: `npm.cmd test -- src/lib/export-backup-domain.test.ts`

Expected: PASS selection tests.

- [ ] **Step 6: Write failing CSV and HTML tests**

Cover:

```ts
expect(escapeCsv('Cafe "A", KK')).toBe('"Cafe ""A"", KK"');
expect(csv).toContain('\uFEFFTransactions');
expect(html).toContain('FinCoach Financial Export');
expect(html).not.toContain('<script>');
expect(html).toContain('&lt;script&gt;');
```

Assert that only selected content sections appear and that transaction/report dates are inclusive.

- [ ] **Step 7: Run RED, implement minimal generators, then run GREEN**

Run before implementation and after:

`npm.cmd test -- src/lib/export-backup-domain.test.ts`

- [ ] **Step 8: Write failing deterministic backup and retention tests**

Assert:

- same logical source produces the same serialized JSON;
- `schemaVersion` is `1`;
- wrong owner, unknown schema version, missing arrays, and malformed primitives are rejected;
- latest five completed automatic backups are kept;
- manual and failed backups are never selected by automatic retention;
- object paths start with `<userId>/manual/` or `<userId>/automatic/`.

- [ ] **Step 9: Implement backup document, validation, filenames, paths, and retention**

The validator returns a typed document or throws a user-safe `Invalid backup file.` / `This backup belongs to another account.` / `This backup version is not supported.` error.

- [ ] **Step 10: Run domain tests**

Run: `npm.cmd test -- src/lib/export-backup-domain.test.ts`

Expected: PASS.

---

### Task 2: Normalized Supabase schema, Storage RLS, and restore RPC

**Files:**
- Modify: `supabase/schema.sql`
- Create: CLI-generated `supabase/migrations/*_complete_financial_data_export_backup.sql`
- Create: `scripts/verify-export-backup-schema.mjs`

**Interfaces:**
- Produces: `public.data_exports`, `public.export_contents`, `public.backups`, `profiles.auto_backup_enabled`, private `financial-backups` bucket, and `public.restore_financial_backup_v1(jsonb, uuid)`.

- [ ] **Step 1: Create the migration through the CLI**

Run:

```powershell
npx.cmd supabase migration new complete_financial_data_export_backup
```

Expected: one new timestamped SQL file.

- [ ] **Step 2: Write the failing schema verifier**

The script must require exact fragments for:

```js
const required = [
  'create table if not exists public.data_exports',
  'create table if not exists public.export_contents',
  'primary key (export_id, content_type)',
  'create table if not exists public.backups',
  'add column if not exists auto_backup_enabled',
  "values ('financial-backups', 'financial-backups', false",
  'alter table public.data_exports enable row level security',
  'alter table public.export_contents enable row level security',
  'alter table public.backups enable row level security',
  "storage.foldername(name))[1] = (select auth.uid()::text)",
  'create or replace function public.restore_financial_backup_v1',
  'security definer',
  "set search_path = ''",
  'revoke execute on function public.restore_financial_backup_v1',
];
```

Read both the new migration and `schema.sql`; fail when a fragment is absent.

- [ ] **Step 3: Run RED**

Run: `node scripts/verify-export-backup-schema.mjs`

Expected: FAIL because schema fragments do not exist.

- [ ] **Step 4: Implement tables and constraints**

Use:

```sql
create table if not exists public.data_exports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  format text not null check (format in ('csv', 'pdf')),
  status text not null check (status in ('pending', 'processing', 'completed', 'failed')),
  file_name text not null,
  file_size_bytes bigint check (file_size_bytes is null or file_size_bytes >= 0),
  date_from date not null,
  date_to date not null,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  check (date_from <= date_to)
);
```

Create `export_contents` with composite PK and cascade FK, and `backups` with manual/automatic, lifecycle, checksum, schema version, and latest restore fields. Add the documented indexes.

- [ ] **Step 5: Implement RLS, grants, and private Storage policies**

Use `TO authenticated`, owner predicates, both `USING` and `WITH CHECK` for updates, and parent ownership subqueries for `export_contents`. Configure a private JSON-only 10 MiB bucket. Add `SELECT`, `INSERT`, `UPDATE`, and `DELETE` object policies scoped to the owner folder.

- [ ] **Step 6: Implement the atomic restore RPC**

The function must:

- revoke `PUBLIC` execution before granting `authenticated`;
- require `auth.uid()` and owner-completed backup metadata;
- validate schema version and payload user;
- set latest restore status to processing;
- delete and insert owner rows in FK-safe order;
- leave auth, default categories, receipt objects, device tokens, `auto_backup_enabled`, exports, and backups unchanged;
- update restore completion fields;
- return JSON row counts;
- roll back all mutations on any exception.

- [ ] **Step 7: Mirror migration SQL into `schema.sql`**

Keep the migration and fresh-project schema semantically identical.

- [ ] **Step 8: Run schema verifier**

Run: `node scripts/verify-export-backup-schema.mjs`

Expected: `EXPORT_BACKUP_SCHEMA_VERIFIED`.

---

### Task 3: Owner-scoped Supabase and Storage client

**Files:**
- Create: `src/lib/export-backup.test.ts`
- Create: `src/lib/export-backup.ts`

**Interfaces:**
- Produces: `fetchExportSourceData()`, `createDataExport()`, `saveExportContents()`, `completeDataExport()`, `fetchBackupSourceData()`, `createBackupRecord()`, `completeBackupRecord()`, `failBackupRecord()`, `fetchBackups()`, `uploadBackupObject()`, `downloadBackupObject()`, `deleteBackup()`, `fetchAutoBackupEnabled()`, `updateAutoBackupEnabled()`, `restoreFinancialBackup()`, and `reconcileStaleRecords()`.

- [ ] **Step 1: Write failing owner-filter and normalized export tests**

Assert exact table order and that:

```ts
await createDataExport(userId, selection, client);
await saveExportContents(exportId, ['transaction', 'report'], client);
```

inserts two `export_contents` rows, not one array column. Every source query must contain an explicit owner filter.

- [ ] **Step 2: Run RED**

Run: `npm.cmd test -- src/lib/export-backup.test.ts`

Expected: FAIL because the client module does not exist.

- [ ] **Step 3: Implement export metadata and source queries**

Query transactions/categories by date, budgets by intersecting months, savings as current state, and reports by `generated_at`. Reject any partial query failure.

- [ ] **Step 4: Run focused tests GREEN**

Run: `npm.cmd test -- src/lib/export-backup.test.ts`

- [ ] **Step 5: Write failing full-backup and Storage tests**

Assert all approved source tables are queried, only user-owned custom categories are selected, object path starts with the user ID, content type is `application/json`, and upload uses `upsert: false`.

- [ ] **Step 6: Implement backup source, Storage, preference, history, and retention operations**

Use authenticated `.download()` for private objects. Delete the Storage object before deleting a completed backup row. Update `profiles.auto_backup_enabled` through an owner-filtered profile update.

- [ ] **Step 7: Write failing restore and stale-record tests**

Assert the RPC receives:

```ts
{
  payload: document,
  backup_record_id: backupId,
}
```

and stale processing rows older than 15 minutes become failed.

- [ ] **Step 8: Implement restore RPC and reconciliation wrappers**

Run: `npm.cmd test -- src/lib/export-backup.test.ts`

Expected: PASS.

---

### Task 4: Expo file, PDF, and native sharing adapter

**Files:**
- Modify: `package.json`
- Modify: `package-lock.json`
- Create: `src/lib/export-files.test.ts`
- Create: `src/lib/export-files.ts`

**Interfaces:**
- Produces: `writeCsvExport()`, `writePdfExport()`, `shareExportFile()`, and `removeCachedExport()`.

- [ ] **Step 1: Install SDK-compatible packages**

Run:

```powershell
npx.cmd expo install expo-print expo-sharing
```

Expected: compatible pinned versions in package files.

- [ ] **Step 2: Write failing injected-adapter tests**

Assert CSV writes UTF-8 content to an export cache file, PDF calls `printToFileAsync({ html })`, and share uses the correct MIME type:

```ts
text/csv
application/pdf
```

- [ ] **Step 3: Run RED**

Run: `npm.cmd test -- src/lib/export-files.test.ts`

- [ ] **Step 4: Implement minimal Expo adapter**

Use SDK 56 `File`, `Directory`, and `Paths.cache`; inject FileSystem, Print, and Sharing wrappers for tests. Throw `Sharing is not available on this device.` when unavailable.

- [ ] **Step 5: Run GREEN**

Run: `npm.cmd test -- src/lib/export-files.test.ts`

Expected: PASS.

---

### Task 5: Export & Backup screens and settings navigation

**Files:**
- Create: `src/lib/export-backup-ui.test.ts`
- Create: `src/components/export-backup/export-sheet.tsx`
- Create: `src/components/export-backup/export-backup-components.tsx`
- Create: `src/app/export-backup/index.tsx`
- Create: `src/app/export-backup/success.tsx`
- Create: `src/app/export-backup/restore.tsx`
- Modify: `src/app/profile/settings.tsx`
- Modify: `src/app/_layout.tsx`

**Interfaces:**
- Consumes: domain, Supabase client, file adapter, and existing authenticated profile/session.
- Produces: `/export-backup`, `/export-backup/success`, and `/export-backup/restore`.

- [ ] **Step 1: Write failing structural UI tests**

Require:

- settings uses `router.push('/export-backup')`;
- no `Coming soon` export message;
- root layout registers all three routes;
- main screen contains `Export as CSV`, `Export as PDF report`, `Auto-backup to cloud`, `Back up now`, and `Restore from backup`;
- restore route contains `Restoring will replace your current data`;
- no hard-coded backup dates or sizes.

- [ ] **Step 2: Run RED**

Run: `npm.cmd test -- src/lib/export-backup-ui.test.ts`

- [ ] **Step 3: Implement the approved visual structure**

Follow the existing Hanken Grotesk, `authColors`, MaterialIcons, rounded cards, page bar, and bottom sheet patterns. Use actual loading/error/empty states.

- [ ] **Step 4: Implement real export orchestration**

On generate:

1. validate;
2. create pending export and normalized content rows;
3. load source;
4. generate CSV or HTML/PDF;
5. update completion metadata;
6. navigate to success with a session-scoped generated-file descriptor;
7. share the file.

Do not put file content in route parameters. Use a module-level ephemeral export store with a tested clear operation.

- [ ] **Step 5: Implement manual backup and restore orchestration**

Backup performs exact JSON serialization, SHA-256 via `expo-crypto`, Storage upload, completion, and retention. Restore downloads authenticated bytes, verifies size/checksum/document ownership/schema, confirms destructive replacement, invokes RPC, and reloads history.

- [ ] **Step 6: Run UI tests GREEN**

Run: `npm.cmd test -- src/lib/export-backup-ui.test.ts`

Expected: PASS.

---

### Task 6: Opportunistic automatic backup

**Files:**
- Create or extend: `src/lib/export-backup.test.ts`
- Modify: `src/lib/export-backup.ts`
- Modify: `src/lib/auth-context.tsx`

**Interfaces:**
- Produces: `runEligibleAutomaticBackup(userId)` with a process-level in-flight lock.

- [ ] **Step 1: Write failing eligibility tests**

Assert no automatic backup when disabled or when a completed automatic backup exists within 24 hours. Assert one backup when eligible and concurrent calls share one in-flight promise.

- [ ] **Step 2: Run RED**

Run: `npm.cmd test -- src/lib/export-backup.test.ts`

- [ ] **Step 3: Implement eligibility and lock**

Keep orchestration outside React. Trigger it after authenticated bootstrap and on `AppState` transition to `active`. Fail silently in the auth shell but persist failed backup state; never block login or foreground rendering.

- [ ] **Step 4: Run GREEN and auth regression tests**

Run:

```powershell
npm.cmd test -- src/lib/export-backup.test.ts src/lib/auth-context.test.tsx
```

If no auth-context test file exists, run the complete test suite after the focused export/backup test.

---

### Task 7: Acceptance documentation and complete verification

**Files:**
- Modify: `docs/acceptance-tests.md`

- [ ] **Step 1: Add real-device acceptance cases**

Document:

- CSV export with commas, quotes, Unicode, and multiple selected sections;
- PDF generation and Android share/save;
- manual private backup creation;
- automatic-backup 24-hour eligibility;
- five-backup automatic retention;
- manual backup retention;
- corrupt checksum blocked before restore;
- cross-user metadata/object denial;
- successful full-data restore round trip;
- restore leaves authentication, default categories, receipt objects, device tokens, preference, and backup history unchanged.
- repeat the export, manual backup, and restore round trip on the Honor 200 physical device.

- [ ] **Step 2: Run focused tests**

```powershell
npm.cmd test -- src/lib/export-backup-domain.test.ts src/lib/export-backup.test.ts src/lib/export-files.test.ts src/lib/export-backup-ui.test.ts
```

Expected: PASS.

- [ ] **Step 3: Run the complete test suite**

Run: `npm.cmd test`

Expected: all tests pass.

- [ ] **Step 4: Run TypeScript and focused lint**

```powershell
npm.cmd run typecheck
npx.cmd eslint src/lib/export-backup-domain.ts src/lib/export-backup.ts src/lib/export-files.ts src/app/export-backup src/components/export-backup src/app/profile/settings.tsx
```

Expected: PASS with no new errors.

- [ ] **Step 5: Verify schema**

Run: `node scripts/verify-export-backup-schema.mjs`

Expected: `EXPORT_BACKUP_SCHEMA_VERIFIED`.

- [ ] **Step 6: Build the Android production bundle**

Run:

```powershell
npx.cmd expo export --platform android --output-dir C:\tmp\fincoach-export-backup-export
```

Expected: successful Android export.

- [ ] **Step 7: Review changes**

Run:

```powershell
git diff --check
git status --short
```

Confirm unrelated dirty files remain preserved and identify only this module's new changes.
