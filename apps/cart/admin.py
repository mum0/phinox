"""apps.cart — admin for Cart + CartItem.

CartItem is edited inline on the Cart admin. business_id on Cart is
auto-generated and therefore read-only.
"""
from django.contrib import admin

from .models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("business_id", "user", "session_key", "promo_code")
    list_filter = ("promo_code",)
    search_fields = ("business_id", "user__username", "user__customer_id", "session_key")
    readonly_fields = ("business_id",)
    inlines = [CartItemInline]


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("cart", "variant", "quantity")
    list_filter = ("variant__product__category",)
    search_fields = ("cart__business_id", "variant__sku", "variant__product__name")
