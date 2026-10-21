# Docker Desktop deployment — 1 October 2026

The existing local Compose service was rebuilt and recreated with the admin
website. This is a Docker Desktop deployment, not a hosted database migration.

| Check | Observed result |
|---|---|
| Compose project / container | `fincoach-backend` / `fincoach-backend` |
| Runtime image | `fincoach-backend:dev` |
| Container health | Healthy |
| `/ready` | HTTP 200; OCR ready, embeddings ready |
| `/admin` | HTTP 200 |
| Compiled JavaScript and CSS | Both HTTP 200 |
| Admin login configuration | Disabled, pending database/account setup |
| Unconfigured `/api/admin/me` | HTTP 503, as expected |

Open **http://localhost:8000/admin** on this PC. Docker Desktop and its backend
container must remain running. The backend also retains its existing port 8000
binding, API settings, `.env` secrets and corpus/application source mounts.

The website bundle is served from `/app/admin-static` through a read-only mount.
Embedding downloads remain in `fincoach-backend_fincoach-model-cache`. Existing
PaddleOCR files were copied from the old container into the new named volume
`fincoach-backend_fincoach-ocr-cache`; startup confirmed both OCR models loaded
from that cache. The copy helper and temporary host files were removed.

Commands from `fincoach-backend`:

```powershell
docker compose ps
docker compose logs --tail 30 backend
docker compose stop backend
docker compose up -d backend
```

For a website update, run `npm run build` from `fincoach-admin`, then run
`docker compose up -d --build backend` from `fincoach-backend`.

The previous image is retained as `fincoach-backend:pre-admin-desktop`.
Application source is bind-mounted, so reverting only the image tag does not
revert source files. No student records, Supabase migrations, administrator
accounts, notification functions or Android builds were changed by this deployment.
