"""
apps.cart.views — cart read + mutation views.

Layering: views are thin HTTP adapters. All cart mutations
(add / update / remove) and the subtotal calculation live in
``apps.cart.services`` (per دستور §3). This module only:

  - resolves the request → Cart (auth user OR guest session)
  - validates + coerces POST params
  - calls the service layer
  - returns JSON for HTMX/AJAX callers, redirects for non-AJAX callers

Routes (mounted under ``/cart/``):
  - GET  ``""          → CartView          (cart detail page)
  - POST ``"add/"      → add_to_cart       (HTMX-friendly)
  - POST ``"update/"   → update_cart_item  (HTMX-friendly)
  - POST ``"remove/"   → remove_cart_item  (HTMX-friendly)

Guest-session contract: a guest cart is keyed by ``request.session.session_key``.
We force the session to save (so a session_key exists) before looking up the
cart — otherwise the very first request from a fresh visitor would have no
session_key and could not be associated with a cart.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

# Imports below are mandated by the task spec (PHINOX-VIEWS-1 §RULES):
#   login_required + method_decorator + View are exposed here for downstream
#   subclasses (e.g. a future `checkout` view that requires auth, or a
#   class-based refactor of the cart mutation endpoints). They are imported
#   once at module level so callers don't need to re-import.
from django.contrib.auth.decorators import login_required  # noqa: F401
from django.db.models import QuerySet
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator  # noqa: F401
from django.views import View  # noqa: F401
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from django.views.generic import DetailView

from apps.cart.models import Cart, CartItem
from apps.cart.services import (
    add_to_cart as add_to_cart_service,
    calculate_cart_subtotal,
    remove_cart_item as remove_cart_item_service,
    update_cart_item as update_cart_item_service,
)
from apps.catalog.models import Product, ProductVariant


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_or_create_cart(request: HttpRequest) -> Cart:
    """Return the cart for the current user OR guest session, creating it.

    Authenticated users: ``Cart.user`` is a OneToOneField, so we
    ``get_or_create`` by ``user``.

    Guests: ``Cart.session_key`` is keyed by ``request.session.session_key``.
    We force the session to save first (``request.session.save()``) so a
    session_key is guaranteed to exist on the very first visit — Django
    doesn't allocate one until the session is persisted.

    The Cart model has a CheckConstraint enforcing ``user XOR session_key``
    exclusivity, so the two branches never overlap.

    Args:
        request: The current HttpRequest.

    Returns:
        The Cart for this request's user/session (created if missing).
    """
    if request.user.is_authenticated:
        cart, _created = Cart.objects.get_or_create(user=request.user)
        return cart

    # Guest: ensure a session_key exists before we look the cart up.
    if not request.session.session_key:
        request.session.save()
    session_key = request.session.session_key
    cart, _created = Cart.objects.get_or_create(session_key=session_key)
    return cart


def _cart_item_count(cart: Cart) -> int:
    """Total quantity of items in the cart (sum of CartItem.quantity)."""
    return sum(item.quantity for item in cart.items.all())


def _format_subtotal(subtotal: Decimal) -> str:
    """Format a Decimal subtotal as a 2-decimal-place string.

    JSON-safe: Decimal isn't JSON-serializable by default, so the views
    stringify it before returning. Two decimal places matches the
    ``max_digits=10, decimal_places=2`` column definition on
    ``Product.base_price`` / ``ProductVariant.price_extra``.
    """
    return f"{subtotal:.2f}"


def _cart_json_payload(
    cart: Cart,
    *,
    success: bool = True,
    message: str = "",
) -> dict[str, Any]:
    """Build the standard JSON response payload for cart mutations.

    Every cart mutation endpoint returns the same shape so the frontend
    (HTMX or vanilla JS) can update a single source of truth:

      {
        "success":     bool,
        "message":     str,
        "subtotal":    str  (e.g. "199.00"),
        "item_count":  int  (total quantity across all items)
      }
    """
    subtotal = calculate_cart_subtotal(cart)
    return {
        "success": success,
        "message": message,
        "subtotal": _format_subtotal(subtotal),
        "item_count": _cart_item_count(cart),
    }


# ---------------------------------------------------------------------------
# Cart detail page
# ---------------------------------------------------------------------------

class CartView(DetailView):
    """Cart detail page.

    Renders the current user's (or guest session's) cart with all line
    items, their variant details (sku, name, unit_price), and the
    cart subtotal. If no cart exists yet, one is created (empty) so the
    page renders consistently on first visit.

    Template:
        ``cart/cart.html``
    Context:
        ``cart``, ``cart_items`` (prefetched with variant + product +
        category for the template), ``subtotal`` (str), ``item_count`` (int).
    """

    template_name = "cart/cart.html"
    context_object_name = "cart"

    def get_object(self, queryset: QuerySet[Cart] | None = None) -> Cart:
        """Get or create the cart for this request (auth user or guest).

        After get-or-create, we re-fetch the cart with
        ``prefetch_related("items__variant__product__category")`` so that
        downstream code (templates, the subtotal service, the cart items
        context) doesn't trigger N+1 queries when looping over line items.
        Without this prefetch, rendering N cart items would issue ~3N+1
        queries (item → variant → product → category).
        """
        cart = get_or_create_cart(self.request)
        return (
            Cart.objects.prefetch_related("items__variant__product__category")
            .get(pk=cart.pk)
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Prefetch variant → product → category for the line items.

        Without this prefetch, rendering N cart items would issue 3N+1
        queries (item → variant → product → category). With it, the whole
        cart page renders in a constant number of queries.
        """
        context = super().get_context_data(**kwargs)
        cart: Cart = context["cart"]
        context["cart_items"] = cart.items.select_related(
            "variant__product__category",
        ).all()
        context["subtotal"] = _format_subtotal(calculate_cart_subtotal(cart))
        context["item_count"] = _cart_item_count(cart)
        return context


# ---------------------------------------------------------------------------
# Cart mutations — POST-only, CSRF-protected, HTMX-friendly.
#
# We use @require_POST + @csrf_protect as function-level decorators on
# function-based views (rather than method_decorator on a View subclass)
# because the cart mutation endpoints are trivially small and the
# function form reads more clearly.
# ---------------------------------------------------------------------------

@require_POST
@csrf_protect
def add_to_cart(request: HttpRequest) -> HttpResponse:
    """Add a variant to the current request's cart.

    POST params:
        ``variant_id`` (int, required) — the ProductVariant.pk to add.
        ``quantity``   (int, optional, default 1) — units to add (>= 1).

    Returns:
        - For AJAX/HTMX requests (``X-Requested-With: XMLHttpRequest`` or
          ``HTTP_HX_REQUEST`` set): ``JsonResponse`` with the standard
          cart payload: ``{success, message, subtotal, item_count}``.
        - For non-AJAX POSTs: ``HttpResponseRedirect`` to the cart page
          (so a no-JS form post still works).

    Error responses (JSON, HTTP 400):
        - Missing / non-integer ``variant_id``.
        - Variant does not exist or is inactive.
        - ``quantity`` < 1 or non-integer.
    """
    variant_id = request.POST.get("variant_id")
    quantity_raw = request.POST.get("quantity", "1")

    # --- Validate + coerce inputs ---------------------------------------
    try:
        variant_pk = int(variant_id) if variant_id else 0
    except (TypeError, ValueError):
        return _cart_mutation_error(request, message="Invalid variant_id.")

    if variant_pk <= 0:
        return _cart_mutation_error(request, message="variant_id is required.")

    try:
        quantity = int(quantity_raw)
    except (TypeError, ValueError):
        return _cart_mutation_error(request, message="Invalid quantity.")
    if quantity < 1:
        return _cart_mutation_error(request, message="quantity must be >= 1.")

    # --- Resolve variant ------------------------------------------------
    variant = get_object_or_404(
        ProductVariant,
        pk=variant_pk,
        is_active=True,
        product__status=Product.Status.ACTIVE,
        product__is_active=True,
    )

    # --- Mutate ----------------------------------------------------------
    cart = get_or_create_cart(request)
    try:
        add_to_cart_service(cart=cart, variant=variant, quantity=quantity)
    except ValueError as exc:
        return _cart_mutation_error(request, message=str(exc))

    payload = _cart_json_payload(
        cart,
        success=True,
        message=f"Added {quantity} × {variant.sku} to your cart.",
    )

    if _is_ajax(request):
        return JsonResponse(payload)
    return redirect("cart:cart")


@require_POST
@csrf_protect
def update_cart_item(request: HttpRequest) -> HttpResponse:
    """Set an absolute quantity on an existing cart item.

    POST params:
        ``item_id``  (int, required) — the CartItem.pk to update.
        ``quantity`` (int, required) — new absolute quantity (>= 1).
                                     To remove an item, use ``remove/``.

    Returns:
        - AJAX: ``JsonResponse`` with ``{success, message, subtotal, item_count}``.
        - Non-AJAX: redirect to cart page.

    The item must belong to the current request's cart — an attempt to
    update another user's item returns 404 (via ``get_object_or_404``
    scoped to ``cart=``).
    """
    item_id = request.POST.get("item_id")
    quantity_raw = request.POST.get("quantity")

    try:
        item_pk = int(item_id) if item_id else 0
    except (TypeError, ValueError):
        return _cart_mutation_error(request, message="Invalid item_id.")
    if item_pk <= 0:
        return _cart_mutation_error(request, message="item_id is required.")

    try:
        quantity = int(quantity_raw)
    except (TypeError, ValueError):
        return _cart_mutation_error(request, message="Invalid quantity.")
    if quantity < 1:
        return _cart_mutation_error(
            request,
            message="quantity must be >= 1; use remove/ to delete an item.",
        )

    cart = get_or_create_cart(request)
    item = get_object_or_404(CartItem, pk=item_pk, cart=cart)

    try:
        update_cart_item_service(item=item, quantity=quantity)
    except ValueError as exc:
        return _cart_mutation_error(request, message=str(exc))

    payload = _cart_json_payload(
        cart,
        success=True,
        message="Cart updated.",
    )

    if _is_ajax(request):
        return JsonResponse(payload)
    return redirect("cart:cart")


@require_POST
@csrf_protect
def remove_cart_item(request: HttpRequest) -> HttpResponse:
    """Delete a cart item.

    POST params:
        ``item_id`` (int, required) — the CartItem.pk to remove.

    Returns:
        - AJAX: ``JsonResponse`` with ``{success, message, subtotal, item_count}``.
        - Non-AJAX: redirect to cart page.

    As with ``update_cart_item``, the item must belong to the current
    request's cart.
    """
    item_id = request.POST.get("item_id")

    try:
        item_pk = int(item_id) if item_id else 0
    except (TypeError, ValueError):
        return _cart_mutation_error(request, message="Invalid item_id.")
    if item_pk <= 0:
        return _cart_mutation_error(request, message="item_id is required.")

    cart = get_or_create_cart(request)
    item = get_object_or_404(CartItem, pk=item_pk, cart=cart)

    remove_cart_item_service(item=item)

    payload = _cart_json_payload(
        cart,
        success=True,
        message="Item removed from cart.",
    )

    if _is_ajax(request):
        return JsonResponse(payload)
    return redirect("cart:cart")


# ---------------------------------------------------------------------------
# Internal helpers (not part of the URLconf)
# ---------------------------------------------------------------------------

def _is_ajax(request: HttpRequest) -> bool:
    """Detect AJAX / HTMX requests.

    Returns True for either:
      - ``X-Requested-With: XMLHttpRequest`` (classic jQuery / fetch)
      - ``HX-Request: true`` (HTMX — sent on every hx-* request)
    """
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    if request.headers.get("HX-Request"):
        return True
    return False


def _cart_mutation_error(request: HttpRequest, *, message: str) -> HttpResponse:
    """Return a 400 JSON error for AJAX callers, or redirect for non-AJAX.

    Non-AJAX callers (no-JS form posts) get a redirect to the cart page
    rather than a 400 — a 400 with no body is a poor UX for a browser
    back-button flow.
    """
    if _is_ajax(request):
        cart = get_or_create_cart(request)
        payload = _cart_json_payload(cart, success=False, message=message)
        return JsonResponse(payload, status=400)
    return HttpResponseRedirect(reverse("cart:cart"))
