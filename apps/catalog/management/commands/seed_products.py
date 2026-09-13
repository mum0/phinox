"""apps.catalog.management.commands.seed_products

Seed the catalog with deterministic demo data so the storefront
(/products/) and the Django admin (admin/) have something to show
right after a fresh migrate.

Creates (idempotent — safe to run repeatedly):
    - 1 Category ("Jackets", family_code="JCK")
    - 1 Color  ("Black", hex="#0B0B0B")
    - 1 Size   ("M")
    - 1 hero product "Phinox Signature Jacket" (status=ACTIVE, is_active=True)
    - 1 variant on the hero product (size=M, color=Black)
    - 1 Inventory row for that variant (quantity_on_hand=50, warehouse=MAIN)
    - 1 Warehouse ("MAIN", Alexandria)
    - 10-20 extra catalog filler products (one variant each, ACTIVE)

Run:
    python manage.py seed_products
    python manage.py seed_products --filler 20   # override filler count

The command is idempotent: re-running it leaves the existing rows alone
(looked up by name) and only fills in missing pieces. Use --reset to
wipe and reseed (skips any rows referenced by orders/payments — safe by
default, aggressive with --reset).
"""
from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import (
    Category,
    Color,
    Product,
    ProductVariant,
    Size,
)
from apps.inventory.models import Inventory, Warehouse

# ---------------------------------------------------------------------------
# Catalog filler — 10 dummy products with deterministic names + prices.
# Kept short and readable so the seeded /products/ page looks "real"
# without inventing photography (the template already renders a PHX
# placeholder block when no ProductImage is attached).
# ---------------------------------------------------------------------------
FILLER_PRODUCTS: tuple[tuple[str, str, str, str], ...] = (
    # (category_family, category_name, product_name, base_price)
    ("JCK", "Jackets", "Phinox Signature Jacket",   "2500.00"),
    ("JCK", "Jackets", "Tech Bomber Jacket",        "2100.00"),
    ("JCK", "Jackets", "Heavyweight Field Jacket",  "2800.00"),
    ("JCK", "Jackets", "Quilted Liner Jacket",      "1750.00"),
    ("JCK", "Jackets", "Reflective Runner Jacket", "2200.00"),
    ("SHT", "Shirts",  "Technical Mesh Shirt",     "850.00"),
    ("SHT", "Shirts",  "Heavyweight Tee — Black",   "650.00"),
    ("SHT", "Shirts",  "Long Sleeve Cotton Shirt",  "950.00"),
    ("PNT", "Pants",   "Tapered Tech Pants",        "1450.00"),
    ("PNT", "Pants",   "Heavyweight Cargo Pants",   "1650.00"),
    ("PNT", "Pants",   "Relaxed Linen Pants",       "1250.00"),
    ("ACC", "Accessories", "Webbing Belt",         "350.00"),
    ("ACC", "Accessories", "Heavyweight Beanie",   "400.00"),
    ("ACC", "Accessories", "Logo Cap — Black",      "550.00"),
    ("ACC", "Accessories", "Cotton Scarf",          "480.00"),
    ("KNW", "Knitwear", "Merino Crew Sweater",      "1350.00"),
    ("KNW", "Knitwear", "Chunky Knit Cardigan",     "1950.00"),
    ("OUT", "Outerwear", "Down Puffer Jacket",     "3200.00"),
    ("OUT", "Outerwear", "Shell Windbreaker",      "2400.00"),
    ("OUT", "Outerwear", "Insulated Parka",        "3900.00"),
)


class Command(BaseCommand):
    help = "Seed the catalog with demo categories, sizes, colors, products, variants, and inventory."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--filler",
            type=int,
            default=20,
            help="Number of filler products to ensure exist (default: 20).",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing catalog/inventory rows before seeding. "
                 "Use with care — will fail if rows are referenced by orders.",
        )

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        filler_count = int(options["filler"])
        do_reset = bool(options["reset"])

        if do_reset:
            self._reset()

        # --- Warehouse (used by every Inventory row we create) ----------
        warehouse, w_created = Warehouse.objects.get_or_create(
            code="MAIN",
            defaults={"name": "Main Warehouse — Alexandria", "governorate": "Alexandria"},
        )
        self.stdout.write(
            f"  Warehouse '{warehouse.code}' {'created' if w_created else 'exists'}"
        )

        # --- Color + Size (the variant-attribute pair the user asked for) --
        color, c_created = Color.objects.get_or_create(
            name="Black",
            defaults={"hex_code": "#0B0B0B"},
        )
        self.stdout.write(
            f"  Color '{color.name}' {'created' if c_created else 'exists'}"
        )

        size, s_created = Size.objects.get_or_create(
            name="M",
            defaults={"category": "apparel", "display_order": 30},
        )
        self.stdout.write(
            f"  Size  '{size.name}' {'created' if s_created else 'exists'}"
        )

        # --- Categories + products + variants + inventory ----------------
        # Group filler rows by (family_code, category_name) so each
        # category only gets created once, and so the SKU sequence is
        # per-family (matches the per-family next_sku contract).
        seen_categories: dict[str, Category] = {}
        created_products = 0
        created_variants = 0
        created_inventory = 0

        for family_code, category_name, product_name, base_price in FILLER_PRODUCTS[:filler_count]:
            # Category (cached per family_code)
            category = seen_categories.get(family_code)
            if category is None:
                category, _ = Category.objects.get_or_create(
                    family_code=family_code,
                    defaults={"name": category_name},
                )
                seen_categories[family_code] = category

            # Product
            product, p_created = Product.objects.get_or_create(
                name=product_name,
                defaults={
                    "category": category,
                    "base_price": Decimal(base_price),
                    "currency": "EGP",
                    "status": Product.Status.ACTIVE,
                    "is_active": True,
                },
            )
            if p_created:
                created_products += 1

            # Variant — one per product, linked to the shared Size M + Color Black.
            variant, v_created = ProductVariant.objects.get_or_create(
                product=product,
                size=size,
                color=color,
                defaults={
                    "name": f"{size.name} / {color.name}",
                    "price_extra": Decimal("0"),
                    "is_active": True,
                },
            )
            if v_created:
                created_variants += 1

                # Inventory — 50 on hand at the MAIN warehouse. Skip if a row
                # already exists (e.g. when re-running on an existing DB).
                _, inv_created = Inventory.objects.get_or_create(
                    variant=variant,
                    warehouse=warehouse,
                    defaults={
                        "quantity_on_hand": 50,
                        "quantity_reserved": 0,
                        "low_stock_threshold": 5,
                    },
                )
                if inv_created:
                    created_inventory += 1

        # --- Hero product guarantee (per user spec: at least one) ---------
        hero_cat = seen_categories.get("JCK") or Category.objects.get(family_code="JCK")
        hero, _ = Product.objects.get_or_create(
            name="Phinox Signature Jacket",
            defaults={
                "category": hero_cat,
                "base_price": Decimal("2500.00"),
                "currency": "EGP",
                "status": Product.Status.ACTIVE,
                "is_active": True,
            },
        )
        hero_variant, _ = ProductVariant.objects.get_or_create(
            product=hero,
            size=size,
            color=color,
            defaults={"name": "M / Black", "price_extra": Decimal("0")},
        )
        Inventory.objects.get_or_create(
            variant=hero_variant,
            warehouse=warehouse,
            defaults={
                "quantity_on_hand": 50,
                "quantity_reserved": 0,
                "low_stock_threshold": 5,
            },
        )

        # --- Summary -----------------------------------------------------
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Seed complete."))
        self.stdout.write(
            f"  Categories : {Category.objects.count()} rows "
            f"({len(seen_categories)} used in this run)"
        )
        self.stdout.write(f"  Colors     : {Color.objects.count()} row(s)")
        self.stdout.write(f"  Sizes      : {Size.objects.count()} row(s)")
        self.stdout.write(f"  Products   : {Product.objects.count()} row(s) "
                          f"({created_products} created in this run)")
        self.stdout.write(f"  Variants   : {ProductVariant.objects.count()} row(s) "
                          f"({created_variants} created in this run)")
        active = Product.objects.filter(
            status=Product.Status.ACTIVE, is_active=True
        ).count()
        self.stdout.write(f"  ACTIVE & is_active=True products : {active}")
        self.stdout.write(f"  Inventory  : {Inventory.objects.count()} row(s) "
                          f"({created_inventory} created in this run)")
        self.stdout.write(f"  Warehouses : {Warehouse.objects.count()} row(s)")
        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "Next: visit /admin/ (login as superuser) and /products/ to verify."
            )
        )

    # ------------------------------------------------------------------
    def _reset(self) -> None:
        """Delete seeded rows. Wrapped in the outer atomic() so a failure
        (e.g. PROTECT FK from an Order) rolls back the whole command."""
        self.stdout.write(self.style.WARNING("Reset: deleting existing rows..."))
        # Inventory + variants + products first (inventory has no inbound FKs);
        # categories are PROTECTed by Product, so delete products first.
        Inventory.objects.all().delete()
        ProductVariant.objects.all().delete()
        Product.objects.all().delete()
        Category.objects.all().delete()
        Color.objects.all().delete()
        Size.objects.all().delete()
        # Keep the Warehouse — it's not strictly part of "catalog seed",
        # and dropping it would surprise operators who set up other
        # warehouses manually.
        self.stdout.write(self.style.WARNING("Reset: done. Seeding from empty."))
