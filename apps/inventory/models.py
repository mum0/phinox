"""
apps.inventory — Warehouse + stock levels per variant.
Phase 2 scope: schema only. Reservation/release logic (StockReservationService
in IMPLEMENTATION_PLAN.md §5.3) is business logic and comes later.
"""
from django.db import models

from apps.catalog.models import ProductVariant


class Warehouse(models.Model):
    """Normalizes stock location out of Inventory itself (3NF: a variant's
    stock can exist at more than one location, so location is its own
    entity rather than a repeated column set on Inventory). Single-warehouse
    deployments just get one row here (e.g. 'MAIN')."""

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=120)
    governorate = models.CharField(max_length=32, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "inventory_warehouse"

    def __str__(self):
        return self.name


class Inventory(models.Model):
    """Stock level for one variant at one warehouse. BigAutoField pk —
    internal operational record, not externally referenced."""

    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name="inventory_records")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="inventory_records")
    quantity_on_hand = models.PositiveIntegerField(default=0)
    quantity_reserved = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=5)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "inventory_stock"
        verbose_name_plural = "inventory"
        constraints = [
            models.UniqueConstraint(fields=["variant", "warehouse"], name="uniq_inventory_per_variant_warehouse"),
            # Reserved cannot exceed on-hand (existing constraint — upper bound).
            models.CheckConstraint(
                check=models.Q(quantity_reserved__lte=models.F("quantity_on_hand")),
                name="inventory_reserved_lte_on_hand",
            ),
            # PHASE-B §B2: reserved must be >= 0 (the PositiveIntegerField
            # enforces this at the form layer, but the CheckConstraint
            # enforces it at the DB layer too — defense in depth against
            # negative values sneaking in via raw SQL or a bug in the F()
            # expression arithmetic). The constraint also catches the
            # edge case where release_inventory_reservation is called
            # twice (the second call would underflow to -1 without
            # this constraint; with it, the second release is a no-op
            # because the F() expression only decrements what's actually
            # reserved — but the constraint is still belt-and-suspenders).
            models.CheckConstraint(
                check=models.Q(quantity_reserved__gte=0),
                name="inventory_reserved_gte_0",
            ),
        ]
        indexes = [
            models.Index(fields=["variant", "warehouse"], name="inventory_variant_wh_idx"),
            models.Index(fields=["quantity_on_hand"], name="inventory_qty_idx"),
        ]

    @property
    def quantity_available(self):
        return self.quantity_on_hand - self.quantity_reserved

    def __str__(self):
        return f"{self.variant.sku} @ {self.warehouse.code}: {self.quantity_on_hand}"
