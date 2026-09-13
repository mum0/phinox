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
            name="Category",
            fields=[
                (
                    "id",
                    models.BigAutoField(primary_key=True, serialize=False),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=120)),
                ("slug", models.SlugField(blank=True, max_length=140, unique=True)),
                (
                    "family_code",
                    models.CharField(
                        help_text="Drives SKU sequence: PHX-{FAMILY_CODE}-001",
                        max_length=10,
                        unique=True,
                    ),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="children",
                        to="catalog.category",
                    ),
                ),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("display_order", models.PositiveIntegerField(default=0)),
            ],
            options={
                "db_table": "catalog_category",
                "verbose_name_plural": "categories",
            },
        ),
        migrations.CreateModel(
            name="Product",
            fields=[
                (
                    "id",
                    models.BigAutoField(primary_key=True, serialize=False),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "business_id",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        editable=False,
                        max_length=30,
                        unique=True,
                    ),
                ),
                ("name", models.CharField(max_length=200)),
                ("slug", models.SlugField(blank=True, max_length=220, unique=True)),
                (
                    "category",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="products",
                        to="catalog.category",
                    ),
                ),
                ("description", models.TextField(blank=True)),
                (
                    "base_price",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0"),
                        max_digits=10,
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
                ("currency", models.CharField(default="EGP", max_length=3)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("active", "Active"),
                            ("archived", "Archived"),
                        ],
                        default="draft",
                        max_length=10,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "catalog_product",
            },
        ),
        migrations.CreateModel(
            name="Collection",
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
                (
                    "products",
                    models.ManyToManyField(
                        blank=True,
                        related_name="collections",
                        to="catalog.product",
                    ),
                ),
            ],
            options={
                "db_table": "catalog_collection",
            },
        ),
        migrations.CreateModel(
            name="ProductVariant",
            fields=[
                (
                    "id",
                    models.BigAutoField(primary_key=True, serialize=False),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="variants",
                        to="catalog.product",
                    ),
                ),
                (
                    "sku",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        editable=False,
                        max_length=30,
                        unique=True,
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        blank=True,
                        help_text="Optional variant label, e.g. 'Large / Black'",
                        max_length=200,
                    ),
                ),
                (
                    "price_extra",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0"),
                        help_text="Added to product.base_price to get the variant's unit_price.",
                        max_digits=10,
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "db_table": "catalog_product_variant",
            },
        ),
        migrations.CreateModel(
            name="ProductImage",
            fields=[
                (
                    "id",
                    models.BigAutoField(primary_key=True, serialize=False),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="images",
                        to="catalog.product",
                    ),
                ),
                (
                    "variant",
                    models.ForeignKey(
                        blank=True,
                        help_text="Optional — set for variant-specific images.",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="images",
                        to="catalog.productvariant",
                    ),
                ),
                ("image", models.ImageField(upload_to="products/%Y/%m/")),
                ("alt_text", models.CharField(blank=True, max_length=255)),
                ("position", models.PositiveSmallIntegerField(default=0)),
            ],
            options={
                "db_table": "catalog_product_image",
                "ordering": ["position"],
            },
        ),
        migrations.AddIndex(
            model_name="category",
            index=models.Index(fields=["slug"], name="category_slug_idx"),
        ),
        migrations.AddIndex(
            model_name="category",
            index=models.Index(fields=["family_code"], name="category_family_idx"),
        ),
        migrations.AddIndex(
            model_name="category",
            index=models.Index(
                fields=["parent", "is_active"], name="category_parent_active_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="category",
            constraint=models.UniqueConstraint(
                fields=["parent", "name"], name="uniq_category_name_per_parent"
            ),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(fields=["slug"], name="product_slug_idx"),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(
                fields=["category", "status"], name="product_category_status_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(
                fields=["status", "is_active"], name="product_status_active_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.CheckConstraint(
                check=models.Q(("base_price__gte", 0)),
                name="product_base_price_non_negative",
            ),
        ),
        migrations.AddIndex(
            model_name="collection",
            index=models.Index(fields=["slug"], name="collection_slug_idx"),
        ),
        migrations.AddIndex(
            model_name="productvariant",
            index=models.Index(fields=["sku"], name="variant_sku_idx"),
        ),
        migrations.AddIndex(
            model_name="productvariant",
            index=models.Index(
                fields=["product", "is_active"], name="variant_product_active_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="productvariant",
            constraint=models.CheckConstraint(
                check=models.Q(("price_extra__gte", 0)),
                name="variant_price_extra_non_negative",
            ),
        ),
        migrations.AddIndex(
            model_name="productimage",
            index=models.Index(
                fields=["product", "position"], name="prodimg_product_pos_idx"
            ),
        ),
    ]
