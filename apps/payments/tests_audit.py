"""apps.payments — tests for the PaymentStatusChange audit log (PHASE-D §D6).

Covers:
  - update_payment_status writes a PaymentStatusChange row in the same
    transaction as the Payment.status update.
  - Idempotent no-op: same status → no audit row written.
  - changed_by + reason are recorded on the audit row.
  - old_status captures the PRE-transition status.
"""
from datetime import datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import CustomUser
from apps.orders.models import Order
from apps.payments.models import Payment, PaymentStatusChange
from apps.payments.services import update_payment_status


def _make_payment() -> Payment:
    user = CustomUser.objects.create_user(username="audit", password="pw123456")
    order = Order.objects.create(
        user=user, subtotal=Decimal("100"), discount_total=Decimal("0"),
        shipping_cost=Decimal("0"), grand_total=Decimal("100"),
    )
    return Payment.objects.create(
        order=order, payment_provider=Payment.PaymentProvider.COD,
        method_type=Payment.MethodType.COD, amount=Decimal("100"),
        currency="EGP", status=Payment.Status.PENDING,
    )


class PaymentStatusChangeAuditTests(TestCase):
    def test_update_writes_audit_row(self) -> None:
        """PHASE-D §D6: updating Payment.status writes a PaymentStatusChange row."""
        payment = _make_payment()
        self.assertEqual(PaymentStatusChange.objects.count(), 0)
        update_payment_status(payment, Payment.Status.PAID, reason="COD manual capture")
        self.assertEqual(PaymentStatusChange.objects.count(), 1)
        change = PaymentStatusChange.objects.first()
        self.assertEqual(change.payment_id, payment.pk)
        self.assertEqual(change.old_status, Payment.Status.PENDING)
        self.assertEqual(change.new_status, Payment.Status.PAID)
        self.assertEqual(change.reason, "COD manual capture")

    def test_idempotent_no_audit_row(self) -> None:
        """PHASE-D §D6: if status doesn't change, no audit row is written."""
        payment = _make_payment()
        # PENDING → PENDING (no change).
        update_payment_status(payment, Payment.Status.PENDING)
        self.assertEqual(PaymentStatusChange.objects.count(), 0)

    def test_changed_by_recorded(self) -> None:
        """The ``changed_by`` field captures the actor (when provided)."""
        payment = _make_payment()
        admin = CustomUser.objects.create_user(username="admin", password="pw123456", is_staff=True)
        update_payment_status(
            payment, Payment.Status.PAID, changed_by=admin, reason="manual capture",
        )
        change = PaymentStatusChange.objects.first()
        self.assertEqual(change.changed_by_id, admin.pk)

    def test_changed_by_null_for_webhook(self) -> None:
        """Webhook-triggered changes leave ``changed_by`` null (no Django user)."""
        payment = _make_payment()
        update_payment_status(payment, Payment.Status.PAID, reason="Paymob webhook")
        change = PaymentStatusChange.objects.first()
        self.assertIsNone(change.changed_by_id)

    def test_multiple_changes_all_audited(self) -> None:
        """Multiple transitions produce multiple audit rows in order."""
        payment = _make_payment()
        update_payment_status(payment, Payment.Status.PAID, reason="capture")
        update_payment_status(payment, Payment.Status.REFUNDED, reason="customer refund")
        # Two audit rows — one per transition.
        self.assertEqual(PaymentStatusChange.objects.count(), 2)
        first = PaymentStatusChange.objects.order_by("created_at").first()
        second = PaymentStatusChange.objects.order_by("-created_at").first()
        self.assertEqual(first.new_status, Payment.Status.PAID)
        self.assertEqual(second.old_status, Payment.Status.PAID)
        self.assertEqual(second.new_status, Payment.Status.REFUNDED)
