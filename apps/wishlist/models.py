"""
apps.wishlist — Saved-for-later items.

Updated: inherits from BaseModel (BigAutoField PK + timestamps) instead
of the deprecated TimeStampedModel.
"""
from django.conf import settings
from django.db import models

from apps.catalog.models import Product, ProductVariant
from apps.core.models import BaseModel


class WishlistItem(BaseModel):
    """A user's saved product (optionally pinned to a specific variant)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist_items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlisted_by")
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name="wishlisted_by",
        null=True,
        blank=True,
        help_text="Optional — set when the user saved a specific size/color.",
    )

    class Meta:
        db_table = "wishlist_item"
        indexes = [models.Index(fields=["user", "-created_at"], name="wishlist_user_created_idx")]
        constraints = [
            models.UniqueConstraint(fields=["user", "product", "variant"], name="uniq_wishlist_entry"),
        ]

    def __str__(self):
        return f"{self.user} ♥ {self.product.name}"
