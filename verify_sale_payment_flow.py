import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE','todo_list.settings')
django.setup()
from decimal import Decimal
from django.contrib.auth.models import User
from base.models import Medicine, StockBatch, Sale, DiscountType, PaymentMethod, StockMovement
from django.utils import timezone

user = User.objects.filter(is_superuser=True).first()
med = Medicine.objects.first()
if not med:
    print('No medicine available to test.')
    raise SystemExit

# Ensure at least one batch
batch = StockBatch.objects.filter(medicine=med, quantity__gt=0).first()
if not batch:
    # create a batch
    batch = StockBatch.objects.create(medicine=med, quantity=10, location='front')
    print('Created test batch with 10 units.')

# Dispense 2 pieces manually (simulate view logic)
movement = StockMovement.objects.create(
    medicine=med,
    batch=batch,
    from_location='front',
    to_location='',
    quantity=2,
    reason='sale',
    remarks='Test dispense',
    user=user
)

sale = Sale.objects.create(user=user, discount_type='regular')
movement.sale = sale
movement.save()

# Attach discount + payment
regular_discount = DiscountType.objects.filter(discount_name__icontains='Regular').first()
if regular_discount:
    sale.discount_type_fk = regular_discount
sale.apply_discount()

cash_received = sale.final_amount + Decimal('50.00')  # simulate overpayment for change
sale.finalize_payment(cash_received)

print(f"Sale ID: {sale.sale_id}")
print(f"Subtotal: {sale.total_amount}")
print(f"Discount Rate: {sale.discount_rate}%")
print(f"Discount Amount: {sale.discount_amount}")
print(f"Final Amount: {sale.final_amount}")
print(f"Cash Received: {sale.cash_received}")
print(f"Change: {sale.change_amount}")
print(f"Invoice Number: {sale.invoice_number}")
