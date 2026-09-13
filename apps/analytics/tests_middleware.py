"""
apps.analytics.tests_middleware — Phase 3 tests for AttributionMiddleware.

Covers the marketing-attribution capture contract (دستور §8/§10):
  - ?utm_source=... (and friends) → Attribution row created
  - ?qr_code=...                   → Attribution row created with qr_code
  - no UTM / no QR                 → no Attribution row created
  - same session_key across hits   → one Attribution, updated (not duplicated)

The middleware is wired in config/settings/base.py as
``apps.analytics.middleware.AttributionMiddleware``, placed immediately
after ``AuthenticationMiddleware`` (so ``request.session`` is available).

Two test strategies are exercised:

1. End-to-end via the Django test client hitting the home page ``/`` —
   this exercises the full middleware stack including SessionMiddleware.
2. Isolated unit-style calls using ``RequestFactory`` + a hand-attached
   session — for cases where we want to assert the middleware's behaviour
   without depending on the public URL routing.

NOTE: this file requires ``apps.analytics.middleware`` to exist (created
by the parallel "views + templates" agent in this phase). Until that
module lands, importing this test file will fail — that's intentional,
it surfaces an unfinished dependency rather than silently passing.
"""
from django.test import RequestFactory, TestCase
from django.contrib.sessions.backends.db import SessionStore

from apps.analytics.middleware import AttributionMiddleware
from apps.analytics.models import Attribution


def _attach_session(request, *, session_key: str | None = None) -> str:
    """Attach a fresh SessionStore to ``request`` and force-save it.

    RequestFactory requests don't carry a session; we synthesize one so
    the middleware can read ``request.session.session_key``.
    """
    session = SessionStore(session_key=session_key) if session_key else SessionStore()
    # Force the session to be saved so a session_key is materialised.
    session["_seed"] = "phinox-mw-test"
    session.save()
    request.session = session
    return session.session_key


def _ok_response(request):
    """Minimal get_response callable used to instantiate the middleware."""
    from django.http import HttpResponse

    return HttpResponse("ok")


# ===========================================================================
# AttributionMiddleware
# ===========================================================================
class AttributionMiddlewareTest(TestCase):
    """Captures UTM + QR attribution on inbound requests, last-touch wins."""

    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.middleware = AttributionMiddleware(_ok_response)

    # ------------------------------------------------------------------
    # UTM
    # ------------------------------------------------------------------
    def test_utm_params_captured(self) -> None:
        """?utm_source=google (and friends) → Attribution row created."""
        request = self.factory.get(
            "/?utm_source=google&utm_medium=cpc&utm_campaign=winter"
        )
        session_key = _attach_session(request)

        # Run the middleware end-to-end.
        response = self.middleware(request)

        # The downstream response is returned untouched.
        self.assertEqual(response.status_code, 200)

        # An Attribution row was created for this session with the UTM fields.
        attr = Attribution.objects.get(session_key=session_key)
        self.assertEqual(attr.utm_source, "google")
        self.assertEqual(attr.utm_medium, "cpc")
        self.assertEqual(attr.utm_campaign, "winter")

    # ------------------------------------------------------------------
    # QR
    # ------------------------------------------------------------------
    def test_qr_code_captured(self) -> None:
        """?qr_code=POSTER01 → Attribution row created with qr_code."""
        request = self.factory.get("/?qr_code=POSTER01")
        session_key = _attach_session(request)

        self.middleware(request)

        attr = Attribution.objects.get(session_key=session_key)
        self.assertEqual(attr.qr_code, "POSTER01")

    # ------------------------------------------------------------------
    # No-op when no attribution params
    # ------------------------------------------------------------------
    def test_no_utm_no_attribution(self) -> None:
        """A request with no UTM/QR params creates no Attribution row."""
        request = self.factory.get("/")
        _attach_session(request)

        self.middleware(request)

        self.assertEqual(
            Attribution.objects.count(),
            0,
            "no Attribution should be created when no UTM/QR params are present",
        )

    # ------------------------------------------------------------------
    # Session-key linkage / last-touch update
    # ------------------------------------------------------------------
    def test_attribution_linked_to_session(self) -> None:
        """Same session_key across two hits → one Attribution, updated.

        ``capture_attribution`` uses ``update_or_create`` so a returning
        session should NOT spawn a duplicate row — its existing Attribution
        should be updated with the latest UTM values (last-touch wins).
        """
        # First hit: arrives via google cpc.
        request1 = self.factory.get("/?utm_source=google&utm_medium=cpc")
        session_key = _attach_session(request1)
        self.middleware(request1)
        self.assertEqual(Attribution.objects.count(), 1)

        # Second hit: same session arrives via instagram social.
        request2 = self.factory.get(
            "/?utm_source=instagram&utm_medium=social"
        )
        # Reuse the SAME session_key — the session has been seen before.
        _attach_session(request2, session_key=session_key)
        self.middleware(request2)

        # Still exactly one Attribution row for this session.
        self.assertEqual(
            Attribution.objects.filter(session_key=session_key).count(),
            1,
            "returning session must update the existing Attribution, not create a new one",
        )
        attr = Attribution.objects.get(session_key=session_key)
        # Last-touch wins: source/medium reflect the most recent hit.
        self.assertEqual(attr.utm_source, "instagram")
        self.assertEqual(attr.utm_medium, "social")
