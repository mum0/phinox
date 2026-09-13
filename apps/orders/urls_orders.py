"""URL config for apps.orders — order management (Phase 2 STITCH-INTEGRATION).

This file is mounted under the ``/orders/`` prefix in ``config/urls.py``
and is separate from ``apps/orders/urls.py`` (which is mounted under
``/checkout/`` for the checkout flow).

Django limitation: when two URL files are include()'d separately under
different prefixes, Django's URL namespace resolver only keeps ONE of
them per ``app_name`` value (the FIRST one, per the W005 warning). To
have BOTH sets of URLs reachable AND have ``{% url 'orders:checkout' %}``
+ ``{% url 'orders_mgmt:history' %}`` both work, we use a SEPARATE
``app_name = "orders_mgmt"`` for this file. Templates that link to
order-detail / order-tracking pages use the ``orders_mgmt:`` namespace
prefix instead of ``orders:``.

Routes (mounted under ``/orders/``):
  - ``""                       → OrderHistoryView   (name="history")
  - ``<business_id>/            → OrderDetailView    (name="detail")
  - ``<business_id>/track/      → OrderTrackingView  (name="tracking")

URL reverse examples:
  - ``{% url 'orders_mgmt:history' %}``                              → ``/orders/``
  - ``{% url 'orders_mgmt:detail' business_id=order.business_id %}``  → ``/orders/PHX-ORD-000001/``
  - ``{% url 'orders_mgmt:tracking' business_id=order.business_id %}``→ ``/orders/PHX-ORD-000001/track/``

Phase 2 user spec:
  - Order History at /orders/ (LoginRequiredMixin + ListView)
  - Order Detail at /orders/<business_id>/ (LoginRequiredMixin + DetailView)
  - Order Tracking at /orders/<business_id>/track/ (LoginRequiredMixin + DetailView)
"""
from django.urls import path

from .views import OrderDetailView, OrderHistoryView, OrderTrackingView

app_name = "orders_mgmt"

urlpatterns = [
    path("", OrderHistoryView.as_view(), name="history"),
    path("<str:business_id>/", OrderDetailView.as_view(), name="detail"),
    path("<str:business_id>/track/", OrderTrackingView.as_view(), name="tracking"),
]
