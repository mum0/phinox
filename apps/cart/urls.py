"""URL config for the cart app.

Routes (mounted under the prefix configured in ``config/urls.py`` —
conventionally ``/cart/``):

  - GET/POST ``""          → CartView          (name="cart")
  - POST     ``"add/"      → add_to_cart       (name="add_to_cart")
  - POST     ``"update/"   → update_cart_item  (name="update_cart_item")
  - POST     ``"remove/"   → remove_cart_item  (name="remove_cart_item")

The mutation endpoints are POST-only at the view level (``@require_POST``),
so the URLconf itself doesn't need to repeat that constraint. All four
endpoints are namespaced under ``cart:`` so templates / reverse() calls
use ``cart:cart``, ``cart:add_to_cart``, etc.
"""
from django.urls import path

from apps.cart.views import (
    CartView,
    add_to_cart,
    remove_cart_item,
    update_cart_item,
)

app_name = "cart"

urlpatterns = [
    path("", CartView.as_view(), name="cart"),
    path("add/", add_to_cart, name="add_to_cart"),
    path("update/", update_cart_item, name="update_cart_item"),
    path("remove/", remove_cart_item, name="remove_cart_item"),
]
