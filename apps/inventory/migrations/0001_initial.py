from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Warehouse",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=20, unique=True)),
                ("name", models.CharField(max_length=120)),
                ("governorate", models.CharField(blank=True, max_length=32)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "db_table": "inventory_warehouse",
            },
        ),
        migrations.CreateModel(
            name="Inventory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity_on_hand", models.PositiveIntegerField(default=0)),
                ("quantity_reserved", models.PositiveIntegerField(default=0)),
                ("low_stock_threshold", models.PositiveIntegerField(default=5)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("variant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="inventory_records", to="catalog.productvariant")),
                ("warehouse", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="inventory_records", to="inventory.warehouse")),
            ],
            options={
                "db_table": "inventory_stock",
                "verbose_name_plural": "inventory",
            },
        ),
        migrations.AddIndex(
            model_name="inventory",
            index=models.Index(fields=["variant", "warehouse"], name="inventory_variant_wh_idx"),
        ),
        migrations.AddIndex(
            model_name="inventory",
            index=models.Index(fields=["quantity_on_hand"], name="inventory_qty_idx"),
        ),
        migrations.AddConstraint(
            model_name="inventory",
            constraint=models.UniqueConstraint(fields=["variant", "warehouse"], name="uniq_inventory_per_variant_warehouse"),
        ),
        migrations.AddConstraint(
            model_name="inventory",
            constraint=models.CheckConstraint(check=models.Q(("quantity_reserved__lte", models.F("quantity_on_hand"))), name="inventory_reserved_lte_on_hand"),
        ),
    ]
