"""
apps.promotions.services — promo code validation + application.

Per دستور §7: promo codes are database-driven (no hard-coded codes).
This module validates a code against its active window / usage limits /
min_order_value, computes the discount, and links it to an order.

Discount calculation:
  - percentage: discount = subtotal * (value / 100), rounded to 2 dp
  - fixed:      discount = min(value, subtotal)  # never exceeds subtotal
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.db import transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from apps.accounts.models import CustomUser
from apps.orders.models import Order
from apps.promotions.models import PromoCode


def _round(value: Decimal) -> Decimal:
    """Round a Decimal to 2 decimal places (ROUND_HALF_UP)."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def validate_promo_code(
    code: str,
    order_subtotal: Decimal,
    user: CustomUser | None = None,
) -> PromoCode:
    """Validate a promo code against all its rules.

    Checks performed (in order):
      1. Code exists.
      2. ``is_active`` is True.
      3. Current time is within ``[starts_at, ends_at]`` (if set).
      4. ``order_subtotal >= min_order_value``.
      5. Total usage ``used_count < usage_limit`` (if usage_limit set).
      6. Per-customer usage ``< per_customer_limit`` (if set + user logged in).

    Args:
        code: The promo code string (case-sensitive).
        order_subtotal: The order's pre-discount subtotal. Must be >= 0.
        user: The authenticated user, or None for guest checkout.

    Returns:
        The validated PromoCode instance.

    Raises:
        ValueError: With a human-readable message if any check fails.
    """
    if not code or not code.strip():
        raise ValueError("Promo code is required.")
    if order_subtotal < 0:
        raise ValueError("order_subtotal must be >= 0.")

    try:
        promo = PromoCode.objects.get(code=code.strip())
    except PromoCode.DoesNotExist:
        raise ValueError(f"Promo code {code!r} does not exist.")

    if not promo.is_active:
        raise ValueError(f"Promo code {code!r} is no longer active.")

    now = timezone.now()
    if promo.starts_at and now < promo.starts_at:
        raise ValueError(f"Promo code {code!r} is not yet valid.")
    if promo.ends_at and now > promo.ends_at:
        raise ValueError(f"Promo code {code!r} has expired.")

    if order_subtotal < promo.min_order_value:
        raise ValueError(
            f"Order subtotal {order_subtotal} is below the minimum "
            f"{promo.min_order_value} for this promo code."
        )

    if not check_usage_limits(promo, user):
        raise ValueError(f"Promo code {code!r} has reached its usage limit.")

    return promo


def check_usage_limits(
    promo_code: PromoCode, user: CustomUser | None = None
) -> bool:
    """Return True if the promo code still has uses available.

    Checks:
      - Total usage: ``used_count < usage_limit`` (if usage_limit is set).
      - Per-customer usage: counted orders linked to this promo for ``user``
        must be < ``per_customer_limit`` (if both are set and user is logged in).

    Args:
        promo_code: The PromoCode to check.
        user: The authenticated user (None for guest — per-customer limit
            is skipped).

    Returns:
        True if the code can still be applied; False otherwise.
    """
    # Global usage limit
    if promo_code.usage_limit is not None:
        if promo_code.used_count >= promo_code.usage_limit:
            return False

    # Per-customer usage limit (only checkable for logged-in users)
    if user is not None and promo_code.per_customer_limit is not None:
        customer_uses = (
            Order.objects.filter(promo_code=promo_code, user=user)
            .exclude(status=Order.Status.CANCELLED)
            .count()
        )
        if customer_uses >= promo_code.per_customer_limit:
            return False

    return True


def apply_promo_code(order: Order, promo_code: PromoCode) -> Order:
    """Apply a validated promo code to an order.

    Computes the discount based on ``promo_code.discount_type``:
      - percentage: discount = order.subtotal * (value / 100), capped at subtotal
      - fixed:      discount = min(value, order.subtotal)

    Then:
      - Updates ``order.discount_total`` and re-derives ``grand_total``
        (grand_total = subtotal - discount_total + shipping_cost).
      - Links ``order.promo_code``.
      - Increments ``promo_code.used_count`` via ``F("used_count") + 1``
        so concurrent applies don't race (PHASE-B §B3).

    PHASE-B §B3 — single-use + race fix:
      - If ``order.promo_code`` is already set to a DIFFERENT code → raise
        ValueError ("order already has a different promo_code applied").
        Stacking is forbidden.
      - If ``order.promo_code`` is already set to the SAME code → no-op
        (idempotent — the second call doesn't re-apply the discount or
        re-increment the used_count).
      - ``select_for_update()`` on the PromoCode row prevents two
        concurrent checkouts from reading the same ``used_count`` value
        and double-incrementing past the ``usage_limit`` ceiling.
      - ``F("used_count") + 1`` ensures the increment is atomic at the
        DB level (no read-modify-write cycle in Python).

    The grand_total CheckConstraint (grand_total = subtotal - discount + shipping)
    is satisfied because both fields are updated together in a single
    transaction.

    Args:
        order: The order to apply the promo to. Must have a non-negative subtotal.
        promo_code: A *pre-validated* PromoCode (run validate_promo_code first).

    Returns:
        The updated Order (reloaded from DB).

    Raises:
        ValueError: If the computed discount would exceed the subtotal, or if
            the order already has a different promo_code applied (PHASE-B §B3).
    """
    if order.subtotal < 0:
        raise ValueError("order.subtotal must be >= 0.")

    # PHASE-B §B3: single-use enforcement.
    if order.promo_code_id is not None:
        if order.promo_code_id != promo_code.pk:
            raise ValueError(
                f"Order {order.business_id} already has a different "
                f"promo_code applied ({order.promo_code.code}). "
                f"Stacking is not allowed — cancel the order and re-place "
                f"with the new code."
            )
        # Same promo code already applied — idempotent no-op.
        return order

    if promo_code.discount_type == PromoCode.DiscountType.PERCENTAGE:
        discount = order.subtotal * (promo_code.value / Decimal("100"))
    elif promo_code.discount_type == PromoCode.DiscountType.FIXED:
        discount = promo_code.value
    else:  # pragma: no cover — defensive, choices are exhaustive
        raise ValueError(f"Unknown discount_type {promo_code.discount_type!r}.")

    discount = _round(discount)

    # Never let the discount exceed the subtotal (would violate the
    # order_discount_lte_subtotal CheckConstraint).
    if discount > order.subtotal:
        discount = order.subtotal

    with transaction.atomic():
        # PHASE-B §B3: lock the PromoCode row so two concurrent checkouts
        # can't both read used_count=0 and both increment to 1 (passing
        # the usage_limit=1 check on both threads).
        locked_promo = (
            PromoCode.objects.select_for_update().get(pk=promo_code.pk)
        )
        # Re-check the usage limit inside the lock (a concurrent apply may
        # have just incremented past the limit).
        if locked_promo.usage_limit is not None and locked_promo.used_count >= locked_promo.usage_limit:
            raise ValueError(
                f"Promo code {locked_promo.code!r} has reached its usage "
                f"limit ({locked_promo.usage_limit})."
            )

        order.discount_total = discount
        order.grand_total = order.subtotal - discount + order.shipping_cost
        order.promo_code = locked_promo
        order.save(update_fields=[
            "discount_total",
            "grand_total",
            "promo_code",
            "updated_at",
        ])

        # PHASE-B §B3: atomic increment via F() expression. The DB does
        # the +1, not Python — so concurrent applies don't lose updates.
        PromoCode.objects.filter(pk=locked_promo.pk).update(
            used_count=F("used_count") + 1
        )
        # Refresh so the in-memory order.promo_code reflects the new
        # used_count (in case the caller inspects it after this call).
        locked_promo.refresh_from_db()
        order.refresh_from_db()
        return order
