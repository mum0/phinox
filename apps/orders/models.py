"""
apps.orders — Order + OrderItem with BOS sync metadata fields.

Per دستور §6/§13: bos_sync_status, bos_reference_id, last_sync_at are
SYNC METADATA ONLY — no BOS integration logic is implemented here or
anywhere in this codebase. These fields exist so the Order schema is
ready for a future BOS integration phase.

Stable IDs:
  - Order.business_id → PHX-ORD-000001 (via BusinessIDModel)

CheckConstraints:
  - discount_total <= subtotal
  - grand_total = subtotal - discount_total + shipping_cost
  - quantities > 0
  - all money fields >= 0
"""
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.functional import cached_property

from apps.core.models import BaseModel, BusinessIDModel
from apps.promotions.models import PromoCode


class Order(BusinessIDModel):
    """An e-commerce order. Business ID: PHX-ORD-000001.

    BOS sync fields are metadata only (no logic):
      - bos_sync_status: 'not_required' | 'pending' | 'synced' | 'failed'
      - bos_reference_id: null until BOS assigns one (future phase)
      - last_sync_at: null until first sync (future phase)

    The idempotency_key is a UUID for safe retries in payment/checkout flows.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        PROCESSING = "processing", "Processing"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "Unpaid"
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    class FulfillmentStatus(models.TextChoices):
        UNFULFILLED = "unfulfilled", "Unfulfilled"
        FULFILLED = "fulfilled", "Fulfilled"
        RETURNED = "returned", "Returned"

    class BosSyncStatus(models.TextChoices):
        NOT_REQUIRED = "not_required", "Not Required"
        PENDING = "pending", "Pending"
        SYNCED = "synced", "Synced"
        FAILED = "failed", "Failed"

    BUSINESS_ID_PREFIX = "ORD"

    # --- Customer ----------------------------------------------------------
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="orders",
        null=True,
        blank=True,
        help_text="Null for guest checkout orders.",
    )

    # --- Shipping -----------------------------------------------------------
    shipping_address = models.ForeignKey(
        "shipping.ShippingAddress",
        on_delete=models.SET_NULL,
        related_name="orders",
        null=True,
        blank=True,
        help_text="Saved shipping address used for this order. SET_NULL so order history survives address deletion.",
    )

    # PHASE-B §B1: shipping snapshot fields. Denormalized from the
    # ShippingAddress at order-placement time so the order's shipping
    # label + delivery info survive even if the address is later deleted
    # or edited. Per دستور §6: snapshot denormalization on Order is
    # deliberate — do NOT normalize it away.
    shipping_recipient_name = models.CharField(
        max_length=150, blank=True,
        help_text="Snapshot of ShippingAddress.full_name at order time.",
    )
    shipping_phone_number = models.CharField(
        max_length=20, blank=True,
        help_text="Snapshot of ShippingAddress.phone at order time.",
    )
    shipping_governorate = models.CharField(
        max_length=32, blank=True,
        help_text="Egyptian governorate (27 values). Snapshot at order time.",
    )
    shipping_city = models.CharField(
        max_length=100, blank=True,
        help_text="Snapshot of ShippingAddress.city at order time.",
    )
    shipping_street_address = models.TextField(
        blank=True,
        help_text="Snapshot of ShippingAddress.address at order time.",
    )

    # --- Status ------------------------------------------------------------
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    payment_status = models.CharField(
        max_length=16,
        choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID,
    )
    fulfillment_status = models.CharField(
        max_length=16,
        choices=FulfillmentStatus.choices,
        default=FulfillmentStatus.UNFULFILLED,
    )

    # --- Promo -------------------------------------------------------------
    promo_code = models.ForeignKey(
        PromoCode,
        on_delete=models.SET_NULL,
        related_name="orders",
        null=True,
        blank=True,
    )

    # --- Money -------------------------------------------------------------
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(0)],
    )
    discount_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(0)],
    )
    shipping_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(0)],
    )
    grand_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(0)],
    )
    currency = models.CharField(max_length=3, default="EGP")

    # --- Timestamps --------------------------------------------------------
    placed_at = models.DateTimeField(null=True, blank=True)
    customer_notes = models.TextField(blank=True)

    # --- BOS sync metadata (no logic — schema only per دستور §6/§13) -----
    bos_sync_status = models.CharField(
        max_length=16,
        choices=BosSyncStatus.choices,
        default=BosSyncStatus.NOT_REQUIRED,
    )
    bos_reference_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        editable=False,
        help_text="BOS-assigned reference ID. Null until BOS integration phase.",
    )
    last_sync_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        help_text="Last BOS sync timestamp. Null until BOS integration phase.",
    )

    # --- Idempotency -------------------------------------------------------
    idempotency_key = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        help_text="For safe retries in payment/checkout flows.",
    )

    class Meta:
        db_table = "orders_order"
        indexes = [
            models.Index(fields=["business_id"], name="order_business_id_idx"),
            models.Index(fields=["user", "-created_at"], name="order_user_created_idx"),
            models.Index(fields=["status"], name="order_status_idx"),
            models.Index(fields=["payment_status"], name="order_payment_status_idx"),
            models.Index(fields=["bos_sync_status"], name="order_bos_sync_idx"),
        ]
        constraints = [
            # All money fields non-negative
            models.CheckConstraint(check=models.Q(subtotal__gte=0), name="order_subtotal_non_negative"),
            models.CheckConstraint(check=models.Q(discount_total__gte=0), name="order_discount_non_negative"),
            models.CheckConstraint(check=models.Q(shipping_cost__gte=0), name="order_shipping_non_negative"),
            models.CheckConstraint(check=models.Q(grand_total__gte=0), name="order_grand_total_non_negative"),
            # discount_total cannot exceed subtotal
            models.CheckConstraint(
                check=models.Q(discount_total__lte=models.F("subtotal")),
                name="order_discount_lte_subtotal",
            ),
            # grand_total = subtotal - discount_total + shipping_cost
            models.CheckConstraint(
                check=models.Q(
                    grand_total=models.F("subtotal")
                    - models.F("discount_total")
                    + models.F("shipping_cost")
                ),
                name="order_grand_total_equals_components",
            ),
        ]

    def __str__(self):
        return f"{self.business_id}"


class OrderItem(BaseModel):
    """A purchased line item. Snapshots the SKU/name/price at purchase time.

    The variant FK is nullable (SET_NULL) so order history survives even
    if the variant is later deleted from the catalog. The snapshot fields
    (sku, name, unit_price) preserve the exact item purchased.

    PHASE-B §B1: added ``product_name``, ``variant_sku``, ``size_label``,
    ``color_name`` as additional denormalized fields. The pre-existing
    ``sku`` + ``name`` fields are KEPT (per spec "احتفظ بالموجود") —
    ``variant_sku`` is the SKU snapshot (same value as ``sku``), added
    for clarity alongside ``product_name``; ``size_label`` and
    ``color_name`` snapshot the variant's size/color names so the order
    detail page can render "Large / Black" even after the variant is
    deleted.

    line_total is a computed property: unit_price * quantity.
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.SET_NULL,
        related_name="order_items",
        null=True,
        blank=True,
    )
    # Snapshot fields (preserve order history accuracy)
    sku = models.CharField(max_length=30)
    name = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )

    # PHASE-B §B1: additional snapshot fields (per critical-remediation spec).
    # All nullable/blank=True so the migration applies cleanly to existing rows.
    product_name = models.CharField(
        max_length=200, blank=True,
        help_text="Snapshot of Product.name at order time.",
    )
    variant_sku = models.CharField(
        max_length=30, blank=True,
        help_text="Snapshot of ProductVariant.sku (same value as ``sku``; duplicated for clarity).",
    )
    size_label = models.CharField(
        max_length=20, blank=True,
        help_text="Snapshot of ProductVariant.size.name (e.g. 'XL').",
    )
    color_name = models.CharField(
        max_length=60, blank=True,
        help_text="Snapshot of ProductVariant.color.name (e.g. 'Fire Orange').",
    )

    class Meta:
        db_table = "orders_order_item"
        indexes = [models.Index(fields=["order"], name="orderitem_order_idx")]
        constraints = [
            models.CheckConstraint(check=models.Q(quantity__gte=1), name="orderitem_quantity_gte_1"),
            models.CheckConstraint(check=models.Q(unit_price__gte=0), name="orderitem_unit_price_non_negative"),
        ]

    @cached_property
    def line_total(self) -> Decimal:
        """Computed: unit_price * quantity.

        Memoized per-instance via ``cached_property`` — the order
        confirmation template often renders this once per line item
        (and the order summary may sum line_totals), so caching avoids
        redundant arithmetic on repeated access within the same request.
        """
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.quantity}x {self.sku} ({self.order.business_id})"
