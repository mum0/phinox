"""
apps.analytics.context_processors — GA4 template context.

Exposes ``GA4_MEASUREMENT_ID`` to templates so the gtag.js snippet in
``templates/analytics/ga4.html`` renders only when GA4 is configured.

Wiring (config/settings/base.py TEMPLATES OPTIONS context_processors)::

    "context_processors": [
        ...
        "apps.analytics.context_processors.ga4_settings",
    ],
"""
from __future__ import annotations

from django.conf import settings


def ga4_settings(request) -> dict[str, str]:
    """Expose GA4 config to templates.

    Returns a dict with a single key ``ga4_measurement_id`` — the value
    of ``settings.GA4_MEASUREMENT_ID`` (or empty string if unset). The
    gtag.js snippet in ``templates/analytics/ga4.html`` is rendered only
    when this value is truthy.

    Args:
        request: The current HttpRequest (unused — present for the
            Django context-processor contract).

    Returns:
        ``{"ga4_measurement_id": "<id or empty>"}``.
    """
    return {
        "ga4_measurement_id": getattr(settings, "GA4_MEASUREMENT_ID", "") or "",
    }
