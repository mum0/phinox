"""
apps.analytics — Attribution + Event tracking.

Per دستور §8/§10: Attribution captures UTM parameters + QR code source
for marketing analytics. Events track user journey (page_view → view_item
→ add_to_cart → begin_checkout → purchase).

No external analytics SDK integration here — schema only. The services
layer (analytics/services.py) provides capture_attribution(), track_event(),
and link_attribution_to_order().
"""
from django.db import models

from apps.core.models import BaseModel


class Attribution(BaseModel):
    """Marketing attribution for a session.

    Captured when a user arrives with UTM parameters or a QR code.
    Linked to an order at purchase time via link_attribution_to_order().
    """

    session_key = models.CharField(max_length=64, unique=True, db_index=True)
    utm_source = models.CharField(max_length=100, blank=True)
    utm_medium = models.CharField(max_length=100, blank=True)
    utm_campaign = models.CharField(max_length=100, blank=True)
    utm_content = models.CharField(max_length=100, blank=True)
    utm_term = models.CharField(max_length=100, blank=True)
    qr_code = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="QR code identifier if the user arrived via a QR scan.",
    )
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    # Link to order (set at purchase time)
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        related_name="attributions",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "analytics_attribution"
        indexes = [
            models.Index(fields=["session_key"], name="attr_session_idx"),
            models.Index(fields=["utm_source"], name="attr_utm_source_idx"),
            models.Index(fields=["qr_code"], name="attr_qr_code_idx"),
        ]

    def __str__(self):
        return f"{self.session_key} — {self.utm_source}/{self.utm_medium}"


class Event(BaseModel):
    """A user journey event.

    Tracks the path from discovery to purchase:
    page_view → view_item → add_to_cart → begin_checkout → purchase
    """

    class EventType(models.TextChoices):
        PAGE_VIEW = "page_view", "Page View"
        VIEW_ITEM = "view_item", "View Item"
        ADD_TO_CART = "add_to_cart", "Add to Cart"
        BEGIN_CHECKOUT = "begin_checkout", "Begin Checkout"
        PURCHASE = "purchase", "Purchase"

    session_key = models.CharField(max_length=64, db_index=True)
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    event_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Event-specific data (e.g. {product_id, variant_sku, quantity}).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "analytics_event"
        indexes = [
            models.Index(fields=["session_key", "event_type"], name="event_session_type_idx"),
            models.Index(fields=["event_type", "-created_at"], name="event_type_created_idx"),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.session_key} — {self.event_type}"
