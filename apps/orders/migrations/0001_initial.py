import django.core.validators
import django.db.models.deletion
import django.db.models.expressions
import uuid
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('accounts', '0001_initial'),
        ('catalog', '0001_initial'),
        ('promotions', '0001_initial'),
        ('core', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Order',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('business_id', models.CharField(blank=True, db_index=True, editable=False, max_length=30, unique=True)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('confirmed', 'Confirmed'), ('processing', 'Processing'), ('shipped', 'Shipped'), ('delivered', 'Delivered'), ('cancelled', 'Cancelled'), ('refunded', 'Refunded')], default='pending', max_length=16)),
                ('payment_status', models.CharField(choices=[('unpaid', 'Unpaid'), ('pending', 'Pending'), ('paid', 'Paid'), ('failed', 'Failed'), ('refunded', 'Refunded')], default='unpaid', max_length=16)),
                ('fulfillment_status', models.CharField(choices=[('unfulfilled', 'Unfulfilled'), ('fulfilled', 'Fulfilled'), ('returned', 'Returned')], default='unfulfilled', max_length=16)),
                ('subtotal', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12, validators=[django.core.validators.MinValueValidator(0)])),
                ('discount_total', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12, validators=[django.core.validators.MinValueValidator(0)])),
                ('shipping_cost', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=10, validators=[django.core.validators.MinValueValidator(0)])),
                ('grand_total', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12, validators=[django.core.validators.MinValueValidator(0)])),
                ('currency', models.CharField(default='EGP', max_length=3)),
                ('placed_at', models.DateTimeField(blank=True, null=True)),
                ('customer_notes', models.TextField(blank=True)),
                ('bos_sync_status', models.CharField(choices=[('not_required', 'Not Required'), ('pending', 'Pending'), ('synced', 'Synced'), ('failed', 'Failed')], default='not_required', max_length=16)),
                ('bos_reference_id', models.CharField(blank=True, editable=False, help_text='BOS-assigned reference ID. Null until BOS integration phase.', max_length=100, null=True)),
                ('last_sync_at', models.DateTimeField(blank=True, editable=False, help_text='Last BOS sync timestamp. Null until BOS integration phase.', null=True)),
                ('idempotency_key', models.UUIDField(default=uuid.uuid4, editable=False, help_text='For safe retries in payment/checkout flows.', unique=True)),
                ('promo_code', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='orders', to='promotions.promocode')),
                ('user', models.ForeignKey(blank=True, help_text='Null for guest checkout orders.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='orders', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'orders_order',
            },
        ),
        migrations.CreateModel(
            name='OrderItem',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('sku', models.CharField(max_length=30)),
                ('name', models.CharField(max_length=200)),
                ('quantity', models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=10, validators=[django.core.validators.MinValueValidator(0)])),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='orders.order')),
                ('variant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='order_items', to='catalog.productvariant')),
            ],
            options={
                'db_table': 'orders_order_item',
            },
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['business_id'], name='order_business_id_idx'),
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['user', '-created_at'], name='order_user_created_idx'),
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['status'], name='order_status_idx'),
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['payment_status'], name='order_payment_status_idx'),
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['bos_sync_status'], name='order_bos_sync_idx'),
        ),
        migrations.AddConstraint(
            model_name='order',
            constraint=models.CheckConstraint(check=models.Q(('subtotal__gte', 0)), name='order_subtotal_non_negative'),
        ),
        migrations.AddConstraint(
            model_name='order',
            constraint=models.CheckConstraint(check=models.Q(('discount_total__gte', 0)), name='order_discount_non_negative'),
        ),
        migrations.AddConstraint(
            model_name='order',
            constraint=models.CheckConstraint(check=models.Q(('shipping_cost__gte', 0)), name='order_shipping_non_negative'),
        ),
        migrations.AddConstraint(
            model_name='order',
            constraint=models.CheckConstraint(check=models.Q(('grand_total__gte', 0)), name='order_grand_total_non_negative'),
        ),
        migrations.AddConstraint(
            model_name='order',
            constraint=models.CheckConstraint(check=models.Q(('discount_total__lte', models.F('subtotal'))), name='order_discount_lte_subtotal'),
        ),
        migrations.AddConstraint(
            model_name='order',
            constraint=models.CheckConstraint(check=models.Q(('grand_total', django.db.models.expressions.CombinedExpression(django.db.models.expressions.CombinedExpression(models.F('subtotal'), '-', models.F('discount_total')), '+', models.F('shipping_cost')))), name='order_grand_total_equals_components'),
        ),
        migrations.AddIndex(
            model_name='orderitem',
            index=models.Index(fields=['order'], name='orderitem_order_idx'),
        ),
        migrations.AddConstraint(
            model_name='orderitem',
            constraint=models.CheckConstraint(check=models.Q(('quantity__gte', 1)), name='orderitem_quantity_gte_1'),
        ),
        migrations.AddConstraint(
            model_name='orderitem',
            constraint=models.CheckConstraint(check=models.Q(('unit_price__gte', 0)), name='orderitem_unit_price_non_negative'),
        ),
    ]
