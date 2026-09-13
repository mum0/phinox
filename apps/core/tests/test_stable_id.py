"""
apps.core — tests for the Stable ID system.

Covers:
  - next_business_id() atomic sequence generation (PHX-ORD-000001 format)
  - next_sku() per-family sequence (PHX-WNT-001, independent families)
  - IDSequence row tracking
  - 6-digit padding for business IDs, 3-digit padding for SKUs
"""
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.core.models import IDSequence, next_business_id, next_sku


class NextBusinessIDTests(TestCase):
    """Tests for next_business_id() — the atomic 6-digit sequence generator."""

    def test_business_id_format(self) -> None:
        """Generated business IDs match the PHX-{PREFIX}-000001 format."""
        bid = next_business_id("ORD")
        self.assertEqual(bid, "PHX-ORD-000001")

        bid2 = next_business_id("CUS")
        self.assertEqual(bid2, "PHX-CUS-000001")

    def test_business_id_sequential(self) -> None:
        """Repeated calls for the same prefix produce sequential IDs."""
        first = next_business_id("ORD")
        second = next_business_id("ORD")
        third = next_business_id("ORD")

        self.assertEqual(first, "PHX-ORD-000001")
        self.assertEqual(second, "PHX-ORD-000002")
        self.assertEqual(third, "PHX-ORD-000003")

    def test_business_id_six_digit_padding(self) -> None:
        """IDs are zero-padded to 6 digits."""
        # Generate 10 IDs so the 10th is PHX-ORD-000010
        for _ in range(9):
            next_business_id("PAD")
        tenth = next_business_id("PAD")
        self.assertEqual(tenth, "PHX-PAD-000010")

    def test_business_id_atomic(self) -> None:
        """Repeated calls produce distinct, sequential IDs — the atomicity contract.

        ``next_business_id`` uses ``select_for_update`` inside
        ``transaction.atomic()`` to guarantee that no two callers ever
        receive the same ID. Under PostgreSQL this provides true
        multi-connection atomicity; under SQLite (the test DB) writes are
        serialized, but the observable contract — uniqueness + sequential
        ordering — must still hold. We verify it with a burst of calls.

        NOTE: a true threaded concurrency test is not reliable under
        SQLite + Django's TestCase (which wraps each test in a single
        connection-scoped transaction). The select_for_update in the
        implementation is the source of correctness; this test asserts
        the externally-observable behavior.
        """
        prefix = "SEQ"
        n_calls = 50
        ids = [next_business_id(prefix) for _ in range(n_calls)]

        # All IDs must be unique
        self.assertEqual(len(ids), len(set(ids)), "Duplicate business IDs generated")
        # All must match the expected sequential format
        for i, bid in enumerate(ids, start=1):
            self.assertEqual(bid, f"PHX-SEQ-{i:06d}")

    def test_business_id_creates_sequence_row(self) -> None:
        """Calling next_business_id creates an IDSequence row for the prefix."""
        self.assertFalse(IDSequence.objects.filter(prefix="NEW").exists())
        next_business_id("NEW")
        seq = IDSequence.objects.get(prefix="NEW")
        self.assertEqual(seq.last_number, 1)

    def test_independent_prefixes_independent_sequences(self) -> None:
        """Different prefixes maintain independent counters."""
        ord1 = next_business_id("ORD")
        cus1 = next_business_id("CUS")
        ord2 = next_business_id("ORD")
        cus2 = next_business_id("CUS")

        self.assertEqual(ord1, "PHX-ORD-000001")
        self.assertEqual(ord2, "PHX-ORD-000002")
        self.assertEqual(cus1, "PHX-CUS-000001")
        self.assertEqual(cus2, "PHX-CUS-000002")


class NextSKUTests(TestCase):
    """Tests for next_sku() — the per-family 3-digit sequence generator."""

    def test_sku_format(self) -> None:
        """SKUs match the PHX-{FAMILY}-001 format with 3-digit padding."""
        sku = next_sku("WNT")
        self.assertEqual(sku, "PHX-WNT-001")

    def test_sku_three_digit_padding(self) -> None:
        """SKUs are zero-padded to 3 digits."""
        for _ in range(9):
            next_sku("PAD")
        tenth = next_sku("PAD")
        self.assertEqual(tenth, "PHX-PAD-010")
        # 100th should be 3 digits still (no overflow until 1000)
        for _ in range(89):
            next_sku("PAD")
        hundredth = next_sku("PAD")
        self.assertEqual(hundredth, "PHX-PAD-100")

    def test_sku_per_family(self) -> None:
        """Each family code maintains an independent sequence.

        PHX-WNT-001, PHX-WNT-002 — and a different family (e.g. SUM)
        starts at its own 001.
        """
        wnt1 = next_sku("WNT")
        wnt2 = next_sku("WNT")
        sum1 = next_sku("SUM")
        wnt3 = next_sku("WNT")
        sum2 = next_sku("SUM")

        self.assertEqual(wnt1, "PHX-WNT-001")
        self.assertEqual(wnt2, "PHX-WNT-002")
        self.assertEqual(wnt3, "PHX-WNT-003")
        self.assertEqual(sum1, "PHX-SUM-001")
        self.assertEqual(sum2, "PHX-SUM-002")

    def test_sku_uses_sku_prefixed_sequence_row(self) -> None:
        """SKU sequences are stored as prefix='SKU_{FAMILY}' in IDSequence."""
        next_sku("WNT")
        seq = IDSequence.objects.get(prefix="SKU_WNT")
        self.assertEqual(seq.last_number, 1)
        # And it's distinct from a raw 'WNT' business-id sequence
        next_business_id("WNT")
        self.assertTrue(IDSequence.objects.filter(prefix="WNT").exists())
        self.assertTrue(IDSequence.objects.filter(prefix="SKU_WNT").exists())


class IDSequenceModelTests(TestCase):
    """Direct tests on the IDSequence model."""

    def test_str_representation(self) -> None:
        seq = IDSequence.objects.create(prefix="ORD", last_number=42)
        self.assertEqual(str(seq), "ORD → 42")

    def test_prefix_unique(self) -> None:
        """Prefix must be unique."""
        IDSequence.objects.create(prefix="DUP", last_number=1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                IDSequence.objects.create(prefix="DUP", last_number=2)

    def test_default_last_number(self) -> None:
        seq = IDSequence.objects.create(prefix="DEF")
        self.assertEqual(seq.last_number, 0)
