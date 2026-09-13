"""PHASE-B §B1 — Backfill snapshot fields on existing Order + OrderItem rows.

Populates the new snapshot fields (added in 0003_phase_b_snapshot_denormalization)
for rows that already existed before this migration. New rows going forward
get the snapshots populated by ``create_order_from_cart`` + ``snapshot_order_items``
in apps/orders/services.py.

The backfill is idempotent — it only fills in empty snapshot fields. If a row
already has a snapshot value (e.g. set by a later code path), the existing
value is preserved.
"""
from django.db import migrations


def backfill_order_snapshots(apps, schema_editor):
    """Copy shipping_address → Order snapshot fields for existing orders."""
    Order = apps.get_model("orders", "Order")
    ShippingAddress = apps.get_model("shipping", "ShippingAddress")

    for order in Order.objects.exclude(shipping_address__isnull=True).all():
        addr = order.shipping_address
        # Only fill empty fields (idempotent — don't overwrite snapshots
        # that were already set by a previous run or by the checkout flow).
        update_fields = []
        if not order.shipping_recipient_name:
            order.shipping_recipient_name = addr.full_name or ""
            update_fields.append("shipping_recipient_name")
        if not order.shipping_phone_number:
            order.shipping_phone_number = addr.phone or ""
            update_fields.append("shipping_phone_number")
        if not order.shipping_governorate:
            order.shipping_governorate = getattr(addr, "governorate", "") or ""
            update_fields.append("shipping_governorate")
        if not order.shipping_city:
            order.shipping_city = addr.city or ""
            update_fields.append("shipping_city")
        if not order.shipping_street_address:
            order.shipping_street_address = addr.address or ""
            update_fields.append("shipping_street_address")
        if update_fields:
            update_fields.append("updated_at")
            order.save(update_fields=update_fields)


def backfill_orderitem_snapshots(apps, schema_editor):
    """Copy variant.product → OrderItem snapshot fields for existing items."""
    OrderItem = apps.get_model("orders", "OrderItem")

    # PHASE-B §B1 fix: the correct select_related chain is variant__size and
    # variant__color (NOT variant__product__size — Product has no `size` FK;
    # the size FK is on ProductVariant, not Product).
    for item in OrderItem.objects.exclude(variant__isnull=True).select_related(
        "variant__product", "variant__size", "variant__color",
    ):
        variant = item.variant
        update_fields = []
        if not item.product_name:
            item.product_name = variant.product.name if variant.product_id else ""
            update_fields.append("product_name")
        if not item.variant_sku:
            item.variant_sku = variant.sku or ""
            update_fields.append("variant_sku")
        if not item.size_label and getattr(variant, "size_id", None):
            size = variant.size
            if size is not None:
                item.size_label = size.name or ""
                update_fields.append("size_label")
        if not item.color_name and getattr(variant, "color_id", None):
            color = variant.color
            if color is not None:
                item.color_name = color.name or ""
                update_fields.append("color_name")
        if update_fields:
            update_fields.append("updated_at")
            item.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0003_phase_b_snapshot_denormalization"),
        ("shipping", "0002_phase_b_snapshot_denormalization"),
        ("catalog", "0002_color_productvariant_color_size_productvariant_size"),
    ]

    operations = [
        migrations.RunPython(
            backfill_order_snapshots,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RunPython(
            backfill_orderitem_snapshots,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
