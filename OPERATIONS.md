# PHINOX Operations Runbook

Day-to-day ops for the PHINOX production deployment on Hetzner Cloud.

## SSH into the VPS

```bash
ssh phinox@<VPS-IP>
cd /srv/phinox
```

## Inspect running services

```bash
# All services + their health status
docker compose -f docker/docker-compose.yml ps

# Tail logs (all services)
docker compose -f docker/docker-compose.yml logs -f

# Tail logs (single service)
docker compose -f docker/docker-compose.yml logs -f web
docker compose -f docker/docker-compose.yml logs -f celery_worker
docker compose -f docker/docker-compose.yml logs -f db
```

## Health checks

```bash
# Liveness (gunicorn is alive)
curl -fsS http://localhost:8000/health/
# Readiness (DB + Redis + cache all OK)
curl -fsS http://localhost:8000/health/ready/
# If the readiness probe returns 503, inspect the JSON payload:
#   {"status": "down", "checks": {"db": "ok", "redis": "down", "cache": "down"}}
# — tells you exactly which service to investigate.
```

## Run migrations manually

Migrations run automatically on container start (entrypoint.sh). To run them
manually (e.g. after rolling back to an older image):

```bash
docker compose -f docker/docker-compose.yml exec web python manage.py migrate --noinput
# To roll back a specific app to a previous migration:
docker compose -f docker/docker-compose.yml exec web python manage.py migrate apps.accounts 0001
# To check pending migrations without applying:
docker compose -f docker/docker-compose.yml exec web python manage.py showmigrations --plan | grep -E "\[ \]|account"
```

## Collect static files manually

```bash
# WhiteNoise manifest needs to be regenerated if dist.css changes
docker compose -f docker/docker-compose.yml exec web python manage.py collectstatic --noinput
```

## Restart Celery worker

```bash
# Restart only the celery worker (graceful — in-flight tasks finish)
docker compose -f docker/docker-compose.yml restart celery_worker

# Restart celery beat (the scheduler)
docker compose -f docker/docker-compose.yml restart celery_beat
```

## Restart nginx (after cert renewal)

```bash
# After Let's Encrypt cert renewal:
docker compose -f docker/docker-compose.yml restart nginx
```

## Rebuild the Tailwind CSS

```bash
# On your local dev machine (not the VPS — node_modules aren't in the prod image)
npm install  # if not already done
npm run build:css  # writes static/css/dist.css
# Commit dist.css + push to main → CI builds the image + deploys.
```

## Common issues

### Issue: `502 Bad Gateway` from nginx

1. Check if gunicorn is alive: `docker compose logs web | tail -50`
2. Check the health endpoint: `curl -fsS http://localhost:8000/health/`
3. If gunicorn crashed, check OOM: `docker stats phinox-web`
4. Restart: `docker compose up -d web`

### Issue: `OperationalError: could not connect to server` (Postgres)

1. Check Postgres health: `docker compose logs db | tail -50`
2. Check disk space: `df -h` (Postgres refuses connections when disk is full)
3. Restart: `docker compose up -d db` (this will lose data on the volume if
   you delete the `phinox_pgdata` volume — NEVER delete that volume)

### Issue: OTP delivery not working in prod

The phone-OTP password reset flow uses `print()` to the console in dev mode.
For prod, an SMS gateway needs to be wired (Phase 7+ — see `worklog.md` open
question #1). To verify the OTP flow works in staging (without SMS):

```bash
docker compose -f docker/docker-compose.yml logs web | grep "OTP DELIVERY"
# Should show: [OTP DELIVERY] phone=+201012345678  code=123456  purpose=password_reset
```

### Issue: Sentry not receiving events

1. Confirm `SENTRY_DSN` is in `.env`: `grep SENTRY_DSN /srv/phinox/.env`
2. Confirm outbound HTTPS works from the VPS: `curl -fsS https://sentry.io`
3. Check Sentry init in the web logs: `docker compose logs web | grep -i sentry`

### Issue: WhiteNoise returning 404 for /static/

1. Run `collectstatic` manually (above).
2. Check the manifest: `docker compose exec web ls /app/staticfiles/`
3. If `dist.css` is missing, rebuild it locally + commit (see "Rebuild the
   Tailwind CSS" above).

### Issue: Celery worker not consuming tasks

1. Check worker health: `docker compose ps celery_worker`
2. Check Redis: `docker compose exec redis redis-cli ping` → `PONG`
3. Check the worker logs for `ConnectionError`: `docker compose logs celery_worker | tail -50`
4. Restart: `docker compose up -d celery_worker`

## Backup procedure

### Postgres (daily snapshot)

Hetzner Cloud supports automated snapshots of the VPS volume. Configure in
the Hetzner Cloud Console (Volumes → Snapshots → Add schedule). For finer
control, use `pg_dump`:

```bash
# On the VPS, as phinox user
docker compose -f docker/docker-compose.yml exec db pg_dump -U phinox phinox > /tmp/phinox_$(date +%Y-%m-%d).sql
# Upload to S3 / Hetzner Storage Box
```

### Media files

If media is on Hetzner Object Storage, the bucket itself is the backup (S3
versioning recommended). If media is on local filesystem (dev/staging without
S3), back up the `media/` directory:

```bash
docker compose -f docker/docker-compose.yml exec web tar -czf - /app/media > /tmp/phinox_media_$(date +%Y-%m-%d).tar.gz
```

## Disaster recovery

If the VPS is lost (Hetzner deletion, disk corruption):

1. **Provision a new VPS** (Step 1 of DEPLOYMENT.md).
2. **Restore .env** from your secret manager (Bitwarden, 1Password, etc.).
3. **Restore the latest Postgres dump** from S3 / Hetzner Storage Box:
   ```bash
   docker compose up -d db
   docker compose exec -T db psql -U phinox phinox < /tmp/phinox_latest.sql
   ```
4. **Restore media files** (if not on S3):
   ```bash
   docker compose cp /tmp/phinox_media_latest.tar.gz web:/tmp/
   docker compose exec web tar -xzf /tmp/phinox_media_latest.tar.gz -C /
   ```
5. **Bring up the rest of the stack**:
   ```bash
   docker compose up -d
   ```
6. **Verify health**:
   ```bash
   curl -fsS http://localhost:8000/health/ready/
   ```

## Monitoring + alerting

- **Sentry**: errors + performance traces (10% sampling in prod).
- **Docker HEALTHCHECK**: every 30s on the web service.
- **Hetzner Cloud Monitoring** (free): configure CPU/RAM alerts in the Cloud Console.
- **UptimeRobot** (free): monitor `https://phinox.example.com/health/ready/` from external locations.

## Phase 7+ recommendations

- **Paymob webhook** (Phase 4) — wire the webhook handler in `apps/payments/views.py`
  + Paymob signature verification + idempotency check.
- **SMS gateway** (Phase 7) — Twilio or Egyptian SMS provider for production OTP delivery.
- **OTP cleanup Celery beat task** — periodic cleanup of expired OTPRequest rows.
- **AuthEvent audit table** — for tracking login/logout/signup events with IP + user agent.
- **DB-level email uniqueness** — migration to add UniqueConstraint on CustomUser.email.
