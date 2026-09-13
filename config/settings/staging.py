"""Staging settings — Phase 6 production hardening.

Staging mirrors production as closely as possible (per دستور §11):
  - DEBUG from env (defaults to False — staging should NOT expose debug pages).
  - Same security headers as prod.
  - Sentry initialized with environment="staging" + PII scrubbing (per دستور §5).
  - Media files via S3 if creds are present, else fall back to local filesystem.
  - Structured JSON logging (same as prod).

Differences from prod:
  - Sentry environment="staging" (so events are grouped separately in the
    Sentry dashboard).
  - DB: staging Postgres instance (env-driven).
  - DEBUG can be set to True via env for ad-hoc debugging (NOT recommended
    for shared staging — use dev settings locally instead).
"""
from .base import *  # noqa: F401,F403

# ---------------------------------------------------------------------------
# Core — staging defaults to non-debug.
# ---------------------------------------------------------------------------
DEBUG = env.bool("DJANGO_DEBUG", default=False)  # noqa: F405

# ---------------------------------------------------------------------------
# Security headers (mirror prod per دستور §11)
# ---------------------------------------------------------------------------
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)  # noqa: F405
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
X_FRAME_OPTIONS = "DENY"

# Cookie hardening (mirror prod)
SESSION_COOKIE_AGE = 86400
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SAMESITE = "Lax"

# CORS + CSRF — from env
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])  # noqa: F405
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])  # noqa: F405
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])  # noqa: F405

# Admin emails — staging recipients get the same error emails as prod.
ADMINS = [
    ("PHINOX Operations", env.str("DJANGO_ADMIN_EMAIL", default="ops@phinox.example")),  # noqa: F405
]
MANAGERS = ADMINS

# ---------------------------------------------------------------------------
# Static / Media storage — Django 5.0 STORAGES dict (per tech debt #6)
# ---------------------------------------------------------------------------
# Staging uses S3 if creds are present (faithful pre-prod check); falls
# back to local filesystem if not. Per دستور §11: staging should mirror
# prod, so we always configure the STORAGES dict; the actual backend is
# determined by whether AWS creds are present.
_AWS_BUCKET = env("AWS_STORAGE_BUCKET_NAME", default="")  # noqa: F405

if _AWS_BUCKET:
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }
    AWS_STORAGE_BUCKET_NAME = _AWS_BUCKET
    AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", default="")  # noqa: F405
    AWS_S3_CUSTOM_DOMAIN = env("AWS_S3_CUSTOM_DOMAIN", default="")  # noqa: F405
    AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default="")  # noqa: F405
    AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", default="")  # noqa: F405
    AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="fsn1")  # noqa: F405
    AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}
    if AWS_S3_CUSTOM_DOMAIN:
        MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/"
else:
    # No S3 creds — use local filesystem (good for ad-hoc staging on a dev VPS).
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }

# ---------------------------------------------------------------------------
# Sentry — staging environment with PII scrubbing (per دستور §5)
# ---------------------------------------------------------------------------
SENTRY_DSN = env("SENTRY_DSN", default="")  # noqa: F405
if SENTRY_DSN:
    from config.observability import init_sentry
    init_sentry(
        dsn=SENTRY_DSN,
        environment="staging",
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.5),  # noqa: F405 — staging samples more aggressively
    )
