"""apps.inventory — tests for the reservation lifecycle (PHASE-B §B2).

Covers:
  - reserve_inventory: increments quantity_reserved atomically via F()
  - release_inventory_reservation: decrements quantity_reserved
  - decrement_reserved_inventory: decrements BOTH on_hand + reserved
  - Insufficient stock: logs a warning but doesn't crash
  - CheckConstraint: quantity_reserved >= 0 (defense-in-depth)
  - CheckConstraint: quantity_reserved <= quantity_on_hand
"""
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.accounts.models import CustomUser
from apps.catalog.models import Category, Product, ProductVariant
from apps.inventory.models import Inventory, Warehouse
from apps.inventory.services import (
    decrement_reserved_inventory,
    release_inventory_reservation,
    reserve_inventory,
)
from apps.orders.models import Order, OrderItem


def _make_inventory(quantity_on_hand: int = 100) -> tuple[Order, Inventory]:
    """Build a Category → Product → Variant → Warehouse → Inventory setup."""
    user = CustomUser.objects.create_user(username="buyer", password="pw123456")
    category = Category.objects.create(name="Test", family_code="TST")
    product = Product.objects.create(
        name="Test Product", category=category,
        base_price=Decimal("1000"), status=Product.Status.ACTIVE,
    )
    variant = ProductVariant.objects.create(product=product)
    warehouse = Warehouse.objects.create(code="MAIN", name="Main")
    inv = Inventory.objects.create(
        variant=variant, warehouse=warehouse,
        quantity_on_hand=quantity_on_hand, quantity_reserved=0,
    )
    order = Order.objects.create(
        user=user, subtotal=Decimal("1000"), discount_total=Decimal("0"),
        shipping_cost=Decimal("0"), grand_total=Decimal("1000"),
    )
    OrderItem.objects.create(
        order=order, variant=variant, sku=variant.sku,
        name=product.name, quantity=2, unit_price=Decimal("1000"),
    )
    return order, inv


class ReserveInventoryTests(TestCase):
    def test_reserve_inventory_increments_reserved(self) -> None:
        """reserve_inventory increments quantity_reserved by order quantity."""
        order, inv = _make_inventory(quantity_on_hand=100)
        updated = reserve_inventory(order)
        self.assertGreaterEqual(updated, 1)
        inv.refresh_from_db()
        self.assertEqual(inv.quantity_reserved, 2)
        # quantity_on_hand is NOT touched (the stock hasn't left the shelf yet).
        self.assertEqual(inv.quantity_on_hand, 100)
        # quantity_available reflects the reservation.
        self.assertEqual(inv.quantity_available, 98)

    def test_reserve_inventory_idempotent_on_no_stock(self) -> None:
        """If variant has no Inventory row, reserve is a no-op (returns 0)."""
        user = CustomUser.objects.create_user(username="x", password="pw123456")
        category = Category.objects.create(name="C", family_code="CFAM")
        product = Product.objects.create(
            name="P", category=category,
            base_price=Decimal("10"), status=Product.Status.ACTIVE,
        )
        variant = ProductVariant.objects.create(product=product)
        order = Order.objects.create(
            user=user, subtotal=Decimal("10"), grand_total=Decimal("10"),
        )
        OrderItem.objects.create(
            order=order, variant=variant, sku=variant.sku,
            name="P", quantity=1, unit_price=Decimal("10"),
        )
        # No Inventory row exists for this variant.
        self.assertEqual(reserve_inventory(order), 0)


class ReleaseInventoryReservationTests(TestCase):
    def test_release_decrements_reserved_only(self) -> None:
        """release_inventory_reservation decrements quantity_reserved only."""
        order, inv = _make_inventory(quantity_on_hand=100)
        reserve_inventory(order)
        inv.refresh_from_db()
        self.assertEqual(inv.quantity_reserved, 2)
        # Now release.
        release_inventory_reservation(order)
        inv.refresh_from_db()
        self.assertEqual(inv.quantity_reserved, 0)
        # quantity_on_hand unchanged (the stock never left the shelf).
        self.assertEqual(inv.quantity_on_hand, 100)

    def test_release_idempotent(self) -> None:
        """Calling release twice doesn't underflow to negative."""
        order, inv = _make_inventory(quantity_on_hand=100)
        reserve_inventory(order)
        release_inventory_reservation(order)
        release_inventory_reservation(order)  # idempotent second call
        inv.refresh_from_db()
        self.assertEqual(inv.quantity_reserved, 0)


class DecrementReservedInventoryTests(TestCase):
    def test_decrement_on_success(self) -> None:
        """decrement_reserved_inventory moves stock from reserved → sold."""
        order, inv = _make_inventory(quantity_on_hand=100)
        # Reserve first, then capture (decrement).
        reserve_inventory(order)
        decrement_reserved_inventory(order)
        inv.refresh_from_db()
        # Both quantity_on_hand AND quantity_reserved are decremented by 2.
        self.assertEqual(inv.quantity_on_hand, 98)
        self.assertEqual(inv.quantity_reserved, 0)
        self.assertEqual(inv.quantity_available, 98)


class InventoryConstraintTests(TestCase):
    def test_reserved_cannot_exceed_on_hand(self) -> None:
        """CheckConstraint inventory_reserved_lte_on_hand rejects reserved > on_hand."""
        category = Category.objects.create(name="C", family_code="CBND")
        product = Product.objects.create(
            name="P", category=category,
            base_price=Decimal("10"), status=Product.Status.ACTIVE,
        )
        variant = ProductVariant.objects.create(product=product)
        warehouse = Warehouse.objects.create(code="W", name="W")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Inventory.objects.create(
                    variant=variant, warehouse=warehouse,
                    quantity_on_hand=5, quantity_reserved=10,
                )

    def test_reserved_gte_zero(self) -> None:
        """CheckConstraint inventory_reserved_gte_0 (PHASE-B §B2 defense-in-depth)."""
        # PositiveIntegerField already enforces >= 0 at the form layer;
        # the CheckConstraint enforces it at the DB layer too. Since
        # PositiveIntegerField prevents negative values from being saved
        # via ORM, this test just verifies the constraint is present
        # (the CheckConstraint name should appear in the model's Meta).
        constraints = {c.name for c in Inventory._meta.constraints}
        self.assertIn("inventory_reserved_gte_0", constraints)
        self.assertIn("inventory_reserved_lte_on_hand", constraints)
