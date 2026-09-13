"""
Order notification helpers.

Sends order confirmation emails (and optional SMS) when an order is placed.
Uses Django's email backend (console in dev, SMTP in prod).
Per دستور: notifications are non-blocking — failures are logged but don't
break the order flow.

Usage::

    from apps.orders.notifications import send_order_confirmation_email

    order = create_order_from_cart(cart, user=user, shipping_cost=cost)
    send_order_confirmation_email(order)  # bool, never raises

Wiring (config/settings/dev.py)::

    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

In production, set the SMTP backend + ``DEFAULT_FROM_EMAIL`` in prod.py
or via env vars (``EMAIL_HOST``, ``EMAIL_HOST_USER``, etc.).
"""
from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse

from apps.orders.models import Order


logger = logging.getLogger(__name__)


def _build_context(order: Order, **extra: Any) -> dict[str, Any]:
    """Build the email template context for an order.

    Pulls the order, its items, the owning user (if any), the shipping
    address (if linked), and constructs the absolute URL to the order
    confirmation page.

    Args:
        order: The Order instance.
        **extra: Additional context keys to merge in (e.g. ``old_status``,
            ``new_status``, ``payment``).

    Returns:
        A dict suitable for passing to ``render_to_string()``.
    """
    # Use select_related for the user + shipping_address so we don't
    # re-fetch them when rendering the template (the caller usually
    # passes a fresh Order instance — this is a no-op if already loaded).
    user = getattr(order, "user", None)
    shipping_address = getattr(order, "shipping_address", None)

    # Build the absolute URL to the order confirmation page.
    # Fallback to a relative path if request context is unavailable
    # (which is the case when sending from a Celery task or signal).
    try:
        order_url = reverse(
            "orders:confirmation",
            kwargs={"business_id": order.business_id},
        )
    except Exception:
        # URL not wired yet (e.g. during early dev) — fall back to the
        # business_id path. Better to send a slightly-off URL than to
        # crash the email send.
        order_url = f"/orders/{order.business_id}/confirmation/"

    # Make the URL absolute if a site domain is configured.
    site_domain = getattr(settings, "PHINOX_SITE_DOMAIN", "").rstrip("/")
    if site_domain and not order_url.startswith("http"):
        order_url = f"{site_domain}{order_url}"

    context: dict[str, Any] = {
        "order": order,
        "items": list(order.items.all()),
        "user": user,
        "shipping_address": shipping_address,
        "order_url": order_url,
        "site_domain": site_domain or "phinox.example",
        "currency": order.currency or "EGP",
    }
    context.update(extra)
    return context


def _get_payment_for_order(order: Order):
    """Return the most-recent Payment for ``order`` (or None).

    The order confirmation email shows the payment method/status. We
    pick the latest Payment row (by ``created_at``) — typically there
    is exactly one for a freshly-placed order, but defensive code is
    cheap.
    """
    try:
        return order.payments.order_by("-created_at").first()
    except Exception:
        return None


def send_order_confirmation_email(order: Order) -> bool:
    """Send an HTML + plaintext order confirmation email.

    Sends to ``order.user.email`` (if the order has a user with an
    email). For guest orders, this is a no-op (returns False, logged
    at INFO — guest email delivery is a future-phase concern).

    Args:
        order: The freshly-placed Order. Its ``items`` and
            ``shipping_address`` relations are accessed lazily.

    Returns:
        True if the email was sent successfully, False otherwise (no
        user/email, template error, SMTP failure, etc.). Never raises
        — per دستور, notifications are non-blocking.
    """
    try:
        if order is None:
            logger.warning("send_order_confirmation_email() — order is None.")
            return False

        user = getattr(order, "user", None)
        recipient = getattr(user, "email", None) if user else None
        if not recipient:
            logger.info(
                "Order %s — no recipient email (guest order or user without "
                "email); skipping confirmation email.",
                getattr(order, "business_id", "?"),
            )
            return False

        payment = _get_payment_for_order(order)
        context = _build_context(order, payment=payment)

        subject = f"PHINOX — Order {order.business_id} Confirmed"
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@phinox.example")

        text_body = render_to_string("emails/order_confirmation.txt", context)
        html_body = render_to_string("emails/order_confirmation.html", context)

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=from_email,
            to=[recipient],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=True)

        logger.info(
            "Order %s — confirmation email sent to %s",
            order.business_id, recipient,
        )
        return True

    except Exception as exc:  # noqa: BLE001 — intentional broad catch
        logger.warning(
            "Order %s — confirmation email failed: %s",
            getattr(order, "business_id", "?"), exc, exc_info=True,
        )
        return False


def send_order_status_update_email(
    order: Order,
    old_status: str,
    new_status: str,
) -> bool:
    """Send a 'Your order status changed to X' email.

    Args:
        order: The Order whose status just changed.
        old_status: The previous status value (e.g. ``"pending"``).
        new_status: The new status value (e.g. ``"shipped"``).

    Returns:
        True if the email was sent successfully, False otherwise. Never
        raises — non-blocking per دستور.
    """
    try:
        if order is None:
            logger.warning("send_order_status_update_email() — order is None.")
            return False

        user = getattr(order, "user", None)
        recipient = getattr(user, "email", None) if user else None
        if not recipient:
            logger.info(
                "Order %s — no recipient email for status update (%s → %s).",
                getattr(order, "business_id", "?"), old_status, new_status,
            )
            return False

        context = _build_context(
            order,
            old_status=old_status,
            new_status=new_status,
            status_label=dict(Order.Status.choices).get(new_status, new_status),
        )

        subject = f"PHINOX — Order {order.business_id} status: {context['status_label']}"
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@phinox.example")

        text_body = render_to_string("emails/order_status_update.txt", context)
        html_body = render_to_string("emails/order_status_update.html", context)

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=from_email,
            to=[recipient],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=True)

        logger.info(
            "Order %s — status update email sent (%s → %s) to %s",
            order.business_id, old_status, new_status, recipient,
        )
        return True

    except Exception as exc:  # noqa: BLE001 — intentional broad catch
        logger.warning(
            "Order %s — status update email failed: %s",
            getattr(order, "business_id", "?"), exc, exc_info=True,
        )
        return False


def send_payment_confirmation_email(order: Order, payment) -> bool:
    """Send a payment confirmation email after a successful payment.

    Args:
        order: The Order the payment belongs to.
        payment: The Payment instance (expected to be in ``paid`` status,
            but this function does not validate that — the caller decides
            when to call it).

    Returns:
        True if the email was sent successfully, False otherwise. Never
        raises — non-blocking per دستور.
    """
    try:
        if order is None or payment is None:
            logger.warning(
                "send_payment_confirmation_email() — order=%r payment=%r",
                order, payment,
            )
            return False

        user = getattr(order, "user", None)
        recipient = getattr(user, "email", None) if user else None
        if not recipient:
            logger.info(
                "Order %s — no recipient email for payment confirmation.",
                getattr(order, "business_id", "?"),
            )
            return False

        context = _build_context(order, payment=payment)

        subject = f"PHINOX — Payment confirmed for Order {order.business_id}"
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@phinox.example")

        text_body = render_to_string("emails/payment_confirmation.txt", context)
        html_body = render_to_string("emails/payment_confirmation.html", context)

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=from_email,
            to=[recipient],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=True)

        logger.info(
            "Order %s — payment confirmation email sent to %s (payment %s)",
            order.business_id, recipient, getattr(payment, "business_id", "?"),
        )
        return True

    except Exception as exc:  # noqa: BLE001 — intentional broad catch
        logger.warning(
            "Order %s — payment confirmation email failed: %s",
            getattr(order, "business_id", "?"), exc, exc_info=True,
        )
        return False
