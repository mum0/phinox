"""Production settings — Phase 6 production hardening.

Per دستور §5 + §7:
  - DEBUG = False (no exceptions — per دستور §5)
  - All security headers (HSTS, SSL redirect, secure cookies, CSP via nginx)
  - ADMINS + MANAGERS for error emails (per دستور §11)
  - ALLOWED_HOSTS + CSRF_TRUSTED_ORIGINS from env (no open defaults)
  - Sentry initialized with PII-scrubbing before_send hook (per دستور §5)
  - Structured JSON logging via config.observability.JSONFormatter (per دستور §11)
  - Media files via django-storages + Hetzner S3 (per دستور §11 / §5.10)
  - Static files via WhiteNoise compressed manifest storage (per دستور §11)

PHASE-A §A1/§A3/§A7 production hardening:
  - SECRET_KEY: no default — ImproperlyConfigured if missing.
  - DATABASES: env.db("DATABASE_URL") with no default — refuses to start
    without Postgres. SQLite is forbidden in prod.
  - PAYMOB_MODE: must be 'sandbox' or 'live'. 'simulation' is forbidden
    in prod (would let orders be confirmed without a real payment).
"""
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403

# ---------------------------------------------------------------------------
# Core — must be False in production
# ---------------------------------------------------------------------------
DEBUG = False

# ---------------------------------------------------------------------------
# PHASE-A §A3: SECRET_KEY — NO DEFAULT in production.
# ---------------------------------------------------------------------------
# If DJANGO_SECRET_KEY is not set in the environment, the deploy must fail
# fast with ImproperlyConfigured rather than silently fall back to the
# insecure dev key (which would let attackers forge session cookies).
SECRET_KEY = env.str("DJANGO_SECRET_KEY")  # noqa: F405 — no default; raises if missing

# ---------------------------------------------------------------------------
# PHASE-A §A1: DATABASES — Postgres mandatory in production.
# ---------------------------------------------------------------------------
# SQLite is a dev-only fallback (see config/settings/base.py). Production
# must wire a real DATABASE_URL — refusing to start without one prevents
# accidental SQLite deploys that would lose data on container restart.
DATABASES = {"default": env.db("DATABASE_URL")}  # noqa: F405 — no default; raises if missing

# ---------------------------------------------------------------------------
# PHASE-A §A7: PAYMOB_MODE — 'simulation' is FORBIDDEN in production.
# ---------------------------------------------------------------------------
# simulation mode skips real Paymob API calls and lets a PaymentSimulationView
# confirm an order without any payment capture. Allowing this in prod would
# mean customers could place orders without paying. The check runs at import
# time so a misconfigured deploy fails fast (container exits, Sentry alerts).
_PAYMOB_MODE_PROD = env.str("PAYMOB_MODE", default="simulation")  # noqa: F405
if _PAYMOB_MODE_PROD == "simulation":
    raise ImproperlyConfigured(
        "PAYMOB_MODE='simulation' is FORBIDDEN in production. "
        "Set PAYMOB_MODE='sandbox' for the Paymob sandbox (real HTTP, test cards) "
        "or PAYMOB_MODE='live' for production card payments."
    )
PAYMOB_MODE = _PAYMOB_MODE_PROD

# ---------------------------------------------------------------------------
# Security headers (per دستور §5 + §11)
# ---------------------------------------------------------------------------
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
X_FRAME_OPTIONS = "DENY"

# Cookie hardening
SESSION_COOKIE_AGE = 86400  # 24 hours
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SAMESITE = "Lax"

# CORS — locked down to explicit origins from env (no open defaults).
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])  # noqa: F405
CORS_ALLOW_CREDENTIALS = True

# CSRF — must list the production domain(s) so POST forms work.
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])  # noqa: F405

# ALLOWED_HOSTS — must be set via env (no open default in prod).
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])  # noqa: F405

# ---------------------------------------------------------------------------
# Admin / Manager emails — Django sends server-error emails to ADMINS
# (500 responses) and MANAGERS (404 responses if SEND_BROKEN_LINK_EMAILS=True).
# Per دستور §11 + §5: PII never logged, but error emails are fine.
# ---------------------------------------------------------------------------
ADMINS = [
    ("PHINOX Operations", env.str("DJANGO_ADMIN_EMAIL", default="ops@phinox.example")),  # noqa: F405
]
MANAGERS = ADMINS

# ---------------------------------------------------------------------------
# Static / Media storage — Django 5.0 uses STORAGES dict (per tech debt #6)
# ---------------------------------------------------------------------------
# Per دستور §11 / §5.10: prod uses django-storages with Hetzner Object
# Storage (S3-compatible) for media uploads + WhiteNoise compressed manifest
# for static files. The Hetzner credentials come from env — never hardcoded
# (per دستور §5).
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
    },
    "staticfiles": {
        # WhiteNoise — serves the compiled dist.css + the staticfiles manifest
        # directly from gunicorn, no nginx needed for /static/. Per دستور §11
        # tech debt #6, STORAGES is the Django 5.0 way (not STATICFILES_STORAGE).
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# django-storages — Hetzner S3-compatible Object Storage
AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="")  # noqa: F405
AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", default="")  # noqa: F405
AWS_S3_CUSTOM_DOMAIN = env("AWS_S3_CUSTOM_DOMAIN", default="")  # noqa: F405
AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default="")  # noqa: F405
AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", default="")  # noqa: F405
AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="fsn1")  # noqa: F405
# Per دستور §5: never log secrets. The S3 backend logs at INFO level by
# default; we don't override that, but the structured JSON formatter
# (config.observability.JSONFormatter) never serializes the raw boto3
# session credentials (they live in env, not in LogRecord.extra).
AWS_S3_OBJECT_PARAMETERS = {
    "CacheControl": "max-age=86400",  # 24h CDN cache
}

# Use S3-backed media URL when AWS_S3_CUSTOM_DOMAIN is set, else fall back
# to MEDIA_URL (local filesystem). This lets staging run without S3 creds.
if AWS_S3_CUSTOM_DOMAIN:
    MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/"

# ---------------------------------------------------------------------------
# Sentry — Phase 6 PII-scrubbing init (per دستور §5)
# ---------------------------------------------------------------------------
SENTRY_DSN = env("SENTRY_DSN", default="")  # noqa: F405
if SENTRY_DSN:
    # Per دستور §5: PII scrub before any event leaves the process.
    from config.observability import init_sentry
    init_sentry(
        dsn=SENTRY_DSN,
        environment="production",
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.1),  # noqa: F405
    )
