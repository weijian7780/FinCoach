# Financial export, backup and restore verification

Implemented in canonical fincoach-mobile on 10 October 2026. Three additive migrations were applied to hosted Supabase project yqsyrzdpvtasldkthhfg; no FastAPI deployment or APK distribution was performed.

## Backup and restore contract

| Data | Saved in v2 | Restore behavior |
|---|---|---|
| Financial profile | Profile snapshot | Restores name, avatar URL reference, allowance, university, year, income source, financial status, coaching style and onboarding state |
| Custom categories and tracked categories | All owned rows and selections | Replaces owned categories and selections; shared system categories remain shared |
| Transactions | All owned rows, no date filter or 1,000-row limit | Replaces current transactions |
| Budgets and category limits | All months | Replaces current budgets and limits |
| Savings goals and contributions | All rows with validated balances and links | Replaces goals and contributions |
| Reports | All owned metadata | Replaces metadata and remaps saved PDF paths |
| Notification preferences, reminders and alerts | All owned rows | Replaces these settings and records |
| Receipt images, generated report PDFs and custom category images | Independent verified copies and SHA-256 manifest | Recovers bytes into new owned paths; deleting one distinct restored file does not break another |
| Consent and authentication email | Profile snapshot may contain existing values | Current consent and authentication identity are preserved |
| Avatar image bytes, AI conversations, passwords/sessions, device tokens, admin/knowledge data, export/backup history | Excluded from financial restoration | Not restored |

Restore is a **whole financial replacement**, restricted to the same active account. Records created after the snapshot are removed. Preview shows section counts, timestamp and attachment count before confirmation. Missing/corrupt required assets prevent replacement. V2 financial content must match the server's immutable snapshot. V1 remains supported with an explicit completeness/attachment warning; inconsistent legacy savings data is blocked.

Automatic backup is checked on sign-in/app foreground at most once daily. This is not an operating-system background schedule. Server serialization rejects duplicate automatic completion within 24 hours. Retention failure does not invalidate the new completed backup. Deletion is durably marked unavailable before files are removed; interrupted deletion is retried on the restore screen.

A lost restore response is reconciled against changed server restore history. If the server cannot confirm the outcome, the app reports an unconfirmed status and preserves potentially committed attachments. A refresh failure following confirmed restore does not overwrite successful server metadata.

## Export contract

CSV and PDF support all seven nonempty combinations of Transactions, Budgets and Savings Goals. Only selected sections appear. Transactions use selected dates; budgets include months overlapping the range; savings show current goals/balances with an explicit notice that dates do not filter them. Report timestamp boundaries use Malaysia time. Table fetching uses stable, count-checked pagination and refuses a detectable incomplete/changing result. CSV escapes formulas, Unicode, commas, quotes and embedded newlines. PDF includes transaction source and human-readable category limits, wrapping and repeating table headers.

## Acceptance evidence

- Hosted isolated run: **134 checks passed, zero failed**. Temporary accounts, financial rows and Storage fixtures were cleaned up.
- Export: **1,109/1,109** selected transactions fetched.
- Backup and restore: **1,111/1,111** transactions; **1,006/1,006** contributions; savings balance **RM1,130.50** before and after.
- Deleted receipt images, report PDFs and custom category images recovered and checked; edited v2 content, invalid links, corrupt checksums, foreign owners and transactional failure paths rejected; denied consent preserved.
- Desktop file inspection: **80 checks passed, zero failed**, covering every selection and a **38-page** large PDF. First/middle/last pages visually inspected; all rows survived rendering and extracted words remained within page bounds.
- 385 unit tests (384 in the full run plus one added deletion regression), TypeScript and focused ESLint pass. Android Hermes bundle compiled successfully.
- Reviewer findings about identical attachment paths, unknown restore outcomes and interrupted deletion were addressed with regression coverage.

Raw evidence: `export-backup-v2-live-verification.json`; files and volume evidence: `../../output/export-backup-v2-20261010/`. Original failing audit remains separate.

## Practical limits and pending verification

Native Android expo-print, save/share/download, FileReader handling, and on-phone preview/restore have **not** been verified on a connected device. The local bundle is not an installed APK. Older v1 backups cannot gain missing records or attachment bytes retroactively. Storage currently limits each uploaded object to 10 MB; large payloads/files must fail rather than be represented as complete. Scale beyond the tested fixtures and interruption outcomes where the server remains unreachable are not proven by this run.
