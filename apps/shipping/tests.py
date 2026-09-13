"""
apps.shipping — tests for ShippingMethod + ShippingAddress.

Covers:
  - ShippingMethod.price >= 0 (CheckConstraint)
  - ShippingMethod creation + defaults
  - ShippingAddress creation
"""
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.accounts.models import CustomUser
from apps.shipping.models import ShippingAddress, ShippingMethod


class ShippingMethodTests(TestCase):
    def test_shipping_method_creation(self) -> None:
        """A standard shipping method can be created with the expected fields."""
        sm = ShippingMethod.objects.create(
            name="Standard Ground",
            code="STD",
            price=Decimal("50"),
            estimated_days_min=3,
            estimated_days_max=5,
        )
        self.assertEqual(sm.name, "Standard Ground")
        self.assertEqual(sm.code, "STD")
        self.assertEqual(sm.price, Decimal("50"))
        self.assertTrue(sm.is_active)
        self.assertEqual(sm.currency, "EGP")
        self.assertEqual(str(sm), "Standard Ground (STD)")

    def test_defaults(self) -> None:
        sm = ShippingMethod.objects.create(name="Default", code="DEF")
        self.assertEqual(sm.price, 0)
        self.assertEqual(sm.estimated_days_min, 1)
        self.assertEqual(sm.estimated_days_max, 5)
        self.assertTrue(sm.is_active)

    def test_code_unique(self) -> None:
        ShippingMethod.objects.create(name="A", code="UNIQ")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ShippingMethod.objects.create(name="B", code="UNIQ")

    def test_negative_price_rejected(self) -> None:
        """CheckConstraint shipmethod_price_non_negative rejects price < 0."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ShippingMethod.objects.create(
                    name="Bad",
                    code="NEG",
                    price=Decimal("-1"),
                )

    def test_zero_price_allowed(self) -> None:
        """price=0 is valid (e.g. free shipping)."""
        sm = ShippingMethod.objects.create(name="Free", code="FREE", price=Decimal("0"))
        self.assertEqual(sm.price, Decimal("0"))

    def test_positive_price_allowed(self) -> None:
        sm = ShippingMethod.objects.create(name="Express", code="EXP", price=Decimal("100.50"))
        self.assertEqual(sm.price, Decimal("100.50"))


class ShippingAddressTests(TestCase):
    def test_address_creation(self) -> None:
        user = CustomUser.objects.create_user(username="ship", password="pw123456")
        addr = ShippingAddress.objects.create(
            user=user,
            full_name="Ahmed Ali",
            phone="+201012345678",
            city="Alexandria",
            country="Egypt",
            address="123 Tahrir St.",
            postal_code="11511",
        )
        self.assertEqual(addr.full_name, "Ahmed Ali")
        self.assertEqual(addr.city, "Alexandria")
        self.assertFalse(addr.is_default)
        self.assertEqual(str(addr), "Ahmed Ali — Alexandria")

    def test_address_default_country(self) -> None:
        user = CustomUser.objects.create_user(username="u2", password="pw123456")
        addr = ShippingAddress.objects.create(
            user=user,
            full_name="X",
            phone="+201000000000",
            city="Giza",
            address="Some address",
        )
        self.assertEqual(addr.country, "Egypt")

    def test_multiple_addresses_per_user(self) -> None:
        user = CustomUser.objects.create_user(username="multi", password="pw123456")
        ShippingAddress.objects.create(
            user=user, full_name="A", phone="+201000000001", city="Alexandria", address="x"
        )
        ShippingAddress.objects.create(
            user=user, full_name="B", phone="+201000000002", city="Giza", address="y"
        )
        self.assertEqual(user.shipping_addresses.count(), 2)
