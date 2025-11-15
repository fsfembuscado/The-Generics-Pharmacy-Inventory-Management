from django.db import migrations

def map_legacy_discounts(apps, schema_editor):
    Sale = apps.get_model('base', 'Sale')
    DiscountType = apps.get_model('base', 'DiscountType')

    # Build lookup dict: simplify to lowercase key tokens
    mapping = {}
    for dt in DiscountType.objects.all():
        key = dt.discount_name.lower()
        if 'regular' in key:
            mapping['regular'] = dt
        elif 'pwd' in key or 'disability' in key:
            mapping['pwd'] = dt
        elif 'senior' in key:
            mapping['senior'] = dt
        elif 'other' in key:
            mapping['other'] = dt

    updated = 0
    for sale in Sale.objects.filter(discount_type_fk__isnull=True):
        legacy = sale.discount_type  # string code
        dt = mapping.get(legacy)
        if dt:
            sale.discount_type_fk = dt
            sale.save(update_fields=['discount_type_fk'])
            updated += 1
    print(f"Mapped legacy discount codes to DiscountType FK for {updated} sale(s).")


def reverse_map_legacy(apps, schema_editor):
    # No reverse action necessary; leave FKs.
    pass

class Migration(migrations.Migration):
    dependencies = [
        ('base','0007_sale_cash_received_sale_change_amount_and_more'),
    ]

    operations = [
        migrations.RunPython(map_legacy_discounts, reverse_map_legacy)
    ]
