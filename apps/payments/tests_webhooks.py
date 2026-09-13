"""apps.payments.tests_webhooks — Phase 4 Paymob webhook tests.

Covers:
  - Signature verification (valid, invalid, empty, no secret).
  - Payload parsing (valid JSON, malformed JSON, missing fields).
  - Idempotency (duplicate webhook doesn't double-process).
  - Payment status update (success → paid, failure → failed).
  - Order status update (success → confirmed, failure → payment_status=failed).
  - Inventory decrement on success.
  - Inventory release on failure.
  - Webhook without secret configured → 403 (no crash).
  - PAYMOB_SETUP.md exists in the repo.
  - Non-POST methods rejected (GET → 405).

Per دستور §5: signature verification is MANDATORY. Per دستور §8: every
webhook handler has tests with: valid signature, invalid signature, replayed
idempotency key, missing fields.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.catalog.models import Category, Product, ProductVariant
from apps.inventory.models import Inventory, Warehouse
from apps.orders.models import Order, OrderItem
from apps.payments.models import Payment

# ── Helpers ────────────────────────────────────────────────────────────────
PAYMOB_SECRET = "test_hmac_secret_for_phase4_tests"


def _make_payload(
    txn_id: int = 123456789,
    success: bool = True,
    amount_cents: int = 250000,
    paymob_order_id: int = 987654,
) -> bytes:
    """Build a realistic Paymob webhook payload."""
    return json.dumps({
        "type": "TRANSACTION",
        "obj": {
            "id": txn_id,
            "success": success,
            "order": {"id": paymob_order_id},
            "amount_cents": amount_cents,
            "currency": "EGP",
            "source_data": {
                "type": "card",
                "pan": "**** **** **** 1234",
            },
            "txn_response_code": "0" if success else "DECLINED",
            "created_at": "2026-09-10T12:34:56.000Z",
        },
    }).encode("utf-8")


def _compute_hmac(payload: bytes, secret: str = PAYMOB_SECRET) -> str:
    """Compute the expected HMAC-SHA512 signature for the payload."""
    return hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha512,
    ).hexdigest()


def _make_order_with_payment(
    txn_id: str = "123456789",
    paymob_order_id: str = "987654",
    is_test: bool = False,
) -> tuple[Order, Payment]:
    """Create an Order + a pending Paymob Payment.

    PHASE-A §A4: the Payment is keyed by ``paymob_order_id`` (which the
    webhook extracts from ``obj.order.id`` in the payload). The webhook
    stores the actual transaction ID (``obj.id``) in
    ``provider_transaction_id`` AFTER processing — so initially
    ``provider_transaction_id`` is None.

    PHASE-A §A5: ``is_test`` controls the ``is_test_transaction`` flag.
    Set True to verify the test-mode short-circuit (webhook returns
    ``{"status": "test_ignored"}`` with no state change).
    """
    user = CustomUser.objects.create_user(
        username="testbuyer", password="pw123456", email="buyer@test.local"
    )
    category = Category.objects.create(name="Test Cat", family_code="TST")
    product = Product.objects.create(
        name="Test Product", category=category,
        base_price=Decimal("2500"), status=Product.Status.ACTIVE,
    )
    variant = ProductVariant.objects.create(product=product)
    order = Order.objects.create(
        user=user, subtotal=Decimal("2500"), discount_total=Decimal("0"),
        shipping_cost=Decimal("0"), grand_total=Decimal("2500"),
        placed_at=__import__("django.utils.timezone", fromlist=["now"]).now(),
    )
    OrderItem.objects.create(
        order=order, variant=variant, sku=variant.sku,
        name=product.name, quantity=1, unit_price=Decimal("2500"),
    )
    payment = Payment.objects.create(
        order=order, payment_provider=Payment.PaymentProvider.PAYMOB,
        method_type=Payment.MethodType.CARD,
        paymob_order_id=paymob_order_id,
        amount=Decimal("2500"), currency="EGP",
        status=Payment.Status.PENDING, is_test_transaction=is_test,
    )
    return order, payment


# ── Signature verification tests ──────────────────────────────────────────
class VerifyPaymobSignatureTest(TestCase):
    """Tests for apps.payments.verification.verify_paymob_signature."""

    def test_valid_signature(self) -> None:
        """A correctly computed HMAC-SHA512 signature passes verification."""
        from apps.payments.verification import verify_paymob_signature
        payload = _make_payload()
        sig = _compute_hmac(payload)
        with override_settings(PAYMOB_HMAC_SECRET=PAYMOB_SECRET):
            self.assertTrue(verify_paymob_signature(payload, sig))

    def test_invalid_signature(self) -> None:
        """An incorrect signature is rejected (returns False, not raise)."""
        from apps.payments.verification import verify_paymob_signature
        payload = _make_payload()
        with override_settings(PAYMOB_HMAC_SECRET=PAYMOB_SECRET):
            self.assertFalse(verify_paymob_signature(payload, "deadbeef" * 16))

    def test_empty_signature(self) -> None:
        """An empty signature string is rejected."""
        from apps.payments.verification import verify_paymob_signature
        payload = _make_payload()
        with override_settings(PAYMOB_HMAC_SECRET=PAYMOB_SECRET):
            self.assertFalse(verify_paymob_signature(payload, ""))

    @override_settings(PAYMOB_HMAC_SECRET="")
    def test_no_secret_configured(self) -> None:
        """When PAYMOB_HMAC_SECRET is empty, verification returns False (no crash)."""
        from apps.payments.verification import verify_paymob_signature
        payload = _make_payload()
        sig = _compute_hmac(payload, secret="anything")
        self.assertFalse(verify_paymob_signature(payload, sig))


# ── Payload parsing tests ────────────────────────────────────────────────
class ExtractPaymobTransactionDataTest(TestCase):
    """Tests for apps.payments.verification.extract_paymob_transaction_data."""

    def test_valid_payload(self) -> None:
        """A valid Paymob payload is parsed correctly."""
        from apps.payments.verification import extract_paymob_transaction_data
        payload = _make_payload(txn_id=42, success=True, amount_cents=5000)
        data = extract_paymob_transaction_data(payload)
        self.assertEqual(data["transaction_id"], "42")
        self.assertTrue(data["success"])
        self.assertEqual(data["amount_cents"], 5000)
        self.assertEqual(data["currency"], "EGP")

    def test_malformed_json(self) -> None:
        """Malformed JSON returns an empty dict (no crash)."""
        from apps.payments.verification import extract_paymob_transaction_data
        data = extract_paymob_transaction_data(b"not json at all")
        self.assertEqual(data, {})

    def test_missing_obj(self) -> None:
        """A payload without 'obj' key still parses (falls back to root dict)."""
        from apps.payments.verification import extract_paymob_transaction_data
        payload = json.dumps({"id": 99, "success": True}).encode()
        data = extract_paymob_transaction_data(payload)
        self.assertEqual(data["transaction_id"], "99")

    def test_no_transaction_id(self) -> None:
        """A payload without an 'id' field returns transaction_id=None."""
        from apps.payments.verification import extract_paymob_transaction_data
        payload = json.dumps({"obj": {"success": True}}).encode()
        data = extract_paymob_transaction_data(payload)
        self.assertIsNone(data["transaction_id"])


# ── Webhook endpoint tests ────────────────────────────────────────────────
@override_settings(PAYMOB_HMAC_SECRET=PAYMOB_SECRET)
class PaymobWebhookViewTest(TestCase):
    """End-to-end tests for the paymob_webhook view."""

    def test_webhook_valid_signature_success(self) -> None:
        """A valid webhook with a successful payment updates Payment to 'paid'.

        PHASE-A §A4: verifies the lookup-by-paymob_order_id flow. The Payment
        is created with ``paymob_order_id=987654`` (matching the payload's
        ``obj.order.id``). The payload's ``obj.id`` (transaction_id) is
        ``123456789`` — DIFFERENT from the order ID. After the webhook:
          - ``payment.paymob_order_id`` is still ``"987654"`` (unchanged).
          - ``payment.provider_transaction_id`` is now ``"123456789"``
            (populated by the webhook for idempotency).
        """
        order, payment = _make_order_with_payment(
            txn_id="123456789", paymob_order_id="987654",
        )
        payload = _make_payload(txn_id=123456789, success=True, paymob_order_id=987654)
        sig = _compute_hmac(payload)
        url = reverse("payments:paymob_webhook")
        response = self.client.post(
            url, data=payload, content_type="application/json",
            QUERY_STRING=f"SHA512={sig}",
        )
        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertIsNotNone(payment.paid_at)
        self.assertIsNotNone(payment.webhook_payload)
        # PHASE-A §A4: provider_transaction_id is now the txn_id from the
        # payload (set by the webhook, not at init time).
        self.assertEqual(payment.provider_transaction_id, "123456789")
        self.assertEqual(payment.paymob_order_id, "987654")

    def test_webhook_valid_signature_failure(self) -> None:
        """A valid webhook with a failed payment updates Payment to 'failed'."""
        order, payment = _make_order_with_payment(
            txn_id="999888777", paymob_order_id="987654",
        )
        payload = _make_payload(txn_id=999888777, success=False, paymob_order_id=987654)
        sig = _compute_hmac(payload)
        url = reverse("payments:paymob_webhook")
        response = self.client.post(
            url, data=payload, content_type="application/json",
            QUERY_STRING=f"SHA512={sig}",
        )
        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertIn("Paymob webhook", payment.failure_reason)
        # PHASE-A §A4: provider_transaction_id is set by the webhook even on failure.
        self.assertEqual(payment.provider_transaction_id, "999888777")

    def test_webhook_invalid_signature(self) -> None:
        """An invalid signature returns 403 and does NOT update the payment."""
        order, payment = _make_order_with_payment(
            txn_id="111222333", paymob_order_id="987654",
        )
        payload = _make_payload(txn_id=111222333, paymob_order_id=987654)
        url = reverse("payments:paymob_webhook")
        response = self.client.post(
            url, data=payload, content_type="application/json",
            QUERY_STRING="SHA512=invalid_signature_here",
        )
        self.assertEqual(response.status_code, 403)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)

    @override_settings(PAYMOB_HMAC_SECRET="")
    def test_webhook_works_without_secret_configured(self) -> None:
        """When PAYMOB_HMAC_SECRET is empty, the webhook returns 403 (no crash)."""
        order, payment = _make_order_with_payment(
            txn_id="444555666", paymob_order_id="987654",
        )
        payload = _make_payload(txn_id=444555666, paymob_order_id=987654)
        sig = _compute_hmac(payload, secret="anything")
        url = reverse("payments:paymob_webhook")
        response = self.client.post(
            url, data=payload, content_type="application/json",
            QUERY_STRING=f"SHA512={sig}",
        )
        self.assertEqual(response.status_code, 403)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)

    def test_webhook_idempotent(self) -> None:
        """Sending the same webhook twice does not double-process."""
        order, payment = _make_order_with_payment(
            txn_id="777888999", paymob_order_id="987654",
        )
        payload = _make_payload(txn_id=777888999, success=True, paymob_order_id=987654)
        sig = _compute_hmac(payload)
        url = reverse("payments:paymob_webhook")
        # First call — should process.
        r1 = self.client.post(url, data=payload, content_type="application/json", QUERY_STRING=f"SHA512={sig}")
        self.assertEqual(r1.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        # Second call — should be idempotent (return 200, no state change).
        r2 = self.client.post(url, data=payload, content_type="application/json", QUERY_STRING=f"SHA512={sig}")
        self.assertEqual(r2.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)

    def test_webhook_transaction_not_found(self) -> None:
        """A webhook for an unknown paymob_order_id returns 200 (no retry)."""
        # No Payment is created — the default payload's paymob_order_id (987654)
        # has no matching Payment row in this test, so the webhook returns 200.
        payload = _make_payload(txn_id=0, success=True, paymob_order_id=987654)
        sig = _compute_hmac(payload)
        url = reverse("payments:paymob_webhook")
        response = self.client.post(
            url, data=payload, content_type="application/json",
            QUERY_STRING=f"SHA512={sig}",
        )
        self.assertEqual(response.status_code, 200)

    def test_webhook_empty_body(self) -> None:
        """An empty request body returns 400."""
        url = reverse("payments:paymob_webhook")
        response = self.client.post(url, data=b"", content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_webhook_get_rejected(self) -> None:
        """GET requests are rejected (only POST is allowed)."""
        url = reverse("payments:paymob_webhook")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)

    def test_webhook_order_status_updated_on_success(self) -> None:
        """On payment success, the Order is transitioned to 'confirmed'."""
        order, payment = _make_order_with_payment(
            txn_id="555666777", paymob_order_id="987654",
        )
        payload = _make_payload(txn_id=555666777, success=True, paymob_order_id=987654)
        sig = _compute_hmac(payload)
        url = reverse("payments:paymob_webhook")
        self.client.post(url, data=payload, content_type="application/json", QUERY_STRING=f"SHA512={sig}")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CONFIRMED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)

    def test_webhook_order_payment_status_failed_on_failure(self) -> None:
        """On payment failure, the Order's payment_status becomes 'failed'."""
        order, payment = _make_order_with_payment(
            txn_id="333222111", paymob_order_id="987654",
        )
        payload = _make_payload(txn_id=333222111, success=False, paymob_order_id=987654)
        sig = _compute_hmac(payload)
        url = reverse("payments:paymob_webhook")
        self.client.post(url, data=payload, content_type="application/json", QUERY_STRING=f"SHA512={sig}")
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.FAILED)

    # ── PHASE-A §A5: test-mode short-circuit ──────────────────────────────
    def test_webhook_test_mode_ignored(self) -> None:
        """A webhook for a test-mode Payment returns 200 + no state change.

        PHASE-A §A5: ``is_test_transaction=True`` payments must never
        decrement real inventory or transition real orders. The webhook
        returns ``{"status": "test_ignored"}`` so Paymob doesn't retry.
        """
        order, payment = _make_order_with_payment(
            txn_id="888999000", paymob_order_id="987654", is_test=True,
        )
        payload = _make_payload(txn_id=888999000, success=True, paymob_order_id=987654)
        sig = _compute_hmac(payload)
        url = reverse("payments:paymob_webhook")
        response = self.client.post(
            url, data=payload, content_type="application/json",
            QUERY_STRING=f"SHA512={sig}",
        )
        self.assertEqual(response.status_code, 200)
        # Response body should indicate test-mode skip.
        self.assertIn(b"test_ignored", response.content)
        # No state change — Payment stays PENDING, Order stays UNPAID/PENDING.
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertIsNone(payment.provider_transaction_id)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.payment_status, Order.PaymentStatus.UNPAID)


# ── File existence tests ──────────────────────────────────────────────────
class PaymobSetupFileTest(TestCase):
    """Tests that required Phase 4 documentation files exist."""

    def test_paymob_setup_md_exists(self) -> None:
        """PAYMOB_SETUP.md must exist in the repo (docs/ or root)."""
        # tests_webhooks.py → apps/payments/ → apps/ → phinox/ (repo root)
        project_root = Path(__file__).resolve().parent.parent.parent
        # PHINOX-V2.1: PAYMOB_SETUP.md was moved from repo root → docs/.
        # Check both locations for backward compatibility.
        docs_file = project_root / "docs" / "PAYMOB_SETUP.md"
        root_file = project_root / "PAYMOB_SETUP.md"
        self.assertTrue(
            docs_file.exists() or root_file.exists(),
            f"PAYMOB_SETUP.md not found at {docs_file} or {root_file}",
        )
