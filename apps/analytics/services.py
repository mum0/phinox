"""
apps.analytics.services — attribution capture + event tracking.

Per دستور §8/§10: attribution (UTM + QR) is captured on session start,
events are tracked along the user journey, and attribution is linked
to an order at purchase time. No external analytics SDK is wired up
here — these functions write to the local Attribution / Event tables
for downstream reporting.
"""
from __future__ import annotations

from typing import Optional

from django.db import transaction

from apps.analytics.models import Attribution, Event
from apps.orders.models import Order


# Allowed UTM keys (extras in utm_data are silently ignored).
_UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")


def capture_attribution(
    session_key: str,
    utm_data: dict,
    qr_code: str = "",
) -> Attribution:
    """Create or update the Attribution row for ``session_key``.

    If an Attribution already exists for this session, its UTM / QR fields
    are updated (last-touch wins — ``first_seen_at`` is preserved via
    ``auto_now_add`` on the model). Otherwise a new row is created.

    Args:
        session_key: The session key (non-empty).
        utm_data: Dict that may contain any of ``utm_source``, ``utm_medium``,
            ``utm_campaign``, ``utm_content``, ``utm_term``. Unknown keys
            are ignored.
        qr_code: Optional QR code identifier.

    Returns:
        The created or updated Attribution.

    Raises:
        ValueError: If ``session_key`` is empty.
    """
    if not session_key or not session_key.strip():
        raise ValueError("session_key must be a non-empty string.")
    if not isinstance(utm_data, dict):
        raise ValueError("utm_data must be a dict.")

    # Sanitize utm_data — only known keys, only string values.
    clean = {
        k: str(v)
        for k, v in utm_data.items()
        if k in _UTM_KEYS and v is not None
    }
    clean["qr_code"] = qr_code or ""

    with transaction.atomic():
        attr, _created = Attribution.objects.update_or_create(
            session_key=session_key,
            defaults=clean,
        )
        return attr


def track_event(
    session_key: str,
    event_type: str,
    event_data: dict | None = None,
) -> Event:
    """Record a user-journey Event.

    Args:
        session_key: The session the event belongs to (non-empty).
        event_type: One of Event.EventType values.
        event_data: Optional JSON-serializable dict with event-specific
            payload (e.g. {"product_id": 1, "variant_sku": "PHX-WNT-001"}).

    Returns:
        The created Event.

    Raises:
        ValueError: If ``session_key`` is empty or ``event_type`` is not
            a valid EventType.
    """
    if not session_key or not session_key.strip():
        raise ValueError("session_key must be a non-empty string.")

    valid_types = {c for c, _ in Event.EventType.choices}
    if event_type not in valid_types:
        raise ValueError(
            f"event_type must be one of {sorted(valid_types)}, got {event_type!r}."
        )

    with transaction.atomic():
        return Event.objects.create(
            session_key=session_key,
            event_type=event_type,
            event_data=event_data or {},
        )


def link_attribution_to_order(
    order: Order, session_key: str
) -> Optional[Attribution]:
    """Link the session's Attribution to ``order`` at purchase time.

    Looks up the Attribution row for ``session_key`` and, if found, sets
    its ``order`` FK to ``order``. This is the final step that connects
    marketing attribution (UTM/QR) to a converted purchase.

    Args:
        order: The order to link the attribution to.
        session_key: The session key whose attribution should be linked.

    Returns:
        The updated Attribution, or None if no Attribution exists for
        this session_key (e.g. user arrived without UTM params).

    Raises:
        ValueError: If ``session_key`` is empty.
    """
    if not session_key or not session_key.strip():
        raise ValueError("session_key must be a non-empty string.")

    with transaction.atomic():
        try:
            attr = Attribution.objects.get(session_key=session_key)
        except Attribution.DoesNotExist:
            return None
        attr.order = order
        attr.save(update_fields=["order", "updated_at"])
        attr.refresh_from_db()
        return attr
