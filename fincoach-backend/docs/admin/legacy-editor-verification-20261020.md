# Existing knowledge-document editor repair

Verified on 20 October 2026 against the local repository and the public FinCoach
Administration website at `https://api.chisquaredv10.dpdns.org/admin`.

## Cause and behavior

The editor applied the new-import provenance requirement to older saved documents.
Their text existed, but the structured `source_urls` array was empty and `file_path`
was null. The Review → Publish control and chunk preview therefore rejected valid
existing content. The shared global error handler scrolled upward, making a chunk
preview failure appear to return to Content preview.

- The editor now checks previewable content separately from save provenance.
- Existing current revisions without provenance may be edited; Supabase verifies
  that exception under the existing source row lock. New imports remain strict.
- Recorded original files and concurrency checks remain enforced.
- Preview errors appear inside Advanced details. Missing provenance is labelled
  honestly. An unchanged published revision stays published and creates no draft.

## Changes and deployment

- `fincoach-admin/src/knowledge-editor.ts`: shared content/save validation,
  provenance label and saved-state message.
- `fincoach-admin/src/App.tsx`: use the shared rules and keep preview failures local.
- `fincoach-mobile/supabase/migrations/20261020081645_fix_existing_knowledge_editor_validation.sql`:
  applied to project `yqsyrzdpvtasldkthhfg`; replaces only
  `public.admin_save_knowledge_revision(uuid,uuid,text,text,jsonb,date,text,uuid)`.
- The production frontend build synced to the running backend's read-only static
  mount. Chrome loaded `index-DMzqN9-B.js` from the public website. No backend
  restart or tunnel change was needed.

Supabase **was changed**: the stored save-function implementation and migration
history were updated. Physical table definitions and the existing knowledge records
were unchanged. This distinction matters for the ERD and table-structure PNGs.
PostgreSQL functions are database-resident routines; see the
[official Supabase function documentation](https://supabase.com/docs/guides/database/functions).

## Verification

| Check | Result |
|---|---|
| Old editor validator against legacy-save and preview cases | Both failed with `Import a file or webpage first.` before the fix |
| Frontend validation and request-gate tests | 17 passed |
| Production TypeScript/Vite build | Passed |
| Existing backend admin-route tests in running container | 10 passed |
| Regression against the original hosted SQL save function | Failed with `ADMIN_INVALID` for an existing legacy revision |
| Same assertions after the function migration, hosted Supabase | Passed; all fixture and audit writes rolled back |
| Fresh isolated local PostgreSQL database | Passed; temporary database dropped |
| Existing Compound interest document, public Chrome | Review → Publish succeeded; already-published message; one retrieval chunk displayed |
| Existing PIDM document, public Chrome | Review → Publish succeeded; already-published message; one retrieval chunk displayed |
| Invalid source-link preview, public Chrome | Error remained inside expanded Advanced details; temporary input discarded |

The SQL assertions cover legacy edits and subsequent drafts, preservation of the
published pointer, stale-revision rejection, rejection of new documents without
an import, URL provenance retention, inherited original-file references, file
ownership, future accuracy dates, and administrator authorization. They execute
inside a rollback subtransaction; no fixture or audit row remains. Sequence values
can advance during rolled-back tests.

The local test container was returned to its original stopped state. The running
FinCoach backend was kept running. A host Python test attempt stalled; the same
current admin-route test file was run successfully inside the backend container.

## Database and diagram integrity

| Compared item | Before | After |
|---|---|---|
| Public physical tables | 10 | 10 |
| Physical columns | 296 | 296 |
| Public constraints | 209 | 209 |
| Column-definition signature | `6f90bc7d4bd10e0514b81a54bae99209` | Same |
| Constraint-definition signature | `b233a00c4f8af8988134d7f5f2eebd5d` | Same |
| All `knowledge_records` row-data signature | `a38d6e0b8a461213645d86ed19012d2a` | Same |
| Save-function privileges | `postgres` and `service_role` execute | Same |

The final record signature was rechecked after the public-browser tests. The table
PNG reference folder was inspected and left untouched:
`G:\My Drive\FYP 1 & 2\diagram (current)\database structure\latest database png`.
Those screenshots and the ERD do not need updating for this function-only repair.

## Evidence and scope

Evidence folder: `output/playwright/admin-editor-fix-20261020/` at workspace root.

- `baseline.json` and `verification.json`: before/after structural and data signatures.
- `01_compound_publish_fixed.jpg`: the real unchanged published document reached Publish.
- `02_compound_chunks_fixed.jpg`: real chunk-preview result.
- `03_preview_error_inline.jpg`: real inline validation error.
- `04_pidm_publish_and_chunks_fixed.jpg`: real PIDM Publish step and retrieval chunk.

Browser checks intentionally did not save edits or publish a new real document.
Save behavior was exercised through the local and hosted transactional SQL checks.
This repair does not constitute a new end-to-end audit of all admin features or
mobile functionality. The earlier thesis screenshot library was not replaced.

## Repeat the focused checks

From `fincoach-admin`:

```powershell
node --experimental-strip-types --test tests/knowledge-editor.test.ts tests/request-gate.test.ts
npm run build
```

From `fincoach-backend`, with the existing dedicated test container running:

```powershell
python docs/admin/test_legacy_editor.py
```

The SQL regression is `docs/admin/legacy-editor-regression.sql`. Hosted execution
is a separate check; the local helper never connects to hosted Supabase.
