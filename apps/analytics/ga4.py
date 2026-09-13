"""
GA4 (Google Analytics 4) integration helper.

Sends events to GA4 via the Measurement Protocol (server-side).
This is OPTIONAL — if GA4_MEASUREMENT_ID or GA4_API_SECRET are not set
in settings, send_event() becomes a no-op (graceful degradation).

Per دستور §8: analytics capture is non-blocking — failures are logged
but never break the user flow.

Usage::

    from apps.analytics.ga4 import send_page_view, send_ecommerce_event

    # Page view (server-side)
    send_page_view(client_id="123.456", page_path="/products/", page_title="Products")

    # Ecommerce purchase (server-side)
    send_ecommerce_event(
        client_id="123.456",
        event_name="purchase",
        order=order,
        items=order.items.all(),
    )

Wiring (config/settings/base.py)::

    GA4_MEASUREMENT_ID = env("GA4_MEASUREMENT_ID", default="")
    GA4_API_SECRET = env("GA4_API_SECRET", default="")

For client-side gtag.js tagging, see ``templates/analytics/ga4.html``
+ ``apps/analytics/context_processors.py``.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterable

from django.conf import settings


logger = logging.getLogger(__name__)


# GA4 Measurement Protocol endpoints.
# `collect` is the live endpoint; `debug_mp/collect` validates the payload
# without recording it (useful in CI / staging — toggled by GA4_DEBUG below).
_GA4_COLLECT_URL = "https://www.google-analytics.com/mp/collect"
_GA4_DEBUG_URL = "https://www.google-analytics.com/debug/mp/collect"

# Request timeout — short, because this is non-blocking fire-and-forget.
# If GA4 is slow we'd rather drop the event than stall the user's request.
_GA4_TIMEOUT_SECONDS = 3.0


def _is_configured() -> bool:
    """Return True iff GA4_MEASUREMENT_ID and GA4_API_SECRET are both set.

    Reads ``settings.GA4_MEASUREMENT_ID`` and ``settings.GA4_API_SECRET``.
    Empty / missing values mean the project hasn't been wired up for GA4
    yet — callers should treat the helpers in this module as no-ops.
    """
    return bool(
        getattr(settings, "GA4_MEASUREMENT_ID", "")
        and getattr(settings, "GA4_API_SECRET", "")
    )


def _debug_mode() -> bool:
    """Return True iff GA4_DEBUG is enabled (uses the debug endpoint)."""
    return bool(getattr(settings, "GA4_DEBUG", False))


def send_event(
    client_id: str,
    event_name: str,
    params: dict[str, Any] | None = None,
) -> bool:
    """Send a single GA4 Measurement Protocol event.

    Posts to ``https://www.google-analytics.com/mp/collect`` with the
    project's ``GA4_MEASUREMENT_ID`` + ``GA4_API_SECRET`` as query params
    and a JSON body containing the ``client_id`` + a single event.

    Args:
        client_id: GA4 client ID (anonymous, per-browser/device). For
            logged-in users this is typically derived from the session
            key or a stable cookie value. Must be non-empty.
        event_name: GA4 event name (e.g. ``page_view``, ``purchase``).
            Must be a non-empty string of 1-40 chars matching GA4's
            naming rules. Unknown names are still sent — GA4 will accept
            any custom event name.
        params: Optional dict of event params. Must be JSON-serializable.

    Returns:
        True if the event was sent successfully (HTTP 2xx), False
        otherwise (not configured, network error, non-2xx response, or
        invalid input). All failures are logged at WARNING / DEBUG level
        — no exceptions escape this function.

    Per دستور §8: this function is **non-blocking**. Any failure (network
    error, GA4 returning 5xx, malformed payload) is swallowed and logged
    — it must never break the user flow that called it.
    """
    try:
        if not _is_configured():
            logger.debug(
                "GA4 send_event('%s') skipped — GA4_MEASUREMENT_ID / "
                "GA4_API_SECRET not configured.", event_name,
            )
            return False

        if not client_id or not str(client_id).strip():
            logger.warning("GA4 send_event('%s') — empty client_id, skipping.", event_name)
            return False
        if not event_name or not str(event_name).strip():
            logger.warning("GA4 send_event() — empty event_name, skipping.")
            return False

        measurement_id = settings.GA4_MEASUREMENT_ID
        api_secret = settings.GA4_API_SECRET

        url = (
            f"{_GA4_DEBUG_URL if _debug_mode() else _GA4_COLLECT_URL}"
            f"?measurement_id={urllib.parse.quote(measurement_id)}"
            f"&api_secret={urllib.parse.quote(api_secret)}"
        )

        payload = {
            "client_id": str(client_id),
            "events": [
                {
                    "name": str(event_name),
                    "params": dict(params) if params else {},
                }
            ],
        }

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        with urllib.request.urlopen(req, timeout=_GA4_TIMEOUT_SECONDS) as resp:
            status = getattr(resp, "status", 200)
            # GA4 returns 204 on success (no body). 2xx is good enough.
            if 200 <= status < 300:
                logger.debug(
                    "GA4 send_event('%s') → %s OK", event_name, status,
                )
                return True
            logger.warning(
                "GA4 send_event('%s') → non-2xx status %s", event_name, status,
            )
            return False

    except urllib.error.URLError as exc:
        # Network / DNS / timeout — most common failure mode in practice.
        logger.warning("GA4 send_event('%s') network error: %s", event_name, exc)
        return False
    except Exception as exc:  # noqa: BLE001 — intentional broad catch
        # Non-blocking: any unexpected error is logged but not re-raised.
        logger.warning(
            "GA4 send_event('%s') unexpected error: %s", event_name, exc,
            exc_info=True,
        )
        return False


def send_page_view(
    client_id: str,
    page_path: str,
    page_title: str = "",
) -> bool:
    """Send a ``page_view`` event to GA4.

    Convenience wrapper around ``send_event()`` for the most common
    server-side tracking call. Pushes ``page_location`` (absolute URL),
    ``page_path``, and ``page_title`` as params.

    Args:
        client_id: GA4 client ID (see ``send_event``).
        page_path: The path component of the URL (e.g. ``/products/``).
            Must be non-empty.
        page_title: Optional page title for the GA4 report.

    Returns:
        True on success, False on failure (or not configured).
    """
    if not page_path:
        logger.warning("GA4 send_page_view() — empty page_path, skipping.")
        return False

    params: dict[str, Any] = {
        "page_path": str(page_path),
        "page_location": str(page_path),  # GA4 expects absolute; we send path.
    }
    if page_title:
        params["page_title"] = str(page_title)

    return send_event(client_id, "page_view", params)


def send_ecommerce_event(
    client_id: str,
    event_name: str,
    order=None,
    items: Iterable | None = None,
    value=None,
    currency: str = "EGP",
) -> bool:
    """Send a GA4 ecommerce event.

    Builds the GA4 ecommerce payload (``items`` array, ``value``,
    ``currency``, ``transaction_id``) from an Order + its OrderItems.

    Supported event names (per GA4 spec):
      - ``view_item`` — user viewed a product detail page
      - ``add_to_cart`` — user added an item to the cart
      - ``begin_checkout`` — user started the checkout flow
      - ``purchase`` — order was placed successfully
      - ``refund`` — order was refunded

    Args:
        client_id: GA4 client ID (see ``send_event``).
        event_name: One of the GA4 ecommerce event names above (or any
            custom event that follows the items/value/currency schema).
        order: Optional Order instance. If provided, its ``business_id``
            is used as ``transaction_id`` and its ``grand_total`` as
            ``value`` (unless ``value`` is explicitly passed).
        items: Optional iterable of OrderItem (or dict) rows. Each is
            converted to a GA4 item dict:
              - ``item_id``   ← item.sku (or dict's ``item_id``)
              - ``item_name`` ← item.name (or dict's ``item_name``)
              - ``price``     ← float(item.unit_price)
              - ``quantity``  ← int(item.quantity)
            If omitted and ``order`` is provided, ``order.items.all()``
            is used.
        value: Override for the monetary ``value`` param. If None,
            ``order.grand_total`` is used (when ``order`` is provided).
        currency: ISO 4217 currency code. Defaults to ``EGP``. Falls
            back to ``order.currency`` when an order is provided.

    Returns:
        True on success, False on failure (or not configured).
    """
    try:
        params: dict[str, Any] = {"currency": currency}

        # Pull value + transaction_id from the order if available.
        if order is not None:
            params["transaction_id"] = str(order.business_id)
            if value is None:
                try:
                    params["value"] = float(order.grand_total)
                except (TypeError, ValueError):
                    params["value"] = 0.0
            # Currency fallback from the order.
            order_ccy = getattr(order, "currency", None)
            if order_ccy and currency == "EGP":
                params["currency"] = str(order_ccy)

        if value is not None:
            try:
                params["value"] = float(value)
            except (TypeError, ValueError):
                logger.warning(
                    "GA4 send_ecommerce_event('%s') — invalid value %r, ignoring.",
                    event_name, value,
                )

        # Build the items array.
        item_dicts: list[dict[str, Any]] = []
        item_source = items
        if item_source is None and order is not None:
            item_source = order.items.all()

        if item_source is not None:
            for it in item_source:
                if isinstance(it, dict):
                    # Already a GA4 item dict — pass through.
                    item_dicts.append(dict(it))
                    continue
                # OrderItem-shaped object.
                try:
                    item_dicts.append({
                        "item_id": str(getattr(it, "sku", "")),
                        "item_name": str(getattr(it, "name", "")),
                        "price": float(getattr(it, "unit_price", 0) or 0),
                        "quantity": int(getattr(it, "quantity", 1) or 1),
                    })
                except (TypeError, ValueError):
                    logger.warning(
                        "GA4 send_ecommerce_event('%s') — skipping malformed item %r",
                        event_name, it,
                    )
                    continue

        if item_dicts:
            params["items"] = item_dicts

        return send_event(client_id, event_name, params)

    except Exception as exc:  # noqa: BLE001 — intentional broad catch
        logger.warning(
            "GA4 send_ecommerce_event('%s') unexpected error: %s",
            event_name, exc, exc_info=True,
        )
        return False
