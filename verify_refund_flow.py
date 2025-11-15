import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE','todo_list.settings')
django.setup()
from django.contrib.auth.models import User
from base.models import Sale, Refund, StockMovement
from decimal import Decimal

user = User.objects.filter(is_superuser=True).first()
latest_sale = Sale.objects.order_by('-sale_id').first()
if not latest_sale:
    print('No sale found to refund.')
    raise SystemExit

# Ensure sale has movements
movements = latest_sale.movements.all()
print(f'Sale #{latest_sale.sale_id} movements count: {movements.count()}')

# Process full refund via model logic similar to view
from base.models import PaymentMethod
pm = latest_sale.payment_method or PaymentMethod.objects.first()

amount = latest_sale.final_amount
if amount <= 0:
    print('Sale has zero amount; cannot refund.')
    raise SystemExit

restored_total = 0
for m in movements.select_related('batch','medicine'):
    if m.batch and m.quantity > 0:
        m.batch.quantity += m.quantity
        m.batch.save()
        restored_total += m.quantity
        StockMovement.objects.create(
            medicine=m.medicine,
            batch=m.batch,
            from_location='',
            to_location=m.batch.location,
            quantity=m.quantity,
            reason='returned',
            remarks=f'Refund reversal of Sale #{latest_sale.sale_id}',
            user=user
        )

refund = Refund.objects.create(
    sale=latest_sale,
    amount_refunded=amount,
    reason='customer_request',
    reason_details='Automated test full refund',
    processed_by=user,
    payment_method=pm,
)

print(f'Refund #{refund.refund_id} created for Sale #{latest_sale.sale_id} amount ₱{amount}')
print(f'Restored pieces: {restored_total}')
