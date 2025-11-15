# Generated manually

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0013_remove_unused_discount_types'),
    ]

    operations = [
        # Add manufactured_date to StockBatch
        migrations.AddField(
            model_name='stockbatch',
            name='manufactured_date',
            field=models.DateField(blank=True, null=True, help_text='Manufacturing date of the medicine'),
        ),
        # Create PurchaseOrder model
        migrations.CreateModel(
            name='PurchaseOrder',
            fields=[
                ('order_id', models.AutoField(primary_key=True, serialize=False)),
                ('supplier_name', models.CharField(max_length=200)),
                ('order_date', models.DateTimeField(default=django.utils.timezone.now)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('received', 'Received'), ('partial', 'Partially Received')], default='pending', max_length=20)),
                ('notes', models.TextField(blank=True, null=True)),
            ],
        ),
        # Create PurchaseOrderLine model
        migrations.CreateModel(
            name='PurchaseOrderLine',
            fields=[
                ('line_id', models.AutoField(primary_key=True, serialize=False)),
                ('quantity_ordered', models.IntegerField()),
                ('quantity_received', models.IntegerField(default=0)),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('manufactured_date', models.DateField(blank=True, help_text='Manufacturing date of the medicine', null=True)),
                ('expiration_date', models.DateField(blank=True, help_text='Expiration date of the medicine', null=True)),
                ('medicine', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='base.medicine')),
                ('purchase_order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lines', to='base.purchaseorder')),
            ],
        ),
    ]
