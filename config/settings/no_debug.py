"""No-debug settings — used only for capturing the Stitch 404 screenshot
and for ``manage.py check --deploy`` in CI.

Same as staging/prod (DEBUG=False so Django uses the custom 404 handler
instead of the debug 404 with URL pattern listing), but with the
security hardening disabled so plain HTTP localhost works for the
screenshot capture. NOT for production — production uses prod.py.

Phase 6 STITCH-INTEGRATION: aligned with prod.py's security hardening
so ``manage.py check --deploy`` shows realistic warnings (rather than
the W004/W008/W012/W016 noise from a stripped no_debug setup).

The STORAGES dict comes from base.py (Django 5.0 style). The staticfiles
backend is overridden to plain StaticFilesStorage (no manifest hashing —
simpler for the 404 screenshot which uses raw static paths).
"""
from .base import *  # noqa: F401,F403

DEBUG = False
ALLOWED_HOSTS = ["*"]

# Bypass SSL redirect + cookie security for local screenshot capture
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# Override the staticfiles backend to non-manifest (simpler for the 404
# screenshot — no hash-suffixed paths).
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# Console email backend (same as dev)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
