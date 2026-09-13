"""
Root URLconf.

Phase 3-4: wires up the public storefront — pages, catalog, cart, checkout,
payments — plus Django Admin and dev static/media serving. Custom error
handlers (403/404/500) render PHINOX-branded error pages.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.pages.urls")),
    path("products/", include("apps.catalog.urls")),
    path("cart/", include("apps.cart.urls")),
    # Phase 2 STITCH-INTEGRATION: split orders URLs.
    # - Checkout flow (CheckoutView + ConfirmationView) at /checkout/
    # - Order management (history / detail / tracking) at /orders/
    # Both url files share the `orders:` namespace; no name overlap.
    path("checkout/", include("apps.orders.urls")),
    path("orders/", include("apps.orders.urls_orders")),
    path("payments/", include("apps.payments.urls")),
    # Phase 2 STITCH-INTEGRATION: wishlist URLs (new).
    path("wishlist/", include("apps.wishlist.urls")),
    # Phase 4 STITCH-INTEGRATION: stub auth URLs (visual templates only).
    # Real auth views (LoginView / phone-OTP SignupView) come in Phase 5.
    # The URL names `accounts:login` / `accounts:register` are kept stable
    # so the Phase 5 swap is a one-line view change in apps/accounts/views.py.
    path("accounts/", include("apps.accounts.urls")),
    # Phase 6 STITCH-INTEGRATION: health check endpoints (liveness + readiness).
    # Wired at root so /health/ and /health/ready/ work without a prefix.
    path("", include(("config.health", "health"))),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    try:
        import debug_toolbar

        urlpatterns += [path("__debug__/", include(debug_toolbar.urls))]
    except ImportError:
        pass

# Custom error handlers — PHINOX-branded 403/404/500 pages
handler403 = "apps.core.views.custom_403"
handler404 = "apps.core.views.custom_404"
handler500 = "apps.core.views.custom_500"
