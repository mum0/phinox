"""apps.payments — admin for Payment + PaymentStatusChange audit log.

business_id on Payment is auto-generated and therefore read-only.
transaction_id is exposed as a display alias for provider_transaction_id.

PHASE-D §D6: PaymentStatusChange is registered read-only — append-only
audit log. Staff can read the audit trail but cannot edit individual
rows (the integrity contract is: Payment.status changes ALWAYS have a
matching PaymentStatusChange row written in the same transaction).
"""
from django.contrib import admin

from .models import Payment, PaymentStatusChange


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "business_id",
        "order",
        "payment_provider",
        "amount",
        "currency",
        "status",
        "transaction_id",
        "paid_at",
    )
    list_filter = ("payment_provider", "status", "currency")
    search_fields = (
        "business_id",
        "order__business_id",
        "provider_transaction_id",
        "paymob_order_id",
    )
    readonly_fields = ("business_id",)

    @admin.display(description="Transaction ID", ordering="provider_transaction_id")
    def transaction_id(self, obj):
        return obj.provider_transaction_id


@admin.register(PaymentStatusChange)
class PaymentStatusChangeAdmin(admin.ModelAdmin):
    """Read-only audit log viewer for Payment status transitions.

    Per دستور §5: the audit log is append-only — staff cannot edit or
    delete rows. They CAN view the full transition history for any
    Payment (filtered by payment, by changed_by, by new_status).
    """
    list_display = (
        "payment",
        "old_status",
        "new_status",
        "changed_by",
        "reason",
        "created_at",
    )
    list_filter = ("new_status", "old_status", "created_at")
    search_fields = (
        "payment__business_id",
        "payment__provider_transaction_id",
        "payment__paymob_order_id",
        "reason",
        "changed_by__username",
    )
    # PHASE-D §D6: read-only — no edits, no deletes, no adds.
    actions = None
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False
    def get_readonly_fields(self, request, obj=None):
        # All fields are read-only — append-only audit log.
        return [f.name for f in self.model._meta.fields]
