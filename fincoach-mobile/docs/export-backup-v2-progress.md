# Export and backup implementation ledger

Plan: the seven-stage plan agreed in this chat on 10 October 2026.

- Ruling: work in canonical fincoach-mobile on the existing codex branch, preserving all dirty work; a clean worktree would omit the previously implemented uncommitted features and audit harness.
- Ruling: introduce v2 immutable attachment copies in financial-backups, retain v1 read/restore with an explicit completeness warning, preserve privacy settings in both paths.
- Ruling: snapshot all financial sections in one SQL statement through an authenticated active-account RPC. Use count-checked stable pagination for exports and history.
- Baseline: 43 existing focused tests passed; live audit had 102 passing and 12 failing checks; failure injection reproduced retention status corruption. Original evidence retained in output/export-backup-deep-audit-20261010.
- Scope: implement all agreed stages, apply tested additive Supabase migration, run isolated live acceptance. Native Android checks require a connected device and APK distribution is not implied by code implementation.
- Tasks 1-7: complete - v2 contract, consistent server snapshots, verified independent attachments, atomic privacy-preserving restore/preview, lifecycle/retention, complete CSV/PDF export and isolated acceptance evidence.
- Hosted migrations applied: 20261010151101_complete_financial_backup_v2; 20261010152639_harden_financial_backup_v2_lifecycle; 20261010160000_backup_deletion_tombstone.
- Live acceptance: 134 checks passed; 1111 transactions and 1006 contributions preserved; RM1130.50 balance preserved; fixture cleanup verified.
- Desktop CSV/PDF inspection: 80 checks passed; all seven selections and 38-page large PDF; visual pages inspected.
- Final reviewer findings resolved: one-to-one attachment paths, uncertain restore replies/post-commit refresh failures, and durable deletion tombstones with retry.
- Validation: full unit suite, TypeScript, focused ESLint and Android Hermes export pass.
- Outstanding environment acceptance: no connected Android device; native print/share/save and on-phone restore require device testing. No APK distributed.
