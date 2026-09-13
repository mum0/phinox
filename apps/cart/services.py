"""
apps.cart.services — cart mutation + subtotal business logic.

Per دستور: models hold no business logic beyond computed properties.
All add/remove/update operations live here so the constraint
``uniq_cartitem_per_variant`` is respected (we update quantity on an
existing item rather than creating a duplicate).
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from apps.cart.models import Cart, CartItem
from apps.catalog.models import ProductVariant


def add_to_cart(cart: Cart, variant: ProductVariant, quantity: int = 1) -> CartItem:
    """Add ``quantity`` of ``variant`` to ``cart``, merging into an existing item.

    If a CartItem for (cart, variant) already exists (the unique constraint
    uniq_cartitem_per_variant enforces this), its quantity is incremented by
    ``quantity`` instead of creating a duplicate.

    PHASE-B §B1: snapshots ``variant.unit_price`` into
    ``CartItem.unit_price_snapshot`` at creation time. If the item already
    exists, the snapshot is NOT refreshed (the customer keeps the price
    they originally agreed to). This is the denormalization the دستور §6
    snapshot rule mandates.

    Args:
        cart: The cart to add to.
        variant: The product variant being added.
        quantity: How many units to add. Must be >= 1.

    Returns:
        The created or updated CartItem.

    Raises:
        ValueError: If ``quantity`` is less than 1.
    """
    if quantity < 1:
        raise ValueError("quantity must be >= 1.")

    with transaction.atomic():
        item, created = CartItem.objects.get_or_create(
            cart=cart,
            variant=variant,
            defaults={
                "quantity": quantity,
                # PHASE-B §B1: snapshot the variant's effective price at
                # add-to-cart time. Falls back to None if variant.unit_price
                # raises (shouldn't happen — variants always have a price).
                "unit_price_snapshot": variant.unit_price,
            },
        )
        if not created:
            # Existing item: increment quantity, keep the original snapshot
            # (the customer keeps their original add-time price).
            item.quantity += quantity
            item.save(update_fields=["quantity", "updated_at"])
        return item


def update_cart_item(item: CartItem, quantity: int) -> CartItem:
    """Set the absolute quantity on an existing CartItem.

    Args:
        item: The CartItem to update.
        quantity: The new absolute quantity. Must be >= 1; to remove an item
            use ``remove_cart_item``.

    Returns:
        The updated CartItem (reloaded from DB).

    Raises:
        ValueError: If ``quantity`` is less than 1.
    """
    if quantity < 1:
        raise ValueError("quantity must be >= 1; use remove_cart_item() to delete.")

    with transaction.atomic():
        item.quantity = quantity
        item.save(update_fields=["quantity", "updated_at"])
        item.refresh_from_db()
        return item


def remove_cart_item(item: CartItem) -> None:
    """Delete a CartItem from its cart.

    Args:
        item: The CartItem to remove.
    """
    with transaction.atomic():
        item.delete()


def calculate_cart_subtotal(cart: Cart) -> Decimal:
    """Compute the cart subtotal: sum(item.unit_price_effective * quantity).

    This mirrors ``Cart.subtotal`` but is exposed as a service-layer function
    for callers that don't want to depend on the model property (e.g. for
    transactional recalculation after mutations).

    PHASE-B §B1: prefers ``CartItem.unit_price_snapshot`` over
    ``variant.unit_price`` so a mid-session variant price bump doesn't
    change what the customer pays.

    Args:
        cart: The cart whose subtotal should be calculated.

    Returns:
        The subtotal as a Decimal, or Decimal("0") for an empty cart.
    """
    total = Decimal("0")
    for item in cart.items.select_related("variant__product__category"):
        total += item.unit_price_effective * item.quantity
    return total
