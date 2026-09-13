"""
apps.analytics — tests for Attribution + Event.

Covers:
  - Attribution creation with UTM + QR fields
  - Attribution.session_key uniqueness
  - Event creation with event_data JSON
  - Event types (page_view, view_item, add_to_cart, begin_checkout, purchase)
  - Linking Attribution to an Order
"""
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.analytics.models import Attribution, Event
from apps.orders.models import Order


class AttributionTests(TestCase):
    def test_attribution_creation(self) -> None:
        """Attribution captures UTM + QR fields for a session."""
        attr = Attribution.objects.create(
            session_key="sess-001",
            utm_source="instagram",
            utm_medium="social",
            utm_campaign="winter_launch",
            utm_content="banner_a",
            utm_term="coat",
            qr_code="QR-WINTER-001",
        )
        self.assertEqual(attr.session_key, "sess-001")
        self.assertEqual(attr.utm_source, "instagram")
        self.assertEqual(attr.utm_medium, "social")
        self.assertEqual(attr.utm_campaign, "winter_launch")
        self.assertEqual(attr.utm_content, "banner_a")
        self.assertEqual(attr.utm_term, "coat")
        self.assertEqual(attr.qr_code, "QR-WINTER-001")
        self.assertIsNone(attr.order)
        self.assertIsNotNone(attr.first_seen_at)
        self.assertIsNotNone(attr.last_seen_at)

    def test_attribution_session_key_unique(self) -> None:
        """session_key must be unique (one attribution per session)."""
        Attribution.objects.create(session_key="dup", utm_source="x")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Attribution.objects.create(session_key="dup", utm_source="y")

    def test_attribution_empty_utm_allowed(self) -> None:
        """All UTM fields are optional (blank=True)."""
        attr = Attribution.objects.create(session_key="empty-utm")
        self.assertEqual(attr.utm_source, "")
        self.assertEqual(attr.utm_medium, "")
        self.assertEqual(attr.qr_code, "")

    def test_attribution_str_representation(self) -> None:
        attr = Attribution.objects.create(
            session_key="s1", utm_source="google", utm_medium="cpc"
        )
        self.assertEqual(str(attr), "s1 — google/cpc")

    def test_attribution_links_to_order(self) -> None:
        """Attribution can be linked to an Order at purchase time."""
        order = Order.objects.create(
            subtotal=Decimal("100"),
            discount_total=Decimal("0"),
            shipping_cost=Decimal("0"),
            grand_total=Decimal("100"),
        )
        attr = Attribution.objects.create(session_key="link-test", order=order)
        self.assertEqual(attr.order, order)
        self.assertIn(attr, order.attributions.all())


class EventTests(TestCase):
    def test_event_creation(self) -> None:
        """Event captures session_key + event_type + JSON event_data."""
        ev = Event.objects.create(
            session_key="sess-001",
            event_type=Event.EventType.ADD_TO_CART,
            event_data={"product_id": 1, "variant_sku": "PHX-WNT-001", "quantity": 2},
        )
        self.assertEqual(ev.session_key, "sess-001")
        self.assertEqual(ev.event_type, Event.EventType.ADD_TO_CART)
        self.assertEqual(ev.event_data["variant_sku"], "PHX-WNT-001")
        self.assertEqual(ev.event_data["quantity"], 2)

    def test_event_default_data_empty_dict(self) -> None:
        """event_data defaults to an empty dict."""
        ev = Event.objects.create(
            session_key="sess-002",
            event_type=Event.EventType.PAGE_VIEW,
        )
        self.assertEqual(ev.event_data, {})

    def test_event_types_choices(self) -> None:
        """All 5 event types from the user journey are defined."""
        choices = {c[0] for c in Event.EventType.choices}
        self.assertEqual(
            choices,
            {"page_view", "view_item", "add_to_cart", "begin_checkout", "purchase"},
        )

    def test_event_ordering_newest_first(self) -> None:
        """Events are ordered by -created_at (newest first)."""
        ev1 = Event.objects.create(
            session_key="o", event_type=Event.EventType.PAGE_VIEW
        )
        ev2 = Event.objects.create(
            session_key="o", event_type=Event.EventType.VIEW_ITEM
        )
        events = list(Event.objects.filter(session_key="o"))
        self.assertEqual(events[0], ev2)
        self.assertEqual(events[1], ev1)

    def test_event_str_representation(self) -> None:
        ev = Event.objects.create(
            session_key="s9", event_type=Event.EventType.PURCHASE
        )
        self.assertEqual(str(ev), "s9 — purchase")

    def test_multiple_events_per_session(self) -> None:
        """A session can have many events across the journey."""
        for et in Event.EventType.values:
            Event.objects.create(session_key="journey", event_type=et)
        self.assertEqual(Event.objects.filter(session_key="journey").count(), 5)
