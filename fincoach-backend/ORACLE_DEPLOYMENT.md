# FinCoach Backend on Oracle Ampere

> **Superseded.** The Oracle tenancy is no longer usable. Use `DEPLOYMENT.md`
> for current x86_64 hosts. This file is retained only as a record of the ARM64
> setup, and its `PADDLE_OCR_ENGINE=paddle_dynamic` workaround is specific to the
> prebuilt ARM64 Paddle wheel.

This deployment runs the FastAPI backend in one ARM64 Docker container and
keeps the existing host Nginx installation as the public HTTPS reverse proxy.

## 1. Server directory

Copy this backend directory to:

```text
/opt/fincoach-backend
```

Do not upload the local `.venv` or `.env`.

## 2. Production environment

Create `/opt/fincoach-backend/.env` from `.env.example`, add the real
server-side secrets, and protect it:

```bash
sudo chmod 600 /opt/fincoach-backend/.env
```

Never place `SUPABASE_SERVICE_ROLE_KEY`, `LLM_API_KEY`, or `GEMINI_API_KEY`
inside the Expo mobile application.

The Oracle Compose profile defaults `PADDLE_OCR_ENGINE` to
`paddle_dynamic`. This preserves real PP-OCRv5 inference while avoiding the
static Paddle `AnalysisPredictor` crash in the prebuilt ARM64 wheel.

Receipt OCR also defaults to a 1600-pixel maximum image side and four CPU
threads. A typical 3024x4032 phone photo is reduced from 12.2 MP to 1.9 MP
before inference while preserving its aspect ratio. Override
`PADDLE_OCR_MAX_SIDE` only after comparing both latency and extraction quality.

## 3. Build and start

```bash
cd /opt/fincoach-backend
sudo docker compose -f compose.oracle.yml build
sudo docker compose -f compose.oracle.yml up -d
sudo docker compose -f compose.oracle.yml logs -f backend
```

Successful scans emit privacy-safe `receipt_ocr` and `receipt_cleanup` timing
events. They contain dimensions, durations, and line counts, but never receipt
text or image content.

The first startup can take several minutes while BGE-M3 and PaddleOCR models
download into persistent Docker volumes.

Verify the private origin before configuring Nginx:

```bash
curl --fail http://127.0.0.1:8000/health
```

The expected response is `{"status":"ok"}`.

## 4. Nginx

Inspect the current configuration before installing the supplied server block.
Do not overwrite an existing site with the same hostname.

```bash
sudo nginx -T 2>/dev/null | grep -nE "server_name|proxy_pass"
```

If the hostname is unused:

```bash
sudo cp deploy/nginx/fincoach-api.conf \
  /etc/nginx/sites-available/fincoach-api
sudo ln -s /etc/nginx/sites-available/fincoach-api \
  /etc/nginx/sites-enabled/fincoach-api
sudo nginx -t
sudo systemctl reload nginx
```

Issue or attach the origin certificate:

```bash
sudo certbot --nginx -d api.chisquaredv10.dpdns.org
```

After HTTPS succeeds, use Cloudflare Full (strict) for this hostname.

## 5. External verification

```bash
curl --fail https://api.chisquaredv10.dpdns.org/health
```

Only after this succeeds should the Expo build use:

```text
EXPO_PUBLIC_FINCOACH_API_URL=https://api.chisquaredv10.dpdns.org
```

## Updates

Copy the new source into the same directory, then rebuild only the application:

```bash
cd /opt/fincoach-backend
sudo docker compose -f compose.oracle.yml up -d --build
```

The two named model volumes survive application rebuilds.
