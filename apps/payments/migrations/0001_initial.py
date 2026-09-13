import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('orders', '0001_initial'),
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Payment',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('business_id', models.CharField(blank=True, db_index=True, editable=False, max_length=30, unique=True)),
                ('payment_provider', models.CharField(choices=[('cod', 'Cash on Delivery'), ('paymob', 'Paymob'), ('fawry', 'Fawry'), ('valu', 'valU (BNPL)')], default='cod', max_length=10)),
                ('method_type', models.CharField(choices=[('cod', 'Cash on Delivery'), ('card', 'Card'), ('wallet', 'Wallet'), ('installment', 'Installment')], default='cod', max_length=12)),
                ('provider_transaction_id', models.CharField(blank=True, db_index=True, help_text='Gateway-assigned transaction ID. Unique per provider.', max_length=100, null=True)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))])),
                ('currency', models.CharField(default='EGP', max_length=3)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('paid', 'Paid'), ('failed', 'Failed'), ('refunded', 'Refunded')], default='pending', max_length=10)),
                ('is_test_transaction', models.BooleanField(default=True, help_text='Per دستور: all payments default to test mode.')),
                ('webhook_payload', models.JSONField(blank=True, help_text='Last raw webhook payload from the provider (for audit/debugging).', null=True)),
                ('failure_reason', models.TextField(blank=True)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='orders.order')),
            ],
            options={
                'db_table': 'payments_payment',
                'indexes': [models.Index(fields=['business_id'], name='pay_business_id_idx'), models.Index(fields=['order'], name='pay_order_idx'), models.Index(fields=['payment_provider', 'status'], name='pay_provider_status_idx'), models.Index(fields=['provider_transaction_id'], name='pay_txn_id_idx')],
            },
        ),
        migrations.AddConstraint(
            model_name='payment',
            constraint=models.CheckConstraint(check=models.Q(('amount__gt', 0)), name='payment_amount_must_be_positive'),
        ),
        migrations.AddConstraint(
            model_name='payment',
            constraint=models.UniqueConstraint(condition=models.Q(('provider_transaction_id__isnull', False)), fields=('payment_provider', 'provider_transaction_id'), name='uniq_provider_transaction_id'),
        ),
    ]
