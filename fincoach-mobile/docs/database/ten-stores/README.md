# FinCoach: ten physical application stores

Status: applied to hosted Supabase project `yqsyrzdpvtasldkthhfg` on **19 October 2026 at 16:39 MYT** (08:39 UTC).

Migration: `supabase/migrations/20261019082834_consolidate_dfd_application_stores.sql`.

The database has **10 physical application tables** in `public`, all with Row Level Security enabled, and **zero physical tables in `private`**. Previously it had 25 public and two private application tables. Supabase-managed Auth and Storage tables are additional platform tables and were retained.

## Readable physical column names (19 October 2026)

Applied migration `20261019121005_readable_physical_column_names.sql` at **2026-10-19T12:12:16.766074+00:00**.
The 277 columns in the nine consolidated tables now use readable names. The 19 `profiles` columns were already readable and were retained. There are still 10 physical application tables and 296 columns.

| Former physical name | Current physical name |
| --- | --- |
| `_row_id` | `record_id` |
| `_record_kind` | `record_type` |
| `r03_user_id` | `account_user_id` |
| `r03_role` | `account_role` |
| `r04_actor_id` | `audit_actor_id` |
| `r11_title` | `session_title` |
| `r09_content` | `message_content` |

All 13 affected trigger functions were updated in the same transaction. Existing views retain their original names and columns, so application requests still use `account_access.user_id`, `coaching_sessions.title`, and `coaching_messages.content`.

`column-renames.csv` and `column-renames.json` contain the complete old-to-new mapping. `store-mapping.json` includes exact physical column mappings; do not assume every name is obtained by simply adding a prefix. Internal constraint, policy and trigger-function names may still contain historical codes; their definitions reference the current physical columns.

The migration checked every one of the 27 logical datasets for exact row-count/hash equality inside the transaction and verified unchanged table/column grants and RLS flags. Local financial/report and backup/admin assertions passed, as did 59 local REST checks. `readable-columns-verification.json` contains the additional hosted checks when complete.

The rename-only inverse, `rollback-readable-column-names.sql`, was successfully tested on the isolated copy. It retains the ten-table structure and restores the former column names. A full return to the earlier 27-table structure remains a separate recovery operation; reconcile both migration-history entries if that is chosen. Keep the applied historical migration files unchanged.

The pre-change logical backup and immediate pre-rename backup are in the ignored workspace directory `output/readable-columns-2026-10-19/`. No mobile/backend deployment or restart was needed for the rename. Phone interaction and actual push delivery were not tested by these database checks.

## Mapping to DFD Level 0

The D1â€“D10 names below were read from the supplied `dfd-level-0-v11-admin-closer.drawio`. Data stores are logical groupings; one physical table per store is this project's requested implementation choice, not a general DFD requirement.

| DFD store | Physical table | Preserved datasets |
| --- | --- | --- |
| D1 Financial Profiles | `profiles` | Financial profiles |
| D2 Transactions & Receipts | `transaction_records` | Transactions and receipt fields, categories, tracked user categories |
| D3 Budgets & Category Limits | `budget_records` | Monthly budgets, category limits |
| D4 Savings Goals | `savings_records` | Savings goals, contributions |
| D5 Export & Backup Records | `export_backup_records` | Exports, export contents, backups, private backup snapshots |
| D6 AI Coaching Sessions | `coaching_records` | Sessions, messages, retrievals, private processing leases |
| D7 Financial Reports | `report_records` | Reports, report attempts |
| D8 Alerts & Reminders | `alert_records` | Alerts, reminders, notification preferences, devices |
| D9 Malaysian Financial Knowledge Base | `knowledge_records` | Knowledge sources, revisions, vector chunks |
| D10 User Accounts | `account_records` | Account roles/status, administrator audit logs |

`auth.users` remains the Supabase-managed identity table. D10 records refer to its identity key. Files remain in Supabase Storage; the application stores their paths and metadata.

## How existing application operations are preserved

The 26 converted table names remain as **security-invoker compatibility views**. `profiles` remains a physical table. The existing `published_knowledge_documents` view also remains, giving 27 views in total. Views are virtual queries over the ten physical tables; they do not hold duplicate copies of the data.

Existing API calls such as `transactions`, `savings_goals`, `coaching_messages`, and `account_access` still use their original names and columns. This avoided a coordinated replacement of the installed Android app, backend, and Edge Functions. No application source deployment or backend restart was performed for this migration.

Each consolidated table has a physical UUID `record_id` primary key and a generated `record_type`. Original attributes retain their PostgreSQL types in descriptively prefixed columns, including `vector(1024)`. Per-kind constraints require the appropriate attributes and prevent unrelated attributes from being populated. Original identifiers remain unique and relationships are enforced by mapped foreign keys. See `store-mapping.json` for exact prefixes and dataset destinations.

Existing functions, triggers, indexes, grants, Storage report-upload policy, and ownership rules were restored or adapted. Child records with ownership derived from a parent use a constrained internal owner column to avoid recursive RLS checks. The original API relationship names were retained and exercised through PostgREST.

**Tradeoff:** this lowers the physical table count, while retaining the original logical datasets and introducing wider, sparse physical tables. It does not eliminate the underlying entities or reduce maintenance complexity. Routine application CRUD should continue through the documented views/RPCs; future schema migrations must update both the physical representation and its compatibility interface.

## Verification evidence

Detailed, non-sensitive results are in `validation-summary.json`. Private backup files and raw test evidence are retained under the workspace's ignored `output` directory.

| Check | Result |
| --- | --- |
| Migration transaction data preservation | All 27 source datasets matched their original row counts and row-JSON hashes before commit |
| Restored baseline versus consolidated candidate | All 27 datasets matched |
| Local SQL integration | Auth/profile triggers, budgets, ownership, coaching leases, report attempts, rollback behavior passed on both schemas |
| Local backup/admin integration | Backup v1/v2 restoration and tamper rejection, admin account/audit operations, knowledge revision publication, device reassignment passed on both schemas |
| Existing REST contracts on PostgREST 14.5 | 59/59 baseline; 59/59 candidate |
| Legacy column/routine privileges | 2,622 comparisons matched; live preflight also matched the tested baseline |
| User read isolation | 135 comparisons matched across the five backed-up users and 27 datasets |
| Hosted read checks | 31/31 passed, including embedded relationships and vector/hybrid search |
| Hosted authenticated operations | 47/47 passed, using two disposable accounts, including sign-in, CRUD, upserts, savings rollups, relationship queries, and prohibited operations |
| Hosted cleanup | No disposable accounts or their tested records remained; five original Auth users and 41 Storage objects remained |
| Backend after commit | `/health` and `/ready` passed; OCR and embeddings reported ready |
| Knowledge worker | Claim RPC completed in a rolled-back probe; zero backend errors between commit and the final 08:49 UTC check |
| Current-data recovery script | Recreated 27 tables locally; all 27 datasets matched, including records added after consolidation |

The first hosted write-test run stopped because the test script concatenated an integer contribution ID into a URL. Its accounts were cleaned up. After correcting the test script, the complete run passed. Limited read requests returning HTTP 206 are successful partial-content responses and are counted accordingly.

The knowledge worker encountered statement timeouts while the migration held table locks. The final timeout occurred before commit; post-commit checks succeeded. The migration therefore involved a brief write/worker interruption, not a zero-downtime cutover.

### Remaining verification limits

- No physical-phone end-to-end run was performed after the migration. Native file sharing, phone restore interactions, camera/OCR interactions, and actual push delivery remain device checks.
- Backup/admin integration exercised database data and metadata. It did not re-upload every Storage binary or send push notifications. Existing binaries were retained and had been included in the earlier full backup.
- The backend health checks and vector RPC checks do not constitute a new full LLM conversation-quality evaluation or public-tunnel reachability test.
- The live baseline had no published application tables in PostgreSQL publications. The existing client subscription to `public.alerts` was therefore not a demonstrated working realtime path before this migration. Compatibility views cannot themselves be published for table-change events. Enabling that path later requires an explicit subscription/publication or broadcast design for `alert_records`.
- Compatibility-view metadata differs from physical-table metadata. Original numeric identifiers retain sequence defaults; clients inspecting identity/primary-key catalog metadata should use the mapping rather than assume views expose physical constraints identically.

## Backups and recovery

Immediately before cutover, a full logical archive was created and its archive contents validated:

- Workspace-relative path: `output/ten-table-cutover-20261019T083535Z/pre-migration.dump`
- Size: **4,171,142 bytes**
- SHA-256: `d1308f20772c29d1192f36693918d345ef492f20e3104c5ad596ce4714338528`

The earlier `output/database-backup-2026-10-19/FinCoach_database_backup_2026-10-19.zip` additionally contains the separately downloaded Storage files and restore-verification evidence. These contain private application data and are intentionally not committed to source control.

`rollback-current-data.sql` is an inverse migration, tested only against a disposable local database. It copies **current** compatibility-view rows to transaction-local temporary tables, recreates the original schema, restores those rows and sequence positions, and aborts on any row mismatch or incorrect table count. It preserves writes made after consolidation; blindly restoring the older dump would not.

If rollback becomes necessary: first take a new backup, quiesce application writes/workers, test the inverse against that backup, execute the reviewed inverse, and reconcile Supabase migration history for version `20261019082834`. Do not run the applied consolidation migration twice. The inverse intentionally does not silently alter migration-history records.

## Thesis and diagram implications

The existing ERD and database-structure PNGs show the previous physical schema and must be regenerated before presenting them as current. A new physical ERD must show these ten physical stores, their actual keys and relationships, and distinguish Supabase-managed Auth/Storage. A logical or compatibility-view ERD may still show the original logical entities if clearly labelled. Do not describe the retained view names as extra physical tables or claim the original entity relationships disappeared.

The DFD can retain the ten store groupings in the mapping above. The physical consolidation alone does not introduce a new external flow or application process.
