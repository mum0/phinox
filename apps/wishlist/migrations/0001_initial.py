import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0001_initial"),
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="WishlistItem",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="wishlisted_by", to="catalog.product")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="wishlist_items", to=settings.AUTH_USER_MODEL)),
                ("variant", models.ForeignKey(blank=True, help_text="Optional — set when the user saved a specific size/color, not just the product.", null=True, on_delete=django.db.models.deletion.CASCADE, related_name="wishlisted_by", to="catalog.productvariant")),
            ],
            options={
                "db_table": "wishlist_item",
            },
        ),
        migrations.AddIndex(
            model_name="wishlistitem",
            index=models.Index(fields=["user", "-created_at"], name="wishlist_user_created_idx"),
        ),
        migrations.AddConstraint(
            model_name="wishlistitem",
            constraint=models.UniqueConstraint(fields=["user", "product", "variant"], name="uniq_wishlist_entry"),
        ),
    ]
