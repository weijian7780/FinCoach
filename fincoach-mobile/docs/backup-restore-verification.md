# Backup and restore verification — 8 October 2026

## Result

The live Supabase test passed all 39 checks at 07:54 MYT. It ran the mobile
backup/restore modules in Node against real Auth, PostgreSQL, and private
Storage. Only Expo bindings were substituted for Node execution. Two disposable
accounts were used; existing users' financial rows were not modified.

Evidence: `backup-restore-live-verification.json`.
Runner: `../scripts/verify-backup-restore.live.test.ts`.

## Repairs

1. `20261007234949_fix_backup_restore_consent_type.sql`: derives the restored
   consent value's type from `public.profiles` instead of assuming the live
   column is an enum. The hosted column is text. Applied on Supabase.
2. `20261007235407_preserve_backup_restore_reports_categories.sql`: restores all
   report PDF metadata and tracked-category selections. Applied on Supabase.
3. New app backups include optional `userCategories` in the v1 document. Old v1
   files remain supported: because they did not capture selections, restore
   preserves current selections for categories available after restoration.
4. The earlier app fix reads native downloaded Blobs through FileReader when
   `Blob.text()` is absent. Verified by the native-Blob regression tests.

Migration filenames match the versions recorded in the hosted migration history.
`backup-restore-pre-fix-functions.sql` preserves the original hosted function
definitions for review; it is not an instruction to restore the broken version.

## Live checks

- Manual backup upload/download, SHA-256 verification, and source-data equality.
- Actual record changes before restore, including a changed amount, an added
  transaction, a changed budget/profile, and deleted tracked-category selections.
- Restored profile, categories, tracked selections, transactions, budgets, limits,
  savings goals/contributions, report metadata, preferences, reminders, and alerts
  match the backup. Trigger-generated `updated_at` values are excluded.
- Restored report path downloads the original synthetic PDF fixture bytes.
  PDF rendering itself is not part of this test.
- A negative transaction amount is rejected by the database and all changes from
  that failed restore roll back.
- Another account cannot read/download/restore the first account's backup.
- Incorrect checksums are rejected before restoration.
- An older v1 backup without tracked selections restores successfully.
- Disabled automatic backup is skipped; enabled automatic backup succeeds;
  a recent successful automatic backup prevents another; the automatic backup
  restores all fixture data, including an explicitly empty category selection.
- All four test Storage objects and both test accounts were removed. An
  independent database query confirmed zero remaining disposable test accounts.

Before-fix evidence is retained in `backup-restore-before-consent-fix.json` and
`backup-restore-before-fidelity-fix.json`.

## Local checks and limits

- 43 focused export/backup tests passed; TypeScript and the schema verifier passed.
- Changed-file ESLint has no errors. Two existing array-style warnings remain in
  unrelated portions of `src/lib/types.ts` (lines 136 and 144).
- The public restore wrapper still checks active-account status and denies anon
  execution. The private implementation cannot be executed by anon/authenticated
  roles directly. Supabase's advisory for an authenticated SECURITY DEFINER RPC
  remains expected for this owner-checking restore operation:
  https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable
- No Android device was connected. No new APK was built or installed. The app
  needs a Metro reload or an updated APK for the Blob fix and new selection
  capture; the database repairs are already live.
- This verifies the representative fixture round trip. It does not certify
  large-account pagination, simultaneous writes during backup, automatic retention,
  or recovery of receipt/report files that have already been deleted from Storage.

## Repeat

From `fincoach-mobile`, in PowerShell:

```powershell
$env:FINCOACH_LIVE_BACKUP_TEST = '1'
.\node_modules\.bin\vitest.cmd run scripts/verify-backup-restore.live.test.ts
Remove-Item Env:FINCOACH_LIVE_BACKUP_TEST
```

The runner reads existing frontend/backend environment files without printing
credentials. It creates its own accounts and cleans up only its own fixtures.
Without the explicit environment flag, the live test is skipped.
