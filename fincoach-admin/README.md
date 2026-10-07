# FinCoach administrator website

Browser application served by the existing FastAPI server at `/admin`. Student
accounts remain in the Android app. This website manages account metadata and
the shared knowledge base; it does not expose individual financial records.

## Local preview

From `fincoach-admin`, run `npm ci` and `npm run build`. The build also copies
assets into `fincoach-backend/admin-static` for the existing Docker images.
From `fincoach-backend`, run `python -m uvicorn app.main:app --port 8123`.
Open `http://127.0.0.1:8123/admin`. Until database setup is complete, the login
screen reports that administration is disabled. It does not simulate live data.

## Docker Desktop

Build the frontend from `fincoach-admin` with `npm run build`. Then, from
`fincoach-backend`, run:

```powershell
docker compose up -d --build backend
docker compose ps
docker compose logs --tail 30 backend
```

Open `http://localhost:8000/admin`. Docker Desktop shows the existing
`fincoach-backend` Compose project and backend container. Embedding and OCR caches
are retained in named volumes, and the compiled website is mounted read-only. The container health
check uses `/ready`; wait for model warm-up before checking coaching or OCR.

Starting Docker does not apply database migrations or create an administrator.
Login remains disabled until the setup/rollout steps below are completed.

## Database setup and rollout order

1. Review and back up the target database. Check its current schema against the
   repository, especially existing restore and retrieval functions. Live rollout
   requires separate approval; local test success is not hosted deployment proof.
2. Apply `fincoach-mobile/supabase/migrations/20261001100105_admin_panel.sql`
   after the existing module migrations. Ensure the existing dense and hybrid
   retrieval RPCs are present. Do not rerun the old knowledge bootstrap SQL after
   this migration: its schema guard now rejects versioned databases atomically.
3. Provision one administrator through the trusted server command below.
4. Set server `ADMIN_PANEL_ENABLED=true`, `ACCOUNT_ACCESS_ENFORCED=true`, and
   `ADMIN_LOGIN_EMAIL` to that administrator's email. Both feature flags default
   to false. Set Edge Function secret `ACCOUNT_ACCESS_ENFORCED=true` and deploy
   `register-device`, `process-alerts`, and `send-alert` together with their
   shared modules **after** the database migration. Keep the cron/webhook secrets.
5. Build the website before building either backend Dockerfile. Both images
   serve assets from `ADMIN_STATIC_DIR=/app/admin-static`. The existing single
   Python worker runs the durable knowledge queue; no Node server is needed.
6. Deploy/rebuild Android with the account access gate. Verify a student account,
   suspend it, verify denied API/table/Storage/restore access, then restore it.
   Verify a draft is absent from retrieval, publish it, archive it, and restore
   a prepared historical version. Confirm audit events and model readiness.

## Initial administrator

Supabase Auth requires an email identity even when the website displays the
username `admin`. On the trusted backend, run:

```powershell
python admin_setup.py --email YOUR_ADMIN_EMAIL --create
python admin_setup.py --email YOUR_ADMIN_EMAIL --create --apply
```

The first command is a dry run. The second creates the account if necessary,
privately prompts for a matching password of at least 12 characters **only when
creating a new account**, then grants the protected administrator role. If that
email already exists, its password is kept and there is no password prompt.
For an existing account, omit `--create`.
Set `ADMIN_LOGIN_EMAIL=YOUR_ADMIN_EMAIL` to sign in with username `admin`.
Passwords and service-role keys are never placed in the frontend bundle.
`123456` is rejected by default. An explicit `--allow-short-password` option
allows 6+ characters for a local demo; Supabase's configured requirements still
apply. Use a stronger password before exposing the website publicly.
No account is automatically
created by building or starting the website.

To set a password for an existing active administrator, including one that
previously used only Google sign-in, run from `fincoach-backend`:

```powershell
docker compose exec backend python admin_setup.py --email YOUR_ADMIN_EMAIL --set-password --apply
```

This prompts privately twice, requires at least 12 characters by default, and updates the
Supabase Auth password for that account. It does not change the account's role.
The same account uses this password in both the admin website and the mobile app.
Omit `--apply` to check the selected account without changing its password.
After changing this script locally, rebuild the backend image before running it
in Docker: `docker compose up -d --build backend`.

Google sign-in uses the existing Supabase provider. Add the deployed
`https://YOUR_HOST/admin/` to the Supabase redirect allowlist before testing it.

## Knowledge workflow

`New document` opens a dedicated editor immediately. `Open` loads the selected
document from Supabase into that same editor. `Back to documents` returns to the
list and asks before discarding unsaved changes.

Upload UTF-8 Markdown/text or an unencrypted text PDF (10 MiB, 100 pages max),
or write text in the editor. Supply HTTP(S) source URLs and the date you checked
them. Save draft → preview → prepare embeddings → publish after review.
Preview shows the first five chunks and warns when verification exceeds 90 days.
Edits preserve the original private upload; PDF editing uses extracted text and
does not invent page citations. Original downloads use 60-second signed URLs.

Older revision history can be loaded in pages rather than being limited to the
first 50 versions.
Each save creates a revision. Preparation leases jobs and validates 1024-dimensional
embeddings. Finish writes a whole revision in one transaction; publish changes
the source's visible revision atomically. Archive excludes it from new dense and
hybrid searches. Older chunks remain for saved coaching citations. Existing
corpus filenames and chunk IDs are preserved during backfill. Imported source
dates stay unknown until reviewed. Tavily remains live web retrieval; its results
are not automatically added to this curated corpus.

## Validation evidence and limits

- Backend: 519 tests passed, including legacy-schema ingestion and admin/auth/upload checks.
- Mobile/notification: 311 tests passed; TypeScript check passed.
- Admin: production TypeScript/Vite build passed. Browser fixture checks passed
  login, accounts, editor, publishing, search, audit and 390px layout.
- Real PostgreSQL/pgvector: isolated tests validate owner RLS, suspension,
  Storage policies, guarded restore, role protection, draft isolation,
  transactional ingestion, publishing/archive/restore, citation preservation,
  optimistic conflicts and lease recovery. A second run loads the full FinCoach
  schema, substituting hosted cron/network/vault extension infrastructure only.

Browser fixture screenshots are interface evidence, not real account/login or
live data evidence. Hosted Auth, Google OAuth, actual Storage downloads, push
delivery, device behavior and deployment have not yet been verified.
Signed download links issued before suspension can remain valid until expiry;
the account checks prevent new authenticated requests rather than revoking
previously issued bearer download links. Locally cached files also remain local.

Run the SQL checks against the dedicated disposable container:

```powershell
docker run --name fincoach-admin-test --detach -e POSTGRES_PASSWORD=local-admin-test-only -p 127.0.0.1:55439:5432 pgvector/pgvector:pg17
python docs/admin/test_local_database.py
python docs/admin/test_local_database.py --retrieval-plan
python docs/admin/test_local_database.py --full-schema
```

These commands use a fixed local container name and never connect to the hosted
Supabase project. Keep uploaded originals/revisions; automated orphan-upload
cleanup and isolated PDF parser execution are not part of this first release.

The legacy `ingest.py` writer is available only before the admin migration.
After migration, database schema detection blocks it even if the server admin
flag is false. `python ingest.py --validate` remains a local read-only check.
Published visibility is updated atomically from source publication/archive
changes; partial HNSW and full-text indexes include published chunks only.
Hidden historical revisions cannot consume ANN candidates for new searches.
See `fincoach-backend/docs/admin/review-corrections.md` for reproduction evidence.
