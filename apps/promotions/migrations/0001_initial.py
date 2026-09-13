from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Campaign",
            fields=[
                (
                    "id",
                    models.BigAutoField(primary_key=True, serialize=False),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=120)),
                ("slug", models.SlugField(blank=True, max_length=140, unique=True)),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("starts_at", models.DateTimeField(blank=True, null=True)),
                ("ends_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "promotions_campaign",
            },
        ),
        migrations.CreateModel(
            name="PromoCode",
            fields=[
                (
                    "id",
                    models.BigAutoField(primary_key=True, serialize=False),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("code", models.CharField(db_index=True, max_length=50, unique=True)),
                (
                    "campaign",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="promo_codes",
                        to="promotions.campaign",
                    ),
                ),
                (
                    "discount_type",
                    models.CharField(
                        choices=[
                            ("percentage", "Percentage"),
                            ("fixed", "Fixed Amount"),
                        ],
                        max_length=11,
                    ),
                ),
                (
                    "value",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=10,
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
                ("currency", models.CharField(default="EGP", max_length=3)),
                (
                    "min_order_value",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0"),
                        max_digits=10,
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
                (
                    "usage_limit",
                    models.PositiveIntegerField(
                        blank=True,
                        help_text="Total uses across all customers. Null = unlimited.",
                        null=True,
                    ),
                ),
                (
                    "per_customer_limit",
                    models.PositiveIntegerField(
                        blank=True,
                        help_text="Max uses per customer. Null = unlimited.",
                        null=True,
                    ),
                ),
                ("used_count", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("starts_at", models.DateTimeField(blank=True, null=True)),
                ("ends_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "promotions_promo_code",
            },
        ),
        migrations.AddIndex(
            model_name="campaign",
            index=models.Index(fields=["slug"], name="campaign_slug_idx"),
        ),
        migrations.AddIndex(
            model_name="promocode",
            index=models.Index(fields=["code"], name="promo_code_idx"),
        ),
        migrations.AddIndex(
            model_name="promocode",
            index=models.Index(
                fields=["is_active", "starts_at", "ends_at"],
                name="promo_validity_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="promocode",
            constraint=models.CheckConstraint(
                check=models.Q(
                    models.Q(
                        ("discount_type", "percentage"),
                        ("value__gte", 0),
                        ("value__lte", 100),
                    ),
                    ("discount_type__exact", "fixed"),
                    _connector="OR",
                ),
                name="promo_percentage_bounds_0_100",
            ),
        ),
        migrations.AddConstraint(
            model_name="promocode",
            constraint=models.CheckConstraint(
                check=models.Q(
                    models.Q(
                        ("discount_type", "fixed"), ("value__gt", 0)
                    ),
                    ("discount_type__exact", "percentage"),
                    _connector="OR",
                ),
                name="promo_fixed_must_be_positive",
            ),
        ),
    ]
