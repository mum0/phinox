"""apps.catalog — admin for Category, Collection, Color, Size, Product,
ProductVariant, ProductImage.

Product is the centerpiece: variants + images are edited inline via
TabularInline. SKU on ProductVariant and business_id on Product are
auto-generated and therefore read-only in the admin.

Size and Color are first-class entities (FK on ProductVariant) so that
swatches / size pickers on the PDP can be driven by a small set of
canonical rows instead of free-text per variant.
"""
from django.contrib import admin

from .models import (
    Category,
    Collection,
    Color,
    Product,
    ProductImage,
    ProductVariant,
    Size,
)


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    readonly_fields = ("sku",)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "family_code", "is_active", "display_order")
    list_filter = ("is_active",)
    search_fields = ("name", "slug", "family_code")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "starts_at", "ends_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "hex_code", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Size)
class SizeAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "category", "display_order", "is_active")
    list_filter = ("is_active", "category")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("business_id", "name", "category", "base_price", "currency", "status", "is_active")
    list_filter = ("status", "is_active", "category")
    search_fields = ("business_id", "name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("business_id",)
    inlines = [ProductVariantInline, ProductImageInline]


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ("sku", "product", "name", "size", "color", "price_extra", "is_active")
    list_filter = ("is_active", "size", "color")
    search_fields = ("sku", "product__name", "product__business_id")
    readonly_fields = ("sku",)


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ("product", "variant", "alt_text", "position")
    list_filter = ("product__category",)
    search_fields = ("product__name", "product__business_id", "alt_text")
