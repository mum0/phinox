"""apps.payments.views_webhook — Paymob webhook receiver view.

App: ``apps.payments``.
Phase: 4 (Paymob Webhook — the final barrier to commercial launch).
Scope: HTTP endpoint that receives Paymob transaction webhooks, verifies
       the HMAC-SHA512 signature, updates ``Payment.status`` + ``Order.status``
       + inventory, and sends the payment confirmation email.
Not in scope: Paymob outbound API calls (order/registration, payment_keys,
  iframe redirect). Those are Phase 4 Part 2 (a future task).

PHASE-A §A4 + §A5 — webhook hardening:
  - §A4 fix 1: ``select_for_update()`` is now called INSIDE
    ``transaction.atomic()`` (the previous code called it outside any
    transaction, which was a no-op on SQLite + a programming error on
    Postgres — the lock was never held).
  - §A4 fix 2: Payment lookup is now by ``paymob_order_id`` (extracted
    from ``obj.order.id`` in the payload), NOT by ``provider_transaction_id``.
    ``initialize_paymob_payment`` stores the Paymob order ID in
    ``payment.paymob_order_id`` at payment initialization time. The
    transaction ID (``obj.id``) is different from the order ID and is
    stored in ``provider_transaction_id`` AFTER the webhook updates the
    Payment (for downstream idempotency + audit).
  - §A5: test transactions (``payment.is_test_transaction=True``) are
    detected early + return ``{"status": "test_ignored"}`` with no state
    change — test-mode payments never decrement real inventory or
    transition real orders.

Per دستور §5 (Payments):
  - **Signature verification is MANDATORY** before any ``Payment.status``
    change. No verification → no state change, full stop.
  - **Idempotency**: every webhook handler must be idempotent. Receiving
    the same webhook twice must not double-decrement inventory.
  - **COD has no webhook** — its "capture" is manual. If a COD webhook
    somehow arrives, ignore it (return 200 but do nothing).
  - **Never log card numbers or PII** — the ``scrub_pii_before_send``
    hook in ``config.observability.py`` masks card PANs + phones + OTPs
    before any Sentry event leaves the process.

Per دستور §6 (DB):
  - ``transaction.atomic()`` for the entire multi-write (Payment update +
    Order update + Inventory decrement + email send). If any step fails,
    all roll back.
  - ``select_for_update()`` on the Payment row to prevent race conditions
    (two concurrent webhooks for the same transaction).

Webhook flow:
  1. Read raw body bytes (``request.body``) — do NOT use ``request.POST``
     (Paymob sends JSON, not form-encoded).
  2. Extract the signature from the ``SHA512`` query param OR the
     ``X-Paymob-Signature`` header.
  3. Verify the signature via ``verify_paymob_signature()``. If invalid
     or secret not configured → return 403 (per دستور §5 — no state
     change without verification).
  4. Parse the payload to extract the Paymob transaction ID (``obj.id``)
     + Paymob order ID (``obj.order.id``).
  5. **Test-mode short-circuit (PHASE-A §A5)**: if a Payment matching
     the paymob_order_id is found and ``is_test_transaction=True``,
     return 200 with ``{"status": "test_ignored"}`` and NO state change.
  6. **Idempotency check**: if the Payment is already in the target status
     (paid/failed), return 200 immediately (no double-processing).
  7. If the payment was successful:
     a. Update Payment.status = 'paid' + paid_at = now + provider_transaction_id.
     b. Update Order.payment_status = 'paid' + Order.status = 'confirmed'.
     c. Decrement inventory (``decrement_reserved_inventory``).
     d. Send payment confirmation email (non-blocking — per دستور §11).
  8. If the payment failed:
     a. Update Payment.status = 'failed' + failure_reason + provider_transaction_id.
     b. Update Order.payment_status = 'failed'.
     c. Release inventory reservation (``release_inventory_reservation``).
  9. Store the raw payload in ``Payment.webhook_payload`` (JSONField —
     for audit/debugging, per دستور §5).
  10. Return 200 (always — Paymob retries on non-200, which could cause
      duplicate processing even with our idempotency check).

URL: ``/payments/webhooks/paymob/`` (wired in ``apps/payments/urls.py``).
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.inventory.services import decrement_reserved_inventory, release_inventory_reservation
from apps.orders.models import Order
from apps.orders.notifications import send_payment_confirmation_email
from apps.orders.services import update_order_status
from apps.payments.models import Payment
from apps.payments.verification import extract_paymob_transaction_data, verify_paymob_signature

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def paymob_webhook(request: HttpRequest) -> HttpResponse:
    """Receive + process a Paymob transaction webhook.

    Per دستور §5: signature verification is mandatory. This view is
    ``@csrf_exempt`` because Paymob doesn't send a CSRF token — it
    authenticates via the HMAC-SHA512 signature instead. The ``@require_POST``
    decorator rejects GET/PUT/DELETE (Paymob only sends POST).

    Returns:
        - 200: webhook processed (or idempotently skipped, or transaction
          not found — we return 200 to prevent Paymob retries).
        - 403: signature verification failed (invalid HMAC or secret
          not configured). Per دستور §5, no state change happens.
        - 400: malformed JSON payload.
    """
    # ── 1. Read raw body ────────────────────────────────────────────────────
    payload = request.body
    if not payload:
        logger.warning("payment.webhook.empty_body")
        return HttpResponse(b"{}", status=400, content_type="application/json")

    # ── 2. Extract signature ───────────────────────────────────────────────
    # Paymob sends the HMAC in the ``SHA512`` query parameter OR in the
    # ``X-Paymob-Signature`` header (depending on the integration type).
    signature = request.GET.get("SHA512", "") or request.headers.get("X-Paymob-Signature", "")

    # ── 3. Verify signature ───────────────────────────────────────────────
    if not verify_paymob_signature(payload, signature):
        # Per دستور §5: no verification → no state change, full stop.
        # Return 403 so Paymob knows the webhook was rejected (and doesn't
        # retry — though Paymob may retry 403s; the idempotency check
        # below handles that on the legitimate side).
        return HttpResponse(
            b'{"error": "signature verification failed"}',
            status=403,
            content_type="application/json",
        )

    # ── 4. Parse payload ──────────────────────────────────────────────────
    txn_data = extract_paymob_transaction_data(payload)
    txn_id = txn_data.get("transaction_id")
    paymob_order_id = txn_data.get("paymob_order_id")
    if not txn_id:
        logger.warning("payment.webhook.no_transaction_id")
        return HttpResponse(
            b'{"error": "no transaction_id in payload"}',
            status=400,
            content_type="application/json",
        )
    if not paymob_order_id:
        # Without paymob_order_id we can't look the Payment up — return 200
        # so Paymob doesn't retry (the payload is malformed for our flow).
        logger.warning(
            "payment.webhook.no_paymob_order_id",
            extra={"transaction_id": txn_id},
        )
        return HttpResponse(
            b'{"error": "no paymob_order_id in payload"}',
            status=400,
            content_type="application/json",
        )

    # ── 5. Find the matching Payment by paymob_order_id ───────────────────
    # PHASE-A §A4 fix 2: lookup by paymob_order_id (the order ID Paymob
    # echoes back in ``obj.order.id``). ``initialize_paymob_payment`` stored
    # this value in ``payment.paymob_order_id`` at payment init time.
    #
    # PHASE-A §A4 fix 1: the lookup + lock now happens INSIDE
    # ``transaction.atomic()`` so ``select_for_update()`` actually acquires
    # the row lock (previously it was outside any transaction — a no-op on
    # SQLite, an error on Postgres).
    #
    # If not found, return 200 (not 404) so Paymob doesn't retry —
    # test-mode payments have synthetic IDs that won't match real Paymob IDs.
    is_success = False  # defensive default for the except handler
    target_status = None
    payment = None
    order = None
    try:
        with transaction.atomic():
            payment = (
                Payment.objects.select_for_update()
                .filter(
                    payment_provider=Payment.PaymentProvider.PAYMOB,
                    paymob_order_id=paymob_order_id,
                )
                .first()
            )
            if not payment:
                logger.info(
                    "payment.webhook.transaction_not_found",
                    extra={
                        "transaction_id": txn_id,
                        "paymob_order_id": paymob_order_id,
                    },
                )
                return HttpResponse(
                    b'{"status": "ok"}',
                    status=200,
                    content_type="application/json",
                )

            # ── 6. PHASE-A §A5 — test-mode short-circuit ────────────────
            # Test transactions (PaymentSimulationView simulation flow)
            # must NEVER decrement real inventory or transition real
            # orders. Detect early + return 200 with no state change so
            # Paymob doesn't retry (which would otherwise loop forever
            # on a payment that we refuse to actually process).
            if payment.is_test_transaction:
                logger.info(
                    "webhook.test_mode_ignored",
                    extra={
                        "payment_id": payment.business_id,
                        "paymob_order_id": paymob_order_id,
                        "transaction_id": txn_id,
                    },
                )
                return HttpResponse(
                    b'{"status": "test_ignored"}',
                    status=200,
                    content_type="application/json",
                )

            # ── 7. Idempotency check ─────────────────────────────────────
            # Per دستور §5: "Receiving the same webhook twice must not
            # double-capture." If the Payment is already in the target
            # status, return 200 immediately.
            is_success = txn_data.get("success", False)
            target_status = Payment.Status.PAID if is_success else Payment.Status.FAILED

            if payment.status == target_status:
                logger.info(
                    "payment.webhook.idempotent_skip",
                    extra={
                        "payment_id": payment.business_id,
                        "transaction_id": txn_id,
                        "paymob_order_id": paymob_order_id,
                        "status": payment.status,
                    },
                )
                return HttpResponse(
                    b'{"status": "ok"}',
                    status=200,
                    content_type="application/json",
                )

            # ── 8. Process the webhook (still inside the atomic block) ──
            order = payment.order

            # 8a. Update Payment — status + paid_at/failure_reason +
            #     webhook_payload + provider_transaction_id (the actual
            #     transaction ID, stored for downstream idempotency per
            #     PHASE-A §A4).
            payment.status = target_status
            payment.webhook_payload = txn_data.get("raw", {})
            payment.provider_transaction_id = txn_id
            if is_success:
                payment.paid_at = timezone.now()
            else:
                payment.failure_reason = (
                    f"Paymob webhook: transaction {txn_id} reported failure. "
                    f"Response code: {txn_data.get('raw', {}).get('obj', {}).get('txn_response_code', 'N/A')}"
                )
            payment.save(update_fields=[
                "status",
                "webhook_payload",
                "provider_transaction_id",
                "paid_at",
                "failure_reason",
                "updated_at",
            ])

            # 8b. Update Order.
            if is_success:
                order.payment_status = Order.PaymentStatus.PAID
                order.save(update_fields=["payment_status", "updated_at"])
                # Transition pending → confirmed (forward-only per دستور §10).
                # Use update_order_status with try/except — if the order is
                # already past 'pending' (e.g. admin confirmed it out-of-band),
                # swallow the ValueError (the order is in a good state).
                try:
                    update_order_status(order, Order.Status.CONFIRMED)
                except ValueError:
                    logger.info(
                        "payment.webhook.order_already_past_pending",
                        extra={
                            "order_id": order.business_id,
                            "current_status": order.status,
                        },
                    )
            else:
                order.payment_status = Order.PaymentStatus.FAILED
                order.save(update_fields=["payment_status", "updated_at"])

        # ── 9. Inventory + email (outside the atomic block — uses its own) ─
        # Per دستور §6: the inventory service wraps its own atomic() block
        # with select_for_update(). We call it OUTSIDE the main transaction
        # so a slow inventory lock doesn't block the payment update.
        # If inventory fails, the Payment + Order are already updated —
        # the ops team can reconcile manually (the email + Sentry alert
        # surface the issue).
        if is_success:
            decrement_reserved_inventory(order)
        else:
            release_inventory_reservation(order)

        # ── 10. Email (non-blocking — per دستور §11) ────────────────────
        if is_success:
            send_payment_confirmation_email(order, payment)

        logger.info(
            "payment.webhook.processed",
            extra={
                "payment_id": payment.business_id,
                "transaction_id": txn_id,
                "paymob_order_id": paymob_order_id,
                "order_id": order.business_id,
                "success": is_success,
                "status": target_status,
            },
        )
        return HttpResponse(
            b'{"status": "ok"}',
            status=200,
            content_type="application/json",
        )

    except Exception as exc:
        # Per دستور §5: never leak PII in logs. The structured JSON logger
        # + Sentry PII scrub handle this. We log the exception class + a
        # sanitized message (no card numbers, no addresses).
        logger.error(
            "payment.webhook.error",
            extra={
                "payment_id": getattr(payment, "business_id", "?"),
                "transaction_id": txn_id,
                "paymob_order_id": paymob_order_id,
                "error_type": type(exc).__name__,
                "error_msg": str(exc)[:200],  # truncate — never log full tracebacks in prod
            },
            exc_info=True,  # full traceback goes to Sentry (PII-scrubbed)
        )
        # Return 500 so Paymob retries (the transaction is in a partially
        # updated state — the retry's idempotency check will skip if the
        # Payment is already in the target status).
        return HttpResponse(
            b'{"error": "internal error"}',
            status=500,
            content_type="application/json",
        )
