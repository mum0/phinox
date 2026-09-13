"""apps.shipping — admin for ShippingMethod + ShippingAddress.

ShippingMethod.estimated_days is computed from estimated_days_min /
estimated_days_max for display convenience.
"""
from django.contrib import admin

from .models import ShippingAddress, ShippingMethod


@admin.register(ShippingMethod)
class ShippingMethodAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "price", "estimated_days", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code")

    @admin.display(description="Estimated days")
    def estimated_days(self, obj):
        if obj.estimated_days_min == obj.estimated_days_max:
            return f"{obj.estimated_days_min}"
        return f"{obj.estimated_days_min}-{obj.estimated_days_max}"


@admin.register(ShippingAddress)
class ShippingAddressAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "phone", "city", "country", "is_default")
    list_filter = ("is_default", "country", "city")
    search_fields = ("full_name", "phone", "city", "address", "user__username", "user__customer_id")
