"""
apps.reviews — Product reviews.

Updated: inherits from BaseModel (BigAutoField PK + timestamps) instead
of the deprecated TimeStampedModel.
"""
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.catalog.models import Product
from apps.core.models import BaseModel


class Review(BaseModel):
    """A product review by a user. Rating 1-5, one review per user per product."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    title = models.CharField(max_length=150, blank=True)
    body = models.TextField(blank=True)
    is_verified_purchase = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False, help_text="Moderation gate — set by staff.")

    class Meta:
        db_table = "reviews_review"
        indexes = [
            models.Index(fields=["product", "is_approved"], name="review_product_approved_idx"),
            models.Index(fields=["user"], name="review_user_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["product", "user"], name="uniq_review_per_user_per_product"),
            models.CheckConstraint(check=models.Q(rating__gte=1) & models.Q(rating__lte=5), name="review_rating_range_1_5"),
        ]

    def __str__(self):
        return f"{self.rating}★ — {self.product.name} by {self.user}"
