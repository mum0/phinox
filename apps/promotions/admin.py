"""apps.promotions — admin for Campaign + PromoCode.

PromoCode is edited inline on the Campaign admin for convenience, and
also registered standalone for direct code lookup / management.
"""
from django.contrib import admin

from .models import Campaign, PromoCode


class PromoCodeInline(admin.TabularInline):
    model = PromoCode
    extra = 1


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "starts_at", "ends_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [PromoCodeInline]


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "discount_type",
        "value",
        "campaign",
        "used_count",
        "usage_limit",
        "is_active",
    )
    list_filter = ("discount_type", "is_active")
    search_fields = ("code", "campaign__name")
