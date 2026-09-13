"""
apps.promotions — Campaign + PromoCode (database-driven, no hard-coded codes).

Per دستور §7: Promo codes are database-driven. No hard-coded promo codes
anywhere in the codebase. The Campaign model groups related codes for
reporting; PromoCode holds the actual discount logic.

CheckConstraints:
  - percentage: 0 <= value <= 100
  - fixed: value > 0
"""
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.text import slugify

from apps.core.models import BaseModel


class Campaign(BaseModel):
    """A marketing campaign that groups one or more promo codes.

    Example: "Winter Launch 2025" campaign with codes WINTER10, WINTER20.
    """

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "promotions_campaign"
        indexes = [models.Index(fields=["slug"], name="campaign_slug_idx")]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class PromoCode(BaseModel):
    """A database-driven promotional code.

    Discount types:
      - percentage: value is 0-100 (percentage of order subtotal)
      - fixed: value is a fixed amount in the given currency

    Limits:
      - usage_limit: total uses across all customers (null = unlimited)
      - per_customer_limit: max uses per customer (null = unlimited)
      - used_count: incremented when applied (managed by services layer)

    Validity window:
      - starts_at / ends_at: when the code is active
      - is_active: manual override to deactivate without deleting
    """

    class DiscountType(models.TextChoices):
        PERCENTAGE = "percentage", "Percentage"
        FIXED = "fixed", "Fixed Amount"

    code = models.CharField(max_length=50, unique=True, db_index=True)
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.SET_NULL,
        related_name="promo_codes",
        null=True,
        blank=True,
    )
    discount_type = models.CharField(max_length=11, choices=DiscountType.choices)
    value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    currency = models.CharField(max_length=3, default="EGP")
    min_order_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(0)],
    )
    usage_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Total uses across all customers. Null = unlimited.",
    )
    per_customer_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Max uses per customer. Null = unlimited.",
    )
    used_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "promotions_promo_code"
        indexes = [
            models.Index(fields=["code"], name="promo_code_idx"),
            models.Index(fields=["is_active", "starts_at", "ends_at"], name="promo_validity_idx"),
        ]
        constraints = [
            # Percentage: 0 <= value <= 100
            models.CheckConstraint(
                check=(
                    models.Q(discount_type="percentage", value__gte=0, value__lte=100)
                    | models.Q(discount_type__exact="fixed")
                ),
                name="promo_percentage_bounds_0_100",
            ),
            # Fixed: value > 0
            models.CheckConstraint(
                check=(
                    models.Q(discount_type="fixed", value__gt=0)
                    | models.Q(discount_type__exact="percentage")
                ),
                name="promo_fixed_must_be_positive",
            ),
        ]

    def __str__(self):
        return f"{self.code} ({self.discount_type} {self.value})"
