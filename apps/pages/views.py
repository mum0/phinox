"""
apps.pages — Home + Contact views.

Phase 4 STITCH-INTEGRATION: Home is no longer a placeholder. It renders the
Stitch "Rule of Two" home page (templates/pages/home.html) and pulls
real products from the catalog so the featured/essentials sections have
content. Contact stays render-only (Phase 1 scope — no POST handling or
ContactMessage model yet per IMPLEMENTATION_PLAN.md §2.3).

URL names:
  - ``pages:home``    → /
  - ``pages:contact`` → /contact/
"""
from __future__ import annotations

from django.shortcuts import render

from apps.catalog.models import Product


def home(request):
    """Render the Stitch-integrated home page with real products.

    Context:
      - ``featured_products``: up to 3 active products for the "DROP 01"
        hero section. Falls back to a single PHINOX-branded card via the
        template's ``{% empty %}`` branch if no products are seeded yet.
      - ``essentials_products``: up to 6 active products for the
        "Essentials" horizontal scroll. The Stitch source hard-codes 3
        cards; we let the catalog drive it so the page survives empty
        state and reflects real inventory.

    Both querysets are scoped to ``status=ACTIVE`` + ``is_active=True`` —
    the same visibility rule used by ``apps.catalog.services.get_active_products``
    (per دستور §3: catalog models hold no business logic beyond computed
    properties; this view is a thin read-side composer, so direct ORM
    access is fine here).
    """
    featured = (
        Product.objects.filter(status=Product.Status.ACTIVE, is_active=True)
        .select_related("category")
        .order_by("-created_at")[:3]
    )
    essentials = (
        Product.objects.filter(status=Product.Status.ACTIVE, is_active=True)
        .select_related("category")
        .order_by("name")[:6]
    )
    return render(
        request,
        "pages/home.html",
        {
            "featured_products": list(featured),
            "essentials_products": list(essentials),
        },
    )


def contact(request):
    """Render the contact page (Phase 1 scope — form is render-only)."""
    return render(request, "pages/contact.html")


def about(request):
    """Render the about/manifesto page (Phase 2 STITCH-INTEGRATION).

    A static editorial page (Brand story + Vision + Values). TemplateView-
    equivalent — no DB access, no POST handling. The Stitch "PHINOX |
    MANIFESTO // ABOUT" design lives at templates/pages/about.html.
    """
    return render(request, "pages/about.html")


def journal(request):
    """Render the journal page stub (Phase: UNIFY-TOPBAR).

    A static placeholder page that will be replaced with real editorial
    content (blog/lookbook) in a future phase.
    """
    return render(request, "pages/journal.html")


# ---------------------------------------------------------------------------
# Phase 3 STITCH-INTEGRATION — static editorial pages
# ---------------------------------------------------------------------------
def faq(request):
    """Render the FAQ / Knowledge Base page (Phase 3).

    Static content — Frequently Asked Questions in 4 categories
    (Sizing & Fit, Orders & Shipping, Returns & Refunds, Account & Payment).
    Template: templates/pages/faq.html (Stitch "Knowledge Base" port).
    """
    return render(request, "pages/faq.html")


def privacy(request):
    """Render the Privacy Policy page (Phase 3).

    Static content — Privacy Policy + Data Integrity statement per
    Egyptian data protection law. Template: templates/pages/privacy.html
    (adapted from Stitch "Legal / Terms / Returns" page).
    """
    return render(request, "pages/privacy.html")


def terms(request):
    """Render the Terms of Service page (Phase 3).

    Static content — Terms of Service + Specification Contract per
    دستور §10 (Egyptian context, EGP currency, 4 payment rails).
    Template: templates/pages/terms.html.
    """
    return render(request, "pages/terms.html")


def returns(request):
    """Render the Returns & Refunds page (Phase 3).

    Static content — Returns policy per دستور §10 (14-day architectural
    guarantee across all 27 Egyptian governorates).
    Template: templates/pages/returns.html.
    """
    return render(request, "pages/returns.html")
