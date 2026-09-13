# syntax=docker/dockerfile:1
# PHINOX production Dockerfile — Phase 6 STITCH-INTEGRATION hardening.
#
# Multi-stage build:
#   - ``builder``:   compiles Python wheels (build-essential + libpq-dev).
#   - ``runtime``:   minimal Python image with only runtime deps.
#
# Per دستور §11 + tech debt:
#   - python:3.12-slim base (small, Debian-derived, glibc-compatible with psycopg).
#   - non-root user (phinox:phinox) per دستور §5 + §11.
#   - HEALTHCHECK every 30s against /health/ (Docker-native, no extra dep).
#   - gunicorn config via gunicorn.conf.py (workers=2*cpu+1, max_requests=1000).
#
# Image size target: ~250MB (vs. ~700MB for the python:3.12 base).

# ─── Stage 1: builder ──────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Build deps: libpq-dev for psycopg[binary] (compiled C extension).
# build-essential for any package with a C extension (rare, but Pillow etc).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps into a virtual env inside the builder stage so the
# runtime stage can copy just the wheels (no build-essential).
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements/ requirements/
RUN pip install --upgrade pip wheel \
    && pip install -r requirements/prod.txt

# ─── Stage 2: runtime ────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.settings.prod \
    PYTHONPATH=/app

# Runtime deps: libpq5 (psycopg runtime), curl (HEALTHCHECK), gettext (for
# django-admin compilemessages if i18n is enabled).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl gettext \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash --uid 1000 phinox

# Copy the venv from the builder stage (chown so the non-root user can read it).
COPY --from=builder --chown=phinox:phinox /opt/venv /opt/venv

WORKDIR /app

# Copy the project (chown to the non-root user so migrations can write
# sqlite/db.sqlite3 if it's ever used in a fallback — not in prod).
COPY --chown=phinox:phinox . .

# PHASE-D §D3: collectstatic at BUILD time (not runtime).
# Previously the entrypoint ran ``collectstatic --noinput`` at container
# start, adding ~5s of cold-start latency + requiring a writable
# STATIC_ROOT at runtime. Moving it to build-time means the manifest is
# baked into the image — the entrypoint just execs the CMD. WhiteNoise
# serves the manifest from /app/staticfiles/ via the STORAGES config.
# Secret-key + DB env vars are dummy (collectstatic doesn't need real
# secrets; it just walks the staticfiles dirs + hashes the contents).
ENV DJANGO_SECRET_KEY=build-time-dummy-secret-not-for-runtime \
    DJANGO_SETTINGS_MODULE=config.settings.prod \
    DATABASE_URL= \
    PAYMOB_MODE=sandbox
RUN python manage.py collectstatic --noinput

USER phinox

EXPOSE 8000

# Per دستور §11 + Docker best practice: HEALTHCHECK probes /health/ every
# 30s. The endpoint is liveness-only (no downstream checks), so a 200
# means the gunicorn process is alive + serving.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/health/ || exit 1

# Entrypoint: wait for DB → migrate → collectstatic → exec the user CMD.
ENTRYPOINT ["./docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--config", "gunicorn.conf.py"]
