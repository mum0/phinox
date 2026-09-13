"""
apps.payments.services — payment creation + status updates + Paymob bridge.

Phase 4 Part 2 (Bridge Fix): ``initialize_paymob_payment`` connects the
``PaymobClient`` (outbound API) to the ``Payment`` model. When
``PAYMOB_MODE`` is ``"simulation"`` it raises ``PaymobDisabledError`` so the
view falls back to the test-mode simulation flow.

Per دستور §5: COD is live; card/online payments are TEST MODE ONLY when
``PAYMOB_MODE == "simulation"``. In ``"sandbox"`` or ``"live"`` mode, real
Paymob API calls are made.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.orders.models import Order
from apps.payments.models import Payment, PaymentStatusChange

logger = logging.getLogger(__name__)


class PaymobDisabledError(Exception):
    """Raised when Paymob is not enabled (PAYMOB_MODE == 'simulation').

    The calling view should fall back to the test-mode simulation flow.
    """


def create_cod_payment(order: Order) -> Payment:
    """Create a Cash-on-Delivery Payment for ``order``.

    COD payments start in status='pending' (the cash is collected on
    delivery, not at order time).

    Args:
        order: The order to create the COD payment for.

    Returns:
        The created Payment instance.

    Raises:
        ValueError: If ``order.grand_total`` is not positive.
    """
    if order.grand_total <= 0:
        raise ValueError("order.grand_total must be > 0 to create a payment.")

    with transaction.atomic():
        return Payment.objects.create(
            order=order,
            payment_provider=Payment.PaymentProvider.COD,
            method_type=Payment.MethodType.COD,
            amount=order.grand_total,
            currency=order.currency,
            status=Payment.Status.PENDING,
        )


def simulate_card_payment(
    order: Order,
    *,
    simulate_success: bool = True,
) -> Payment:
    """TEST MODE ONLY — simulate a card payment via Paymob.

    No real Paymob API call is made. A Payment row is created with
    ``is_test_transaction=True``.

    Args:
        order: The order to simulate payment for.
        simulate_success: If True (default) the simulated payment succeeds.

    Returns:
        The created Payment instance.
    """
    if order.grand_total <= 0:
        raise ValueError("order.grand_total must be > 0 to create a payment.")

    txn_id = f"TEST-{uuid.uuid4().hex[:24]}"

    with transaction.atomic():
        if simulate_success:
            payment = Payment.objects.create(
                order=order,
                payment_provider=Payment.PaymentProvider.PAYMOB,
                method_type=Payment.MethodType.CARD,
                provider_transaction_id=txn_id,
                amount=order.grand_total,
                currency=order.currency,
                status=Payment.Status.PAID,
                is_test_transaction=True,
                paid_at=timezone.now(),
            )
        else:
            payment = Payment.objects.create(
                order=order,
                payment_provider=Payment.PaymentProvider.PAYMOB,
                method_type=Payment.MethodType.CARD,
                provider_transaction_id=txn_id,
                amount=order.grand_total,
                currency=order.currency,
                status=Payment.Status.FAILED,
                is_test_transaction=True,
                failure_reason="Simulated failure (test mode).",
            )
        return payment


def update_payment_status(
    payment: Payment,
    status: str,
    paid_at: Optional[datetime] = None,
    *,
    changed_by=None,
    reason: str = "",
) -> Payment:
    """Update a Payment's status, setting paid_at automatically when 'paid'.

    PHASE-D §D6: writes a PaymentStatusChange audit row in the SAME
    transaction as the Payment update, so the audit log is always in
    sync with the Payment state.

    Args:
        payment: The Payment to update.
        status: One of Payment.Status values.
        paid_at: Optional explicit timestamp.
        changed_by: Optional User instance (the actor). Null for webhook-
            triggered changes (Paymob doesn't have a Django user).
        reason: Short human-readable note for the audit log (e.g.
            "Paymob webhook captured", "COD manual capture by admin").

    Returns:
        The updated Payment (reloaded from DB).

    Raises:
        ValueError: If ``status`` is not a valid Payment.Status.
    """
    valid_statuses = {c for c, _ in Payment.Status.choices}
    if status not in valid_statuses:
        raise ValueError(
            f"status must be one of {sorted(valid_statuses)}, got {status!r}."
        )

    with transaction.atomic():
        old_status = payment.status
        payment.status = status
        if status == Payment.Status.PAID and paid_at is None:
            paid_at = timezone.now()
        if paid_at is not None:
            payment.paid_at = paid_at
        payment.save(update_fields=["status", "paid_at", "updated_at"])

        # PHASE-D §D6: write the audit-log row in the same transaction.
        # Skip if the status didn't actually change (idempotent no-op).
        if old_status != status:
            PaymentStatusChange.objects.create(
                payment=payment,
                old_status=old_status,
                new_status=status,
                changed_by=changed_by,
                reason=reason or f"{old_status} → {status}",
            )

        payment.refresh_from_db()
        return payment


# ---------------------------------------------------------------------------
# Phase 4 Part 2 — Paymob integration bridge
# ---------------------------------------------------------------------------
def initialize_paymob_payment(order: Order) -> tuple[Payment, str]:
    """Initialize a real Paymob card payment for ``order``.

    Steps:
      1. If ``PAYMOB_MODE == "simulation"`` → raise ``PaymobDisabledError``.
      2. Create a ``Payment`` row with ``status=PENDING``, ``provider=CARD``.
      3. Call ``PaymobClient.register_order()`` → ``paymob_order_id``.
      4. Store ``paymob_order_id`` in ``payment.provider_transaction_id``
         (used as the unique key — Paymob guarantees uniqueness).
      5. Call ``PaymobClient.get_payment_key()`` → ``payment_token``.
      6. Build the iframe URL via ``PaymobClient.build_iframe_url()``.
      7. Return ``(payment, iframe_url)``.

    The caller (``PaymentSimulationView.post``) redirects the user to the
    iframe URL. After payment, Paymob sends a webhook (handled by
    ``views_webhook.paymob_webhook``) which updates ``Payment.status``.

    Per دستور §5: transaction.atomic() wraps the Payment creation +
    Paymob order registration so a partial write never persists.

    Args:
        order: The Order to create the payment for.

    Returns:
        A tuple ``(payment, iframe_url)``.

    Raises:
        PaymobDisabledError: If ``PAYMOB_MODE == "simulation"``.
        PaymobAPIError: If a Paymob API call fails.
        ValueError: If ``order.grand_total`` is not positive.
    """
    from apps.payments.paymob_client import PaymobAPIError, PaymobClient

    paymob_mode = getattr(settings, "PAYMOB_MODE", "simulation")
    if paymob_mode == "simulation":
        raise PaymobDisabledError(
            "Paymob is in simulation mode. Set PAYMOB_MODE=sandbox or live "
            "to enable real card payments."
        )

    if order.grand_total <= 0:
        raise ValueError("order.grand_total must be > 0 to create a payment.")

    api_key = getattr(settings, "PAYMOB_API_KEY", "")
    integration_id = getattr(settings, "PAYMOB_INTEGRATION_ID", "")
    iframe_id = getattr(settings, "PAYMOB_IFRAME_ID", "")
    sandbox = getattr(settings, "PAYMOB_SANDBOX", True)

    client = PaymobClient(
        api_key=api_key,
        integration_id=integration_id,
        iframe_id=iframe_id,
        sandbox=sandbox,
    )

    amount_cents = PaymobClient.decimal_to_cents(order.grand_total)

    with transaction.atomic():
        # 2. Create the pending Payment row.
        payment = Payment.objects.create(
            order=order,
            payment_provider=Payment.PaymentProvider.PAYMOB,
            method_type=Payment.MethodType.CARD,
            amount=order.grand_total,
            currency=order.currency,
            status=Payment.Status.PENDING,
            is_test_transaction=(paymob_mode == "sandbox"),
        )

        # 3. Register the order in Paymob.
        paymob_order_id = client.register_order(
            merchant_order_id=order.business_id,
            amount_cents=amount_cents,
            currency=order.currency,
        )

        # 4. PHASE-A §A4: store paymob_order_id in the dedicated field.
        # Previously this stored the order_id in ``provider_transaction_id``,
        # which the webhook then tried to match against the webhook's
        # ``transaction_id`` (``obj.id``) — but those are different values.
        # The webhook now looks up by ``paymob_order_id`` (matching
        # ``obj.order.id`` in the payload) and populates
        # ``provider_transaction_id`` with the transaction ID after capture.
        payment.paymob_order_id = str(paymob_order_id)
        payment.save(update_fields=["paymob_order_id", "updated_at"])

    # 5. Get payment key (outside the atomic block — it's an API call, not a DB write).
    billing_data = _build_billing_data(order)
    payment_token = client.get_payment_key(
        paymob_order_id=paymob_order_id,
        amount_cents=amount_cents,
        billing_data=billing_data,
        currency=order.currency,
    )

    # 6. Build the iframe URL.
    iframe_url = client.build_iframe_url(payment_token)

    logger.info(
        "payment.paymob.initialized",
        extra={
            "payment_id": payment.business_id,
            "order_id": order.business_id,
            "paymob_order_id": paymob_order_id,
            "mode": paymob_mode,
        },
    )
    return payment, iframe_url


def _build_billing_data(order: Order) -> dict[str, str]:
    """Build the ``billing_data`` dict Paymob requires for payment_keys.

    Paymob requires at minimum: first_name, last_name, email, phone_number.
    Falls back to placeholder values if the order has no user or the user
    has no email/phone (per دستور §5 — never crash the payment flow).

    Args:
        order: The Order to build billing data for.

    Returns:
        Dict with the 4 required fields + optional building/street/etc.
    """
    user = getattr(order, "user", None)
    email = getattr(user, "email", "") if user else ""
    phone = getattr(user, "phone", "") if user else ""
    first_name = getattr(user, "first_name", "") if user else ""
    last_name = getattr(user, "last_name", "") if user else ""

    return {
        "first_name": first_name or "PHINOX",
        "last_name": last_name or "Customer",
        "email": email or "no-reply@phinox.example",
        "phone_number": phone or "+201000000000",
        "building": "N/A",
        "street": "N/A",
        "city": "Alexandria",
        "country": "EG",
        "state": "Alexandria",
        "apartment": "N/A",
        "floor": "N/A",
    }
