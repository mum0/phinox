import uuid

from django.conf import settings
import django.core.validators
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
            name="Review",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("rating", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)])),
                ("title", models.CharField(blank=True, max_length=150)),
                ("body", models.TextField(blank=True)),
                ("is_verified_purchase", models.BooleanField(default=False)),
                ("is_approved", models.BooleanField(default=False, help_text="Moderation gate — set by staff review, not by the customer.")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reviews", to="catalog.product")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reviews", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "reviews_review",
            },
        ),
        migrations.AddIndex(
            model_name="review",
            index=models.Index(fields=["product", "is_approved"], name="review_product_approved_idx"),
        ),
        migrations.AddIndex(
            model_name="review",
            index=models.Index(fields=["user"], name="review_user_idx"),
        ),
        migrations.AddConstraint(
            model_name="review",
            constraint=models.UniqueConstraint(fields=["product", "user"], name="uniq_review_per_user_per_product"),
        ),
        migrations.AddConstraint(
            model_name="review",
            constraint=models.CheckConstraint(check=models.Q(("rating__gte", 1), ("rating__lte", 5)), name="review_rating_range_1_5"),
        ),
    ]
