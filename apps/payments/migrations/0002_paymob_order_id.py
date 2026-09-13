"""PHASE-A §A4 — Add ``paymob_order_id`` to Payment + unique constraint.

This migration fixes the Paymob webhook double-bug:

  Bug A (lookup-key mismatch):
    ``initialize_paymob_payment`` previously stored the Paymob order ID in
    ``provider_transaction_id``. The webhook then looked up the Payment by
    filtering on ``provider_transaction_id`` against the webhook's
    ``transaction_id`` (``obj.id`` in the payload). But ``obj.id`` is the
    Paymob *transaction* ID, NOT the Paymob *order* ID — they are different
    values. So the lookup never matched and every real webhook returned
    ``transaction_not_found``.

  Fix:
    Introduce a dedicated ``paymob_order_id`` field. ``initialize_paymob_payment``
    stores the order ID there. The webhook looks up by ``paymob_order_id``
    (extracted from ``obj.order.id`` in the payload), and AFTER updating the
    Payment it stores the transaction ID (``obj.id``) in
    ``provider_transaction_id`` for downstream idempotency.

  Bug B (select_for_update outside atomic):
    The previous webhook view called ``select_for_update()`` *before* entering
    ``transaction.atomic()`` — which is a no-op on SQLite and a programming
    error on Postgres (the lock would never be held). Fixed in the view code
    by moving the lookup inside the atomic block.

The new field is nullable because old Payment rows (COD, simulate_card_payment
rows, etc.) have no paymob_order_id. The unique constraint is conditional on
``paymob_order_id__isnull=False`` so NULLs don't collide.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="paymob_order_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text=(
                    "PHASE-A §A4: Paymob's order ID (``obj.order.id`` from the "
                    "webhook payload). Stored at payment initialization time "
                    "(``initialize_paymob_payment``) so the webhook can look "
                    "the Payment up by this key. Different from "
                    "``provider_transaction_id`` (which is the transaction ID, "
                    "populated later by the webhook)."
                ),
                max_length=100,
                null=True,
            ),
        ),
        migrations.AddIndex(
            model_name="payment",
            index=models.Index(
                fields=["paymob_order_id"],
                name="pay_paymob_order_id_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.UniqueConstraint(
                condition=models.Q(paymob_order_id__isnull=False),
                fields=["payment_provider", "paymob_order_id"],
                name="uniq_paymob_order_id",
            ),
        ),
    ]
