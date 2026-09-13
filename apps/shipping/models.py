"""
apps.shipping — ShippingMethod + ShippingAddress.

ShippingMethod: available shipping options (Standard, Same-Day Alexandria, etc.)
ShippingAddress: user's saved delivery addresses.

CheckConstraints: price >= 0 on ShippingMethod.
"""
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import BaseModel


class ShippingMethod(BaseModel):
    """A shipping option available at checkout.

    Example: "Standard Ground" (code=STD, price=50, estimated_days=3-5)
             "Same Day Alexandria" (code=SDC, price=100, estimated_days=1)
    """

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=10, unique=True, db_index=True)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    currency = models.CharField(max_length=3, default="EGP")
    estimated_days_min = models.PositiveSmallIntegerField(default=1)
    estimated_days_max = models.PositiveSmallIntegerField(default=5)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "shipping_method"
        indexes = [models.Index(fields=["code", "is_active"], name="shipmethod_code_active_idx")]
        constraints = [
            models.CheckConstraint(check=models.Q(price__gte=0), name="shipmethod_price_non_negative"),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class ShippingAddress(BaseModel):
    """A user's saved delivery address.

    PHASE-B §B1: added ``governorate`` (Egyptian context per دستور §5 —
    27 governorates). The Order snapshot copies this into
    ``shipping_governorate`` at checkout time.

    PHASE-B §B4: added ``is_active`` for soft-delete. When a user deletes
    an address that's referenced by an Order, we soft-delete (is_active=False)
    instead of hard-deleting — the Order's shipping_address FK is SET_NULL
    on hard-delete, but the snapshot fields (shipping_recipient_name etc.)
    survive regardless.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="shipping_addresses",
    )
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    # Egyptian context (per دستور §5): one of the 27 governorates.
    governorate = models.CharField(
        max_length=32, blank=True,
        help_text="One of the 27 Egyptian governorates (e.g. 'Alexandria', 'Cairo').",
    )
    city = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default="Egypt")
    address = models.TextField()
    postal_code = models.CharField(max_length=20, blank=True)
    is_default = models.BooleanField(default=False)
    # PHASE-B §B4: soft-delete flag. AddressListView filters is_active=True;
    # AddressDeleteView soft-deletes when the address is referenced by an Order.
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "shipping_address"
        indexes = [models.Index(fields=["user", "is_default"], name="shipaddr_user_default_idx")]

    def __str__(self):
        return f"{self.full_name} — {self.city}"
