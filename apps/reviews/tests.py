"""apps.reviews — tests for Review (PHASE-C §C4).

Covers:
  - Review rating bounds (1-5, reject 0 and 6)
  - UniqueConstraint: one review per (product, user)
  - Default is_approved=False (moderation gate)
  - is_verified_purchase defaults to False
"""
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.accounts.models import CustomUser
from apps.catalog.models import Category, Product
from apps.reviews.models import Review


def _make_product(name: str = "Test Product") -> Product:
    cat = Category.objects.create(name="Test", family_code="REV")
    return Product.objects.create(
        name=name, category=cat,
        base_price=Decimal("1000"), status=Product.Status.ACTIVE,
    )


class ReviewRatingBoundsTests(TestCase):
    def test_rating_min_allowed(self) -> None:
        """Rating=1 is the lower bound (allowed)."""
        user = CustomUser.objects.create_user(username="u1", password="pw123456")
        prod = _make_product()
        r = Review.objects.create(product=prod, user=user, rating=1)
        self.assertEqual(r.rating, 1)

    def test_rating_max_allowed(self) -> None:
        """Rating=5 is the upper bound (allowed)."""
        user = CustomUser.objects.create_user(username="u2", password="pw123456")
        prod = _make_product()
        r = Review.objects.create(product=prod, user=user, rating=5)
        self.assertEqual(r.rating, 5)

    def test_rating_zero_rejected(self) -> None:
        """CheckConstraint review_rating_range_1_5 rejects rating=0."""
        user = CustomUser.objects.create_user(username="u3", password="pw123456")
        prod = _make_product()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Review.objects.create(product=prod, user=user, rating=0)

    def test_rating_six_rejected(self) -> None:
        """CheckConstraint review_rating_range_1_5 rejects rating=6."""
        user = CustomUser.objects.create_user(username="u4", password="pw123456")
        prod = _make_product()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Review.objects.create(product=prod, user=user, rating=6)


class ReviewUniquePerUserProductTests(TestCase):
    def test_one_review_per_user_per_product(self) -> None:
        """UniqueConstraint uniq_review_per_user_per_product blocks duplicates."""
        user = CustomUser.objects.create_user(username="u5", password="pw123456")
        prod = _make_product()
        Review.objects.create(product=prod, user=user, rating=5)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Review.objects.create(product=prod, user=user, rating=3)

    def test_different_users_can_review_same_product(self) -> None:
        """Two different users can each leave one review on the same product."""
        prod = _make_product()
        u1 = CustomUser.objects.create_user(username="u6", password="pw123456")
        u2 = CustomUser.objects.create_user(username="u7", password="pw123456")
        Review.objects.create(product=prod, user=u1, rating=5)
        Review.objects.create(product=prod, user=u2, rating=4)
        self.assertEqual(Review.objects.filter(product=prod).count(), 2)


class ReviewDefaultsTests(TestCase):
    def test_defaults(self) -> None:
        """Reviews default to is_approved=False + is_verified_purchase=False."""
        user = CustomUser.objects.create_user(username="u8", password="pw123456")
        prod = _make_product()
        r = Review.objects.create(product=prod, user=user, rating=4)
        self.assertFalse(r.is_approved)
        self.assertFalse(r.is_verified_purchase)
        self.assertEqual(r.title, "")
        self.assertEqual(r.body, "")
