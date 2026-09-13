"""apps.core.utils — Phase: Google Free Tier cost-control utilities.

App: ``apps.core``.
Phase: Google Free Tier (cost-control flags).
Scope: helper functions that read the cost-control env flags (set in
       ``config/settings/base.py``) and return the active backend choice.
       Each function logs a WARNING if production is running with a
       simulation/local backend.
Not in scope: the actual backend wiring (Django's STORAGES / CACHES /
  LOGGING dicts in base.py read these helpers lazily — currently the
  flags are informational; the settings modules override the concrete
  backends directly).

Per دستور §2: no new deps. These functions only read ``settings`` +
``logging`` (both stdlib/Django built-ins).
"""
from __future__ import annotations

import logging
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)


def _is_production() -> bool:
    """True if the active settings module is prod."""
    return "prod" in getattr(settings, "SETTINGS_MODULE", "")


def _warn_if_prod_with_simulation(backend_name: str, value: str) -> None:
    """Log a WARNING if production is running with a simulation/local backend.

    Args:
        backend_name: human-readable label (e.g. "PAYMOB_MODE").
        value: the current value (e.g. "simulation").
    """
    if _is_production() and value in ("simulation", "console", "local", "locmem", "none"):
        logger.warning(
            "cost_control.prod_with_free_tier",
            extra={"backend": backend_name, "value": value},
        )


def get_error_tracker() -> str:
    """Return the active error-tracking backend.

    Returns one of: ``"none"``, ``"sentry"``, ``"gcp"``.
    Reads ``settings.ERROR_TRACKING`` (default: ``"none"``).
    """
    value = getattr(settings, "ERROR_TRACKING", "none")
    _warn_if_prod_with_simulation("ERROR_TRACKING", value)
    return value


def get_storage_backend() -> str:
    """Return the active file-storage backend.

    Returns one of: ``"local"``, ``"gcs"``, ``"s3"``.
    Reads ``settings.STORAGE_BACKEND`` (default: ``"local"``).
    """
    value = getattr(settings, "STORAGE_BACKEND", "local")
    _warn_if_prod_with_simulation("STORAGE_BACKEND", value)
    return value


def get_cache_backend() -> str:
    """Return the active cache backend.

    Returns one of: ``"locmem"``, ``"redis"``.
    Reads ``settings.CACHE_BACKEND`` (default: ``"locmem"``).
    """
    value = getattr(settings, "CACHE_BACKEND", "locmem")
    _warn_if_prod_with_simulation("CACHE_BACKEND", value)
    return value


def get_email_backend() -> str:
    """Return the active email backend mode.

    Returns one of: ``"console"``, ``"gmail"``.
    Reads ``settings.EMAIL_BACKEND_MODE`` (default: ``"console"``).
    """
    value = getattr(settings, "EMAIL_BACKEND_MODE", "console")
    _warn_if_prod_with_simulation("EMAIL_BACKEND_MODE", value)
    return value


def get_paymob_mode() -> str:
    """Return the active Paymob processing mode.

    Returns one of: ``"simulation"``, ``"sandbox"``, ``"live"``.
    Reads ``settings.PAYMOB_MODE`` (default: ``"simulation"``).
    """
    value = getattr(settings, "PAYMOB_MODE", "simulation")
    _warn_if_prod_with_simulation("PAYMOB_MODE", value)
    return value


def get_sms_backend() -> str:
    """Return the active SMS delivery backend.

    Returns one of: ``"console"``, ``"twilio"``, ``"vonage"``.
    Reads ``settings.SMS_BACKEND`` (default: ``"console"``).
    """
    value = getattr(settings, "SMS_BACKEND", "console")
    _warn_if_prod_with_simulation("SMS_BACKEND", value)
    return value
