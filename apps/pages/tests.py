"""apps.pages — tests for the static editorial pages (PHASE-C §C4).

Covers:
  - home: 200 + context exposes featured_products + essentials_products
  - about: 200
  - faq: 200
  - contact: 200
  - privacy: 200
  - terms: 200
  - returns: 200
  - journal: 200
"""
from django.test import TestCase
from django.urls import reverse


class PagesRenderTests(TestCase):
    """Smoke tests: each static editorial page renders 200."""

    def test_home_renders(self) -> None:
        """GET / → 200, with featured_products + essentials_products in context."""
        response = self.client.get(reverse("pages:home"))
        self.assertEqual(response.status_code, 200)
        # Context should expose the two querysets even if empty.
        self.assertIn("featured_products", response.context)
        self.assertIn("essentials_products", response.context)

    def test_about_renders(self) -> None:
        """GET /about/ → 200."""
        response = self.client.get(reverse("pages:about"))
        self.assertEqual(response.status_code, 200)

    def test_faq_renders(self) -> None:
        """GET /faq/ → 200."""
        response = self.client.get(reverse("pages:faq"))
        self.assertEqual(response.status_code, 200)

    def test_contact_renders(self) -> None:
        """GET /contact/ → 200."""
        response = self.client.get(reverse("pages:contact"))
        self.assertEqual(response.status_code, 200)

    def test_privacy_renders(self) -> None:
        """GET /privacy/ → 200."""
        response = self.client.get(reverse("pages:privacy"))
        self.assertEqual(response.status_code, 200)

    def test_terms_renders(self) -> None:
        """GET /terms/ → 200."""
        response = self.client.get(reverse("pages:terms"))
        self.assertEqual(response.status_code, 200)

    def test_returns_renders(self) -> None:
        """GET /returns/ → 200."""
        response = self.client.get(reverse("pages:returns"))
        self.assertEqual(response.status_code, 200)

    def test_journal_renders(self) -> None:
        """GET /journal/ → 200."""
        response = self.client.get(reverse("pages:journal"))
        self.assertEqual(response.status_code, 200)
