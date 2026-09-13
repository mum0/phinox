"""
Add shipping_address FK to Order.

This was identified as a gap during Phase 3 — the Order model didn't have
a shipping_address FK, so the CheckoutView couldn't persist the chosen
address. This migration adds it (nullable, SET_NULL).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0001_initial"),
        ("shipping", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="shipping_address",
            field=models.ForeignKey(
                blank=True,
                help_text="Saved shipping address used for this order. SET_NULL so order history survives address deletion.",
                null=True,
                on_delete=models.SET_NULL,
                related_name="orders",
                to="shipping.shippingaddress",
            ),
        ),
    ]
