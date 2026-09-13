"""URL config for apps.orders — checkout flow only.

Phase 2 STITCH-INTEGRATION: This file is now scoped to the CHECKOUT flow
only (empty-path checkout + order confirmation). Order history, order
detail, and order tracking URLs live in ``apps/orders/urls_orders.py``
which is mounted under the ``/orders/`` prefix in ``config/urls.py``.

Routes (mounted under ``/checkout/`` from config/urls.py):
  - ``""                          → CheckoutView          (name="checkout")
  - ``<business_id>/confirmation/ → OrderConfirmationView (name="confirmation")

URL reverse examples:
  - ``{% url 'orders:checkout' %}``     → ``/checkout/``
  - ``{% url 'orders:confirmation' business_id=order.business_id %}``
                                       → ``/checkout/PHX-ORD-000001/confirmation/``

Phase 1 fix applied: removed the ``checkout/`` path prefix from
CheckoutView so ``orders:checkout`` reverses to ``/checkout/`` instead
of the awkward ``/checkout/checkout/``.
"""
from django.urls import path

from .views import CheckoutView, OrderConfirmationView

app_name = "orders"

urlpatterns = [
    path("", CheckoutView.as_view(), name="checkout"),
    path(
        "<str:business_id>/confirmation/",
        OrderConfirmationView.as_view(),
        name="confirmation",
    ),
]
