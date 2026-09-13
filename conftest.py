"""PHINOX pytest conftest — shared fixtures for all test modules.

Per دستور §8: pytest-django is the test runner. Factory-boy generates
test data. This conftest exposes a minimal set of fixtures (db, client,
user, admin_user) so test modules don't need to re-implement them.

Existing Django TestCase subclasses in apps/*/tests*.py continue to work
under pytest (pytest-django auto-collects them). New tests written in
pytest style (function-based, ``@pytest.mark.django_db``) can use these
fixtures directly.
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client


User = get_user_model()


@pytest.fixture
def user(db):
    """A plain authenticated user with a stable customer_id."""
    return User.objects.create_user(
        username="testuser",
        email="testuser@phinox.local",
        password="TestPass123!",
    )


@pytest.fixture
def admin_user(db):
    """A staff/superuser for admin-only test paths."""
    return User.objects.create_superuser(
        username="admin",
        email="admin@phinox.local",
        password="AdminPass123!",
    )


@pytest.fixture
def client():
    """An anonymous Django test client."""
    return Client()


@pytest.fixture
def auth_client(client, user):
    """A Django test client authenticated as ``user``."""
    client.login(username="testuser", password="TestPass123!")
    return client


# ---------------------------------------------------------------------------
# Catalog factories (C2 — light wrappers around factory-boy)
# ---------------------------------------------------------------------------
@pytest.fixture
def category(db):
    """A test Category with family_code='TST' (drives SKU prefix PHX-TST-001)."""
    from apps.catalog.models import Category
    return Category.objects.create(name="Test Cat", family_code="TST")


@pytest.fixture
def product(db, category):
    """A test Product (ACTIVE status, base_price=1000 EGP)."""
    from decimal import Decimal
    from apps.catalog.models import Product
    return Product.objects.create(
        name="Test Product",
        category=category,
        base_price=Decimal("1000"),
        status=Product.Status.ACTIVE,
    )


@pytest.fixture
def variant(db, product):
    """A test ProductVariant (price_extra=0 → unit_price=1000 EGP)."""
    from decimal import Decimal
    from apps.catalog.models import ProductVariant
    return ProductVariant.objects.create(product=product, price_extra=Decimal("0"))


@pytest.fixture
def shipping_method(db):
    """A test ShippingMethod (STD, 50 EGP)."""
    from decimal import Decimal
    from apps.shipping.models import ShippingMethod
    return ShippingMethod.objects.create(
        name="Standard",
        code="STD",
        price=Decimal("50"),
    )


@pytest.fixture
def shipping_address(db, user):
    """A test ShippingAddress for ``user`` (Alexandria, Egypt)."""
    from apps.shipping.models import ShippingAddress
    return ShippingAddress.objects.create(
        user=user,
        full_name="Test Buyer",
        phone="+201012345678",
        governorate="Alexandria",
        city="Alexandria",
        country="Egypt",
        address="1 Tahrir Square",
        is_default=True,
    )


@pytest.fixture
def cart(db, user):
    """An empty Cart for ``user``."""
    from apps.cart.models import Cart
    return Cart.objects.create(user=user)


@pytest.fixture
def cart_with_item(db, cart, variant):
    """A Cart with one CartItem (quantity=2)."""
    from apps.cart.models import CartItem
    return CartItem.objects.create(cart=cart, variant=variant, quantity=2)
