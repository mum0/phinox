"""PHINOX shared test factories (factory-boy).

Per دستور §8: factory-boy is the test-data generator. These factories
are the canonical builders for tests across all apps — use them instead
of re-implementing helper ``make_*`` functions in every test module.

Available factories:
  - UserFactory         — CustomUser with a stable customer_id.
  - AddressFactory      — ShippingAddress (Alexandria, Egypt).
  - CategoryFactory     — catalog.Category with family_code 'TST'.
  - ProductFactory      — catalog.Product (ACTIVE, base_price=1000).
  - VariantFactory      — catalog.ProductVariant (price_extra=0).
  - InventoryFactory    — inventory.Inventory at the default Warehouse.
  - OrderFactory        — orders.Order (subtotal=1000, no items).
  - PaymentFactory      — payments.Payment (COD, PENDING).
  - CartFactory         — cart.Cart owned by a user.

Usage (pytest):
    from apps.core.tests.factories import UserFactory
    def test_something(db):
        user = UserFactory()
        ...

Usage (Django TestCase):
    from apps.core.tests.factories import ProductFactory
    class MyTest(TestCase):
        def setUp(self):
            self.product = ProductFactory()
"""
from __future__ import annotations

from decimal import Decimal

import factory
from django.contrib.auth import get_user_model

from apps.cart.models import Cart
from apps.catalog.models import Category, Product, ProductVariant
from apps.inventory.models import Inventory, Warehouse
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.shipping.models import ShippingAddress

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    """CustomUser with a unique username + email + customer_id."""

    class Meta:
        model = User
        django_get_or_create = ("username",)

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@phinox.local")
    phone = "+201012345678"
    is_active = True


class AddressFactory(factory.django.DjangoModelFactory):
    """ShippingAddress for the Alexandria governorate."""

    class Meta:
        model = ShippingAddress

    user = factory.SubFactory(UserFactory)
    full_name = "Test Buyer"
    phone = "+201012345678"
    governorate = "Alexandria"
    city = "Alexandria"
    country = "Egypt"
    address = "1 Tahrir Square"
    is_default = True


class CategoryFactory(factory.django.DjangoModelFactory):
    """Category with a unique family_code (drives the SKU prefix)."""

    class Meta:
        model = Category
        django_get_or_create = ("family_code",)

    name = "Test Category"
    family_code = "TST"


class ProductFactory(factory.django.DjangoModelFactory):
    """ACTIVE Product with base_price=1000 EGP."""

    class Meta:
        model = Product

    name = factory.Sequence(lambda n: f"Test Product {n}")
    category = factory.SubFactory(CategoryFactory)
    base_price = Decimal("1000")
    currency = "EGP"
    status = Product.Status.ACTIVE
    is_active = True


class VariantFactory(factory.django.DjangoModelFactory):
    """ProductVariant with price_extra=0 (unit_price = base_price)."""

    class Meta:
        model = ProductVariant

    product = factory.SubFactory(ProductFactory)
    price_extra = Decimal("0")
    is_active = True


class WarehouseFactory(factory.django.DjangoModelFactory):
    """A single test Warehouse (code='MAIN')."""

    class Meta:
        model = Warehouse
        django_get_or_create = ("code",)

    code = "MAIN"
    name = "Main Warehouse"
    governorate = "Alexandria"
    is_active = True


class InventoryFactory(factory.django.DjangoModelFactory):
    """Inventory row: 100 units on hand, 0 reserved, low_stock=5."""

    class Meta:
        model = Inventory

    variant = factory.SubFactory(VariantFactory)
    warehouse = factory.SubFactory(WarehouseFactory)
    quantity_on_hand = 100
    quantity_reserved = 0
    low_stock_threshold = 5


class OrderFactory(factory.django.DjangoModelFactory):
    """A minimal Order: subtotal=1000, grand_total=1000, PENDING status."""

    class Meta:
        model = Order

    user = factory.SubFactory(UserFactory)
    subtotal = Decimal("1000")
    discount_total = Decimal("0")
    shipping_cost = Decimal("0")
    grand_total = Decimal("1000")
    currency = "EGP"
    status = Order.Status.PENDING
    payment_status = Order.PaymentStatus.UNPAID


class PaymentFactory(factory.django.DjangoModelFactory):
    """A COD Payment in PENDING status."""

    class Meta:
        model = Payment

    order = factory.SubFactory(OrderFactory)
    payment_provider = Payment.PaymentProvider.COD
    method_type = Payment.MethodType.COD
    amount = Decimal("1000")
    currency = "EGP"
    status = Payment.Status.PENDING
    is_test_transaction = True


class CartFactory(factory.django.DjangoModelFactory):
    """A Cart owned by ``user`` (OneToOneField)."""

    class Meta:
        model = Cart

    user = factory.SubFactory(UserFactory)
