"""apps.core — admin registration for the IDSequence counter.

The IDSequence table is the atomic counter backing the PHINOX stable ID
system (PHX-ORD-000001, PHX-CUS-000001, etc.). It should be effectively
read-only from the admin — operators should not be hand-editing the
sequence. We expose it for visibility / debugging only.
"""
from django.contrib import admin

from .models import IDSequence


@admin.register(IDSequence)
class IDSequenceAdmin(admin.ModelAdmin):
    list_display = ("prefix", "last_number", "updated_at")
    search_fields = ("prefix",)
    readonly_fields = ("prefix", "last_number", "updated_at")

    # Effectively read-only: prevent creating / deleting sequences by hand
    # — they are managed atomically by next_business_id() / next_sku().
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
