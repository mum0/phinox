"""URL config for apps.payments.

Routes:
  - test/<order_business_id>/ → PaymentSimulationView (TEST MODE ONLY)
  - webhooks/paymob/         → paymob_webhook (Phase 4 — real Paymob webhook)

Per دستور §5: the webhook endpoint is ``@csrf_exempt`` because Paymob
authenticates via HMAC-SHA512, not via a Django CSRF token. The ``@require_POST``
decorator (in the view) rejects non-POST methods.

The webhook URL is registered in the Paymob Dashboard → Settings → Webhooks
as ``https://<domain>/payments/webhooks/paymob/``.
"""
from django.urls import path

from .views import PaymentSimulationView
from .views_webhook import paymob_webhook

app_name = "payments"

urlpatterns = [
    path(
        "test/<str:order_business_id>/",
        PaymentSimulationView.as_view(),
        name="test_payment",
    ),
    # Phase 4 — Paymob webhook receiver (real payment capture).
    path(
        "webhooks/paymob/",
        paymob_webhook,
        name="paymob_webhook",
    ),
]
