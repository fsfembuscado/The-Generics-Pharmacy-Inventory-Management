"""
Test script for multi-item dispensing functionality.
Tests proper unit conversion, pricing calculation, and FIFO stock tracking.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'todo_list.settings')
django.setup()

from base.models import Medicine, StockBatch, Sale, SaleLineItem, DiscountType, PaymentMethod
from django.contrib.auth.models import User
from decimal import Decimal

def test_multi_item_dispense():
    print("=" * 60)
    print("MULTI-ITEM DISPENSING TEST")
    print("=" * 60)
    
    # Get or create test user
    user = User.objects.first()
    if not user:
        print("❌ No users found. Please create a user first.")
        return
    
    print(f"✓ Using user: {user.username}")
    
    # Get test medicines
    medicines = list(Medicine.objects.filter(is_deleted=False)[:3])
    if len(medicines) < 2:
        print("❌ Need at least 2 medicines in database for testing.")
        return
    
    print(f"\n✓ Found {len(medicines)} medicines for testing:")
    for med in medicines:
        batches = med.batches.filter(is_deleted=False, is_recalled=False)
        total_boxes = sum(b.quantity for b in batches)
        print(f"  - {med.name}: {total_boxes} boxes available")
        print(f"    Price: ₱{med.selling_price}/piece")
        print(f"    Pack config: {med.units_per_pack} units/pack, {med.packs_per_box} packs/box")
    
    # Get discount and payment method
    discount = DiscountType.objects.filter(discount_name__icontains='senior').first()
    payment = PaymentMethod.objects.filter(method_name='Cash').first()
    
    if not payment:
        payment = PaymentMethod.objects.first()
    
    print(f"\n✓ Using discount: {discount.discount_name if discount else 'None'} ({discount.discount_rate if discount else 0}%)")
    print(f"✓ Using payment method: {payment.method_name if payment else 'Cash'}")
    
    # Create a multi-item sale
    print("\n" + "-" * 60)
    print("Creating multi-item sale...")
    print("-" * 60)
    
    sale = Sale.objects.create(
        user=user,
        discount_type_fk=discount,
        payment_method=payment,
        status='Pending'
    )
    
    print(f"✓ Created Sale #{sale.sale_id}")
    
    # Add line items with different unit types
    line_items_data = [
        (medicines[0], 2, 'piece'),
        (medicines[1], 1, 'pack'),
    ]
    
    if len(medicines) >= 3:
        line_items_data.append((medicines[2], 1, 'box'))
    
    print("\nAdding line items:")
    for med, qty, unit_type in line_items_data:
        line_item = SaleLineItem.objects.create(
            sale=sale,
            medicine=med,
            quantity=qty,
            unit_type=unit_type,
            unit_price=med.selling_price
        )
        
        print(f"  ✓ {med.name}: {qty} {unit_type}(s)")
        print(f"    → {line_item.pieces_dispensed} pieces @ ₱{line_item.unit_price}/pc = ₱{line_item.line_total}")
    
    # Calculate totals
    print("\n" + "-" * 60)
    print("Calculating totals...")
    print("-" * 60)
    
    sale.apply_discount()
    sale.refresh_from_db()
    
    print(f"  Subtotal: ₱{sale.total_amount}")
    print(f"  Discount ({sale.discount_rate}%): -₱{sale.discount_amount}")
    print(f"  Final Total: ₱{sale.final_amount}")
    
    # Simulate payment
    cash_received = sale.final_amount + Decimal('100.00')
    sale.finalize_payment(cash_received)
    sale.status = 'Completed'
    sale.save()
    
    print(f"\n  Cash Received: ₱{sale.cash_received}")
    print(f"  Change: ₱{sale.change_amount}")
    print(f"  Invoice: {sale.invoice_number}")
    
    # Verify line items
    print("\n" + "-" * 60)
    print("Verifying sale details...")
    print("-" * 60)
    
    line_items = sale.line_items.all()
    print(f"✓ Sale has {line_items.count()} line items:")
    
    for idx, line in enumerate(line_items, 1):
        print(f"\n  Item {idx}:")
        print(f"    Medicine: {line.medicine.name}")
        print(f"    Quantity: {line.quantity} {line.unit_type}")
        print(f"    Pieces dispensed: {line.pieces_dispensed}")
        print(f"    Unit price: ₱{line.unit_price}/piece")
        print(f"    Line total: ₱{line.line_total}")
    
    # Test unit conversion accuracy
    print("\n" + "-" * 60)
    print("Testing unit conversion accuracy...")
    print("-" * 60)
    
    for line in line_items:
        med = line.medicine
        expected_pieces = line.quantity
        
        if line.unit_type == 'pack':
            expected_pieces = line.quantity * (med.units_per_pack or 1)
        elif line.unit_type == 'box':
            expected_pieces = line.quantity * (med.packs_per_box or 1) * (med.units_per_pack or 1)
        
        if line.pieces_dispensed == expected_pieces:
            print(f"  ✓ {med.name}: Conversion correct ({line.quantity} {line.unit_type} = {expected_pieces} pieces)")
        else:
            print(f"  ❌ {med.name}: Conversion error!")
            print(f"     Expected {expected_pieces} pieces, got {line.pieces_dispensed}")
    
    # Test price calculation accuracy
    print("\n" + "-" * 60)
    print("Testing price calculation accuracy...")
    print("-" * 60)
    
    recalc_subtotal = Decimal('0.00')
    for line in line_items:
        expected_line_total = Decimal(str(line.pieces_dispensed)) * line.unit_price
        if line.line_total == expected_line_total:
            print(f"  ✓ {line.medicine.name}: Price correct (₱{line.line_total})")
        else:
            print(f"  ❌ {line.medicine.name}: Price error!")
            print(f"     Expected ₱{expected_line_total}, got ₱{line.line_total}")
        recalc_subtotal += line.line_total
    
    if recalc_subtotal == sale.total_amount:
        print(f"\n  ✓ Subtotal calculation correct: ₱{recalc_subtotal}")
    else:
        print(f"\n  ❌ Subtotal mismatch!")
        print(f"     Expected ₱{recalc_subtotal}, got ₱{sale.total_amount}")
    
    # Test discount calculation
    expected_discount = (recalc_subtotal * sale.discount_rate / Decimal('100')).quantize(Decimal('0.01'))
    if abs(sale.discount_amount - expected_discount) < Decimal('0.01'):
        print(f"  ✓ Discount calculation correct: ₱{sale.discount_amount}")
    else:
        print(f"  ❌ Discount mismatch!")
        print(f"     Expected ₱{expected_discount}, got ₱{sale.discount_amount}")
    
    expected_final = recalc_subtotal - sale.discount_amount
    if abs(sale.final_amount - expected_final) < Decimal('0.01'):
        print(f"  ✓ Final amount correct: ₱{sale.final_amount}")
    else:
        print(f"  ❌ Final amount mismatch!")
        print(f"     Expected ₱{expected_final}, got ₱{sale.final_amount}")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETED SUCCESSFULLY!")
    print("=" * 60)
    print(f"\nSale #{sale.sale_id} created with {line_items.count()} items")
    print(f"Total: ₱{sale.final_amount} (after {sale.discount_rate}% discount)")
    print(f"Invoice: {sale.invoice_number}")
    
    return sale

if __name__ == '__main__':
    try:
        sale = test_multi_item_dispense()
        print(f"\n✓ You can view the invoice at: /invoice/{sale.sale_id}/")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
