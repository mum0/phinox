"""apps.inventory — admin for Warehouse + Inventory.

Warehouse is the location entity (one row per physical stock location).
Inventory is the stock level for one variant at one warehouse — edited
inline on the variant admin via the ProductVariantInline in catalog's
admin, and exposed here as a top-level admin for direct stock adjustments.
"""
from django.contrib import admin

from .models import Inventory, Warehouse


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "governorate", "is_active")
    list_filter = ("is_active", "governorate")
    search_fields = ("code", "name", "governorate")


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = (
        "variant",
        "warehouse",
        "quantity_on_hand",
        "quantity_reserved",
        "quantity_available",
        "low_stock_threshold",
    )
    list_filter = ("warehouse",)
    search_fields = ("variant__sku", "variant__product__name", "warehouse__code")

    @admin.display(description="Available", ordering="quantity_on_hand")
    def quantity_available(self, obj):
        """Computed: quantity_on_hand - quantity_reserved (read-only display)."""
        return obj.quantity_available
