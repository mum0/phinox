"""
apps.payments.views — Payment simulation + Paymob iframe redirect.

Phase 4 Part 2 (Bridge Fix): When ``PAYMOB_MODE`` is ``"sandbox"`` or
``"live"``, the POST handler calls ``initialize_paymob_payment()`` which
creates a real Paymob order + payment key, then redirects the user to
Paymob's iframe. When ``PAYMOB_MODE == "simulation"`` (default), the
view falls back to the test-mode simulation flow (no real API calls).

Per دستور §5: card payments are TEST MODE ONLY when PAYMOB_MODE=simulation.
"""
from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views import View

from apps.orders.models import Order
from apps.orders.services import update_order_status
from apps.payments.services import (
    PaymobDisabledError,
    initialize_paymob_payment,
    simulate_card_payment,
)

logger = logging.getLogger(__name__)

_FAILURE_TRUTHY = {"1", "true", "on", "yes"}


@method_decorator(login_required, name="dispatch")
class PaymentSimulationView(View):
    """Payment view — simulation or real Paymob iframe redirect.

    GET: renders the payment form page with a TEST MODE banner when
    ``PAYMOB_MODE == "simulation"``. In sandbox/live mode, it still
    renders the same page (the form is cosmetic — the real redirect
    happens on POST).

    POST:
      - If ``PAYMOB_MODE == "simulation"`` (default): simulate the
        payment via ``simulate_card_payment()`` — no real API calls.
      - If ``PAYMOB_MODE in ("sandbox", "live")``: call
        ``initialize_paymob_payment()`` → redirect to Paymob iframe URL.
        The webhook (``paymob_webhook``) handles the post-payment update.
    """

    template_name = "payments/payment_test.html"

    def get(self, request, order_business_id: str) -> HttpResponse:
        """Render the payment form with TEST MODE banner (if simulation)."""
        order = self._get_order(request, order_business_id)
        from django.conf import settings
        paymob_mode = getattr(settings, "PAYMOB_MODE", "simulation")
        context = {
            "order": order,
            "test_mode": paymob_mode == "simulation",
            "paymob_mode": paymob_mode,
        }
        return render(request, self.template_name, context)

    def post(self, request, order_business_id: str) -> HttpResponse:
        """Process the payment — simulation or real Paymob redirect."""
        order = self._get_order(request, order_business_id)

        from django.conf import settings
        paymob_mode = getattr(settings, "PAYMOB_MODE", "simulation")

        if paymob_mode == "simulation":
            # ── Simulation mode: no real Paymob API calls ───────────────
            return self._handle_simulation(request, order)
        else:
            # ── Sandbox/Live mode: redirect to Paymob iframe ───────────
            return self._handle_real_paymob(request, order)

    def _handle_simulation(self, request, order: Order) -> HttpResponse:
        """Simulation flow — no real Paymob API calls."""
        simulate_failure = (
            (request.POST.get("simulate_failure") or "").strip().lower()
            in _FAILURE_TRUTHY
        )
        payment = simulate_card_payment(order, simulate_success=not simulate_failure)

        if payment.status == payment.Status.PAID:
            order.payment_status = Order.PaymentStatus.PAID
            order.save(update_fields=["payment_status", "updated_at"])
            try:
                update_order_status(order, Order.Status.CONFIRMED)
            except ValueError:
                pass
            messages.success(
                request,
                f"TEST PAYMENT SUCCESS — order {order.business_id} confirmed. "
                "(No real payment was processed.)",
            )
        else:
            order.payment_status = Order.PaymentStatus.FAILED
            order.save(update_fields=["payment_status", "updated_at"])
            messages.error(
                request,
                f"TEST PAYMENT FAILED for order {order.business_id}. "
                "(No real payment was processed.)",
            )
        return redirect("orders:confirmation", business_id=order.business_id)

    def _handle_real_paymob(self, request, order: Order) -> HttpResponse:
        """Real Paymob flow — create order + redirect to iframe."""
        try:
            payment, iframe_url = initialize_paymob_payment(order)
            logger.info(
                "payment.redirect_to_iframe",
                extra={
                    "order_id": order.business_id,
                    "payment_id": payment.business_id,
                    "iframe_url_host": iframe_url.split("?")[0],
                },
            )
            return redirect(iframe_url)
        except PaymobDisabledError:
            # Shouldn't happen (we checked mode above) but be defensive.
            messages.error(request, "Paymob is not enabled. Please contact support.")
            return redirect("orders:confirmation", business_id=order.business_id)
        except Exception as exc:
            logger.error(
                "payment.paymob_init_error",
                extra={
                    "order_id": order.business_id,
                    "error_type": type(exc).__name__,
                    "error_msg": str(exc)[:200],
                },
                exc_info=True,
            )
            messages.error(
                request,
                f"Payment initialization failed: {type(exc).__name__}. "
                "Please try again or contact support."
            )
            return redirect("orders:confirmation", business_id=order.business_id)

    def _get_order(self, request, order_business_id: str) -> Order:
        """Fetch the order by ``business_id``, restricted to owner-or-staff."""
        qs = Order.objects.all()
        if not request.user.is_staff:
            qs = qs.filter(user=request.user)
        return get_object_or_404(qs, business_id=order_business_id)
