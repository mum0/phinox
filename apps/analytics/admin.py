"""apps.analytics — admin for Attribution + Event.

Schema-only models — no analytics SDK integration in the codebase.
The admin provides visibility into captured attribution / event rows.
"""
from django.contrib import admin

from .models import Attribution, Event


@admin.register(Attribution)
class AttributionAdmin(admin.ModelAdmin):
    list_display = (
        "session_key",
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "qr_code",
        "first_seen_at",
    )
    list_filter = ("utm_source", "utm_medium")
    search_fields = ("session_key", "utm_campaign", "utm_content", "utm_term", "qr_code")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("session_key", "event_type", "created_at")
    list_filter = ("event_type",)
    search_fields = ("session_key",)
