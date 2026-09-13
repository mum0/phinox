"""
apps.catalog — Category, Product, Collection, ProductVariant, ProductImage.

Stable IDs:
  - Product.business_id  → PHX-PROD-000001 (via BusinessIDModel)
  - ProductVariant.sku   → PHX-WNT-001     (via next_sku, per-family)

CheckConstraints: base_price >= 0, price_extra >= 0.
"""
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.functional import cached_property
from django.utils.text import slugify

from apps.core.models import BaseModel, BusinessIDModel, next_sku


class Category(BaseModel):
    """Self-referential hierarchy (e.g. Men > Outerwear > Jackets).

    ``family_code`` drives the SKU sequence for products in this category
    (e.g. family_code="WNT" → SKUs PHX-WNT-001, PHX-WNT-002, ...).
    """

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    family_code = models.CharField(
        max_length=10,
        unique=True,
        help_text="Drives SKU sequence: PHX-{FAMILY_CODE}-001",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "catalog_category"
        verbose_name_plural = "categories"
        indexes = [
            models.Index(fields=["slug"], name="category_slug_idx"),
            models.Index(fields=["family_code"], name="category_family_idx"),
            models.Index(fields=["parent", "is_active"], name="category_parent_active_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["parent", "name"], name="uniq_category_name_per_parent"),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Product(BusinessIDModel):
    """A sellable product. Business ID: PHX-PROD-000001.

    Variant-specific data (SKU, price_extra) lives on ProductVariant.
    The base_price here is the default price; a variant's effective
    price is base_price + variant.price_extra.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    BUSINESS_ID_PREFIX = "PROD"

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
    )
    description = models.TextField(blank=True)
    base_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(0)],
    )
    currency = models.CharField(max_length=3, default="EGP")
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    is_active = models.BooleanField(default=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "catalog_product"
        indexes = [
            models.Index(fields=["slug"], name="product_slug_idx"),
            models.Index(fields=["category", "status"], name="product_category_status_idx"),
            models.Index(fields=["status", "is_active"], name="product_status_active_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(base_price__gte=0),
                name="product_base_price_non_negative",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.business_id} — {self.name}"


class Collection(BaseModel):
    """A curated, cross-category grouping (e.g. a seasonal drop)."""

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.TextField(blank=True)
    products = models.ManyToManyField(Product, related_name="collections", blank=True)
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "catalog_collection"
        indexes = [models.Index(fields=["slug"], name="collection_slug_idx")]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Color(BaseModel):
    """A product color option (e.g. Black, White, Fire Orange).

    Used as a foreign key on ProductVariant so multiple variants of the
    same product can share the same color without re-typing the label.
    ``hex_code`` is optional but useful for rendering swatches on the PLP/PDP.
    """

    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=80, unique=True, blank=True)
    hex_code = models.CharField(
        max_length=9,
        blank=True,
        help_text="Optional CSS hex color, e.g. '#000000' for black. Used for swatches.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "catalog_color"
        indexes = [models.Index(fields=["slug"], name="color_slug_idx")]
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Size(BaseModel):
    """A product size option (e.g. XS, S, M, L, XL, 42, 44).

    Used as a foreign key on ProductVariant. ``display_order`` controls
    the order sizes appear in variant pickers on the PDP.
    """

    name = models.CharField(max_length=20, unique=True)
    slug = models.SlugField(max_length=40, unique=True, blank=True)
    category = models.CharField(
        max_length=20,
        blank=True,
        help_text="Optional grouping label, e.g. 'apparel' or 'footwear'.",
    )
    display_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "catalog_size"
        indexes = [models.Index(fields=["slug"], name="size_slug_idx")]
        ordering = ["display_order", "name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ProductVariant(BaseModel):
    """The purchasable unit: a specific variant of a product.

    SKU is auto-generated from the product's category family_code:
    PHX-{FAMILY_CODE}-{3-digit}. Each family has its own sequence.

    ``unit_price`` is a computed property: product.base_price + price_extra.
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants",
    )
    sku = models.CharField(max_length=30, unique=True, editable=False, blank=True, db_index=True)
    name = models.CharField(max_length=200, blank=True, help_text="Optional variant label, e.g. 'Large / Black'")
    size = models.ForeignKey(
        Size,
        on_delete=models.PROTECT,
        related_name="variants",
        null=True,
        blank=True,
        help_text="Optional — set for size-aware variants (apparel/footwear).",
    )
    color = models.ForeignKey(
        Color,
        on_delete=models.PROTECT,
        related_name="variants",
        null=True,
        blank=True,
        help_text="Optional — set for color-aware variants.",
    )
    price_extra = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(0)],
        help_text="Added to product.base_price to get the variant's unit_price.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "catalog_product_variant"
        indexes = [
            models.Index(fields=["sku"], name="variant_sku_idx"),
            models.Index(fields=["product", "is_active"], name="variant_product_active_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(price_extra__gte=0),
                name="variant_price_extra_non_negative",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.sku:
            family_code = self.product.category.family_code
            self.sku = next_sku(family_code)
        super().save(*args, **kwargs)

    @cached_property
    def unit_price(self) -> Decimal:
        """Effective price: product.base_price + price_extra.

        Memoized per-instance via ``cached_property`` — ``unit_price`` is
        accessed repeatedly when computing cart subtotals and order line
        totals, so caching the arithmetic avoids redundant work within a
        single request. The cache is per-instance, so a freshly-fetched
        variant (e.g. after a price_extra update) will recompute.
        """
        return self.product.base_price + self.price_extra

    def __str__(self):
        return f"{self.sku} — {self.product.name}"


class ProductImage(BaseModel):
    """Product photography. Optional variant pin for variant-specific images."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name="images",
        null=True,
        blank=True,
        help_text="Optional — set for variant-specific images.",
    )
    image = models.ImageField(upload_to="products/%Y/%m/")
    alt_text = models.CharField(max_length=255, blank=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "catalog_product_image"
        indexes = [models.Index(fields=["product", "position"], name="prodimg_product_pos_idx")]
        ordering = ["position"]

    def __str__(self):
        return f"{self.product.name} image #{self.id}"
