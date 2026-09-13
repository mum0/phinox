"""
apps.catalog.views — read-side catalog views (PLP + PDP).

Thin view layer that delegates query construction to
``apps.catalog.services`` (per دستور §3: models hold no business logic,
services own it, views stay thin).

  - ``ProductListView``  → /catalog/        (product listing + ?category + ?q)
  - ``ProductDetailView`` → /catalog/<slug>/ (single product page)

Both views only surface products where ``status == ACTIVE`` and
``is_active == True`` — draft / archived / soft-killed products are
invisible to shoppers.
"""
from __future__ import annotations

from typing import Any

from django.db.models import QuerySet
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.views.generic import DetailView, ListView

from apps.catalog.models import Category, Product
from apps.catalog.services import (
    get_active_products,
    get_product_with_variants,
    get_products_by_category,
    search_products,
)


class ProductListView(ListView):
    """Product Listing Page (PLP).

    Renders all active products, paginated 24/page. Supports two optional
    query-string filters, evaluated in this order:

      1. ``?category=<slug>`` — restrict to one category (uses
         ``get_products_by_category`` service).
      2. ``?q=<query>``       — case-insensitive name/slug search (uses
         ``search_products`` service).

    If both are supplied, ``q`` wins (search across the whole catalog).
    The filter sidebar is fed by ``categories`` in ``get_context_data``.

    Template (default Django convention):
        ``catalog/product_list.html``
    Context:
        ``products``, ``product_list``, ``page_obj``, ``categories``,
        ``current_category``, ``search_query``.
    """

    model = Product
    paginate_by = 24
    template_name = "catalog/product_list.html"
    # ``products`` is the name the template iterates over (see
    # templates/catalog/product_list.html). The view also exposes the
    # conventional ``product_list`` alias in get_context_data below for
    # backwards compatibility with the view tests in tests_views.py.
    context_object_name = "products"

    def get_queryset(self) -> QuerySet[Product]:
        """Return the active-products queryset, scoped by ?category / ?q.

        Order of precedence: search (?q) > category filter (?category) >
        default active-products list. Empty / whitespace-only ``q`` falls
        through to the category / default branch (rather than raising —
        the service itself raises ValueError on empty input).
        """
        query = self.request.GET.get("q", "").strip()
        category_slug = self.request.GET.get("category", "").strip()

        if query:
            # search_products raises ValueError on empty input — guarded above.
            return (
                search_products(query)
                .select_related("category")
                .prefetch_related("variants", "images")
            )

        if category_slug:
            return (
                get_products_by_category(category_slug)
                .select_related("category")
                .prefetch_related("variants", "images")
            )

        return (
            get_active_products()
            .select_related("category")
            .prefetch_related("variants", "images")
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Inject the category sidebar + active filter state into context.

        Also exposes the queryset under the ``product_list`` alias (the
        ListView default name) so legacy code/tests that read
        ``context["product_list"]`` continue to work alongside the
        ``products`` name the template uses.
        """
        context = super().get_context_data(**kwargs)
        # Backwards-compatible alias for the default Django ListView
        # context_object_name. The template iterates over ``products``;
        # tests in tests_views.py read either name (product_list / products
        # / object_list), so we surface both.
        context.setdefault("product_list", context.get("products"))
        # Sidebar: top-level active categories, ordered for display.
        context["categories"] = (
            Category.objects.filter(is_active=True, parent__isnull=True)
            .order_by("display_order", "name")
        )
        context["current_category"] = self.request.GET.get("category", "").strip()
        context["search_query"] = self.request.GET.get("q", "").strip()
        return context


class ProductDetailView(DetailView):
    """Product Detail Page (PDP).

    Fetches a single product by slug, only if ``status == ACTIVE`` (draft /
    archived products 404). Uses ``get_product_with_variants`` so variants
    and images are prefetched in a constant number of queries — ideal for a
    PDP that loops over variant swatches + a gallery.

    Template (default Django convention):
        ``catalog/product_detail.html``
    Context:
        ``product``, ``variants``, ``primary_image``, ``related_products``.
    """

    model = Product
    slug_field = "slug"
    slug_url_kwarg = "slug"
    template_name = "catalog/product_detail.html"
    context_object_name = "product"

    def get_queryset(self) -> QuerySet[Product]:
        """Restrict to active products — anything else 404s for shoppers.

        ``select_related("category")`` + ``prefetch_related`` for variants,
        images, and reviews keeps the PDP at a constant number of queries
        (no N+1 when the template loops over variant swatches / gallery /
        review list).
        """
        return Product.objects.filter(
            status=Product.Status.ACTIVE,
            is_active=True,
        ).select_related("category").prefetch_related(
            "variants__product", "images", "reviews"
        )

    def get_object(self, queryset: QuerySet[Product] | None = None) -> Product:
        """Fetch by slug, then reload via the service for prefetched variants.

        We do a two-step fetch: first a cheap slug → id lookup on the
        active-products queryset (so drafts/archived 404 cleanly), then
        ``get_product_with_variants`` to get the prefetched version. This
        keeps the view thin (no manual Prefetch boilerplate) and ensures
        the variant/image prefetching logic lives in one place.
        """
        qs = queryset if queryset is not None else self.get_queryset()
        slug = self.kwargs.get(self.slug_url_kwarg)
        if not slug:
            raise Http404("Product slug not provided.")
        product = get_object_or_404(qs, **{self.slug_field: slug})
        # Reload with prefetched variants + images (1 extra hit, constant
        # number of queries overall for the PDP).
        return get_product_with_variants(product.pk)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Add variants, primary_image, and related_products to context."""
        context = super().get_context_data(**kwargs)
        product: Product = context["product"]

        # Variants are already prefetched (active only, ordered by id) by
        # get_product_with_variants. Re-expose as a list for the template.
        variants = list(product.variants.all())
        context["variants"] = variants

        # Primary image: lowest-position image attached to the product
        # (or None if the product has no images yet — PDP template should
        # guard for this).
        primary_image = (
            product.images.order_by("position").first() if product.images.all() else None
        )
        context["primary_image"] = primary_image

        # Related products: up to 8 other active products in the same
        # category, excluding the current one. Cheap query — uses the
        # ``product_category_status_idx`` index.
        context["related_products"] = (
            Product.objects.filter(
                category=product.category,
                status=Product.Status.ACTIVE,
                is_active=True,
            )
            .exclude(pk=product.pk)
            .select_related("category")
            .order_by("-created_at")[:8]
        )
        return context


# ---------------------------------------------------------------------------
# Phase 3 STITCH-INTEGRATION — Advanced Search + Collections
# ---------------------------------------------------------------------------
from django.db.models import Q  # noqa: E402


class AdvancedSearchView(ListView):
    """Advanced search view with filter facets.

    Per user Phase 3 spec: ``/search/`` with filter support.

    Filters (all optional via GET params):
      - ``q``      — free-text search on product name + slug + description
      - ``category`` — category slug (restricts to that category)
      - ``min_price`` / ``max_price`` — base_price range (Decimal)
      - ``sort``   — ``newest`` (default), ``price_asc``, ``price_desc``, ``name``

    Inherits the visibility contract from ``ProductListView``: only
    ``status=ACTIVE`` + ``is_active=True`` products are surfaced.
    """

    model = Product
    paginate_by = 24
    template_name = "catalog/search.html"
    context_object_name = "products"

    def get_queryset(self) -> QuerySet[Product]:
        qs = (
            Product.objects.filter(status=Product.Status.ACTIVE, is_active=True)
            .select_related("category")
            .prefetch_related("variants", "images")
        )

        # Free-text search
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(slug__icontains=q)
                | Q(description__icontains=q)
                | Q(business_id__icontains=q)
            )

        # Category filter
        category_slug = self.request.GET.get("category", "").strip()
        if category_slug:
            qs = qs.filter(category__slug=category_slug)

        # Price range
        try:
            min_price = self.request.GET.get("min_price", "").strip()
            if min_price:
                qs = qs.filter(base_price__gte=float(min_price))
        except (TypeError, ValueError):
            pass
        try:
            max_price = self.request.GET.get("max_price", "").strip()
            if max_price:
                qs = qs.filter(base_price__lte=float(max_price))
        except (TypeError, ValueError):
            pass

        # Sort
        sort = self.request.GET.get("sort", "newest").strip()
        if sort == "price_asc":
            qs = qs.order_by("base_price")
        elif sort == "price_desc":
            qs = qs.order_by("-base_price")
        elif sort == "name":
            qs = qs.order_by("name")
        else:
            qs = qs.order_by("-created_at")
        return qs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Inject filter state + category sidebar + sort options."""
        context = super().get_context_data(**kwargs)
        context["categories"] = Category.objects.filter(
            is_active=True, parent__isnull=True
        ).order_by("display_order", "name")
        context["search_query"] = self.request.GET.get("q", "").strip()
        context["current_category"] = self.request.GET.get("category", "").strip()
        context["min_price"] = self.request.GET.get("min_price", "").strip()
        context["max_price"] = self.request.GET.get("max_price", "").strip()
        context["current_sort"] = self.request.GET.get("sort", "newest").strip()
        return context


class CollectionListView(ListView):
    """Collections matrix — list all active collections.

    Per user Phase 3 spec: ``/collections/`` page showing the
    architectural taxonomy of PHINOX collections (e.g. "CORE FLEECE &
    HOODIES", "OUTERWEAR & HARDSHELL", "STRUCTURAL TROUSERS").
    """

    from apps.catalog.models import Collection as _Collection
    model = _Collection
    paginate_by = 24
    template_name = "catalog/collection_list.html"
    context_object_name = "collections"

    def get_queryset(self):
        return self.model.objects.filter(is_active=True).prefetch_related(
            "products"
        ).order_by("-starts_at", "name")


class CollectionDetailView(DetailView):
    """Single collection detail — show the curated products in it.

    URL: ``/collections/<slug>/`` — looks up the Collection by slug.
    Only ``is_active=True`` collections are visible to shoppers.
    """

    from apps.catalog.models import Collection as _Collection
    model = _Collection
    slug_field = "slug"
    slug_url_kwarg = "slug"
    template_name = "catalog/collection_detail.html"
    context_object_name = "collection"

    def get_queryset(self):
        return self.model.objects.filter(is_active=True).prefetch_related(
            "products__category", "products__images", "products__variants"
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        collection = self.object
        # Only surface active products inside the collection
        context["collection_products"] = (
            collection.products.filter(
                status=Product.Status.ACTIVE, is_active=True
            ).select_related("category").prefetch_related("images", "variants")
        )
        return context
