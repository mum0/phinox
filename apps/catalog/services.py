"""
apps.catalog.services — read-side product catalog queries.

Business logic for browsing/searching the catalog. Per دستور §3:
catalog models hold no business logic beyond computed properties; all
query helpers live here so views / API layers stay thin.

All functions are pure read-side helpers (no mutations) and return
QuerySets (or a single Product with prefetched relations) so callers
can further refine / paginate without extra DB hits.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Prefetch, QuerySet

from apps.catalog.models import Product, ProductImage, ProductVariant

if TYPE_CHECKING:  # pragma: no cover
    pass


def get_active_products() -> QuerySet[Product]:
    """Return all products that are visible to shoppers.

    A product is "active" when both:
      - ``status == Product.Status.ACTIVE`` (the publishing lifecycle state)
      - ``is_active == True`` (the manual kill-switch)

    Returns:
        QuerySet of active products, ordered by creation date (newest first).
    """
    return (
        Product.objects.filter(status=Product.Status.ACTIVE, is_active=True)
        .select_related("category")
        .order_by("-created_at")
    )


def get_products_by_category(category_slug: str) -> QuerySet[Product]:
    """Return active products belonging to the category with the given slug.

    Args:
        category_slug: The category's slug (e.g. "winter-coats").

    Returns:
        QuerySet of active products in that category.

    Raises:
        ValueError: If ``category_slug`` is empty.
    """
    if not category_slug or not category_slug.strip():
        raise ValueError("category_slug must be a non-empty string.")
    return (
        Product.objects.filter(
            category__slug=category_slug,
            status=Product.Status.ACTIVE,
            is_active=True,
        )
        .select_related("category")
        .order_by("created_at")
    )


def search_products(query: str) -> QuerySet[Product]:
    """Case-insensitive search over product name and slug.

    Args:
        query: The search term. Whitespace is trimmed; empty / whitespace-only
            queries raise ValueError.

    Returns:
        QuerySet of active products whose name or slug contains the query
        (case-insensitive). Ordered by name.

    Raises:
        ValueError: If ``query`` is empty or whitespace-only.
    """
    if not query or not query.strip():
        raise ValueError("query must be a non-empty string.")
    q = query.strip()
    return (
        Product.objects.filter(
            status=Product.Status.ACTIVE,
            is_active=True,
        )
        .filter(models_name_or_slug_icontains(q))
        .select_related("category")
        .order_by("name")
    )


def models_name_or_slug_icontains(q: str):
    """Build a Q() for name__icontains OR slug__icontains."""
    from django.db.models import Q

    return Q(name__icontains=q) | Q(slug__icontains=q)


def get_product_with_variants(product_id: int) -> Product:
    """Fetch a single product with its variants and images prefetched.

    Uses Prefetch so ``product.variants.all()`` and each
    ``variant.images.all()`` (as well as ``product.images.all()``) are
    loaded in a constant number of queries — ideal for a PDP view.

    Args:
        product_id: The internal PK (BigAutoField) of the product.

    Returns:
        The Product instance with ``variants`` and ``images`` prefetched.

    Raises:
        ValueError: If ``product_id`` is not a positive integer.
        Product.DoesNotExist: If no product exists with the given id.
    """
    if not isinstance(product_id, int) or product_id <= 0:
        raise ValueError("product_id must be a positive integer.")

    return (
        Product.objects.select_related("category")
        .prefetch_related(
            Prefetch(
                "variants",
                queryset=ProductVariant.objects.filter(is_active=True).order_by("id"),
            ),
            Prefetch(
                "images",
                queryset=ProductImage.objects.order_by("position"),
            ),
        )
        .get(pk=product_id)
    )
