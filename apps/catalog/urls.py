"""URL config for the catalog app.

Routes:
  - ``""                       → ProductListView        (name="product_list")
  - ``search/                  → AdvancedSearchView     (name="search") [Phase 3]
  - ``collections/             → CollectionListView     (name="collection_list") [Phase 3]
  - ``collections/<slug:slug>/ → CollectionDetailView   (name="collection_detail") [Phase 3]
  - ``<slug:slug>/             → ProductDetailView      (name="product_detail")

URL ordering: the more-specific literal paths (``search/``, ``collections/``,
``collections/<slug>/``) MUST come before the catch-all ``<slug:slug>/``
pattern, otherwise "search" or "collections" would be matched as a product
slug and return 404 (no product exists with those slugs).

Included from the root URLconf under the ``catalog:`` namespace.
"""
from django.urls import path

from apps.catalog.views import (
    AdvancedSearchView,
    CollectionDetailView,
    CollectionListView,
    ProductDetailView,
    ProductListView,
)

app_name = "catalog"

urlpatterns = [
    path("", ProductListView.as_view(), name="product_list"),
    # Phase 3 STITCH-INTEGRATION: advanced search + collections — MUST come
    # before the catch-all product_detail pattern so /products/search/ and
    # /products/collections/ are matched as the literal patterns (not as
    # a product slug).
    path("search/", AdvancedSearchView.as_view(), name="search"),
    path("collections/", CollectionListView.as_view(), name="collection_list"),
    path("collections/<slug:slug>/", CollectionDetailView.as_view(), name="collection_detail"),
    # Catch-all product detail (by slug) — must come AFTER the literal
    # paths above so "search" and "collections" don't get treated as a
    # product slug.
    path("<slug:slug>/", ProductDetailView.as_view(), name="product_detail"),
]
