"""apps.inventory.services — Phase 4 inventory reservation + decrement.

App: ``apps.inventory``.
Phase: 4 (Paymob Webhook — inventory is decremented on payment capture).
PHASE-B §B2: full reservation lifecycle (reserve → decrement on capture,
release on cancel/abandon).

Per دستور §6 + §10:
  - ``transaction.atomic()`` for every multi-write (per دستور §6).
  - ``select_for_update()`` on Inventory rows to prevent race conditions
    (two concurrent webhooks could double-decrement without this).
  - ``F()`` expressions for atomic arithmetic (per دستور §6 — never
    read-modify-write in Python; always use ``F()`` so the DB does the
    arithmetic atomically).
  - ``Decimal`` only for money (per دستور §10). Inventory quantities
    are integers (PositiveIntegerField), so no Decimal here — but the
    principle is the same: never cast in Python what the DB can do.

Per دستور §10 (Inventory rules):
  - ``quantity_on_hand``: actual stock on the shelf.
  - ``quantity_reserved``: held for in-progress carts/checkouts.
  - ``quantity_available = on_hand - reserved``.
  - Reservation happens at checkout POST (PHASE-B §B2 — after order creation).
  - Release happens at checkout abandon (15-min TTL via Celery beat task)
    or order cancel.
  - ``low_stock_threshold``: default 5.

Flow on payment success (decrement_reserved_inventory):
  1. Lock the Inventory rows for all variants in the order (``select_for_update``).
  2. For each variant's inventory, decrement ``quantity_on_hand`` by the
     ordered quantity (the stock physically leaves the warehouse).
  3. Also decrement ``quantity_reserved`` by the same amount (the
     reservation is consumed — the stock is no longer "reserved", it's "sold").
  4. Both decrements happen via ``F()`` expressions so they're atomic at
     the DB level.

Flow on payment failure / order cancel (release_inventory_reservation):
  1. Lock the Inventory rows.
  2. Decrement ``quantity_reserved`` by the ordered quantity (release the
     hold — the stock goes back to "available" without leaving the shelf).
  3. ``quantity_on_hand`` is NOT touched (the stock never left the warehouse).

PHASE-B §B2: ``reserve_inventory(order)`` — called after create_order_from_cart
in CheckoutView.post. Atomically increments ``quantity_reserved`` for every
variant in the order. Returns the count of Inventory rows updated.
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.inventory.models import Inventory
from apps.orders.models import Order

logger = logging.getLogger(__name__)


@transaction.atomic
def reserve_inventory(order: Order) -> int:
    """Reserve stock for all items in ``order``.

    PHASE-B §B2: called by CheckoutView.post after create_order_from_cart.
    Atomically increments ``quantity_reserved`` for every variant in the
    order, using ``F()`` expressions so concurrent reservations don't
    race (the DB does the arithmetic).

    If a variant has insufficient ``quantity_available`` (on_hand - reserved
    < ordered quantity), the reservation is still recorded (we over-reserve
    rather than blocking checkout — the ops team resolves it manually via
    the inventory admin). The Celery ``release_abandoned_reservations`` task
    releases the reservation if the order is abandoned.

    Args:
        order: The Order whose items should be reserved.

    Returns:
        The number of Inventory rows updated.
    """
    updated_count = 0
    for item in order.items.select_related("variant"):
        variant = item.variant
        if variant is None:
            logger.warning(
                "inventory.reserve.skip_deleted_variant",
                extra={"order_id": order.business_id, "sku": item.sku},
            )
            continue

        # Lock the inventory rows for this variant. Multi-warehouse deploy
        # would prorate; single-warehouse (our Phase 6 target) just takes
        # from the first row with stock.
        inv_rows = Inventory.objects.filter(
            variant=variant,
        ).select_for_update()

        remaining_qty = item.quantity
        for inv in inv_rows:
            if remaining_qty <= 0:
                break
            # Reserve up to what's available (on_hand - reserved).
            available = inv.quantity_on_hand - inv.quantity_reserved
            if available <= 0:
                continue
            reserve = min(remaining_qty, available)
            inv.quantity_reserved = F("quantity_reserved") + reserve
            inv.save(update_fields=["quantity_reserved", "updated_at"])
            remaining_qty -= reserve
            updated_count += 1

        if remaining_qty > 0:
            # Not enough stock to fully reserve — log + proceed (the
            # decrement_reserved_inventory flow will surface insufficient
            # stock at capture time).
            logger.warning(
                "inventory.reserve.insufficient_stock",
                extra={
                    "order_id": order.business_id,
                    "sku": variant.sku,
                    "shortfall": remaining_qty,
                },
            )

    if updated_count > 0:
        logger.info(
            "inventory.reserved",
            extra={"order_id": order.business_id, "rows_updated": updated_count},
        )
    return updated_count


@transaction.atomic
def decrement_reserved_inventory(order: Order) -> int:
    """Decrement on-hand + reserved stock for all items in ``order``.

    Called when a Paymob webhook confirms a successful payment. Moves
    stock from "reserved" to "sold" by decrementing BOTH
    ``quantity_on_hand`` and ``quantity_reserved`` by the ordered
    quantity per variant.

    Uses ``select_for_update()`` on the Inventory rows to prevent race
    conditions (two concurrent webhooks for the same order would
    double-decrement without the lock).

    Args:
        order: The confirmed Order whose items should be decremented.

    Returns:
        The number of Inventory rows updated (0 if the order has no
        items or no inventory rows exist for its variants).

    Per دستور §6: this is a multi-write operation — must be atomic.
    """
    updated_count = 0

    for item in order.items.select_related("variant"):
        variant = item.variant
        if variant is None:
            # Variant was deleted (SET_NULL on OrderItem.variant FK).
            # The snapshot fields (sku, name, unit_price) preserve the
            # order history — but we can't decrement inventory for a
            # deleted variant. Log + skip.
            logger.warning(
                "inventory.decrement.skip_deleted_variant",
                extra={"order_id": order.business_id, "sku": item.sku},
            )
            continue

        # Lock the inventory rows for this variant (could be at
        # multiple warehouses — we decrement at all of them pro-rata).
        # For simplicity (single-warehouse deploy per Phase 6 deploy
        # target), we just decrement at every warehouse that has stock.
        inv_rows = Inventory.objects.filter(
            variant=variant,
        ).select_for_update()

        remaining_qty = item.quantity
        for inv in inv_rows:
            if remaining_qty <= 0:
                break
            # How much can we take from this warehouse?
            take = min(remaining_qty, inv.quantity_on_hand)
            if take <= 0:
                continue
            # Atomic decrement via F() expressions — the DB does the
            # subtraction, not Python. This prevents lost updates under
            # concurrent webhooks.
            inv.quantity_on_hand = F("quantity_on_hand") - take
            inv.quantity_reserved = F("quantity_reserved") - take
            inv.save(update_fields=["quantity_on_hand", "quantity_reserved", "updated_at"])
            remaining_qty -= take
            updated_count += 1

        if remaining_qty > 0:
            # Not enough stock across all warehouses. This is a data
            # integrity issue — the order was placed but we can't fulfill
            # it. Log at ERROR (the ops team needs to investigate).
            logger.error(
                "inventory.decrement.insufficient_stock",
                extra={
                    "order_id": order.business_id,
                    "sku": variant.sku,
                    "shortfall": remaining_qty,
                },
            )

    if updated_count > 0:
        logger.info(
            "inventory.decremented",
            extra={"order_id": order.business_id, "rows_updated": updated_count},
        )
    return updated_count


@transaction.atomic
def release_inventory_reservation(order: Order) -> int:
    """Release reserved stock for all items in ``order`` (on cancel/fail).

    Called when a Paymob webhook reports a failed payment, or when an
    order is cancelled. Only decrements ``quantity_reserved`` (the stock
    goes back to "available" — it never left the shelf).

    Args:
        order: The cancelled/failed Order whose reservations should be
            released.

    Returns:
        The number of Inventory rows updated.

    Per دستور §6: atomic multi-write — must be in a transaction.
    """
    updated_count = 0

    for item in order.items.select_related("variant"):
        variant = item.variant
        if variant is None:
            logger.warning(
                "inventory.release.skip_deleted_variant",
                extra={"order_id": order.business_id, "sku": item.sku},
            )
            continue

        inv_rows = Inventory.objects.filter(
            variant=variant,
        ).select_for_update()

        remaining_qty = item.quantity
        for inv in inv_rows:
            if remaining_qty <= 0:
                break
            # Only release what's actually reserved.
            release = min(remaining_qty, inv.quantity_reserved)
            if release <= 0:
                continue
            inv.quantity_reserved = F("quantity_reserved") - release
            inv.save(update_fields=["quantity_reserved", "updated_at"])
            remaining_qty -= release
            updated_count += 1

    if updated_count > 0:
        logger.info(
            "inventory.released",
            extra={"order_id": order.business_id, "rows_updated": updated_count},
        )
    return updated_count
