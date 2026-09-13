"""
apps.payments — tests for Payment.

Covers:
  - Payment.business_id (PHX-PAY-000001)
  - amount > 0 (CheckConstraint)
  - is_test_transaction defaults to True
  - UniqueConstraint on (payment_provider, provider_transaction_id)
  - defaults: provider='cod', method_type='cod', status='pending'
"""
import uuid
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.accounts.models import CustomUser
from apps.orders.models import Order
from apps.payments.models import Payment


def make_order() -> Order:
    return Order.objects.create(
        subtotal=Decimal("100"),
        discount_total=Decimal("0"),
        shipping_cost=Decimal("0"),
        grand_total=Decimal("100"),
    )


class PaymentBusinessIDTests(TestCase):
    def test_payment_business_id(self) -> None:
        """Payment business ID is PHX-PAY-000001, then 000002."""
        order = make_order()
        p1 = Payment.objects.create(order=order, amount=Decimal("50"))
        p2 = Payment.objects.create(order=order, amount=Decimal("50"))
        self.assertEqual(p1.business_id, "PHX-PAY-000001")
        self.assertEqual(p2.business_id, "PHX-PAY-000002")

    def test_payment_business_id_format(self) -> None:
        order = make_order()
        p = Payment.objects.create(order=order, amount=Decimal("10"))
        self.assertRegex(p.business_id, r"^PHX-PAY-\d{6}$")


class PaymentAmountTests(TestCase):
    def test_negative_amount_rejected(self) -> None:
        """CheckConstraint payment_amount_must_be_positive rejects amount <= 0."""
        order = make_order()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Payment.objects.create(order=order, amount=Decimal("-1"))

    def test_zero_amount_rejected(self) -> None:
        """amount must be strictly > 0 (MinValueValidator(0.01) + CheckConstraint)."""
        order = make_order()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Payment.objects.create(order=order, amount=Decimal("0"))

    def test_positive_amount_allowed(self) -> None:
        order = make_order()
        p = Payment.objects.create(order=order, amount=Decimal("0.01"))
        self.assertEqual(p.amount, Decimal("0.01"))


class PaymentDefaultsTests(TestCase):
    def test_is_test_transaction_default_true(self) -> None:
        """Per دستور: all payments default to test mode."""
        order = make_order()
        p = Payment.objects.create(order=order, amount=Decimal("10"))
        self.assertTrue(p.is_test_transaction)

    def test_defaults(self) -> None:
        order = make_order()
        p = Payment.objects.create(order=order, amount=Decimal("10"))
        self.assertEqual(p.payment_provider, Payment.PaymentProvider.COD)
        self.assertEqual(p.method_type, Payment.MethodType.COD)
        self.assertEqual(p.status, Payment.Status.PENDING)
        self.assertEqual(p.currency, "EGP")
        self.assertIsNone(p.provider_transaction_id)
        self.assertIsNone(p.paid_at)


class PaymentUniqueTransactionIDTests(TestCase):
    def test_unique_provider_transaction_id(self) -> None:
        """UniqueConstraint uniq_provider_transaction_id blocks duplicates per provider."""
        order = make_order()
        Payment.objects.create(
            order=order,
            amount=Decimal("10"),
            payment_provider=Payment.PaymentProvider.PAYMOB,
            provider_transaction_id="TXN-001",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Payment.objects.create(
                    order=order,
                    amount=Decimal("20"),
                    payment_provider=Payment.PaymentProvider.PAYMOB,
                    provider_transaction_id="TXN-001",
                )

    def test_same_txn_id_different_providers_allowed(self) -> None:
        """The same provider_transaction_id is allowed across different providers."""
        order = make_order()
        Payment.objects.create(
            order=order,
            amount=Decimal("10"),
            payment_provider=Payment.PaymentProvider.PAYMOB,
            provider_transaction_id="SHARED-001",
        )
        p2 = Payment.objects.create(
            order=order,
            amount=Decimal("10"),
            payment_provider=Payment.PaymentProvider.FAWRY,
            provider_transaction_id="SHARED-001",
        )
        self.assertEqual(p2.provider_transaction_id, "SHARED-001")

    def test_null_provider_transaction_id_allowed_multiple(self) -> None:
        """Multiple payments with NULL provider_transaction_id are allowed (COD case)."""
        order = make_order()
        Payment.objects.create(order=order, amount=Decimal("10"))
        Payment.objects.create(order=order, amount=Decimal("20"))
        # both should have null provider_transaction_id
        self.assertEqual(
            Payment.objects.filter(provider_transaction_id__isnull=True).count(), 2
        )


class PaymentMultiplePerOrderTests(TestCase):
    def test_multiple_payments_per_order(self) -> None:
        """An order can have multiple Payment rows (e.g. failed retry + success)."""
        order = make_order()
        Payment.objects.create(
            order=order, amount=Decimal("100"), status=Payment.Status.FAILED
        )
        Payment.objects.create(
            order=order, amount=Decimal("100"), status=Payment.Status.PAID
        )
        self.assertEqual(order.payments.count(), 2)
