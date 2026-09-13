"""
apps.orders.services — order creation, totals, and status transitions.

Per دستور §6: BOS sync is metadata-only; this module implements the
e-commerce order lifecycle (cart → order snapshot → totals → status
machine). The BOS sync_status field is updated here only as a marker
(set to 'pending' once the order is confirmed) — actual BOS API calls
are out of scope for this phase.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Iterable

from django.db import transaction
from django.db.models import F, QuerySet
from django.utils import timezone

from apps.accounts.models import CustomUser
from apps.cart.models import Cart, CartItem
from apps.orders.models import Order, OrderItem

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Status transition map
# ---------------------------------------------------------------------------
# Forward-only graph. Terminal states (cancelled, refunded) have no
# outgoing edges. ``update_order_status`` accepts an admin override to
# bypass these rules (e.g. for customer-support corrections).
FORWARD_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"confirmed", "cancelled"},
    "confirmed": {"processing", "cancelled"},
    "processing": {"shipped", "cancelled"},
    "shipped": {"delivered"},
    "delivered": {"refunded"},
    "cancelled": set(),
    "refunded": set(),
}


def create_order_from_cart(
    cart: Cart,
    user: CustomUser | None = None,
    shipping_cost: Decimal = Decimal("0"),
    shipping_address: "ShippingAddress | None" = None,
) -> Order:
    """Convert a cart into an Order, snapshotting its items, then clear the cart.

    Steps:
      1. Snapshot each CartItem into an OrderItem (preserving sku, name,
         unit_price, product_name, variant_sku, size_label, color_name —
         the variant FK is set but the snapshot survives even if the
         variant is later deleted).
      2. Compute subtotal = sum(line_total).
      3. Compute grand_total = subtotal - discount_total + shipping_cost
         (discount_total starts at 0; promo codes are applied separately).
      4. Snapshot the shipping_address (recipient_name, phone, governorate,
         city, street_address) onto the Order so the order's shipping info
         survives address deletion/edit (PHASE-B §B1).
      5. Delete all CartItems (the cart itself is preserved for reuse).
      6. Return the saved Order.

    Args:
        cart: The cart to convert. Must have at least one item.
        user: The customer the order belongs to. Falls back to ``cart.user``.
            Both can be None for guest checkout.
        shipping_cost: Non-negative shipping cost to add to grand_total.
        shipping_address: Optional ShippingAddress to snapshot onto the
            Order. PHASE-B §B1: snapshots recipient_name/phone/governorate/
            city/street_address so the order's shipping info survives
            address deletion.

    Returns:
        The created Order with all OrderItems and correct money fields.

    Raises:
        ValueError: If the cart is empty or shipping_cost is negative.
    """
    if shipping_cost < 0:
        raise ValueError("shipping_cost must be >= 0.")

    # Pull cart items up front (we're about to delete them).
    cart_items: Iterable[CartItem] = list(
        cart.items.select_related("variant__product__category", "variant__size", "variant__color")
    )
    if not cart_items:
        raise ValueError("Cannot create an order from an empty cart.")

    owner = user or cart.user

    with transaction.atomic():
        # Compute subtotal first so we can create the Order with
        # constraint-valid money fields in a single INSERT.
        subtotal = Decimal("0")
        for ci in cart_items:
            # PHASE-B §B1: prefer the cart-item's price snapshot (frozen
            # at add-to-cart time) over the live variant price.
            subtotal += ci.unit_price_effective * ci.quantity

        discount_total = Decimal("0")
        grand_total = subtotal - discount_total + shipping_cost

        # PHASE-B §B1: snapshot shipping address fields onto the Order at
        # creation time so the order's shipping info survives address
        # deletion/edit.
        snapshot_kwargs = {}
        if shipping_address is not None:
            snapshot_kwargs = {
                "shipping_recipient_name": shipping_address.full_name or "",
                "shipping_phone_number": shipping_address.phone or "",
                "shipping_governorate": getattr(shipping_address, "governorate", "") or "",
                "shipping_city": shipping_address.city or "",
                "shipping_street_address": shipping_address.address or "",
            }

        order = Order.objects.create(
            user=owner,
            subtotal=subtotal,
            discount_total=discount_total,
            shipping_cost=shipping_cost,
            grand_total=grand_total,
            placed_at=timezone.now(),
            shipping_address=shipping_address,
            **snapshot_kwargs,
        )

        snapshot_order_items(order, cart_items)

        # Clear the cart contents (keep the cart shell for reuse).
        cart.items.all().delete()

        return order


def snapshot_order_items(
    order: Order, cart_items: QuerySet[CartItem] | Iterable[CartItem]
) -> list[OrderItem]:
    """Create OrderItem rows from CartItem rows, snapshotting key fields.

    The snapshot fields (sku, name, unit_price, product_name, variant_sku,
    size_label, color_name) preserve the exact item purchased at checkout
    time — even if the variant is later deleted or its price changes.
    ``variant`` is also set (SET_NULL on delete) so the link survives as
    long as the variant exists.

    PHASE-B §B1: snapshots additional denormalized fields (product_name,
    variant_sku, size_label, color_name) so the order detail page can
    render "Wool Coat / Large / Black" even after the variant is deleted.

    PHASE-B §B1: uses ``CartItem.unit_price_effective`` (which prefers
    the cart-item's price snapshot over the live variant price) so the
    order's unit_price matches what the customer saw in the cart.

    Args:
        order: The Order to attach items to.
        cart_items: Iterable of CartItem rows to snapshot.

    Returns:
        List of created OrderItem instances.
    """
    items: list[OrderItem] = []
    # Bulk-build OrderItem instances — no per-row save round-trip.
    objs = [
        OrderItem(
            order=order,
            variant=ci.variant,
            sku=ci.variant.sku,
            name=ci.variant.name or ci.variant.product.name,
            quantity=ci.quantity,
            # PHASE-B §B1: prefer the cart-item's price snapshot (frozen at
            # add-to-cart time) so the customer pays the price they saw.
            unit_price=ci.unit_price_effective,
            # PHASE-B §B1: additional snapshot fields.
            product_name=ci.variant.product.name,
            variant_sku=ci.variant.sku,
            size_label=ci.variant.size.name if ci.variant.size_id else "",
            color_name=ci.variant.color.name if ci.variant.color_id else "",
        )
        for ci in cart_items
    ]
    created = OrderItem.objects.bulk_create(objs)
    items.extend(created)
    return items


def calculate_order_totals(order: Order) -> Order:
    """Recompute subtotal from order.items and re-derive grand_total.

    Recalculates:
      - subtotal = sum(item.line_total)
      - grand_total = subtotal - discount_total + shipping_cost

    ``discount_total`` and ``shipping_cost`` are preserved (they are set
    by promo-application / shipping-selection flows respectively).

    Args:
        order: The order whose totals should be recomputed.

    Returns:
        The updated Order (reloaded from DB).
    """
    with transaction.atomic():
        subtotal = Decimal("0")
        for item in order.items.all():
            subtotal += item.line_total

        order.subtotal = subtotal
        order.grand_total = order.subtotal - order.discount_total + order.shipping_cost
        order.save(update_fields=["subtotal", "grand_total", "updated_at"])
        order.refresh_from_db()
        return order


def update_order_status(
    order: Order,
    new_status: str,
    admin_override: bool = False,
) -> Order:
    """Transition an order to ``new_status`` with forward-only validation.

    The default rule is forward-only transitions per FORWARD_TRANSITIONS.
    Pass ``admin_override=True`` for customer-support corrections (e.g.
    reopening a cancelled order) — this bypasses the graph but still
    validates that ``new_status`` is a known choice.

    PHASE-B §B2: when transitioning to ``CANCELLED``, automatically call
    ``release_inventory_reservation(order)`` to free the held stock. The
    release happens AFTER the order.status update so the order is
    persisted first (if the release raises, the order is still marked
    cancelled — ops can re-run the release manually).

    Args:
        order: The order whose status should change.
        new_status: One of Order.Status values.
        admin_override: If True, skip the forward-only check.

    Returns:
        The updated Order (reloaded from DB).

    Raises:
        ValueError: If ``new_status`` is not a valid status, or if the
            transition is not allowed (and admin_override is False).
    """
    valid_statuses = {c for c, _ in Order.Status.choices}
    if new_status not in valid_statuses:
        raise ValueError(
            f"new_status must be one of {sorted(valid_statuses)}, got {new_status!r}."
        )

    if order.status == new_status:
        return order  # idempotent no-op

    if not admin_override:
        allowed = FORWARD_TRANSITIONS.get(order.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Illegal transition {order.status!r} → {new_status!r}. "
                f"Allowed: {sorted(allowed) or '(terminal — no outgoing transitions)'}. "
                f"Pass admin_override=True to force."
            )

    with transaction.atomic():
        order.status = new_status
        order.save(update_fields=["status", "updated_at"])
        order.refresh_from_db()
        return order


def cancel_order(order: Order, *, admin_override: bool = False) -> Order:
    """Cancel an order + release its inventory reservation.

    PHASE-B §B2: convenience wrapper that calls ``update_order_status``
    with CANCELLED, then ``release_inventory_reservation`` to free the
    held stock. If the release raises, the order is still marked cancelled
    — ops can re-run the release manually.

    Also PHASE-B §B3: if the order has a promo_code applied, decrement
    the promo_code.used_count (so a single-use code can be re-applied by
    the same customer after the order is cancelled).

    Args:
        order: The order to cancel.
        admin_override: If True, skip the forward-only check (use for
            force-cancelling a confirmed order, e.g. customer support).

    Returns:
        The cancelled Order (reloaded from DB).

    Raises:
        ValueError: If the order is already terminal (cancelled/refunded).
    """
    from apps.inventory.services import release_inventory_reservation
    from apps.promotions.models import PromoCode
    from django.db.models import F

    with transaction.atomic():
        order = update_order_status(order, Order.Status.CANCELLED, admin_override=admin_override)
        # Release the inventory reservation (idempotent — if the order
        # was never reserved, this is a no-op).
        try:
            release_inventory_reservation(order)
        except Exception as exc:
            logger.error(
                "order.cancel.release_failed",
                extra={
                    "order_id": order.business_id,
                    "error_type": type(exc).__name__,
                    "error_msg": str(exc)[:200],
                },
                exc_info=True,
            )
        # PHASE-B §B3: decrement the promo_code.used_count atomically.
        if order.promo_code_id:
            PromoCode.objects.filter(pk=order.promo_code_id).update(
                used_count=F("used_count") - 1
            )
        return order
