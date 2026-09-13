"""apps.orders — admin for Order + OrderItem.

OrderItem is edited inline on the Order admin. business_id and
idempotency_key are auto-generated and therefore read-only.
"""
from django.contrib import admin

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("sku",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "business_id",
        "user",
        "status",
        "payment_status",
        "grand_total",
        "currency",
        "bos_sync_status",
    )
    list_filter = ("status", "payment_status", "fulfillment_status", "bos_sync_status")
    search_fields = ("business_id", "user__username", "user__email", "user__customer_id")
    readonly_fields = ("business_id", "idempotency_key", "bos_reference_id", "last_sync_at")
    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "sku", "name", "quantity", "unit_price")
    list_filter = ("order__status",)
    search_fields = ("sku", "name", "order__business_id")
    readonly_fields = ("sku",)
