import django.core.validators
import django.db.models.deletion
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
            name='Cart',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('business_id', models.CharField(blank=True, db_index=True, editable=False, max_length=30, unique=True)),
                ('session_key', models.CharField(blank=True, db_index=True, max_length=64, null=True)),
                ('promo_code', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='carts', to='promotions.promocode')),
                ('user', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='cart', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'cart_cart',
            },
        ),
        migrations.CreateModel(
            name='CartItem',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('quantity', models.PositiveIntegerField(default=1, validators=[django.core.validators.MinValueValidator(1)])),
                ('cart', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='cart.cart')),
                ('variant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cart_items', to='catalog.productvariant')),
            ],
            options={
                'db_table': 'cart_item',
            },
        ),
        migrations.AddIndex(
            model_name='cart',
            index=models.Index(fields=['session_key'], name='cart_session_idx'),
        ),
        migrations.AddConstraint(
            model_name='cart',
            constraint=models.CheckConstraint(check=models.Q(models.Q(('session_key__isnull', True), ('user__isnull', False)), models.Q(('session_key__isnull', False), ('user__isnull', True)), _connector='OR'), name='cart_user_xor_session_exclusive'),
        ),
        migrations.AddIndex(
            model_name='cartitem',
            index=models.Index(fields=['cart'], name='cartitem_cart_idx'),
        ),
        migrations.AddConstraint(
            model_name='cartitem',
            constraint=models.UniqueConstraint(fields=('cart', 'variant'), name='uniq_cartitem_per_variant'),
        ),
        migrations.AddConstraint(
            model_name='cartitem',
            constraint=models.CheckConstraint(check=models.Q(('quantity__gte', 1)), name='cartitem_quantity_gte_1'),
        ),
    ]
