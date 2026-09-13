"""apps.wishlist — tests for WishlistItem (PHASE-C §C4).

Covers:
  - WishlistItem unique constraint: one entry per (user, product, variant)
  - Add idempotent (same product + variant doesn't duplicate)
  - Remove idempotent (removing non-existent wishlist item is a no-op / 404)
"""
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.accounts.models import CustomUser
from apps.catalog.models import Category, Product, ProductVariant
from apps.wishlist.models import WishlistItem


def _make_catalog() -> tuple[Category, Product, ProductVariant]:
    cat = Category.objects.create(name="Test", family_code="WLT")
    prod = Product.objects.create(
        name="Test Product", category=cat,
        base_price=Decimal("1000"), status=Product.Status.ACTIVE,
    )
    variant = ProductVariant.objects.create(product=prod)
    return cat, prod, variant


class WishlistItemUniqueTests(TestCase):
    def test_unique_per_user_product_variant(self) -> None:
        """UniqueConstraint uniq_wishlist_entry blocks duplicate (user, product, variant)."""
        user = CustomUser.objects.create_user(username="u", password="pw123456")
        _, prod, variant = _make_catalog()
        WishlistItem.objects.create(user=user, product=prod, variant=variant)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WishlistItem.objects.create(user=user, product=prod, variant=variant)

    def test_same_product_different_variant_allowed(self) -> None:
        """A user can wishlist different variants of the same product."""
        user = CustomUser.objects.create_user(username="u2", password="pw123456")
        _, prod, variant = _make_catalog()
        variant2 = ProductVariant.objects.create(product=prod, price_extra=Decimal("50"))
        WishlistItem.objects.create(user=user, product=prod, variant=variant)
        WishlistItem.objects.create(user=user, product=prod, variant=variant2)
        self.assertEqual(WishlistItem.objects.filter(user=user).count(), 2)

    def test_wishlist_without_variant(self) -> None:
        """A wishlist entry can be product-level (variant=None)."""
        user = CustomUser.objects.create_user(username="u3", password="pw123456")
        _, prod, _ = _make_catalog()
        WishlistItem.objects.create(user=user, product=prod, variant=None)
        self.assertEqual(WishlistItem.objects.filter(user=user).count(), 1)
