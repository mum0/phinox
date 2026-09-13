import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('accounts', '0001_initial'),
        ('core', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ShippingAddress',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('full_name', models.CharField(max_length=150)),
                ('phone', models.CharField(max_length=20)),
                ('city', models.CharField(max_length=100)),
                ('country', models.CharField(default='Egypt', max_length=100)),
                ('address', models.TextField()),
                ('postal_code', models.CharField(blank=True, max_length=20)),
                ('is_default', models.BooleanField(default=False)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shipping_addresses', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'shipping_address',
            },
        ),
        migrations.CreateModel(
            name='ShippingMethod',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=100)),
                ('code', models.CharField(db_index=True, max_length=10, unique=True)),
                ('price', models.DecimalField(decimal_places=2, default=0, max_digits=10, validators=[django.core.validators.MinValueValidator(0)])),
                ('currency', models.CharField(default='EGP', max_length=3)),
                ('estimated_days_min', models.PositiveSmallIntegerField(default=1)),
                ('estimated_days_max', models.PositiveSmallIntegerField(default=5)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'db_table': 'shipping_method',
                'indexes': [models.Index(fields=['code', 'is_active'], name='shipmethod_code_active_idx')],
            },
        ),
        migrations.AddConstraint(
            model_name='shippingmethod',
            constraint=models.CheckConstraint(check=models.Q(('price__gte', 0)), name='shipmethod_price_non_negative'),
        ),
        migrations.AddIndex(
            model_name='shippingaddress',
            index=models.Index(fields=['user', 'is_default'], name='shipaddr_user_default_idx'),
        ),
    ]
