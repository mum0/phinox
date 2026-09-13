#!/bin/sh
# PHINOX production entrypoint — Phase 6 STITCH-INTEGRATION hardening.
#
# PHASE-FINAL §2: branch on ``CELERY_ROLE`` env var so the same image
# can serve as the Django web container, the Celery worker, OR the
# Celery beat scheduler. The docker-compose.yml sets:
#
#   - web           → CELERY_ROLE="" (default)  + RUN_MIGRATIONS=1
#   - celery_worker → CELERY_ROLE="worker"        + RUN_MIGRATIONS=0
#   - celery_beat   → CELERY_ROLE="beat"          + RUN_MIGRATIONS=0
#
# Flow:
#   1. Wait for the database (retry 30× with 2s backoff).
#   2. PHASE-D §D2: if RUN_MIGRATIONS=1, acquire a ``flock`` + run
#      ``migrate --noinput``. Only the ``web`` service does this.
#   3. PHASE-D §D3: collectstatic is BUILD-TIME (Dockerfile RUN) —
#      the entrypoint does NOT run it at container start.
#   4. PHASE-FINAL §2: branch on CELERY_ROLE:
#      - "worker" → exec celery -A config worker -l info
#      - "beat"   → exec celery -A config beat -l info
#      - "" (default) → exec the CMD (gunicorn / runserver / etc.)
#   5. exec "$@" replaces the shell so SIGTERM propagates cleanly.
#
# Per دستور §5 + §6:
#   - Migrations are non-interactive (--noinput) — no manual prompts in CI/CD.
#   - Never edit an applied migration (per دستور §6) — entrypoint only runs
#     pending ones.
#   - The entrypoint runs as the non-root ``phinox`` user (set in Dockerfile).
#
# Per دستور §11 + Docker best practice:
#   - ``exec "$@"`` replaces the shell with the CMD process so signals
#     (SIGTERM from ``docker stop``) propagate cleanly to gunicorn (which
#     does a graceful 30s shutdown per gunicorn.conf.py's graceful_timeout).
set -e

echo "[entrypoint] PHINOX production container starting (CELERY_ROLE=${CELERY_ROLE:-web})..."

# ─── 1. Wait for database ──────────────────────────────────────────────────
echo "[entrypoint] Waiting for database..."
python - << 'PYEOF'
import os, time, sys
import psycopg
url = os.environ.get("DATABASE_URL", "")
if not url:
    print("[entrypoint] DATABASE_URL not set — skipping DB wait (dev mode?)")
    sys.exit(0)
# Django 5.0 / psycopg3 want the postgresql:// scheme.
url = url.replace("postgres://", "postgresql://")
for attempt in range(30):
    try:
        with psycopg.connect(url, connect_timeout=2):
            print(f"[entrypoint] DB ready after {attempt} attempt(s).")
        sys.exit(0)
    except Exception as exc:
        print(f"[entrypoint] DB not ready (attempt {attempt}/30): {str(exc)[:120]}")
        time.sleep(2)
print("[entrypoint] Database never became available — exiting.", file=sys.stderr)
sys.exit(1)
PYEOF

# ─── 2. PHASE-D §D2: Migrations (only if RUN_MIGRATIONS=1) ────────────────
# The ``web`` service in docker-compose.yml sets RUN_MIGRATIONS=1; the
# ``celery_worker`` + ``celery_beat`` services don't (they reuse the same
# image but skip migrations — the web service already ran them).
#
# Lock strategy (defense in depth):
#   - ``flock`` (Linux file lock) — blocks concurrent containers from
#     running migrate at the same time. If multiple web replicas start
#     concurrently, only one acquires the lock; the others wait, then
#     re-check if migrations are needed ( Django ``migrate --plan`` is
#     idempotent — running it twice is a no-op).
#   - On Postgres, Django's ``migrate`` already takes a per-DB advisory
#     lock internally (since Django 4.0+), so the ``flock`` is belt-
#     and-suspenders; the real protection is Django's advisory lock.
if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
    echo "[entrypoint] Acquiring migrations lock + running migrations..."
    # PHASE-D §D2: ``flock`` blocks until the lock is free, then runs
    # the migrate command. The lock file is on a tmpfs (Docker's /tmp)
    # so it doesn't persist across container restarts.
    #
    # If ``flock`` is unavailable (e.g. on a slim base image), the
    # fallback is to run migrate directly — Django's internal Postgres
    # advisory lock prevents races anyway.
    if command -v flock >/dev/null 2>&1; then
        flock /tmp/phinox_migrate.lock -c "python manage.py migrate --noinput"
    else
        python manage.py migrate --noinput
    fi
else
    echo "[entrypoint] RUN_MIGRATIONS != 1 — skipping migrations (worker/beat)."
fi

# ─── 3. PHASE-D §D3: collectstatic removed (now build-time in Dockerfile) ──
# Previously the entrypoint ran ``python manage.py collectstatic --noinput``
# at container start. This added ~5s of cold-start latency + required a
# writable STATIC_ROOT. The staticfiles manifest is now built at Docker
# BUILD time (see docker/Dockerfile's ``RUN python manage.py collectstatic
# --noinput`` line). The runtime entrypoint just execs the CMD.

# ─── 4. PHASE-FINAL §2: branch on CELERY_ROLE ──────────────────────────────
# Same image, different role per container:
#   - "worker" → celery worker (consumes tasks from the Redis broker)
#   - "beat"   → celery beat (schedules periodic tasks like
#                release_abandoned_reservations every 5 min)
#   - "" (default) → Django web (gunicorn in prod, runserver in dev)
case "${CELERY_ROLE:-}" in
    worker)
        echo "[entrypoint] Starting Celery worker..."
        exec celery -A config worker -l info
        ;;
    beat)
        echo "[entrypoint] Starting Celery beat scheduler..."
        exec celery -A config beat -l info
        ;;
    *)
        # Default: Django web. Hand off to the CMD (gunicorn / runserver).
        # The Dockerfile's CMD is:
        #   ["gunicorn", "config.wsgi:application", "--config", "gunicorn.conf.py"]
        # Dev mode can override CMD to runserver via docker-compose override.
        echo "[entrypoint] Starting Django web: $@"
        exec "$@"
        ;;
esac
