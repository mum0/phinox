"""apps.orders.tasks — Phase 4 + PHASE-B §B2 Celery tasks.

Tasks:
  - ``release_abandoned_reservations`` — runs every 5 minutes via Celery
    beat. Releases inventory reservations for orders that have been
    PENDING for more than 15 minutes without payment confirmation.
    The order is also marked CANCELLED so the customer sees a clear
    state in their order history.

PHASE-B §B2 spec:
  - Celery task: ``release_abandoned_reservations()`` every 5 minutes.
  - Trigger: Orders with status=PENDING + created_at < now - 15 min.
  - Action: release_inventory_reservation + mark order CANCELLED.

Per دستور §6 + §10:
  - ``transaction.atomic()`` per order so partial releases don't leave
    the inventory in an inconsistent state.
  - ``select_for_update()`` inside the release service prevents races
    with concurrent webhook handlers that might be confirming the
    same order at the same time the beat task fires.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.inventory.services import release_inventory_reservation
from apps.orders.models import Order

logger = logging.getLogger(__name__)

# PHASE-B §B2: 15-minute abandonment window. Orders in PENDING status
# older than this are considered abandoned → release the reservation.
ABANDONMENT_WINDOW = timedelta(minutes=15)


@shared_task
def release_abandoned_reservations() -> int:
    """Release inventory reservations for abandoned orders.

    PHASE-B §B2: scans for orders in PENDING status with
    ``created_at < now - 15min``. For each, calls
    ``release_inventory_reservation`` (idempotent — only releases what's
    actually reserved) and transitions the order to CANCELLED.

    Returns:
        The number of abandoned orders processed.
    """
    cutoff = timezone.now() - ABANDONMENT_WINDOW
    abandoned = Order.objects.filter(
        status=Order.Status.PENDING,
        created_at__lt=cutoff,
    )

    count = 0
    for order in abandoned.iterator():
        try:
            with transaction.atomic():
                # Re-lock the order row to prevent races with concurrent
                # webhook confirmations.
                locked_order = (
                    Order.objects.select_for_update().get(pk=order.pk)
                )
                # Re-check status inside the lock — a webhook may have
                # just confirmed the order (status no longer PENDING).
                if locked_order.status != Order.Status.PENDING:
                    logger.info(
                        "order.abandon_skip_already_processed",
                        extra={
                            "order_id": locked_order.business_id,
                            "current_status": locked_order.status,
                        },
                    )
                    continue
                # Release the inventory reservation.
                release_inventory_reservation(locked_order)
                # Mark the order as cancelled so the customer sees a clear
                # state in their order history. We bypass the forward-only
                # transition check since PENDING → CANCELLED is allowed
                # per FORWARD_TRANSITIONS anyway.
                locked_order.status = Order.Status.CANCELLED
                locked_order.save(update_fields=["status", "updated_at"])
                count += 1
                logger.info(
                    "order.abandoned_released",
                    extra={
                        "order_id": locked_order.business_id,
                        "abandoned_at": locked_order.created_at.isoformat(),
                    },
                )
        except Exception as exc:
            logger.error(
                "order.abandon_release_failed",
                extra={
                    "order_id": order.business_id,
                    "error_type": type(exc).__name__,
                    "error_msg": str(exc)[:200],
                },
                exc_info=True,
            )
    if count:
        logger.info(
            "order.abandoned_batch_complete",
            extra={"count": count, "cutoff": cutoff.isoformat()},
        )
    return count
