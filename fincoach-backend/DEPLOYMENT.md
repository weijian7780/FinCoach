# FinCoach Backend Deployment (host-agnostic, x86_64)

The original Oracle Ampere instance was terminated, but the tenancy itself is
still usable — authentication works and the A1 service limit is intact, so a
re-host is blocked only by A1 host capacity ("Out of host capacity" on every
launch). This guide covers any x86_64 Linux host as the option that does not
depend on that capacity appearing; `ORACLE_DEPLOYMENT.md` remains the live
ARM64 guide for when a free A1 slot does open.

## The one rule that saves you an app rebuild

`EXPO_PUBLIC_*` values are inlined into the APK at build time. All three
profiles in `fincoach-mobile/eas.json` hard-code:

```text
EXPO_PUBLIC_FINCOACH_API_URL=https://api.chisquaredv10.dpdns.org
```

Every APK already installed on a phone will only ever call that hostname. The
domain is on Cloudflare nameservers, so **keep the hostname and repoint the
origin behind it**. Do not issue a new URL — that would force an EAS rebuild and
a reinstall for anyone holding your build.

## Which topology to use

| | Public entry point | Needs open ports | Needs Certbot |
|---|---|---|---|
| **A. Cloudflare Tunnel** | Cloudflare edge | No | No |
| **B. Host reverse proxy** | Nginx on the host | 80/443 | Yes |

Prefer **A**. The container stays bound to `127.0.0.1:8000`, nothing is exposed
to the internet, and TLS is Cloudflare's problem. Topology B is only worth it if
you need the host reachable without Cloudflare; its Nginx server block is in
`deploy/nginx/fincoach-api.conf`.

## Host sizing

The process loads BGE-M3 and PaddleOCR into one worker (`app/main.py` warms both
at startup), so plan for **4 GB RAM**. 2 GB only works if you first move
embeddings off-box.

On Azure for Students ($100 credit, no credit card, verified with a university
email), that means a **B2s: 2 vCPU / 4 GB**, roughly $30/month, so the credit
covers about three months of 24/7 uptime. Spending, not the expiry date, is the
binding limit — the credit window is longer than the credit lasts. Check the
pricing calculator for **B2als v2** (2 vCPU / 4 GB, AMD) before creating the VM;
it is usually cheaper than B2s for the same memory. Picking a low-cost region
also helps and costs nothing that matters here, since every coaching request
already blocks on a remote LLM call.

The 750 free monthly VM hours are B1s, B2pts v2, and B2ats v2 — all 1 GB, which
is too small for this image. There is no free-hours SKU that fits; the 4 GB
requirement necessarily draws down credit.

## 1. Prepare the host

```bash
sudo apt-get update && sudo apt-get install --yes ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER" && newgrp docker
```

## 2. Copy the backend

Upload this directory to `/opt/fincoach-backend`. Never upload `.venv` or `.env`.

```bash
rsync -av --exclude .venv --exclude .env --exclude __pycache__ \
  ./fincoach-backend/ user@HOST:/opt/fincoach-backend/
```

## 3. Production environment

Create `/opt/fincoach-backend/.env` from `.env.example`, fill in the real
secrets, and lock it down:

```bash
sudo chmod 600 /opt/fincoach-backend/.env
```

`SUPABASE_SERVICE_ROLE_KEY`, `LLM_API_KEY`, and `GEMINI_API_KEY` belong only in
this file — never in the Expo app.

Two Oracle-specific values in `.env.example` should be dropped on x86_64:

- `PADDLE_OCR_ENGINE=paddle_dynamic` — existed only because the prebuilt ARM64
  Paddle wheel segfaults creating the static predictor. Leave it unset.
- `PADDLE_OCR_CPU_THREADS=4` — set this to the host's actual vCPU count (2 on a
  B2s). `compose.vps.yml` already defaults to 2.

No re-ingestion is needed. The embedding model is unchanged, so the vectors
already in Supabase stay valid.

## 4. Build and start

```bash
cd /opt/fincoach-backend
docker compose -f compose.vps.yml build
docker compose -f compose.vps.yml up -d
docker compose -f compose.vps.yml logs -f backend
```

First start downloads BGE-M3 (~2.3 GB) and the PaddleOCR models into two named
volumes; the healthcheck allows 15 minutes for it. Later rebuilds reuse them.

Verify the private origin before exposing anything:

```bash
curl --fail http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/ready
```

`/health` returns `{"status":"ok"}` as soon as the process is up. `/ready`
returns 503 until both `ocr` and `embeddings` report `ready` — wait for it.

## 5. Publish with a Cloudflare Tunnel

In the Cloudflare dashboard: **Zero Trust → Networks → Tunnels → Create a
tunnel** (type `cloudflared`). Copy the token, then add it to `.env`:

```text
CLOUDFLARE_TUNNEL_TOKEN=eyJ...
```

Add one Public Hostname to the tunnel:

| Field | Value |
|---|---|
| Subdomain | `api` |
| Domain | `chisquaredv10.dpdns.org` |
| Service | `http://backend:8000` |

Use `http://backend:8000`, not `127.0.0.1:8000` — `cloudflared` runs in its own
container and resolves `backend` over the compose network. Then start it:

```bash
docker compose -f compose.vps.yml --profile tunnel up -d
```

Saving the Public Hostname replaces the old proxied `A` record (which still
points at the dead Oracle IP) with a tunnel `CNAME`. Confirm from outside:

```bash
curl --fail https://api.chisquaredv10.dpdns.org/health
```

Receipt uploads need a body-size ceiling above Cloudflare's default 100 MB only
if you raise the mobile client's limit; the Nginx path caps it at 15 MB.

## Updates

```bash
cd /opt/fincoach-backend
docker compose -f compose.vps.yml up -d --build
```

The two model volumes survive application rebuilds.

## If the host dies again

Nothing irreplaceable lives on it: all user data is in Supabase, the LLM is a
remote API, the models re-download, and the corpus and code are in git. Recovery
is re-running this guide on a new host and re-pointing the same tunnel hostname.
