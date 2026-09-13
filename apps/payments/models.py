"""
apps.payments — Payment with provider support.

Supports: COD (Cash on Delivery), Paymob (card/valu), Fawry.
Per دستور: COD is live, card payments are test-mode only (is_test_transaction=True).

Stable IDs:
  - Payment.business_id → PHX-PAY-000001 (via BusinessIDModel)

CheckConstraints: amount > 0.
No payment gateway logic here — that's in services.py (test-mode simulation only).
"""
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import BusinessIDModel


class Payment(BusinessIDModel):
    """A payment record against an order. Business ID: PHX-PAY-000001.

    An order may have multiple Payment rows over its lifetime (e.g. a
    failed attempt followed by a successful retry, or a later refund).

    provider_transaction_id is unique per provider to prevent duplicate
    processing of the same gateway transaction.

    is_test_transaction defaults to True per دستور (payments in test mode).
    """

    class PaymentProvider(models.TextChoices):
        COD = "cod", "Cash on Delivery"
        PAYMOB = "paymob", "Paymob"
        FAWRY = "fawry", "Fawry"
        VALU = "valu", "valU (BNPL)"

    class MethodType(models.TextChoices):
        COD = "cod", "Cash on Delivery"
        CARD = "card", "Card"
        WALLET = "wallet", "Wallet"
        INSTALLMENT = "installment", "Installment"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    BUSINESS_ID_PREFIX = "PAY"

    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="payments",
    )
    payment_provider = models.CharField(
        max_length=10,
        choices=PaymentProvider.choices,
        default=PaymentProvider.COD,
    )
    method_type = models.CharField(
        max_length=12,
        choices=MethodType.choices,
        default=MethodType.COD,
    )
    provider_transaction_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "Gateway-assigned transaction ID (Paymob's ``obj.id`` from the "
            "webhook payload). Unique per provider. Populated by the webhook "
            "handler on first capture for idempotency."
        ),
    )
    paymob_order_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "PHASE-A §A4: Paymob's order ID (``obj.order.id`` from the webhook "
            "payload). Stored at payment initialization time "
            "(``initialize_paymob_payment``) so the webhook can look the "
            "Payment up by this key. Different from ``provider_transaction_id`` "
            "(which is the transaction ID, populated later by the webhook)."
        ),
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    currency = models.CharField(max_length=3, default="EGP")
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    is_test_transaction = models.BooleanField(
        default=True,
        help_text="Per دستور: all payments default to test mode.",
    )
    webhook_payload = models.JSONField(
        null=True,
        blank=True,
        help_text="Last raw webhook payload from the provider (for audit/debugging).",
    )
    failure_reason = models.TextField(blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "payments_payment"
        indexes = [
            models.Index(fields=["business_id"], name="pay_business_id_idx"),
            models.Index(fields=["order"], name="pay_order_idx"),
            models.Index(fields=["payment_provider", "status"], name="pay_provider_status_idx"),
            models.Index(fields=["provider_transaction_id"], name="pay_txn_id_idx"),
            # PHASE-A §A4: webhook lookup path is by paymob_order_id.
            models.Index(fields=["paymob_order_id"], name="pay_paymob_order_id_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name="payment_amount_must_be_positive",
            ),
            # Unique transaction ID per provider (when not null)
            models.UniqueConstraint(
                fields=["payment_provider", "provider_transaction_id"],
                name="uniq_provider_transaction_id",
                condition=models.Q(provider_transaction_id__isnull=False),
            ),
            # PHASE-A §A4: paymob_order_id is unique per provider so two
            # Payment rows can never claim the same Paymob order.
            models.UniqueConstraint(
                fields=["payment_provider", "paymob_order_id"],
                name="uniq_paymob_order_id",
                condition=models.Q(paymob_order_id__isnull=False),
            ),
        ]

    def __str__(self):
        return f"{self.business_id} — {self.amount} {self.currency} ({self.status})"


# ---------------------------------------------------------------------------
# PHASE-D §D6: PaymentStatusChange — audit log for status transitions.
# ---------------------------------------------------------------------------
# Per دستور §5 (Payments): "every Payment.status change is auditable."
# This model records each transition (old_status → new_status, the actor
# who triggered it, + a reason). The webhook handler, the PaymentSimulationView,
# and any admin manual-capture action (e.g. COD manual capture) all write a
# row here.
#
# Designed as an append-only audit log: no UPDATEs, only INSERTs. Per
# دستور §5: never log secrets / PII in Sentry breadcrumbs — the reason
# field is short + human-readable (no card numbers, no addresses).
class PaymentStatusChange(models.Model):
    """Audit-log row for a Payment.status transition.

    One row per status change. Records:
      - payment: FK to the Payment (CASCADE — if the Payment is deleted,
        the audit log goes too; in practice Payments are never deleted).
      - old_status: the status BEFORE the transition (null for the initial
        PENDING → ... transition on Payment creation).
      - new_status: the status AFTER the transition.
      - changed_by: FK to the user who triggered the change (null for
        webhook-triggered changes — Paymob doesn't have a Django user).
      - reason: short human-readable note (e.g. "Paymob webhook captured",
        "COD manual capture by admin", "Payment refunded via dashboard").
      - created_at: timestamp of the transition (auto-set).

    The model is append-only — never UPDATE a row. Per دستور §6:
    ``transaction.atomic()`` for the (Payment update + PaymentStatusChange
    insert) pair so the audit log is always in sync with the Payment state.
    """

    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name="status_changes",
    )
    old_status = models.CharField(
        max_length=10,
        choices=Payment.Status.choices,
        null=True,
        blank=True,
        help_text="Status BEFORE the transition. Null for the initial creation.",
    )
    new_status = models.CharField(
        max_length=10,
        choices=Payment.Status.choices,
        help_text="Status AFTER the transition.",
    )
    changed_by = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.SET_NULL,
        related_name="payment_status_changes",
        null=True,
        blank=True,
        help_text=(
            "The user who triggered the change. Null for webhook-triggered "
            "changes (Paymob doesn't have a Django user)."
        ),
    )
    reason = models.CharField(
        max_length=200,
        blank=True,
        help_text="Short human-readable note (e.g. 'Paymob webhook captured').",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "payments_status_change"
        verbose_name = "Payment status change"
        verbose_name_plural = "Payment status changes"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["payment", "-created_at"], name="paychg_payment_created_idx"),
            models.Index(fields=["changed_by"], name="paychg_changed_by_idx"),
            models.Index(fields=["new_status"], name="paychg_new_status_idx"),
        ]

    def __str__(self):
        actor = self.changed_by.username if self.changed_by_id else "system"
        return f"{self.payment.business_id}: {self.old_status}→{self.new_status} by {actor}"
