"""
AttributionMiddleware — captures UTM parameters + QR codes from incoming
requests and stores them in the session for later attribution tracking.

Runs BEFORE view middleware so all views have access to session attribution.

Wiring (config/settings/base.py — to be added when this app's phase is
greenlit per AGENTS.md §0.3 phase discipline)::

    MIDDLEWARE = [
        ...
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        ...
        # After SessionMiddleware + AuthenticationMiddleware so the session
        # is available. Before any view-level middleware so every view sees
        # ``request.attribution``.
        "apps.analytics.middleware.AttributionMiddleware",
    ]

Behaviour per request:
  1. Read ``utm_*`` / ``qr_code`` query params from ``request.GET``.
  2. If any are present, ensure a session exists (saving one if needed so
     we have a ``session_key``), then call ``capture_attribution()`` to
     upsert the Attribution row (last-touch wins per services.py).
  3. Always attach the session's Attribution (or ``None``) to
     ``request.attribution`` so views don't have to re-query.
  4. Delegate to ``get_response`` and return the response unchanged.

Errors from ``capture_attribution`` (e.g. ValueError on bad input) are
swallowed — attribution is observability, never a reason to break a
customer's request.
"""
from __future__ import annotations

from apps.analytics.models import Attribution
from apps.analytics.services import capture_attribution


# Allowed UTM keys — must match ``apps.analytics.services._UTM_KEYS``.
# Duplicated here (rather than imported) so this module has no dependency
# on a private symbol of services.py.
_UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")


class AttributionMiddleware:
    """Capture marketing attribution (UTM + QR) on every incoming request.

    Adds ``request.attribution: Attribution | None`` for downstream views.
    """

    def __init__(self, get_response):
        """Standard Django middleware constructor.

        Args:
            get_response: The next middleware / view in the chain. Stored
                and called in ``__call__``.
        """
        self.get_response = get_response

    def __call__(self, request):
        # SessionMiddleware guarantees ``request.session`` exists, but the
        # session_key is None until the session is saved. Capture it lazily.
        session_key = request.session.session_key

        # Collect any UTM / QR params present on this request. Unknown
        # query keys are ignored; capture_attribution() will sanitize
        # further (only known UTM keys are persisted).
        utm_data = {
            key: request.GET[key]
            for key in _UTM_KEYS
            if key in request.GET
        }
        qr_code = request.GET.get("qr_code", "")

        if utm_data or qr_code:
            # We have attribution data to persist. Ensure a session exists
            # so we have a stable session_key to attach it to.
            if not session_key:
                request.session.save()
                session_key = request.session.session_key
            try:
                capture_attribution(
                    session_key=session_key,
                    utm_data=utm_data,
                    qr_code=qr_code,
                )
            except ValueError:
                # Invalid input — silently skip. Attribution is observability
                # and must never break a customer's request.
                pass

        # Always expose the session's Attribution (or None) on the request
        # so views / templates don't have to re-query.
        if session_key:
            request.attribution = (
                Attribution.objects
                .filter(session_key=session_key)
                .first()
            )
        else:
            request.attribution = None

        response = self.get_response(request)
        return response

    def process_template_response(self, request, response):
        """Make ``request.attribution`` available to template responses.

        Optional hook — DRF / regular TemplateResponse flows don't carry
        the request's attribution by default. We attach it to the context
        if it's missing so templates can use ``{{ attribution }}`` without
        each view having to wire it manually.
        """
        if hasattr(response, "context_data") and response.context_data is not None:
            response.context_data.setdefault(
                "attribution", getattr(request, "attribution", None)
            )
        return response
