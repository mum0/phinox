import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('orders', '0001_initial'),
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('session_key', models.CharField(db_index=True, max_length=64)),
                ('event_type', models.CharField(choices=[('page_view', 'Page View'), ('view_item', 'View Item'), ('add_to_cart', 'Add to Cart'), ('begin_checkout', 'Begin Checkout'), ('purchase', 'Purchase')], max_length=20)),
                ('event_data', models.JSONField(blank=True, default=dict, help_text='Event-specific data (e.g. {product_id, variant_sku, quantity}).')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'analytics_event',
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['session_key', 'event_type'], name='event_session_type_idx'), models.Index(fields=['event_type', '-created_at'], name='event_type_created_idx')],
            },
        ),
        migrations.CreateModel(
            name='Attribution',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('session_key', models.CharField(db_index=True, max_length=64, unique=True)),
                ('utm_source', models.CharField(blank=True, max_length=100)),
                ('utm_medium', models.CharField(blank=True, max_length=100)),
                ('utm_campaign', models.CharField(blank=True, max_length=100)),
                ('utm_content', models.CharField(blank=True, max_length=100)),
                ('utm_term', models.CharField(blank=True, max_length=100)),
                ('qr_code', models.CharField(blank=True, db_index=True, help_text='QR code identifier if the user arrived via a QR scan.', max_length=100)),
                ('first_seen_at', models.DateTimeField(auto_now_add=True)),
                ('last_seen_at', models.DateTimeField(auto_now=True)),
                ('order', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='attributions', to='orders.order')),
            ],
            options={
                'db_table': 'analytics_attribution',
                'indexes': [models.Index(fields=['session_key'], name='attr_session_idx'), models.Index(fields=['utm_source'], name='attr_utm_source_idx'), models.Index(fields=['qr_code'], name='attr_qr_code_idx')],
            },
        ),
    ]
