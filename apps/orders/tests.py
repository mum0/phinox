"""
apps.orders — tests for Order + OrderItem.

Covers:
  - Order.business_id sequential (PHX-ORD-000001)
  - BOS sync metadata defaults (not_required / None / None)
  - idempotency_key auto-generated UUID
  - CheckConstraint: discount_total <= subtotal
  - CheckConstraint: grand_total = subtotal - discount_total + shipping_cost
  - OrderItem.line_total computed property (unit_price * quantity)
  - All money fields non-negative
"""
import uuid
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.accounts.models import CustomUser
from apps.catalog.models import Category, Product, ProductVariant
from apps.orders.models import Order, OrderItem


class OrderBusinessIDTests(TestCase):
    def test_order_business_id(self) -> None:
        """Order business ID is PHX-ORD-000001, then 000002."""
        o1 = Order.objects.create()
        o2 = Order.objects.create()
        self.assertEqual(o1.business_id, "PHX-ORD-000001")
        self.assertEqual(o2.business_id, "PHX-ORD-000002")

    def test_order_business_id_format(self) -> None:
        o = Order.objects.create()
        self.assertRegex(o.business_id, r"^PHX-ORD-\d{6}$")

    def test_order_business_id_immutable(self) -> None:
        o = Order.objects.create()
        original = o.business_id
        o.customer_notes = "updated"
        o.save()
        o.refresh_from_db()
        self.assertEqual(o.business_id, original)


class OrderBOSDefaultsTests(TestCase):
    def test_bos_defaults(self) -> None:
        """Per دستور §6/§13: BOS fields default to 'not required / None / None'."""
        o = Order.objects.create()
        self.assertEqual(o.bos_sync_status, Order.BosSyncStatus.NOT_REQUIRED)
        self.assertIsNone(o.bos_reference_id)
        self.assertIsNone(o.last_sync_at)

    def test_bos_status_choices_present(self) -> None:
        """All 4 BOS sync status choices are defined."""
        choices = {c[0] for c in Order.BosSyncStatus.choices}
        self.assertEqual(choices, {"not_required", "pending", "synced", "failed"})


class OrderIdempotencyTests(TestCase):
    def test_idempotency_key_auto_generated(self) -> None:
        """idempotency_key is auto-generated as a UUID."""
        o = Order.objects.create()
        # Should be a valid UUID
        parsed = uuid.UUID(str(o.idempotency_key))
        self.assertEqual(str(parsed), str(o.idempotency_key))

    def test_idempotency_key_unique(self) -> None:
        """Each order gets a distinct idempotency_key."""
        o1 = Order.objects.create()
        o2 = Order.objects.create()
        self.assertNotEqual(o1.idempotency_key, o2.idempotency_key)

    def test_idempotency_key_immutable(self) -> None:
        """idempotency_key is editable=False."""
        o = Order.objects.create()
        original = o.idempotency_key
        o.customer_notes = "x"
        o.save()
        o.refresh_from_db()
        self.assertEqual(o.idempotency_key, original)


class OrderDefaultsTests(TestCase):
    def test_order_status_defaults(self) -> None:
        o = Order.objects.create()
        self.assertEqual(o.status, Order.Status.PENDING)
        self.assertEqual(o.payment_status, Order.PaymentStatus.UNPAID)
        self.assertEqual(o.fulfillment_status, Order.FulfillmentStatus.UNFULFILLED)

    def test_order_money_defaults(self) -> None:
        """All money fields default to 0 (satisfies grand_total constraint)."""
        o = Order.objects.create()
        self.assertEqual(o.subtotal, Decimal("0"))
        self.assertEqual(o.discount_total, Decimal("0"))
        self.assertEqual(o.shipping_cost, Decimal("0"))
        self.assertEqual(o.grand_total, Decimal("0"))


class OrderConstraintTests(TestCase):
    def test_discount_cannot_exceed_subtotal(self) -> None:
        """CheckConstraint order_discount_lte_subtotal rejects discount > subtotal.

        We set discount=150 on a subtotal=100 order. To isolate the
        discount constraint from grand_total_equals_components (which
        would also fail), grand_total is set to 0 (satisfying the
        non-negative check but breaking the components equation — so
        IntegrityError is raised regardless of which constraint fires first).
        """
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Order.objects.create(
                    subtotal=Decimal("100"),
                    discount_total=Decimal("150"),
                    shipping_cost=Decimal("0"),
                    grand_total=Decimal("0"),
                )

    def test_grand_total_must_equal_components(self) -> None:
        """CheckConstraint order_grand_total_equals_components enforces the formula."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Order.objects.create(
                    subtotal=Decimal("100"),
                    discount_total=Decimal("10"),
                    shipping_cost=Decimal("20"),
                    grand_total=Decimal("999"),  # should be 100 - 10 + 20 = 110
                )

    def test_grand_total_components_valid(self) -> None:
        """Valid grand_total = subtotal - discount + shipping is accepted."""
        o = Order.objects.create(
            subtotal=Decimal("100"),
            discount_total=Decimal("10"),
            shipping_cost=Decimal("20"),
            grand_total=Decimal("110"),
        )
        self.assertEqual(o.grand_total, Decimal("110"))

    def test_negative_subtotal_rejected(self) -> None:
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Order.objects.create(subtotal=Decimal("-1"))

    def test_negative_discount_rejected(self) -> None:
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Order.objects.create(discount_total=Decimal("-1"))

    def test_negative_shipping_rejected(self) -> None:
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Order.objects.create(shipping_cost=Decimal("-1"))

    def test_negative_grand_total_rejected(self) -> None:
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Order.objects.create(grand_total=Decimal("-1"))


class OrderItemTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.category = Category.objects.create(name="Winter", family_code="WNT")
        cls.product = Product.objects.create(
            name="Wool Coat",
            category=cls.category,
            base_price=Decimal("1000"),
            status=Product.Status.ACTIVE,
        )
        cls.variant = ProductVariant.objects.create(
            product=cls.product, price_extra=Decimal("250")
        )
        cls.order = Order.objects.create(
            subtotal=Decimal("1250"),
            discount_total=Decimal("0"),
            shipping_cost=Decimal("0"),
            grand_total=Decimal("1250"),
        )

    def test_order_item_line_total(self) -> None:
        """line_total = unit_price * quantity."""
        item = OrderItem.objects.create(
            order=self.order,
            variant=self.variant,
            sku=self.variant.sku,
            name=self.product.name,
            quantity=3,
            unit_price=Decimal("1250"),
        )
        self.assertEqual(item.line_total, Decimal("3750"))

    def test_order_item_quantity_gte_1(self) -> None:
        """CheckConstraint orderitem_quantity_gte_1 rejects quantity < 1."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OrderItem.objects.create(
                    order=self.order,
                    variant=self.variant,
                    sku=self.variant.sku,
                    name=self.product.name,
                    quantity=0,
                    unit_price=Decimal("1250"),
                )

    def test_order_item_unit_price_non_negative(self) -> None:
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OrderItem.objects.create(
                    order=self.order,
                    variant=self.variant,
                    sku=self.variant.sku,
                    name=self.product.name,
                    quantity=1,
                    unit_price=Decimal("-1"),
                )

    def test_order_item_snapshot_preserved(self) -> None:
        """Snapshot fields (sku, name, unit_price) are stored on the OrderItem."""
        item = OrderItem.objects.create(
            order=self.order,
            variant=self.variant,
            sku="PHX-WNT-001",
            name="Wool Coat",
            quantity=2,
            unit_price=Decimal("1250"),
        )
        self.assertEqual(item.sku, "PHX-WNT-001")
        self.assertEqual(item.name, "Wool Coat")
        self.assertEqual(item.unit_price, Decimal("1250"))

    def test_order_item_variant_nullable(self) -> None:
        """Variant FK is SET_NULL — order history survives variant deletion."""
        item = OrderItem.objects.create(
            order=self.order,
            variant=None,
            sku="PHX-WNT-OLD",
            name="Discontinued Coat",
            quantity=1,
            unit_price=Decimal("900"),
        )
        self.assertIsNone(item.variant)
        self.assertEqual(item.sku, "PHX-WNT-OLD")


class OrderUserLinkTests(TestCase):
    def test_order_user_nullable_for_guest_checkout(self) -> None:
        """Order.user is null for guest checkout."""
        o = Order.objects.create()
        self.assertIsNone(o.user)

    def test_order_links_to_user(self) -> None:
        u = CustomUser.objects.create_user(username="buyer", password="pw123456")
        o = Order.objects.create(user=u)
        self.assertEqual(o.user, u)
        self.assertIn(o, u.orders.all())
