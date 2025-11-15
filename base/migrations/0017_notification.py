# Generated manually

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('base', '0016_purchaseorder_purchaseorderline'),
    ]

    operations = [
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('notification_id', models.AutoField(primary_key=True, serialize=False)),
                ('notification_type', models.CharField(choices=[('expiry', 'Near Expiry'), ('low_stock', 'Low Stock'), ('out_of_stock', 'Out of Stock')], max_length=20)),
                ('title', models.CharField(max_length=255)),
                ('message', models.TextField()),
                ('is_read', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('related_batch', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='base.stockbatch')),
                ('related_medicine', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='base.medicine')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
