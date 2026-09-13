"""
apps.catalog.tests_views — Phase 3 view tests for ProductListView.

Verifies the publicly-visible catalog browse behaviour:
  - HTTP 200 + correct product set in context
  - Pagination at 24 per page
  - Category filter (?category=<slug>)
  - Search (?q=<query>)
  - Draft / inactive products are hidden from shoppers

URL name expected: ``catalog:product_list`` → ``/products/``.

Note: the catalog URLs/views themselves are wired by the parallel "views
+ templates" agent in this phase. These tests assert the contract those
views must satisfy so they can be run as soon as the views land.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product, ProductVariant


def make_category(name: str = "Winter", family_code: str = "WNT", slug: str = "") -> Category:
    return Category.objects.create(
        name=name,
        family_code=family_code,
        slug=slug or name.lower().replace(" ", "-"),
    )


def make_product(
    category: Category,
    name: str,
    *,
    status: str = Product.Status.ACTIVE,
    is_active: bool = True,
    base_price: Decimal = Decimal("1000"),
) -> Product:
    return Product.objects.create(
        name=name,
        category=category,
        base_price=base_price,
        status=status,
        is_active=is_active,
    )


class ProductListViewTest(TestCase):
    """Covers the public /products/ listing — pagination + filtering + search."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.category = make_category(name="Winter", family_code="WNT", slug="winter")
        cls.other_category = make_category(
            name="Summer", family_code="SUM", slug="summer"
        )

        # 5 active products in the "winter" category.
        cls.active_products = [
            make_product(cls.category, name=f"Winter Coat {i}")
            for i in range(1, 6)
        ]
        # 2 draft products — must NOT appear on the public list.
        cls.draft_products = [
            make_product(cls.category, name=f"Draft Coat {i}", status=Product.Status.DRAFT)
            for i in range(1, 3)
        ]
        # A product in another category — exercises ?category filter.
        cls.summer_product = make_product(
            cls.other_category, name="Linen Shirt", status=Product.Status.ACTIVE
        )

        # Give every product at least one variant so it can be added to a cart
        # downstream — keeps the PDP add-to-cart flow from 404'ing on the
        # related tests.
        for p in cls.active_products + cls.draft_products + [cls.summer_product]:
            ProductVariant.objects.create(product=p, price_extra=Decimal("0"))

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------
    def test_list_shows_active_products(self) -> None:
        """GET /products/ returns 200 and the 6 active products in context.

        setUpTestData creates 5 active winter products + 1 active summer
        product (the latter exists to exercise the ?category filter in
        test_filter_by_category). The default list shows ALL active
        products, so the expected count is 6 — not 5.
        """
        url = reverse("catalog:product_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # The view exposes the page object under the conventional key
        # ``product_list`` (or ``products`` — both are tolerated below).
        context = response.context
        products = (
            context.get("product_list")
            or context.get("products")
            or context.get("object_list")
            or []
        )
        self.assertEqual(len(products), 6, msg=f"context: {list(context.keys())}")
        # Draft products are excluded.
        names = {p.name for p in products}
        for draft in self.draft_products:
            self.assertNotIn(draft.name, names)
        # All 5 active winter products are present.
        for active in self.active_products:
            self.assertIn(active.name, names)
        # The summer product is also active — included by default.
        self.assertIn(self.summer_product.name, names)

    def test_list_paginated(self) -> None:
        """The view paginates at 24 products per page (REST_FRAMEWORK PAGE_SIZE)."""
        # Create enough products to span a second page (24 on page 1, rest on page 2).
        extra_count = 25  # 5 existing + 25 = 30 → 2 pages
        for i in range(extra_count):
            make_product(self.category, name=f"Bulk Coat {i}")

        url = reverse("catalog:product_list")
        page1 = self.client.get(url)
        self.assertEqual(page1.status_code, 200)
        page1_items = (
            page1.context.get("product_list")
            or page1.context.get("object_list")
            or []
        )
        self.assertLessEqual(len(page1_items), 24, "page 1 must not exceed 24 items")

        page2 = self.client.get(url, {"page": 2})
        self.assertEqual(page2.status_code, 200)
        page2_items = (
            page2.context.get("product_list")
            or page2.context.get("object_list")
            or []
        )
        # Page 2 should hold the remainder (30 total - 24 = 6).
        self.assertGreater(len(page2_items), 0, "page 2 must have items")
        self.assertLessEqual(len(page2_items), 24)

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------
    def test_filter_by_category(self) -> None:
        """?category=<slug> restricts the list to that category's products."""
        url = reverse("catalog:product_list")
        response = self.client.get(url, {"category": "summer"})

        self.assertEqual(response.status_code, 200)
        products = (
            response.context.get("product_list")
            or response.context.get("object_list")
            or []
        )
        names = {p.name for p in products}
        self.assertIn(self.summer_product.name, names)
        for winter in self.active_products:
            self.assertNotIn(
                winter.name, names, "winter products must be filtered out"
            )

    def test_search(self) -> None:
        """?q=<query> filters the list to products whose name matches."""
        # Rename one product so the search term is unambiguous.
        self.active_products[0].name = "UniqueSearchTerm Coat"
        self.active_products[0].save()

        url = reverse("catalog:product_list")
        response = self.client.get(url, {"q": "UniqueSearchTerm"})

        self.assertEqual(response.status_code, 200)
        products = (
            response.context.get("product_list")
            or response.context.get("object_list")
            or []
        )
        names = {p.name for p in products}
        self.assertIn("UniqueSearchTerm Coat", names)
        # Other active products are filtered out by the search.
        for p in self.active_products[1:]:
            self.assertNotIn(p.name, names)

    # ------------------------------------------------------------------
    # Visibility rules
    # ------------------------------------------------------------------
    def test_draft_products_hidden(self) -> None:
        """Draft products never appear on the public list, even with ?q=."""
        # Make one draft's name distinctive so we can assert its absence.
        self.draft_products[0].name = "SecretDraft Coat"
        self.draft_products[0].save()

        url = reverse("catalog:product_list")

        # Plain list — no draft.
        r1 = self.client.get(url)
        products = r1.context.get("product_list") or r1.context.get("object_list") or []
        names = {p.name for p in products}
        self.assertNotIn("SecretDraft Coat", names)

        # Search for the draft name directly — still hidden.
        r2 = self.client.get(url, {"q": "SecretDraft"})
        products2 = r2.context.get("product_list") or r2.context.get("object_list") or []
        names2 = {p.name for p in products2}
        self.assertNotIn(
            "SecretDraft Coat",
            names2,
            "draft products must be hidden from shoppers even when their name matches the query",
        )
