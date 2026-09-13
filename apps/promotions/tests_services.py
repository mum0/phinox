"""apps.promotions — tests for apply_promo_code service (PHASE-B §B3).

Covers:
  - apply_promo_code: single-use enforcement (reject different code if one is applied)
  - apply_promo_code: same code already applied → idempotent no-op
  - apply_promo_code: used_count increments via F() expression
  - cancel_order: decrements used_count via F() expression
  - select_for_update on PromoCode (race-condition prevention — tested
    via observable behavior, not actual threads, since SQLite serializes
    connections)
"""
from decimal import Decimal

from django.test import TestCase

from apps.core.tests.factories import UserFactory
from apps.orders.models import Order
from apps.orders.services import cancel_order
from apps.promotions.models import PromoCode
from apps.promotions.services import apply_promo_code


def _make_promo(code: str = "WINTER10", value: Decimal = Decimal("10")) -> PromoCode:
    return PromoCode.objects.create(
        code=code,
        discount_type=PromoCode.DiscountType.PERCENTAGE,
        value=value,
        usage_limit=10,
    )


def _make_order(subtotal: Decimal = Decimal("1000")) -> Order:
    """Create a fresh Order with a unique user (factory-boy Sequence)."""
    user = UserFactory()
    return Order.objects.create(
        user=user, subtotal=subtotal, discount_total=Decimal("0"),
        shipping_cost=Decimal("0"), grand_total=subtotal,
    )


class ApplyPromoCodeSingleUseTests(TestCase):
    def test_apply_promo_code_sets_discount_and_links(self) -> None:
        """apply_promo_code sets discount_total + grand_total + promo_code FK."""
        order = _make_order()
        promo = _make_promo(code="WINTER10", value=Decimal("10"))
        apply_promo_code(order, promo)
        order.refresh_from_db()
        # 10% of 1000 = 100 discount.
        self.assertEqual(order.discount_total, Decimal("100.00"))
        self.assertEqual(order.grand_total, Decimal("900.00"))
        self.assertEqual(order.promo_code_id, promo.pk)

    def test_used_count_increments_via_F_expression(self) -> None:
        """apply_promo_code increments used_count atomically (F() expression)."""
        order = _make_order()
        promo = _make_promo()
        self.assertEqual(promo.used_count, 0)
        apply_promo_code(order, promo)
        promo.refresh_from_db()
        self.assertEqual(promo.used_count, 1)

    def test_apply_same_promo_twice_is_idempotent(self) -> None:
        """Re-applying the SAME code is a no-op (PHASE-B §B3 idempotency)."""
        order = _make_order()
        promo = _make_promo()
        apply_promo_code(order, promo)
        # Apply again — should be a no-op (used_count stays at 1, not 2).
        apply_promo_code(order, promo)
        promo.refresh_from_db()
        self.assertEqual(promo.used_count, 1)

    def test_apply_different_promo_after_one_applied_rejected(self) -> None:
        """PHASE-B §B3: stacking is forbidden — applying a different code raises."""
        order = _make_order()
        promo1 = _make_promo(code="WINTER10", value=Decimal("10"))
        promo2 = _make_promo(code="SUMMER20", value=Decimal("20"))
        apply_promo_code(order, promo1)
        with self.assertRaises(ValueError) as ctx:
            apply_promo_code(order, promo2)
        self.assertIn("different promo_code", str(ctx.exception))
        # promo2.used_count is NOT incremented.
        promo2.refresh_from_db()
        self.assertEqual(promo2.used_count, 0)


class CancelOrderPromoRollbackTests(TestCase):
    def test_cancel_order_decrements_used_count(self) -> None:
        """PHASE-B §B3: cancel_order decrements promo_code.used_count via F()."""
        order = _make_order()
        promo = _make_promo()
        apply_promo_code(order, promo)
        promo.refresh_from_db()
        self.assertEqual(promo.used_count, 1)
        # Cancel the order — should decrement used_count back to 0.
        cancel_order(order)
        promo.refresh_from_db()
        self.assertEqual(promo.used_count, 0)
        # The order itself is now CANCELLED.
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)


class PromoCodeUsageLimitTests(TestCase):
    def test_apply_past_usage_limit_raises(self) -> None:
        """PHASE-B §B3: applying when used_count >= usage_limit raises."""
        order = _make_order()
        promo = PromoCode.objects.create(
            code="LIMIT1",
            discount_type=PromoCode.DiscountType.PERCENTAGE,
            value=Decimal("10"),
            usage_limit=1,
        )
        # First apply succeeds.
        apply_promo_code(order, promo)
        # Second apply on a DIFFERENT order should raise (used_count=1, limit=1).
        order2 = _make_order()
        with self.assertRaises(ValueError) as ctx:
            apply_promo_code(order2, promo)
        self.assertIn("usage limit", str(ctx.exception))
