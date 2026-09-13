"""
Base settings shared by every environment.
Environment-specific files (dev.py / staging.py / prod.py) import * from here
and override only what differs.
"""
from pathlib import Path
import environ

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    environ.Env.read_env(str(ENV_FILE))

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
# NOTE (PHASE-A §A3): the insecure-dev default is INTENTIONAL for dev only.
# config/settings/prod.py overrides this with `env("DJANGO_SECRET_KEY")` (no
# default) so production raises ImproperlyConfigured if the secret is missing.
SECRET_KEY = env("DJANGO_SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "corsheaders",
    "django_filters",
]

# PHINOX apps.
# NOTE (Phase 1): every app below is scaffolded with __init__.py + apps.py ONLY.
# No models.py, no business logic, no auth wiring, per Phase 1 scope in
# IMPLEMENTATION_PLAN.md. Models/logic are added app-by-app in later phases.
LOCAL_APPS = [
    "apps.core",
    "apps.pages",
    "apps.accounts",
    "apps.catalog",
    "apps.inventory",
    "apps.cart",
    "apps.checkout",
    "apps.orders",
    "apps.payments",
    "apps.shipping",
    "apps.promotions",
    "apps.reviews",
    "apps.wishlist",
    "apps.analytics",
    "apps.api",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Phase 3 — captures UTM + QR marketing attribution per-session.
    "apps.analytics.middleware.AttributionMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # PHINOX custom middleware is added in later phases (e.g. CheckoutStepGuardMiddleware
    # in Phase 3, RequestIDMiddleware for log correlation) — none exist yet in Phase 1.
]

ROOT_URLCONF = "config.urls"

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # "apps.core.context_processors.design_tokens" is added when the
                # base templates start consuming token data dynamically (Phase 3+).
                # GA4 — exposes GA4_MEASUREMENT_ID so the gtag.js snippet in
                # templates/analytics/ga4.html renders only when configured.
                "apps.analytics.context_processors.ga4_settings",
                # Phase: UNIFY-TOPBAR — cart badge count for the unified topbar.
                "apps.cart.context_processors.cart_item_count",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database (PostgreSQL in prod/staging; SQLite fallback for dev only)
# ---------------------------------------------------------------------------
# PHASE-A §A1: SQLite is a DEV-ONLY fallback. When DATABASE_URL is set (CI,
# staging, prod), it takes precedence. config/settings/prod.py overrides this
# entirely with `env.db("DATABASE_URL")` (no default) so production refuses
# to start without a real Postgres connection.
DATABASE_URL = env.str("DATABASE_URL", default="")
if DATABASE_URL:
    DATABASES = {"default": env.db("DATABASE_URL")}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Custom user model (apps.accounts.User) — must be set before the first
# migrate; added in Phase 2 alongside the model itself.
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.CustomUser"

# ---------------------------------------------------------------------------
# Auth / passwords
# NOTE: password validators are configured now (schema/foundation concern);
# actual login/registration views, OTP flow, and permissions wiring happen in
# a later phase per IMPLEMENTATION_PLAN.md §5.5 — Phase 2 is schema-only.
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Auth redirects — Phase 5 STITCH-INTEGRATION (real auth wiring)
# ---------------------------------------------------------------------------
# After successful login: send the user to the home page (or the ?next=
# URL they were trying to reach before being bounced to login).
LOGIN_REDIRECT_URL = "pages:home"
# After logout: send the user to the login page so they can log in again.
LOGOUT_REDIRECT_URL = "accounts:login"
# Login URL used by ``LoginRequiredMixin`` + ``login_required`` decorator.
LOGIN_URL = "accounts:login"

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = env("DJANGO_TIME_ZONE", default="Africa/Cairo")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & media files
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
# Django 5.0 STORAGES dict (per دستور §11 + tech debt #6 in ARCHITECTURE_MAP.md).
# Replaces STATICFILES_STORAGE + DEFAULT_FILE_STORAGE (Django 4.x style).
# Prod/staging override the "default" backend to django-storages S3.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage",
    },
}

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# In prod.py + staging.py the "default" backend is overridden to use
# django-storages with S3-compatible object storage (Hetzner Object
# Storage), per IMPLEMENTATION_PLAN.md §5.10 / §11.

# ---------------------------------------------------------------------------
# Redis / Cache / Celery
# NOTE: wired here per Phase 1's "configure the foundation" scope; task definitions
# and cache usage in views are added when the relevant app gains business logic.
# ---------------------------------------------------------------------------
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# ---------------------------------------------------------------------------
# PHINOX-V2.1: Celery Beat schedule — periodic task definitions.
# ---------------------------------------------------------------------------
# Per دستور §11 + PHASE-B §B2: ``release_abandoned_reservations`` runs
# every 5 minutes to free inventory reservations on orders stuck in
# PENDING for > 15 min (abandoned checkouts).
#
# Beat is wired via:
#   - ``CELERY_BEAT_SCHEDULER`` = the default PersistentScheduler (writes
#     the schedule to a local ``celerybeat-schedule.db`` file — survives
#     beat restarts so missed schedules don't fire all at once on restart).
#   - ``CELERY_BEAT_SCHEDULE`` = the dict of {task_name: {task, schedule}}.
#     Add new periodic tasks here (don't edit the beat service's command).
#
# In dev: Celery is eager (USE_CELERY=False runs tasks synchronously, so
# beat isn't needed). In prod: docker-compose.yml's celery_beat service
# reads CELERY_ROLE=beat + execs ``celery -A config beat -l info``.
from datetime import timedelta

CELERY_BEAT_SCHEDULER = "celery.beat.PersistentScheduler"
CELERY_BEAT_SCHEDULE = {
    # PHASE-B §B2: release inventory reservations on abandoned orders.
    # Triggered every 5 min; the task itself filters for Orders with
    # status=PENDING + created_at < now - 15min.
    "release-abandoned-reservations": {
        "task": "apps.orders.tasks.release_abandoned_reservations",
        "schedule": timedelta(minutes=5),
    },
    # Future periodic tasks (placeholder for documentation):
    #   - "sync-bos-orders" → sync orders to the BOS ERP (every 15 min).
    #   - "low-stock-alert" → email ops when any variant hits low_stock_threshold
    #     (every hour).
    #   - "cleanup-expired-otps" → delete OTPRequest rows past expires_at
    #     (daily at 03:00 CLT).
}

# ---------------------------------------------------------------------------
# Django REST Framework (surface scaffolded, no viewsets/serializers yet)
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 24,
}

# ---------------------------------------------------------------------------
# CORS (locked down by default; open per-origin in dev.py only)
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])

# ---------------------------------------------------------------------------
# Security headers (tightened further in prod.py)
# ---------------------------------------------------------------------------
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# ---------------------------------------------------------------------------
# PHINOX-specific: which design-token family a given request should render.
# See IMPLEMENTATION_PLAN.md §1 / §6.3 — both families are shipped side-by-side
# in static/css/tokens.css until Open Question #5 is resolved by the client.
# ---------------------------------------------------------------------------
PHINOX_DEFAULT_TOKEN_FAMILY = env("PHINOX_DEFAULT_TOKEN_FAMILY", default="a")

# ---------------------------------------------------------------------------
# GA4 (Google Analytics 4) — optional.
# Set GA4_MEASUREMENT_ID + GA4_API_SECRET in .env to enable:
#   - Server-side Measurement Protocol events (apps/analytics/ga4.py)
#   - Client-side gtag.js snippet (templates/analytics/ga4.html)
# When empty (default), both paths degrade to no-ops (per دستور §8: analytics
# capture is non-blocking and never breaks the user flow).
# GA4_DEBUG=True routes server-side hits to the GA4 debug endpoint (no recording).
# ---------------------------------------------------------------------------
GA4_MEASUREMENT_ID = env("GA4_MEASUREMENT_ID", default="")
GA4_API_SECRET = env("GA4_API_SECRET", default="")
GA4_DEBUG = env.bool("GA4_DEBUG", default=False)

# ---------------------------------------------------------------------------
# Email (defaults — overridden per-environment). dev.py uses the console
# backend; prod.py wires up SMTP via env vars (EMAIL_HOST, EMAIL_HOST_USER,
# EMAIL_HOST_PASSWORD, etc.). Used by apps/orders/notifications.py for
# order-confirmation + status-update emails.
# ---------------------------------------------------------------------------
DEFAULT_FROM_EMAIL = env("DJANGO_DEFAULT_FROM_EMAIL", default="PHINOX <no-reply@phinox.example>")
PHINOX_SITE_DOMAIN = env("DJANGO_SITE_DOMAIN", default="https://phinox.example")

# ---------------------------------------------------------------------------
# Logging — Phase 6 STITCH-INTEGRATION (production hardening)
# ---------------------------------------------------------------------------
# Dev: human-readable console output (Django default + a Console handler).
# Prod: structured JSON via ``config.observability.JSONFormatter`` so logs
# can be ingested by Loki/Cloudwatch/etc. without an extra dep (per دستور
# §2). The JSON schema is documented in config/observability.py.
#
# Per دستور §5: ``apps.accounts`` + ``apps.payments`` loggers emit at INFO
# so we can audit auth events + payment webhooks (when wired in Phase 7).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        # Used in dev (DEBUG=True)
        "simple": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
        # Used in prod (DEBUG=False) — JSON one-line-per-event
        "json": {
            "()": "config.observability.JSONFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json" if not DEBUG else "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        # Django framework — WARNING to keep migration noise out of prod.
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        # Django request logging — INFO is too noisy for prod; WARNING keeps
        # only the 4xx/5xx error responses in the log stream.
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        # PHINOX apps — INFO level so business events (otp.issued, order.placed,
        # payment.captured, etc.) reach the log stream per دستور §11.
        "apps": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps.accounts": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps.payments": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "config.health": {
            "handlers": ["console"],
            "level": "WARNING",  # health-check failures only — not successful pings
            "propagate": False,
        },
    },
}

# ---------------------------------------------------------------------------
# PAYMOB — Webhook Configuration (Phase 4)
# ---------------------------------------------------------------------------
# TODO: Fill these after completing Paymob onboarding.
#    See PAYMOB_SETUP.md for step-by-step instructions.
#
# Per دستور §5: webhook signature verification is MANDATORY before any
# Payment.status change. The PAYMOB_HMAC_SECRET is used by
# apps.payments.verification.verify_paymob_signature to verify the
# HMAC-SHA512 signature on incoming webhooks. If the secret is empty,
# the verification function returns False (no crash, no state change).
# ---------------------------------------------------------------------------

# Paymob HMAC secret — used to verify webhook signatures.
# Get it from: Paymob Dashboard -> Settings -> Account Info -> HMAC Secret
# Keep empty until you have the real value.
PAYMOB_HMAC_SECRET = env.str("PAYMOB_HMAC_SECRET", default="")  # noqa: F405

# Paymob API credentials — used for order/registration + payment_keys
# (Phase 4 Part 2 — the outbound API calls). Not needed for the webhook
# receiver itself, but wired here so Phase 4 Part 2 is a no-config change.
PAYMOB_API_KEY = env.str("PAYMOB_API_KEY", default="")  # noqa: F405
PAYMOB_INTEGRATION_ID = env.str("PAYMOB_INTEGRATION_ID", default="")  # noqa: F405
PAYMOB_IFRAME_ID = env.str("PAYMOB_IFRAME_ID", default="")  # noqa: F405
PAYMOB_SANDBOX = env.bool("PAYMOB_SANDBOX", default=True)  # noqa: F405

# Webhook URL to register in Paymob Dashboard.
# In production: https://phinox.example.com/payments/webhooks/paymob/
# In dev (ngrok): https://<ngrok-subdomain>.ngrok.io/payments/webhooks/paymob/
PAYMOB_WEBHOOK_URL = env.str(  # noqa: F405
    "PAYMOB_WEBHOOK_URL",
    default="http://localhost:8000/payments/webhooks/paymob/",
)

# ---------------------------------------------------------------------------
# Cost Control Flags (Phase: Google Free Tier — defaults = $0)
# ---------------------------------------------------------------------------
# These flags control which backend services are active. All default to
# the zero-cost local option. To enable Google Cloud free-tier
# alternatives, set the env var + uncomment the matching dep in
# requirements/prod.txt. See docs/DEPLOYMENT_MODES.md for the upgrade
# path.
# ---------------------------------------------------------------------------

# Payment processing mode. "simulation" = in-process test-mode (no real
# Paymob API calls). "sandbox" = Paymob sandbox API (real HTTP, test
# cards). "live" = production Paymob API.
#
# PHASE-A §A7: "simulation" is DEV-ONLY. config/settings/prod.py raises
# ImproperlyConfigured at import time if this value lands in production —
# simulation mode would otherwise let customers "confirm" orders without
# paying anything.
PAYMOB_MODE = env.str("PAYMOB_MODE", default="simulation")  # noqa: F405

# SMS delivery backend for OTP. "console" = print to stdout (dev only).
# "twilio" = Twilio API (requires SMS_TWILIO_* creds). "vonage" = Vonage API.
SMS_BACKEND = env.str("SMS_BACKEND", default="console")  # noqa: F405

# File storage backend. "local" = filesystem (MEDIA_ROOT). "gcs" = Google
# Cloud Storage. "s3" = S3-compatible (Hetzner Object Storage).
STORAGE_BACKEND = env.str("STORAGE_BACKEND", default="local")  # noqa: F405

# Cache backend. "locmem" = Django LocMemCache (in-process, no Redis
# needed). "redis" = django-redis (requires REDIS_URL).
CACHE_BACKEND = env.str("CACHE_BACKEND", default="locmem")  # noqa: F405

# Error tracking. "none" = no external error tracking. "sentry" = Sentry
# SDK (requires SENTRY_DSN). "gcp" = Google Cloud Error Reporting.
ERROR_TRACKING = env.str("ERROR_TRACKING", default="none")  # noqa: F405

# Email backend. "console" = print to stdout. "gmail" = Gmail SMTP
# (requires EMAIL_HOST_USER + EMAIL_HOST_PASSWORD).
EMAIL_BACKEND_MODE = env.str("EMAIL_BACKEND_MODE", default="console")  # noqa: F405

# Async task processing. False = run tasks synchronously (eager Celery or
# no Celery). True = use Celery + Redis broker.
USE_CELERY = env.bool("USE_CELERY", default=False)  # noqa: F405

# Google Cloud Tasks (alternative to Celery). False = disabled.
USE_CLOUD_TASKS = env.bool("USE_CLOUD_TASKS", default=False)  # noqa: F405

# Google Cloud project ID — used when STORAGE_BACKEND="gcs" or
# ERROR_TRACKING="gcp" or USE_CLOUD_TASKS=True.
GOOGLE_CLOUD_PROJECT = env.str("GOOGLE_CLOUD_PROJECT", default="")  # noqa: F405

# Path to Google service-account JSON key file.
GOOGLE_APPLICATION_CREDENTIALS = env.str("GOOGLE_APPLICATION_CREDENTIALS", default="")  # noqa: F405

# GCS bucket name for media files (when STORAGE_BACKEND="gcs").
GCS_BUCKET_NAME = env.str("GCS_BUCKET_NAME", default="")  # noqa: F405

# ---------------------------------------------------------------------------
# Google OAuth 2.0 (PHINOX-GOOGLE-OAUTH-MANUAL)
# ---------------------------------------------------------------------------
# Used for "Sign in with Google" on the login + register pages. Get these
# from Google Cloud Console → APIs & Services → Credentials → OAuth 2.0
# Client ID (type: Web application). The redirect URI must be added to the
# "Authorized redirect URIs" list in the Console.
#
# When empty (default), the Google sign-in button is hidden on login/register
# (per PHINOX-GOOGLE-OAUTH-MANUAL spec: "if GOOGLE_CLIENT_ID is not set, the
# button doesn't render"). The OAuth views return 404 if called without
# configuration.
GOOGLE_CLIENT_ID = env.str("GOOGLE_CLIENT_ID", default="")  # noqa: F405
# Per دستور §5: client_secret is sensitive — never logged. The
# JSONFormatter's PII scrub also masks it if it ends up in a log record.
GOOGLE_CLIENT_SECRET = env.str("GOOGLE_CLIENT_SECRET", default="")  # noqa: F405
# The callback URL. Must match what's registered in Google Cloud Console.
GOOGLE_REDIRECT_URI = env.str(  # noqa: F405
    "GOOGLE_REDIRECT_URI",
    default="http://localhost:8000/accounts/google/callback/",
)
