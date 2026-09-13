# PHINOX Deployment Guide

Production deployment on Hetzner Cloud VPS via docker compose. Single-node
deployment (no Kubernetes — out of scope for Phase 6; tracked in
`ARCHITECTURE_MAP.md` open question).

## Prerequisites

1. **Hetzner Cloud account** + a VPS (CX21 or larger — 2 vCPU / 4GB RAM minimum).
2. **Domain name** pointed at the VPS IP (A record).
3. **TLS certs** — Let's Encrypt via certbot (instructions below) OR a
   Hetzner-managed cert mounted into the `phinox_certs` volume.
4. **Hetzner Object Storage** bucket (for media files in prod). Get the
   access key + secret + endpoint URL from the Hetzner Cloud Console.
5. **Sentry project** (optional but recommended) — create one at
   sentry.io (or self-host) + copy the DSN.
6. **GitHub repo** with the `main` branch protected (CI runs first).
7. **GitHub repo secrets** (Settings → Secrets → Actions):
   - `HETZNER_HOST` — VPS IP or hostname
   - `HETZNER_USER` — SSH user (default: `phinox`)
   - `SSH_PRIVATE_KEY` — private key matching `~/.ssh/authorized_keys` on the VPS
   - `HETZNER_PROJECT_DIR` — path to docker-compose.yml on the VPS (default: `/srv/phinox`)

## Step-by-step: First deploy

### 1. Provision the VPS

```bash
# On your local machine (or via Hetzner web console)
hcloud server create --name phinox-prod --type cx21 --image ubuntu-24.04 --ssh-key <your-key>
hcloud server ssh phinox-prod  # SSH in
```

### 2. Install Docker + Docker Compose on the VPS

```bash
# On the VPS
apt-get update && apt-get install -y docker.io docker-compose-plugin
systemctl enable --now docker
useradd --create-home --shell /bin/bash phinox
usermod -aG docker phinox
mkdir -p /srv/phinox/.env /srv/phinox/.ssh
chown -R phinox:phinox /srv/phinox
```

### 3. Set up the SSH deploy key

```bash
# On your local machine
ssh-keygen -t ed25519 -f ~/.ssh/phinox_deploy -C "github-actions-deploy"
# Copy the contents of ~/.ssh/phinox_deploy.pub to the VPS:
scp ~/.ssh/phinox_deploy.pub phinox@<VPS-IP>:/tmp/deploy.pub
ssh phinox@<VPS-IP> "mkdir -p ~/.ssh && cat /tmp/deploy.pub >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
# Copy the contents of ~/.ssh/phinox_deploy (private key) to GitHub
# repo Settings → Secrets → Actions → "SSH_PRIVATE_KEY"
```

### 4. Configure the .env on the VPS

```bash
# On the VPS (as phinox user)
cd /srv/phinox
# Copy the repo's .env.example to /srv/phinox/.env, then fill in production values:
nano /srv/phinox/.env
```

Required production values (replace the dummies):
```bash
DJANGO_SECRET_KEY=<generate via: python -c "import secrets; print(secrets.token_urlsafe(64))">
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=phinox.example.com,www.phinox.example.com
DATABASE_URL=postgres://phinox:<strong-postgres-pw>@db:5432/phinox
POSTGRES_PASSWORD=<strong-postgres-pw>
REDIS_URL=redis://redis:6379/0
CORS_ALLOWED_ORIGINS=https://phinox.example.com
CSRF_TRUSTED_ORIGINS=https://phinox.example.com
DJANGO_DEFAULT_FROM_EMAIL=no-reply@phinox.example.com
DJANGO_SITE_DOMAIN=https://phinox.example.com
DJANGO_ADMIN_EMAIL=ops@phinox.example.com
SENTRY_DSN=<from sentry.io>
SENTRY_TRACES_SAMPLE_RATE=0.1
AWS_STORAGE_BUCKET_NAME=phinox-prod-media
AWS_S3_ENDPOINT_URL=https://fsn1.your-objectstorage.com
AWS_S3_CUSTOM_DOMAIN=cdn.phinox.example.com
AWS_ACCESS_KEY_ID=<from Hetzner Console>
AWS_SECRET_ACCESS_KEY=<from Hetzner Console>
AWS_S3_REGION_NAME=fsn1
```

### 5. Set up TLS certs via certbot

```bash
# On the VPS
apt-get install -y certbot
certbot certonly --standalone -d phinox.example.com -d www.phinox.example.com
# Mount the certs into the docker-compose phinox_certs volume:
mkdir -p /srv/phinox/certs
cp /etc/letsencrypt/live/phinox.example.com/fullchain.pem /srv/phinox/certs/
cp /etc/letsencrypt/live/phinox.example.com/privkey.pem  /srv/phinox/certs/
chmod 644 /srv/phinox/certs/*.pem
# Add to /srv/phinox/.env:
#   NGINX_CERTS_DIR=/srv/phinox/certs
```

### 6. Build + start the stack

```bash
# On the VPS (as phinox user)
cd /srv/phinox
docker compose -f docker/docker-compose.yml up -d
docker compose logs -f web  # watch gunicorn logs
# Verify health
curl -fsS http://localhost:8000/health/ | head
curl -fsS http://localhost:8000/health/ready/ | head
# Should return {"status": "ok", ...}
```

### 7. Push to main → auto-deploy

Once the GitHub Actions `deploy.yml` is wired (Step 3), every push to `main`:
1. CI runs (lint + test + migrations check + check --deploy).
2. `deploy.yml` builds the Docker image + pushes to GHCR.
3. `deploy.yml` SSHes to the VPS + runs `docker compose pull && up -d`.
4. `deploy.yml` waits for `/health/` to return 200 (up to 60s).

## Rollback procedure

If a deploy breaks production:

```bash
# On the VPS
cd /srv/phinox
# Find the previous image tag (each deploy tags with the GitHub run number)
docker images phinox-web:*
# Revert to the previous tag:
docker compose -f docker/docker-compose.yml down
docker tag phinox-web:deploy-<previous-run> phinox-web:latest
docker compose -f docker/docker-compose.yml up -d
# Verify health:
curl -fsS http://localhost:8000/health/ | head
```

If a migration broke the DB schema:
```bash
# Use the previous deploy's image (which knows the previous schema)
docker compose -f docker/docker-compose.yml down
docker tag phinox-web:deploy-<previous-run> phinox-web:latest
docker compose -f docker/docker-compose.yml up -d
# The previous image's entrypoint runs the old migrations — but if the new
# migrations already ran, you need to manually roll them back via
# ``migrate <app> <previous-migration>``:
docker compose -f docker/docker-compose.yml exec web python manage.py migrate apps.accounts 0001
# Then revert the image (already done above)
```

## Common pitfalls

1. **CSRF cookie not set in production** — confirm `CSRF_TRUSTED_ORIGINS` matches
   the production domain (https:// prefix required).
2. **S3 media not loading** — confirm `AWS_S3_CUSTOM_DOMAIN` matches the CDN
   domain + the bucket policy allows public read.
3. **Sentry not receiving events** — confirm `SENTRY_DSN` is set + the VPS can
   reach sentry.io (some Hetzner regions block outbound 443 — check firewall).
4. **Health endpoint 503** — `/health/ready/` returns 503 if any of db/redis/cache
   is down. Check `docker compose logs db redis` for the failing service.

## Next steps after first deploy

- Smoke-test the live site: login + register + cart + checkout (COD) + order tracking.
- Configure Sentry alert routing (email / Slack) per دستور §11.
- Set up Hetzner Cloud backups for the postgres volume (daily snapshot).
- Wire Phase 4 (Paymob webhook) — see `OPERATIONS.md` for the integration steps.
