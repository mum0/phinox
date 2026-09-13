"""apps.accounts — admin for CustomUser.

Extends Django's UserAdmin so the standard auth fieldsets (password,
permissions) keep working, and adds a PHINOX fieldset with the stable
customer_id (read-only) and phone number.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(DjangoUserAdmin):
    list_display = ("customer_id", "username", "email", "phone", "is_staff", "is_active")
    list_filter = ("is_staff", "is_superuser", "is_active")
    search_fields = ("customer_id", "username", "email", "phone")
    readonly_fields = ("customer_id",)

    fieldsets = DjangoUserAdmin.fieldsets + (
        ("PHINOX", {"fields": ("customer_id", "phone")}),
    )

    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("PHINOX", {"fields": ("phone",)}),
    )
