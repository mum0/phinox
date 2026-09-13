"""URL config for apps.wishlist — saved-for-later list (Phase 2).

Routes (mounted under ``/wishlist/`` from config/urls.py):
  - ``""          → WishlistView  (name="list")
  - ``add/        → add_to_wishlist (POST-only, name="add")
  - ``remove/     → remove_from_wishlist (POST-only, name="remove")

URL reverse examples:
  - ``{% url 'wishlist:list' %}``                            → ``/wishlist/``
  - ``{% url 'wishlist:add' %}``                             → ``/wishlist/add/``
  - ``{% url 'wishlist:remove' %}``                          → ``/wishlist/remove/``
"""
from django.urls import path

from .views import WishlistView, add_to_wishlist, remove_from_wishlist

app_name = "wishlist"

urlpatterns = [
    path("", WishlistView.as_view(), name="list"),
    path("add/", add_to_wishlist, name="add"),
    path("remove/", remove_from_wishlist, name="remove"),
]
