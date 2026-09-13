"""
apps.cart — Cart + CartItem.

Cart supports both authenticated users (OneToOneField) and guest sessions
(session_key). A CheckConstraint enforces user XOR session_key exclusivity.

Cart.subtotal is a computed property: sum(variant.unit_price * quantity).

Per دستور: no business logic in models beyond computed properties.
The add/remove/update logic lives in cart/services.py (Phase 2).
"""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.functional import cached_property

from apps.core.models import BusinessIDModel, BaseModel
from apps.promotions.models import PromoCode


class Cart(BusinessIDModel):
    """Shopping cart. Business ID: PHX-CART-000001.

    For authenticated users: one cart per user (OneToOneField).
    For guests: identified by session_key.
    A CheckConstraint enforces that exactly one of (user, session_key) is set.
    """

    BUSINESS_ID_PREFIX = "CART"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cart",
        null=True,
        blank=True,
    )
    session_key = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        db_index=True,
    )
    promo_code = models.ForeignKey(
        PromoCode,
        on_delete=models.SET_NULL,
        related_name="carts",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "cart_cart"
        indexes = [
            models.Index(fields=["session_key"], name="cart_session_idx"),
        ]
        constraints = [
            # user XOR session_key — exactly one must be set
            models.CheckConstraint(
                check=(
                    models.Q(user__isnull=False, session_key__isnull=True)
                    | models.Q(user__isnull=True, session_key__isnull=False)
                ),
                name="cart_user_xor_session_exclusive",
            ),
        ]

    @cached_property
    def subtotal(self) -> Decimal:
        """Sum of (effective unit_price * quantity) for all items.

        PHASE-B §B1: uses ``CartItem.unit_price_effective`` which prefers
        the price snapshot (frozen at add-time) over the live variant price.
        This means a price change on the variant AFTER the item was added
        to the cart does NOT propagate to the cart subtotal — the customer
        sees the price they agreed to.
        """
        total = Decimal("0")
        for item in self.items.all():
            total += item.unit_price_effective * item.quantity
        return total

    def __str__(self):
        ident = self.user.username if self.user_id else f"guest:{self.session_key}"
        return f"{self.business_id} ({ident})"


class CartItem(BaseModel):
    """A line item in a cart. Unique per cart+variant.

    PHASE-B §B1: ``unit_price_snapshot`` freezes the variant's price at
    the moment the item was added to the cart. This way, if the variant's
    ``price_extra`` (or the product's ``base_price``) changes while the
    item is still in the cart, the customer still sees the price they
    agreed to at add-time. The snapshot is nullable so existing CartItem
    rows (created before this field landed) don't break — the cart
    subtotal falls back to ``variant.unit_price`` when the snapshot is null.
    """

    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.CASCADE,
        related_name="cart_items",
    )
    quantity = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
    )
    unit_price_snapshot = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text=(
            "PHASE-B §B1: price snapshot at add-to-cart time. Null for legacy "
            "rows — the subtotal service falls back to variant.unit_price."
        ),
    )

    class Meta:
        db_table = "cart_item"
        indexes = [models.Index(fields=["cart"], name="cartitem_cart_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "variant"],
                name="uniq_cartitem_per_variant",
            ),
            models.CheckConstraint(
                check=models.Q(quantity__gte=1),
                name="cartitem_quantity_gte_1",
            ),
        ]

    def __str__(self):
        return f"{self.quantity}x {self.variant.sku}"

    @property
    def unit_price_effective(self) -> Decimal:
        """The price to charge for this cart line.

        PHASE-B §B1: returns ``unit_price_snapshot`` when set (frozen at
        add-to-cart time), else falls back to ``variant.unit_price``. This
        is what the cart subtotal + checkout order creation use, so a
        variant price bump mid-session doesn't change what the customer
        pays.
        """
        if self.unit_price_snapshot is not None:
            return self.unit_price_snapshot
        return self.variant.unit_price
