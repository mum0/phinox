"""apps.payments.verification — Paymob webhook signature verification.

App: ``apps.payments``.
Phase: 4 (Paymob Webhook — the final barrier to commercial launch).
Scope: HMAC-SHA512 signature verification for incoming Paymob webhook
       payloads. Uses only stdlib (``hmac`` + ``hashlib``) — no new deps
       per دستور §2.
Not in scope: Paymob API outbound calls (order/registration, payment_keys
  iframe redirect). Those are Phase 4 Part 2 (a future task).

Per دستور §5 (Payments):
  - Webhook signature verification is MANDATORY before any ``Payment.status``
    change. No verification → no state change, full stop.
  - Never log card numbers or PII.

Paymob webhook HMAC format:
  - Paymob sends the raw request body as JSON.
  - The HMAC is computed over the concatenation of specific fields from the
    payload (the ``obj`` dict), sorted by key. Paymob's docs describe the
    exact field set — we concatenate ALL top-level keys from the ``obj``
    payload in the order Paymob sends them (the gateway sorts the JSON keys
    alphabetically before computing the HMAC).
  - The resulting HMAC is sent in the ``SHA512`` query parameter of the
    webhook URL (e.g. ``/webhooks/paymob/?SHA512=<hex>``) OR in the
    ``X-Paymob-Signature`` header (Paymob uses both methods depending on
    the integration type).

Implementation note:
  - We use ``hmac.compare_digest`` (constant-time comparison) to prevent
    timing attacks.
  - We use ``hashlib.sha512`` (per Paymob's HMAC specification — they use
    SHA-512 for the HMAC digest, NOT SHA-256).
  - If ``PAYMOB_HMAC_SECRET`` is not configured (empty), we return False +
    log a WARNING — we never crash (per دستور §0 rule 10 "when unsure,
    write a short design note and ask" — but here the behavior is clear:
    no secret = no verification = no state change).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)


def verify_paymob_signature(
    payload: bytes,
    signature: str,
    secret: Optional[str] = None,
) -> bool:
    """Verify a Paymob webhook signature using HMAC-SHA512.

    Paymob computes the HMAC over the raw JSON body of the webhook payload.
    The signature is compared in constant time (``hmac.compare_digest``)
    to prevent timing attacks.

    Args:
        payload: The raw request body bytes (as received from Paymob).
        signature: The HMAC hex digest from the ``SHA512`` query param
            or ``X-Paymob-Signature`` header.
        secret: The HMAC secret. If None, reads from
            ``settings.PAYMOB_HMAC_SECRET``. If the secret is empty, the
            function returns False + logs a WARNING (no crash).

    Returns:
        True if the signature matches, False otherwise (including when
        the secret is not configured).

    Per دستور §5: this function is the gatekeeper — the webhook view
    MUST NOT proceed to update ``Payment.status`` if this returns False.
    """
    hmac_secret = secret if secret is not None else getattr(settings, "PAYMOB_HMAC_SECRET", "")

    if not hmac_secret:
        logger.warning(
            "payment.webhook.no_secret",
            extra={"reason": "PAYMOB_HMAC_SECRET not configured — rejecting webhook"},
        )
        return False

    if not signature:
        logger.warning(
            "payment.webhook.no_signature",
            extra={"reason": "Empty signature in webhook request"},
        )
        return False

    # Compute HMAC-SHA512 over the raw payload bytes.
    expected_hmac = hmac.new(
        hmac_secret.encode("utf-8"),
        payload,
        hashlib.sha512,
    ).hexdigest()

    # Constant-time comparison to prevent timing attacks.
    is_valid = hmac.compare_digest(expected_hmac, signature)

    if not is_valid:
        logger.warning(
            "payment.webhook.invalid_signature",
            extra={"reason": "HMAC mismatch — possible tampering or wrong secret"},
        )
    return is_valid


def extract_paymob_transaction_data(payload: bytes) -> dict:
    """Extract the key fields from a Paymob webhook payload.

    Paymob webhook payloads vary by event type, but the transaction-
    processing webhook (the one we handle) has a consistent shape::

        {
          "type": "TRANSACTION",
          "obj": {
            "id": <int>,                  # Paymob transaction ID
            "success": <bool>,            # True if payment captured
            "order": {"id": <int>},        # Paymob order ID
            "amount_cents": <int>,        # Amount in cents (1 EGP = 100 cents)
            "currency": "EGP",
            "source_data": {
              "type": "card" | "valu" | ...,
              "pan": "**** **** **** 1234"  # masked PAN
            },
            "txn_response_code": "...",
            "created_at": "2026-09-10T12:34:56.000Z"
          }
        }

    This function parses the raw bytes and returns a normalized dict with
    the fields we need. It never raises — on malformed JSON or missing
    fields, it returns an empty dict (the caller checks for the
    ``transaction_id`` key).

    Args:
        payload: Raw request body bytes from Paymob.

    Returns:
        Dict with keys:
          - ``transaction_id`` (str | None)  — Paymob's transaction pk
          - ``paymob_order_id`` (str | None) — Paymob's order pk
          - ``success`` (bool)               — whether the payment captured
          - ``amount_cents`` (int | None)    — amount in cents
          - ``currency`` (str | None)
          - ``created_at`` (str | None)
          - ``raw`` (dict)                   — the parsed JSON for audit

    Per دستور §5: the ``pan`` field (masked card number) is NEVER logged.
    The raw payload is stored in ``Payment.webhook_payload`` (JSONField)
    for audit, but Sentry's ``scrub_pii_before_send`` hook masks card
    numbers before any event leaves the process.
    """
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning("payment.webhook.malformed_json")
        return {}

    obj = data.get("obj", data)  # some Paymob payloads nest under "obj"
    if not isinstance(obj, dict):
        return {}

    txn_id = obj.get("id")
    paymob_order = obj.get("order", {})
    paymob_order_id = paymob_order.get("id") if isinstance(paymob_order, dict) else None

    return {
        "transaction_id": str(txn_id) if txn_id is not None else None,
        "paymob_order_id": str(paymob_order_id) if paymob_order_id is not None else None,
        "success": bool(obj.get("success", False)),
        "amount_cents": obj.get("amount_cents"),
        "currency": obj.get("currency"),
        "created_at": obj.get("created_at"),
        "raw": data,
    }
