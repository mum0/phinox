"""apps.catalog.management.commands.seed_product_images

Generate brand-aligned placeholder PNG images for every active product and
attach them as ``ProductImage`` rows so the storefront (cart, wishlist, PDP,
order detail, order tracking, order confirmation) shows real photography
instead of the Stitch grayscale fallback.

Per دستور §0.6 brand law:
  - Zero border-radius on all elements (the placeholder PNGs have sharp corners)
  - Fire orange #E85D04 for accent (used as a vertical "lock stitch" line)
  - Dark surface #121414 background
  - Text in JetBrains Mono (technical labels) + Hanken Grotesk (body)

Why placeholders instead of reusing Stitch images:
  - Stitch images are editorial / lifestyle shots (a model wearing a hoodie,
    a backpack on concrete, etc.) — they are NOT product photography for
    the 20 seeded products (Phinox Signature Jacket, Tech Bomber Jacket,
    Heavyweight Field Jacket, ...).
  - Mapping Stitch images to specific products would force incorrect
    pairings (e.g. showing a hoodie photo for a "Quilted Liner Jacket").
  - Generating deterministic placeholder PNGs per-product avoids the
    mismatch, looks consistent with the brand system, and is re-runnable.

Each generated PNG:
  - 800x1000 pixels (aspect 4:5, matching typical e-commerce product photos)
  - Background: #121414 (dark surface)
  - Subtle border: 2px #343535 (phx-border)
  - Top text: business_id (e.g. "PHX-PROD-000001") in JetBrains Mono
  - Center text: product name (large) in Hanken Grotesk
  - Bottom text: category name + base_price in JetBrains Mono
  - Vertical "lock stitch": 4px wide × 60% height #E85D04 line on the left
  - Horizontal grid lines (subtle): for the industrial blueprint look

Output:
  - PNG saved to ``media/products/<business_id>.png``
  - ``ProductImage`` row created with:
      - product = the Product instance
      - image = "products/<business_id>.png" (relative path; Django's
        ImageField prepends MEDIA_ROOT)
      - alt_text = product.name
      - position = 0 (the first/primary image)

Idempotent: re-running the command skips products that already have at
least one ProductImage (use ``--reset`` to wipe + regenerate).
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import Product, ProductImage

# ---------------------------------------------------------------------------
# Brand law (per دستور §0.6)
# ---------------------------------------------------------------------------
COLOR_BG = (18, 20, 20)            # #121414 — dark surface
COLOR_BORDER = (52, 53, 53)        # #343535 — phx-border (ghost border)
COLOR_FIRE = (232, 93, 4)          # #E85D04 — fire orange (accent only)
COLOR_TEXT = (227, 226, 226)       # #e3e2e2 — on-surface (primary text)
COLOR_TEXT_DIM = (142, 145, 146)   # #8e9192 — on-surface-variant (muted)
COLOR_GRID = (28, 30, 30)          # #1e2020 — phx-surface-mid (grid lines)

# Image dimensions — 4:5 aspect matches typical e-commerce product photos
IMG_W, IMG_H = 800, 1000

# Font paths (system fonts that approximate the brand families)
# DejaVu Sans Mono ≈ JetBrains Mono (mono)
# DejaVu Sans Bold ≈ Hanken Grotesk (display)
FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_MONO_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
FONT_DISPLAY = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

MEDIA_PRODUCTS_DIR = Path(settings.MEDIA_ROOT) / "products"


class Command(BaseCommand):
    help = "Generate brand-aligned placeholder PNG images for every active product and attach them as ProductImage rows."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing ProductImage rows + their files before regenerating. "
                 "Use with care — the files are removed from media/products/.",
        )
        parser.add_argument(
            "--status",
            choices=["active", "draft", "all"],
            default="active",
            help="Filter products by status (default: active only).",
        )

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        do_reset = bool(options["reset"])
        status_filter = options["status"]

        if do_reset:
            self._reset()

        # Filter products
        qs = Product.objects.select_related("category")
        if status_filter == "active":
            qs = qs.filter(status=Product.Status.ACTIVE, is_active=True)
        elif status_filter == "draft":
            qs = qs.filter(status=Product.Status.DRAFT)
        # "all" = no filter
        products = list(qs.order_by("business_id"))

        if not products:
            self.stdout.write(self.style.WARNING("No products matched the filter."))
            return

        self.stdout.write(f"Processing {len(products)} product(s) (status={status_filter})...")

        # Make sure media/products/ exists
        MEDIA_PRODUCTS_DIR.mkdir(parents=True, exist_ok=True)

        created = 0
        skipped = 0
        for product in products:
            # Skip products that already have at least one ProductImage (idempotent).
            # ``--reset`` would have wiped them already, so this branch only fires
            # on the default re-run path.
            if not do_reset and product.images.exists():
                skipped += 1
                continue

            png_bytes = self._render_placeholder(product)
            file_name = f"{product.business_id}.png"
            relative_path = f"products/{file_name}"

            # Save the file via Django's ImageField (uses the storage backend,
            # which is local filesystem in dev). ContentFile wraps the bytes.
            file_obj = ContentFile(png_bytes, name=file_name)

            # Create the ProductImage row. ``position=0`` makes it the
            # first image (the PDP / cart / wishlist templates pick
            # ``product.images.first`` as the primary).
            ProductImage.objects.create(
                product=product,
                image=file_obj,
                alt_text=product.name,
                position=0,
            )
            created += 1
            self.stdout.write(f"  ✓ {product.business_id} → {relative_path}")

        # --- Summary ---
        total_images = ProductImage.objects.count()
        products_with_images = (
            Product.objects.filter(images__isnull=False).distinct().count()
        )
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Seed complete."))
        self.stdout.write(f"  Created this run : {created}")
        self.stdout.write(f"  Skipped (existing): {skipped}")
        self.stdout.write(f"  Total ProductImage rows: {total_images}")
        self.stdout.write(f"  Products with ≥ 1 image : {products_with_images}")
        self.stdout.write(f"  Media directory : {MEDIA_PRODUCTS_DIR}")
        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "Next: visit /wishlist/, /cart/, /products/<slug>/, /orders/<id>/ to verify."
            )
        )

    # ------------------------------------------------------------------
    def _reset(self) -> None:
        """Delete existing ProductImage rows + their files. Wrapped in the
        outer ``atomic()`` so a failure rolls back the whole command."""
        self.stdout.write(self.style.WARNING("Reset: deleting existing ProductImage rows..."))
        count = ProductImage.objects.count()
        # The ImageField file is auto-deleted by Django when the row is deleted
        # ONLY if the storage backend supports it; we delete explicitly to be safe.
        for img in ProductImage.objects.all():
            try:
                img.image.delete(save=False)
            except Exception:
                pass
        ProductImage.objects.all().delete()
        self.stdout.write(self.style.WARNING(f"Reset: removed {count} row(s)."))

    # ------------------------------------------------------------------
    def _render_placeholder(self, product: Product) -> bytes:
        """Render a brand-aligned placeholder PNG for the given product.

        Returns the PNG bytes (ready for ``ContentFile``).
        """
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (IMG_W, IMG_H), COLOR_BG)
        draw = ImageDraw.Draw(img)

        # ── Ghost border (2px) ────────────────────────────────────────────
        draw.rectangle([(0, 0), (IMG_W - 1, IMG_H - 1)], outline=COLOR_BORDER, width=2)

        # ── Subtle grid lines (industrial blueprint feel) ─────────────────
        grid_step = 80
        for x in range(grid_step, IMG_W, grid_step):
            draw.line([(x, 0), (x, IMG_H)], fill=COLOR_GRID, width=1)
        for y in range(grid_step, IMG_H, grid_step):
            draw.line([(0, y), (IMG_W, y)], fill=COLOR_GRID, width=1)

        # ── Lock stitch: 4px wide vertical fire-orange line, 25-75% height ─
        stitch_x = 40
        stitch_y_top = int(IMG_H * 0.25)
        stitch_y_bot = int(IMG_H * 0.75)
        draw.rectangle(
            [(stitch_x, stitch_y_top), (stitch_x + 4, stitch_y_bot)],
            fill=COLOR_FIRE,
        )

        # ── Top header: business_id + category ─────────────────────────────
        try:
            font_mono_sm = ImageFont.truetype(FONT_MONO, 18)
        except OSError:
            font_mono_sm = ImageFont.load_default()
        try:
            font_mono_md = ImageFont.truetype(FONT_MONO_BOLD, 22)
        except OSError:
            font_mono_md = ImageFont.load_default()

        margin = 80

        # business_id top-left
        bid_text = product.business_id or "PHX-PROD-??????"
        draw.text((margin, margin), bid_text, fill=COLOR_FIRE, font=font_mono_md)

        # category name top-right
        cat_text = (product.category.name if product.category else "UNCATEGORIZED").upper()
        cat_bbox = draw.textbbox((0, 0), cat_text, font=font_mono_sm)
        cat_w = cat_bbox[2] - cat_bbox[0]
        draw.text((IMG_W - margin - cat_w, margin), cat_text, fill=COLOR_TEXT_DIM, font=font_mono_sm)

        # Horizontal rule under header
        draw.line([(margin, margin + 36), (IMG_W - margin, margin + 36)], fill=COLOR_BORDER, width=1)

        # ── Center: product name (large display) ───────────────────────────
        try:
            font_display_lg = ImageFont.truetype(FONT_DISPLAY, 56)
        except OSError:
            font_display_lg = ImageFont.load_default()
        try:
            font_display_md = ImageFont.truetype(FONT_DISPLAY, 38)
        except OSError:
            font_display_md = ImageFont.load_default()

        name_text = product.name.upper()
        # Word-wrap to a max width
        max_name_width = IMG_W - 2 * margin - 40  # leave room for the stitch line
        wrapped_lines = self._wrap_text(name_text, font_display_lg, max_name_width, draw)
        if len(wrapped_lines) > 2:
            # If the name wraps to more than 2 lines at the large font, drop to medium
            font_display_lg = font_display_md
            wrapped_lines = self._wrap_text(name_text, font_display_lg, max_name_width, draw)

        # Compute total block height for vertical centering
        line_h = font_display_lg.size + 8
        block_h = len(wrapped_lines) * line_h
        start_y = (IMG_H - block_h) // 2
        for i, line in enumerate(wrapped_lines):
            bbox = draw.textbbox((0, 0), line, font=font_display_lg)
            line_w = bbox[2] - bbox[0]
            x = (IMG_W - line_w) // 2  # horizontally centered
            y = start_y + i * line_h
            draw.text((x, y), line, fill=COLOR_TEXT, font=font_display_lg)

        # ── Bottom: base_price + currency + status ─────────────────────────
        try:
            font_mono_xs = ImageFont.truetype(FONT_MONO, 16)
        except OSError:
            font_mono_xs = ImageFont.load_default()

        price_text = f"{product.base_price:.2f} {product.currency}"
        bbox = draw.textbbox((0, 0), price_text, font=font_mono_md)
        price_w = bbox[2] - bbox[0]
        draw.text(
            (margin, IMG_H - margin - 64),
            "BASE PRICE",
            fill=COLOR_TEXT_DIM,
            font=font_mono_xs,
        )
        draw.text(
            (margin, IMG_H - margin - 36),
            price_text,
            fill=COLOR_FIRE,
            font=font_mono_md,
        )

        # Status badge bottom-right
        status_text = (product.status or "draft").upper()
        bbox = draw.textbbox((0, 0), status_text, font=font_mono_sm)
        st_w = bbox[2] - bbox[0]
        # Background swatch behind the status text
        badge_pad = 8
        badge_x0 = IMG_W - margin - st_w - 2 * badge_pad
        badge_y0 = IMG_H - margin - 22 - 2 * badge_pad
        badge_x1 = IMG_W - margin + badge_pad
        badge_y1 = IMG_H - margin + badge_pad
        status_color = COLOR_FIRE if status_text == "ACTIVE" else COLOR_TEXT_DIM
        draw.rectangle([(badge_x0, badge_y0), (badge_x1, badge_y1)], fill=COLOR_BORDER)
        draw.text(
            (badge_x0 + badge_pad, badge_y0 + badge_pad - 2),
            status_text,
            fill=status_color,
            font=font_mono_sm,
        )

        # Horizontal rule above footer
        draw.line(
            [(margin, IMG_H - margin - 90), (IMG_W - margin, IMG_H - margin - 90)],
            fill=COLOR_BORDER,
            width=1,
        )

        # Encode as PNG, return bytes
        buf = BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    # ------------------------------------------------------------------
    @staticmethod
    def _wrap_text(text: str, font, max_width: int, draw) -> list[str]:
        """Word-wrap ``text`` so each line fits within ``max_width``."""
        words = text.split()
        if not words:
            return [""]
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            bbox = draw.textbbox((0, 0), candidate, font=font)
            if (bbox[2] - bbox[0]) > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        lines.append(current)
        return lines
