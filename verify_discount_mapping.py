import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE','todo_list.settings')
django.setup()
from base.models import Sale

missing = Sale.objects.filter(discount_type_fk__isnull=True).count()
print(f"Sales still without FK discount_type: {missing}")
example = Sale.objects.filter(discount_type_fk__isnull=False).order_by('-sale_id').first()
if example:
    print(f"Sample Sale #{example.sale_id}: legacy={example.discount_type} mapped_to={example.discount_type_fk.discount_name} rate={example.discount_type_fk.discount_rate}")
