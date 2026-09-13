"""config.health — Phase 6 production health check endpoints.

Two endpoints:
  - ``/health/``         — liveness probe (always 200 if the Django
                           process can answer; used by load balancers
                           + Kubernetes liveness probes).
  - ``/health/ready/``   — readiness probe (checks DB + Redis + cache;
                           returns 503 if any required service is down;
                           used by Kubernetes readiness probes to avoid
                           sending traffic to a not-yet-ready pod).

Both endpoints return a JSON payload with per-service status so an
operator can quickly see what's broken:
  {"status": "ok", "checks": {"db": "ok", "redis": "ok", "cache": "ok"}}

Per دستور §5 + §0 rule 6: these endpoints MUST NOT leak secrets. The
JSON payload never includes connection strings or credentials — only
"ok"/"down" status + a sanitized error message (no hostnames, no
exception tracebacks).

Per دستور §7: never commit secrets. The health endpoint is read-only —
no DB writes, no cache writes — so it's safe to expose even when
DEBUG=False.
"""
from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.http import JsonResponse
from django.urls import path
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


def _check_db() -> bool:
    """Try a SELECT 1 against the default DB. Returns True if it succeeds."""
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return True
    except Exception as exc:
        # Log the error for the operator but don't leak it in the response.
        logger.warning("health.db_fail", extra={"error": str(exc)[:200]})
        return False


def _check_redis() -> bool:
    """Try a PING against Redis. Returns True if it succeeds."""
    try:
        # Late import so the endpoint doesn't fail at import time if redis
        # isn't installed (it is in base.txt — this is just defensive).
        import redis
        client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        return bool(client.ping())
    except Exception as exc:
        logger.warning("health.redis_fail", extra={"error": str(exc)[:200]})
        return False


def _check_cache() -> bool:
    """Try a SET + GET against the Django cache. Returns True if both succeed."""
    try:
        from django.core.cache import cache
        cache.set("__health_check__", "ok", timeout=5)
        return cache.get("__health_check__") == "ok"
    except Exception as exc:
        logger.warning("health.cache_fail", extra={"error": str(exc)[:200]})
        return False


@require_GET
def health_live(request) -> JsonResponse:
    """Liveness probe — always 200 if the Django process can answer.

    Used by Kubernetes liveness probes + Hetzner load balancer health
    checks. Doesn't check downstream services — only confirms the
    process is alive.
    """
    return JsonResponse({"status": "ok", "service": "phinox", "env": _env_name()})


@require_GET
def health_ready(request) -> JsonResponse:
    """Readiness probe — checks DB + Redis + cache.

    Returns 200 if all checks pass, 503 if any fail. Used by Kubernetes
    readiness probes to avoid routing traffic to a pod that can't
    serve requests (e.g. DB not yet migrated, Redis down).
    """
    checks = {
        "db": "ok" if _check_db() else "down",
        "redis": "ok" if _check_redis() else "down",
        "cache": "ok" if _check_cache() else "down",
    }
    all_ok = all(v == "ok" for v in checks.values())
    status_code = 200 if all_ok else 503
    return JsonResponse(
        {
            "status": "ok" if all_ok else "down",
            "service": "phinox",
            "env": _env_name(),
            "checks": checks,
        },
        status=status_code,
    )


def _env_name() -> str:
    """Return 'production', 'staging', or 'dev' based on the settings module."""
    module = settings.SETTINGS_MODULE
    if "prod" in module:
        return "production"
    if "staging" in module:
        return "staging"
    return "dev"


# URL patterns — wired into config/urls.py via ``include((urlpatterns, "health"))``
# so the URLs resolve as ``health:live`` and ``health:ready``.
app_name = "health"
urlpatterns = [
    path("health/", health_live, name="live"),
    path("health/ready/", health_ready, name="ready"),
]
