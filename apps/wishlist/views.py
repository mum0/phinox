"""apps.wishlist — saved-for-later list views (Phase 2 STITCH-INTEGRATION).

Per user Phase 2 spec:
  - ``WishlistView``: LoginRequiredMixin + ListView over
    ``WishlistItem.objects.filter(user=request.user)``.
  - ``add_to_wishlist``: POST-only endpoint to add a product (optionally
    a specific variant) to the user's wishlist. Idempotent per the
    ``uniq_wishlist_entry`` constraint — re-adding is a no-op.
  - ``remove_from_wishlist``: POST-only endpoint to remove an entry
    by its WishlistItem.pk.

URLs mounted under ``/wishlist/`` (see apps/wishlist/urls.py).
"""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from apps.catalog.models import Product, ProductVariant

from .models import WishlistItem


class WishlistView(LoginRequiredMixin, ListView):
    """List the requesting user's saved products.

    Renders the Stitch "Wishlist Vault" design with each row showing
    the product image, name, base price, "ADD TO CART" CTA, and a
    "REMOVE" CTA. The add-to-cart CTA links to the existing
    ``cart:add_to_cart`` endpoint with the product's default variant
    (or the user-pinned variant if one was saved).
    """

    template_name = "wishlist/wishlist.html"
    context_object_name = "wishlist_items"
    paginate_by = 24

    def get_queryset(self):
        return (
            WishlistItem.objects.filter(user=self.request.user)
            .select_related("product__category", "variant")
            .prefetch_related("product__images")
            .order_by("-created_at")
        )


@require_POST
def add_to_wishlist(request) -> HttpResponse:
    """POST-only: add a product (or product+variant) to the user's wishlist.

    POST params:
      - ``product_id`` (int, required) — the Product.pk to save.
      - ``variant_id`` (int, optional) — pin to a specific variant.

    Idempotent per the ``uniq_wishlist_entry`` DB constraint — if the
    (user, product, variant) tuple already exists, we just redirect back
    with a "already in wishlist" message (the constraint would otherwise
    raise IntegrityError; we use ``get_or_create`` to avoid that).
    """
    if not request.user.is_authenticated:
        return redirect("accounts:login")

    product_id = request.POST.get("product_id")
    variant_id = request.POST.get("variant_id") or None

    try:
        product_pk = int(product_id) if product_id else 0
    except (TypeError, ValueError):
        product_pk = 0
    if product_pk <= 0:
        messages.error(request, "Invalid product_id.")
        return _redirect_back_or_wishlist(request)

    product = get_object_or_404(Product, pk=product_pk, is_active=True)

    variant = None
    if variant_id:
        try:
            variant = ProductVariant.objects.get(pk=int(variant_id), product=product)
        except (TypeError, ValueError, ProductVariant.DoesNotExist):
            variant = None

    _, created = WishlistItem.objects.get_or_create(
        user=request.user,
        product=product,
        variant=variant,
    )
    if created:
        messages.success(request, f"Added '{product.name}' to wishlist.")
    else:
        messages.info(request, f"'{product.name}' is already in your wishlist.")
    return _redirect_back_or_wishlist(request)


@require_POST
def remove_from_wishlist(request) -> HttpResponse:
    """POST-only: remove an entry by ``item_id`` (WishlistItem.pk).

    The item must belong to the requesting user — an attempt to remove
    another user's item returns 404 via ``get_object_or_404`` scoped to
    ``user=``.
    """
    if not request.user.is_authenticated:
        return redirect("accounts:login")

    item_id = request.POST.get("item_id")
    try:
        item_pk = int(item_id) if item_id else 0
    except (TypeError, ValueError):
        item_pk = 0
    if item_pk <= 0:
        messages.error(request, "Invalid item_id.")
        return _redirect_back_or_wishlist(request)

    item = get_object_or_404(WishlistItem, pk=item_pk, user=request.user)
    name = item.product.name
    item.delete()
    messages.success(request, f"Removed '{name}' from wishlist.")
    return _redirect_back_or_wishlist(request)


def _redirect_back_or_wishlist(request) -> HttpResponse:
    """Redirect to the HTTP Referer if present, else the wishlist list."""
    referer = request.META.get("HTTP_REFERER")
    if referer:
        return HttpResponseRedirect(referer)
    return redirect("wishlist:list")
