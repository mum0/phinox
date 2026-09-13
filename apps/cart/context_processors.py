"""apps.cart.context_processors — cart item count for the topbar badge.

Phase: UNIFY-TOPBAR.
Scope: expose ``cart_item_count`` to every template context so the
unified topbar can render the cart badge without each view having to
compute it.

Per دستور §6: guest carts identified by session_key. The session_key
is NEVER exposed in any API response or URL (per دستور §5 Auth & PII).
"""
from __future__ import annotations

from typing import Any

from apps.cart.models import Cart


def cart_item_count(request) -> dict[str, Any]:
    """Return the total item count in the request's cart (0 if no cart).

    Authenticated users: Cart.user FK.
    Guests: Cart.session_key FK (session is forced to save on first
    access so session_key always exists).

    Returns ``{"cart_item_count": int}``.
    """
    if not hasattr(request, "session"):
        return {"cart_item_count": 0}

    if request.user.is_authenticated:
        cart = Cart.objects.filter(user=request.user).first()
    else:
        sk = request.session.session_key
        if not sk:
            request.session.save()
            sk = request.session.session_key
        cart = Cart.objects.filter(session_key=sk).first() if sk else None

    count = 0
    if cart:
        count = cart.items.count()

    return {"cart_item_count": count}
