from django.db import models, transaction
from django.contrib.auth.models import User
from django.utils.timezone import now
from datetime import timedelta
from django.utils import timezone
from django.db.models.signals import post_migrate
from django.apps import apps
from decimal import Decimal
# --------------------------- SOFT DELETE BASE MODEL ---------------------------
class SoftDeleteManager(models.Manager):
    """Default manager that hides soft-deleted objects."""
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

class SoftDeleteModel(models.Model):
    """Abstract base class providing soft delete functionality."""
    is_deleted = models.BooleanField(default=False)

    # Managers
    objects = SoftDeleteManager()       # Only non-deleted
    all_objects = models.Manager()      # Includes deleted

    def delete(self, *args, **kwargs):
        """Always perform a soft delete (never hard delete)."""
        self.is_deleted = True
        self.save()

    def restore(self):
        """Restore a soft-deleted object."""
        self.is_deleted = False
        self.save()

    class Meta:
        abstract = True

# --------------------------- TASK MODEL ---------------------------
class Task(SoftDeleteModel):
    title = models.CharField(max_length=200, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    complete = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        ordering = ["complete"]

    def __str__(self):
        return self.title or f"Task {self.id}"

# --------------------------- ACTIVITY LOG MODEL ---------------------------
class ActivityLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    action = models.CharField(max_length=255)
    timestamp = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.user.username} - {self.action} at {self.timestamp}" 

# --------------------------- NOTIFICATION MODEL ---------------------------
class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('expiry', 'Near Expiry'),
        ('low_stock', 'Low Stock'),
        ('out_of_stock', 'Out of Stock'),
    ]
    
    notification_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=255)
    message = models.TextField()
    related_medicine = models.ForeignKey('Medicine', on_delete=models.CASCADE, null=True, blank=True)
    related_batch = models.ForeignKey('StockBatch', on_delete=models.CASCADE, null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.notification_type} - {self.title}"

# --------------------------- ROLE MODEL ---------------------------
class Role(models.Model):
    """
    Defines user roles in the system (Manager, Staff, etc.)
    Replaces Django's default Group system for pharmacy-specific roles.
    """
    role_id = models.AutoField(primary_key=True)
    role_name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True, help_text="Description of role permissions and responsibilities")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['role_name']
        verbose_name = "Role"
        verbose_name_plural = "Roles"

    def __str__(self):
        return self.role_name

# --------------------------- EMPLOYEE MODEL ---------------------------
class Employee(SoftDeleteModel):
    """
    Links User accounts to employee-specific information.
    Separates authentication (User) from employee data (Employee).
    """
    employee_id = models.AutoField(primary_key=True)
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name='employee_profile',
        help_text="Linked Django User account"
    )
    employee_number = models.CharField(
        max_length=20, 
        unique=True, 
        blank=True,
        help_text="Unique employee identifier (e.g., EMP-001)"
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    contact_number = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    hire_date = models.DateField(default=now)
    
    class Meta:
        ordering = ['employee_number', 'last_name', 'first_name']
        verbose_name = "Employee"
        verbose_name_plural = "Employees"

    def __str__(self):
        return f"{self.employee_number} - {self.first_name} {self.last_name}"
    
    def save(self, *args, **kwargs):
        # Auto-generate employee number if not provided
        if not self.employee_number:
            last_emp = Employee.all_objects.order_by('-employee_id').first()
            next_id = (last_emp.employee_id + 1) if last_emp else 1
            self.employee_number = f"EMP-{next_id:04d}"
        super().save(*args, **kwargs)
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    def has_role(self, role_name):
        """Check if employee has a specific role"""
        return self.designations.filter(role__role_name=role_name).exists()
    
    def get_primary_role(self):
        """Get the primary role for this employee"""
        designation = self.designations.filter(is_primary=True).first()
        return designation.role if designation else None
    
    def get_all_roles(self):
        """Get all roles assigned to this employee"""
        return [d.role for d in self.designations.all()]

# --------------------------- EMPLOYEE DESIGNATION MODEL ---------------------------
class EmployeeDesignation(models.Model):
    """
    Assigns roles to employees. Allows multiple roles per employee if needed.
    Links Employee → Role with optional metadata.
    """
    designation_id = models.AutoField(primary_key=True)
    employee = models.ForeignKey(
        Employee, 
        on_delete=models.CASCADE, 
        related_name='designations'
    )
    role = models.ForeignKey(
        Role, 
        on_delete=models.PROTECT, 
        related_name='employee_designations'
    )
    assigned_date = models.DateField(default=now)
    is_primary = models.BooleanField(
        default=True, 
        help_text="Primary role for this employee"
    )
    
    class Meta:
        ordering = ['-is_primary', 'assigned_date']
        verbose_name = "Employee Designation"
        verbose_name_plural = "Employee Designations"
        unique_together = ['employee', 'role']  # Prevent duplicate role assignments

    def __str__(self):
        primary = " (Primary)" if self.is_primary else ""
        return f"{self.employee.full_name} - {self.role.role_name}{primary}"

# --------------------------- DISCOUNT TYPE MODEL ---------------------------
class DiscountType(models.Model):
    """
    Configurable discount types for sales (replaces hardcoded DISCOUNT_CHOICES).
    ERD: discountTypeID with discountName, discountNumber, unit
    """
    discount_type_id = models.AutoField(primary_key=True)
    discount_name = models.CharField(
        max_length=100, 
        unique=True,
        help_text="Name of discount (e.g., PWD, Senior Citizen, Regular)"
    )
    discount_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Percentage discount rate (e.g., 20.00 for 20%)"
    )
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this discount type is currently available"
    )
    requires_id = models.BooleanField(
        default=False,
        help_text="Whether this discount requires ID verification (e.g., PWD, Senior)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['discount_name']
        verbose_name = "Discount Type"
        verbose_name_plural = "Discount Types"

    def __str__(self):
        return f"{self.discount_name} ({self.discount_rate}%)"

# --------------------------- PAYMENT METHOD MODEL ---------------------------
class PaymentMethod(models.Model):
    """
    Payment methods for tracking how customers pay.
    ERD: paymentMethodID, modeOfPaymentName
    """
    payment_method_id = models.AutoField(primary_key=True)
    method_name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Payment method name (e.g., Cash, Credit Card, GCash)"
    )
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this payment method is currently available"
    )
    requires_reference = models.BooleanField(
        default=False,
        help_text="Whether this payment method requires a reference number (e.g., card transactions)"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['method_name']
        verbose_name = "Payment Method"
        verbose_name_plural = "Payment Methods"

    def __str__(self):
        return self.method_name

# --------------------------- REFUND MODEL ---------------------------
class Refund(models.Model):
    """
    Track refunds for returned products or cancelled sales.
    ERD: refundID, amountRefunded, reason, date
    """
    refund_id = models.AutoField(primary_key=True)
    sale = models.ForeignKey(
        'Sale',
        on_delete=models.CASCADE,
        related_name='refunds',
        help_text="Original sale being refunded"
    )
    refund_date = models.DateTimeField(default=now)
    amount_refunded = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Amount returned to customer"
    )
    
    REFUND_REASON_CHOICES = [
        ('expired', 'Expired Product'),
        ('damaged', 'Damaged Product'),
        ('wrong_item', 'Wrong Item Sold'),
        ('customer_request', 'Customer Request'),
        ('overcharge', 'Overcharge/Pricing Error'),
        ('other', 'Other Reason'),
    ]
    
    reason = models.CharField(
        max_length=50,
        choices=REFUND_REASON_CHOICES,
        help_text="Reason for refund"
    )
    reason_details = models.TextField(
        blank=True,
        null=True,
        help_text="Additional details about the refund"
    )
    processed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='processed_refunds',
        help_text="User who processed the refund"
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_refunds',
        help_text="Manager who approved the refund"
    )
    payment_method = models.ForeignKey(
        PaymentMethod,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Method used for refund (usually same as original payment)"
    )
    reference_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Reference number for refund transaction"
    )

    # New fields for enhanced workflow
    STATUS_CHOICES = [
        ('Pending', 'Pending Approval'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Approved')
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='refunds_approved'
    )
    approved_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-refund_date']
        verbose_name = "Refund"
        verbose_name_plural = "Refunds"

    def __str__(self):
        return f"Refund #{self.refund_id} - Sale #{self.sale.sale_id} (₱{self.amount_refunded})"

class RefundLine(models.Model):
    """Individual line items for partial refunds, linked to original stock movement."""
    refund = models.ForeignKey(Refund, on_delete=models.CASCADE, related_name='lines')
    movement = models.ForeignKey('StockMovement', on_delete=models.CASCADE, related_name='refund_lines')
    refunded_quantity = models.PositiveIntegerField(help_text="Quantity refunded from this movement")

    class Meta:
        verbose_name = 'Refund Line'
        verbose_name_plural = 'Refund Lines'

    def __str__(self):
        return f"RefundLine #{self.id} refund={self.refund_id} movement={self.movement_id} qty={self.refunded_quantity}"

# --------------------------- PRODUCT CATEGORY ---------------------------
class Category(SoftDeleteModel):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ["name"]

    def __str__(self):
        return self.name

# --------------------------- PRODUCT TYPE MODEL ---------------------------
class ProductType(SoftDeleteModel):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="product_types")
    name = models.CharField(max_length=200)

    class Meta:
        verbose_name_plural = "Product Types"
        ordering = ["category__name", "name"]

    def __str__(self):
        return f"{self.name} ({self.category.name})"

# --------------------------- MEDICINE / PRODUCT MODEL ---------------------------
class Medicine(SoftDeleteModel):
    name = models.CharField(max_length=200)
    brand = models.CharField(max_length=200, null=True, blank=True)
    description = models.TextField(null=True, blank=True)

    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="medicines",
        null=True,
        blank=True,
    )

    product_type = models.ForeignKey(
        ProductType,
        on_delete=models.PROTECT,
        related_name="medicines",
        null=True,
        blank=True,
        help_text="Product type within the selected category"
    )

    DOSAGE_CHOICES = [
        ("tablet", "Tablet"),
        ("capsule", "Capsule"),
        ("powder", "Powder"),
        ("oral_solution", "Oral Solution"),
        ("injectable_solution", "Injectable Solution"),
    ]
    dosage_form = models.CharField(
        max_length=30, choices=DOSAGE_CHOICES, null=True, blank=True
    )

    units_per_pack = models.PositiveIntegerField(
        default=0,
        help_text="How many pieces per pack (e.g., 12 tablets per pack)."
    )

    packs_per_box = models.PositiveIntegerField(
        default=0,
        help_text="How many packs per box (e.g., 10 packs per box)."
    )

    box_quantity = models.PositiveIntegerField(
        default=0,
        help_text="How many boxes are currently in stock (e.g., 3 boxes)."
    )

    strength = models.CharField(max_length=100, default="N/A")
    base_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        cat = self.category.name if self.category else "Uncategorized"
        return f"{self.name} ({self.brand or 'Generic'}) - {self.get_dosage_form_display() if self.dosage_form else ''} [{cat}]"

    @property
    def total_pieces(self):
        return self.box_quantity * self.packs_per_box * self.units_per_pack

# --------------------------- PRICE HISTORY MODEL ---------------------------
class PriceHistory(models.Model):
    """Track all price changes for medicines over time."""
    medicine = models.ForeignKey(
        Medicine, 
        on_delete=models.CASCADE, 
        related_name='price_history'
    )
    old_base_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Previous base price before change"
    )
    new_base_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="New base price after change"
    )
    old_selling_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Previous selling price before change"
    )
    new_selling_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="New selling price after change"
    )
    changed_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='price_changes'
    )
    change_date = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(blank=True, null=True, help_text="Optional reason for price change")
    
    class Meta:
        ordering = ['-change_date']
        verbose_name_plural = "Price Histories"
    
    def __str__(self):
        return f"{self.medicine.name} - ₱{self.old_selling_price} → ₱{self.new_selling_price} on {self.change_date.strftime('%Y-%m-%d %H:%M')}"

# --------------------------- STOCK BATCH MODEL ---------------------------
class StockBatch(SoftDeleteModel):
    LOCATION_CHOICES = [
        ("front", "Store Shelf"),
        ("back", "Stock Room"),
    ]

    medicine = models.ForeignKey("Medicine", on_delete=models.CASCADE, related_name="batches")
    # Quantity of full boxes in this batch
    quantity = models.PositiveIntegerField()
    # Additional loose pieces not forming a full box
    loose_pieces = models.PositiveIntegerField(default=0)
    expiry_date = models.DateField(blank=True, null=True)
    manufactured_date = models.DateField(blank=True, null=True, help_text="Manufacturing date of the batch")
    location = models.CharField(max_length=10, choices=LOCATION_CHOICES)
    date_received = models.DateField(default=now)
    is_recalled = models.BooleanField(
        default=False,
        help_text="Mark this batch as recalled if it is damaged or withdrawn from sale."
    )

    class Meta:
        ordering = ["date_received"]

    def save(self, *args, **kwargs):
        if self.date_received and not self.expiry_date:
            self.expiry_date = self.date_received + timedelta(days=180)
        super().save(*args, **kwargs)

    def __str__(self):
        recall_status = " [RECALLED]" if self.is_recalled else ""
        return f"{self.medicine.name} - {self.quantity} boxes (+{self.loose_pieces} pcs) ({self.location}){recall_status}"

    @property
    def pieces_per_box(self):
        return (self.medicine.packs_per_box or 1) * (self.medicine.units_per_pack or 1)

    @property
    def total_pieces(self):
        return (self.quantity * self.pieces_per_box) + (self.loose_pieces or 0)

    def get_total_pieces(self, quantity, unit_type="box"):
        units_per_pack = self.medicine.units_per_pack or 1
        packs_per_box = self.medicine.packs_per_box or 1
        if unit_type == "piece":
            return quantity
        elif unit_type == "pack":
            return quantity * units_per_pack
        elif unit_type == "box":
            return quantity * packs_per_box * units_per_pack
        return quantity
    @staticmethod
    @transaction.atomic
    def dispense(medicine_id, pieces_needed, unit_type="box", user=None):
        try:
            medicine = Medicine.objects.get(pk=medicine_id)
        except Medicine.DoesNotExist:
            return pieces_needed

        # Convert pieces_needed based on unit_type
        if unit_type != "piece":
            if unit_type == "pack":
                pieces_needed *= (medicine.units_per_pack or 1)
            elif unit_type == "box":
                pieces_needed *= (medicine.packs_per_box or 1) * (medicine.units_per_pack or 1)

        # Prefer front (store shelf) first, then back (stock room)
        from django.db.models import Case, When, Value, IntegerField
        batches = StockBatch.objects.filter(
            medicine_id=medicine_id,
            is_deleted=False,
            is_recalled=False
        ).select_related("medicine").annotate(
            loc_order=Case(
                When(location='front', then=Value(0)),
                When(location='back', then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            )
        ).order_by("loc_order", "date_received")

        total_dispensed = 0

        for batch in batches:
            if pieces_needed <= 0:
                break

            batch_total_pieces = batch.total_pieces

            if batch_total_pieces <= pieces_needed:
                consumed = batch_total_pieces
                total_dispensed += consumed
                pieces_needed -= consumed
                StockMovement.objects.create(
                    medicine=batch.medicine,
                    batch=batch,
                    from_location=batch.location,
                    to_location="",
                    quantity=consumed,
                    reason="sale",
                    remarks="Dispensed (full batch) via FIFO",
                    user=user
                )
                batch.delete()
            else:
                consumed = pieces_needed
                remaining_pieces = batch_total_pieces - consumed
                pieces_per_box = batch.pieces_per_box
                batch.quantity = remaining_pieces // pieces_per_box
                batch.loose_pieces = remaining_pieces % pieces_per_box
                batch.save()
                StockMovement.objects.create(
                    medicine=batch.medicine,
                    batch=batch,
                    from_location=batch.location,
                    to_location="",
                    quantity=consumed,
                    reason="sale",
                    remarks="Dispensed (partial batch) via FIFO",
                    user=user
                )
                total_dispensed += consumed
                pieces_needed = 0

        # Auto-promote: if no front batches remain but there are back batches, move the oldest back to front
        try:
            medicine = Medicine.objects.get(pk=medicine_id)
            has_front = StockBatch.objects.filter(medicine=medicine, is_deleted=False, is_recalled=False, location='front').exists()
            if not has_front:
                back_batch = StockBatch.objects.filter(medicine=medicine, is_deleted=False, is_recalled=False, location='back').order_by('date_received').first()
                if back_batch:
                    # Move entire batch to front and log transfer movement of all pieces
                    total_pieces_move = back_batch.total_pieces
                    back_batch.location = 'front'
                    back_batch.save()
                    try:
                        StockMovement.objects.create(
                            medicine=back_batch.medicine,
                            batch=back_batch,
                            from_location='back',
                            to_location='front',
                            quantity=total_pieces_move,
                            reason='transfer',
                            remarks='Auto-promotion to Store Shelf after front empty',
                            user=user
                        )
                    except Exception:
                        pass
        except Exception:
            pass

        return pieces_needed

    def is_expired(self):
        total = self.total_pieces
        if total > 0:
            self.quantity = 0
            self.loose_pieces = 0
            self.save()
            from base.models import log_stock_movement
            log_stock_movement(
                self,
                "expired",
                total,
                remarks=f"Batch {self.id} ({self.medicine.name}) expired and removed from inventory."
            )
        self.delete()

class StockMovement(models.Model):
    """
    Tracks all inventory movements: sales, transfers, expirations, etc.
    For sales, links to both Sale (transaction) and SaleLineItem (specific product line).
    """
    MOVEMENT_REASON_CHOICES = [
        ("sale", "Sale / Dispensed"),
        ("expired", "Expired"),
        ("damaged", "Damaged"),
        ("returned", "Returned"),
        ("transfer", "Transfer"),
        ("adjustment", "Stock Adjustment"),
    ]

    medicine = models.ForeignKey("Medicine", on_delete=models.CASCADE, related_name="movements")
    batch = models.ForeignKey(StockBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name="movements")
    from_location = models.CharField(max_length=20, blank=True, null=True)
    to_location = models.CharField(max_length=20, blank=True, null=True)
    movement_time = models.TimeField(default=timezone.now)
    movement_date = models.DateTimeField(default=now)
    quantity = models.PositiveIntegerField(help_text="Quantity in pieces")
    reason = models.CharField(max_length=20, choices=MOVEMENT_REASON_CHOICES)
    remarks = models.TextField(blank=True, null=True)
    user = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="stock_movements")
    
    # Link to sale transaction and specific line item
    sale = models.ForeignKey('base.Sale', on_delete=models.CASCADE, null=True, blank=True, related_name='movements')
    line_item = models.ForeignKey('base.SaleLineItem', on_delete=models.SET_NULL, null=True, blank=True, related_name='movements')

    class Meta:
        ordering = ["-movement_date"]

    def __str__(self):
        return f"{self.medicine.name} - {self.reason} ({self.quantity} pcs)"

class Sale(models.Model):
    """
    Sale header/transaction record. 
    Contains overall sale info: totals, discounts, payment details.
    Individual line items tracked in SaleLineItem.
    """
    sale_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='sales')
    customer_name = models.CharField(max_length=255, blank=True, null=True)
    # Link to ordering if this sale fulfills a customer order
    # Note: Ordering model has OneToOne to Sale, so we use related_name 'customer_order'
    sale_date = models.DateTimeField(auto_now_add=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Subtotal before discount")
    status = models.CharField(max_length=50, default='Completed')

    # Discount-related fields
    discount_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Percentage discount applied based on type."
    )
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Computed discount amount based on total and rate."
    )
    final_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Final amount after discount is applied."
    )

    # Discount/payment fields
    discount_type_fk = models.ForeignKey('DiscountType', on_delete=models.SET_NULL, null=True, blank=True, help_text="Configured discount type applied")
    payment_method = models.ForeignKey('PaymentMethod', on_delete=models.SET_NULL, null=True, blank=True, help_text="Payment method used")
    cash_received = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Amount tendered by customer")
    change_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Change returned to customer")
    invoice_number = models.CharField(max_length=30, blank=True, null=True, help_text="Printable invoice number")

    def __str__(self):
        return f"Sale #{self.sale_id} - {self.sale_date.strftime('%Y-%m-%d %H:%M')}"

    def apply_discount(self):
        """Calculate discount and final totals from line items."""
        from decimal import Decimal
        subtotal = Decimal('0.00')
        # Sum up line items instead of movements
        for line in self.line_items.all():
            subtotal += line.line_total
        
        self.total_amount = subtotal
        self.discount_rate = Decimal(str(self.discount_type_fk.discount_rate)) if (self.discount_type_fk and self.discount_type_fk.is_active) else Decimal('0')
        self.discount_amount = (subtotal * self.discount_rate / Decimal('100')) if self.discount_rate > 0 else Decimal('0.00')
        self.final_amount = subtotal - self.discount_amount
        self.save(update_fields=['total_amount', 'discount_rate', 'discount_amount', 'final_amount'])

    def finalize_payment(self, cash_received):
        from decimal import Decimal
        if self.final_amount == 0:
            self.apply_discount()
        cash = Decimal(str(cash_received or 0))
        self.cash_received = cash
        self.change_amount = cash - self.final_amount if cash >= self.final_amount else Decimal('0.00')
        if not self.invoice_number:
            self.invoice_number = f"INV-{self.sale_id:06d}"
        self.save(update_fields=['cash_received', 'change_amount', 'invoice_number'])

    def effective_discount_label(self):
        return self.discount_type_fk.discount_name if self.discount_type_fk else 'No Discount'


# --------------------------- SALE LINE ITEM MODEL ---------------------------
class SaleLineItem(models.Model):
    """
    Individual product line in a sale.
    Tracks: which medicine, quantity, unit type, unit price, line total.
    Links to Sale (header) and connects to StockMovements for inventory tracking.
    """
    UNIT_CHOICES = [
        ('piece', 'Piece'),
        ('pack', 'Pack'),
        ('box', 'Box'),
    ]
    
    line_item_id = models.AutoField(primary_key=True)
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='line_items')
    medicine = models.ForeignKey(Medicine, on_delete=models.PROTECT, related_name='sale_lines')
    quantity = models.PositiveIntegerField(help_text="Quantity in selected unit type (box/pack/piece)")
    unit_type = models.CharField(max_length=10, choices=UNIT_CHOICES, default='piece')
    unit_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Price per single piece (always stored as per-piece price)"
    )
    line_total = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Total for this line: quantity (in pieces) × unit_price"
    )
    pieces_dispensed = models.PositiveIntegerField(
        default=0,
        help_text="Total pieces dispensed (quantity converted to pieces)"
    )

    class Meta:
        ordering = ['line_item_id']

    def __str__(self):
        return f"Sale #{self.sale.sale_id} - {self.medicine.name} ({self.quantity} {self.unit_type})"

    def save(self, *args, **kwargs):
        """Auto-calculate pieces_dispensed and line_total on save."""
        from decimal import Decimal
        
        # Convert quantity to pieces based on unit_type
        if self.unit_type == 'piece':
            self.pieces_dispensed = self.quantity
        elif self.unit_type == 'pack':
            self.pieces_dispensed = self.quantity * (self.medicine.units_per_pack or 1)
        elif self.unit_type == 'box':
            packs_per_box = self.medicine.packs_per_box or 1
            units_per_pack = self.medicine.units_per_pack or 1
            self.pieces_dispensed = self.quantity * packs_per_box * units_per_pack
        
        # Calculate line total: pieces × per-piece price
        self.line_total = Decimal(str(self.pieces_dispensed)) * Decimal(str(self.unit_price))
        
        super().save(*args, **kwargs)


# --------------------------- ORDERING MODEL (Customer Orders) ---------------------------
class Ordering(models.Model):
    """
    Customer orders for pre-orders, reservations, or named customer purchases.
    ERD: orderingID, orderedProductID, userID, status, orderDate
    Different from Purchase Orders - this is customer-facing.
    """
    ordering_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='customer_orders',
        help_text="Staff member who created the order"
    )
    customer_name = models.CharField(
        max_length=255,
        help_text="Customer name for the order"
    )
    customer_contact = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Phone number or contact info"
    )
    order_date = models.DateTimeField(
        default=now,
        help_text="When the order was placed"
    )
    expected_pickup_date = models.DateField(
        blank=True,
        null=True,
        help_text="When customer expects to pick up"
    )
    
    STATUS_CHOICES = [
        ('Pending', 'Pending - Not Yet Confirmed'),
        ('Confirmed', 'Confirmed - Items Reserved'),
        ('Ready', 'Ready for Pickup'),
        ('Completed', 'Completed - Picked Up and Paid'),
        ('Cancelled', 'Cancelled'),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='Pending',
        help_text="Current order status"
    )
    
    notes = models.TextField(
        blank=True,
        null=True,
        help_text="Special instructions or notes"
    )
    
    # Link to sale when order is completed
    sale = models.OneToOneField(
        'Sale',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customer_order',
        help_text="Sale record when order is completed and paid"
    )
    
    # Tracking
    confirmed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='confirmed_orders',
        help_text="Staff who confirmed the order"
    )
    confirmed_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When order was confirmed"
    )
    completed_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When order was completed"
    )
    
    class Meta:
        ordering = ['-order_date']
        verbose_name = "Customer Order"
        verbose_name_plural = "Customer Orders"
    
    def __str__(self):
        return f"Order #{self.ordering_id} - {self.customer_name} ({self.status})"
    
    def get_total_amount(self):
        """Calculate total from ordered products"""
        from decimal import Decimal
        total = Decimal('0.00')
        for item in self.ordered_products.all():
            total += item.line_total
        return total
    
    def confirm_order(self, confirmed_by_user):
        """Confirm order and reserve stock"""
        if self.status != 'Pending':
            return False
        
        # Check if all items have sufficient stock
        for item in self.ordered_products.all():
            available = item.medicine.total_pieces if hasattr(item.medicine, 'total_pieces') else 0
            if available < item.pieces_needed:
                return False
        
        self.status = 'Confirmed'
        self.confirmed_by = confirmed_by_user
        self.confirmed_date = now()
        self.save(update_fields=['status', 'confirmed_by', 'confirmed_date'])
        return True
    
    def mark_ready(self):
        """Mark order as ready for pickup"""
        if self.status == 'Confirmed':
            self.status = 'Ready'
            self.save(update_fields=['status'])
            return True
        return False
    
    def cancel_order(self):
        """Cancel the order"""
        if self.status in ['Pending', 'Confirmed', 'Ready']:
            self.status = 'Cancelled'
            self.save(update_fields=['status'])
            return True
        return False


# --------------------------- ORDERED PRODUCT MODEL (Order Line Items) ---------------------------
class OrderedProduct(models.Model):
    """
    Line items for customer orders.
    ERD: orderedProductID, batchID, quantity
    Enhanced with medicine reference and pricing info.
    """
    ordered_product_id = models.AutoField(primary_key=True)
    ordering = models.ForeignKey(
        Ordering,
        on_delete=models.CASCADE,
        related_name='ordered_products',
        help_text="Parent order"
    )
    medicine = models.ForeignKey(
        Medicine,
        on_delete=models.PROTECT,
        related_name='ordered_items',
        help_text="Product being ordered"
    )
    batch = models.ForeignKey(
        StockBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ordered_items',
        help_text="Specific batch if reserved (optional)"
    )
    
    UNIT_CHOICES = [
        ('piece', 'Piece'),
        ('pack', 'Pack'),
        ('box', 'Box'),
    ]
    unit_type = models.CharField(
        max_length=10,
        choices=UNIT_CHOICES,
        default='piece',
        help_text="Unit type for ordering"
    )
    quantity = models.PositiveIntegerField(
        help_text="Quantity in selected unit type"
    )
    pieces_needed = models.PositiveIntegerField(
        default=0,
        help_text="Total pieces needed (calculated from quantity and unit_type)"
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Price per piece at time of order"
    )
    line_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Total for this line item"
    )
    
    class Meta:
        ordering = ['ordered_product_id']
        verbose_name = "Ordered Product"
        verbose_name_plural = "Ordered Products"
    
    def __str__(self):
        return f"Order #{self.ordering.ordering_id} - {self.medicine.name} ({self.quantity} {self.unit_type})"
    
    def save(self, *args, **kwargs):
        """Auto-calculate pieces_needed and line_total"""
        from decimal import Decimal
        
        # Convert quantity to pieces
        if self.unit_type == 'piece':
            self.pieces_needed = self.quantity
        elif self.unit_type == 'pack':
            self.pieces_needed = self.quantity * (self.medicine.units_per_pack or 1)
        elif self.unit_type == 'box':
            packs_per_box = self.medicine.packs_per_box or 1
            units_per_pack = self.medicine.units_per_pack or 1
            self.pieces_needed = self.quantity * packs_per_box * units_per_pack
        
        # Calculate line total
        self.line_total = Decimal(str(self.pieces_needed)) * Decimal(str(self.unit_price))
        
        super().save(*args, **kwargs)


# --------------------------- DEFAULT CATEGORIES SIGNAL ---------------------------
def create_default_categories(sender, **kwargs):
    Category = apps.get_model('base', 'Category')
    default_categories = [
        "Prescription Medicine",
        "Over the Counter Medicine",
        "Vitamins And Supplements",
        "Home Remedies",
        "Beauty And Personal Care",
        "Medical Supplies",
        "Babies/Kids",
    ]
    for cat in default_categories:
        Category.objects.get_or_create(name=cat)
post_migrate.connect(create_default_categories)

# --------------------------- DEFAULT ROLES SIGNAL ---------------------------
def create_default_roles(sender, **kwargs):
    """Create default Manager and Staff roles on first migrate"""
    # Only run if we're migrating the 'base' app
    if sender.name != 'base':
        return
    
    # Check if the table exists before trying to query it
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.tables 
            WHERE table_schema = DATABASE()
            AND table_name = 'base_role'
        """)
        table_exists = cursor.fetchone()[0] > 0
    
    if not table_exists:
        return
    
    Role = apps.get_model('base', 'Role')
    default_roles = [
        {
            'role_name': 'Manager',
            'description': 'Full system access including user management, reports, price changes, and all operations'
        },
        {
            'role_name': 'Staff',
            'description': 'Standard pharmacy staff with access to sales, dispensing, and inventory viewing'
        },
    ]
    for role_data in default_roles:
        Role.objects.get_or_create(
            role_name=role_data['role_name'],
            defaults={'description': role_data['description']}
        )
post_migrate.connect(create_default_roles)

# Post-migrate signal to create default discount types
def create_default_discount_types(sender, **kwargs):
    """Create default discount types on first migrate"""
    if sender.name != 'base':
        return
    
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.tables 
            WHERE table_schema = DATABASE()
            AND table_name = 'base_discounttype'
        """)
        table_exists = cursor.fetchone()[0] > 0
    
    if not table_exists:
        return
    
    DiscountType = apps.get_model('base', 'DiscountType')
    default_discounts = [
        {
            'discount_name': 'Person with Disability (PWD)',
            'discount_rate': 20,
            'description': '20% discount for PWD cardholders (RA 7277)',
            'requires_id': True
        },
        {
            'discount_name': 'Senior Citizen',
            'discount_rate': 20,
            'description': '20% discount for senior citizens 60+ (RA 9994)',
            'requires_id': True
        },
    ]
    for discount_data in default_discounts:
        DiscountType.objects.get_or_create(
            discount_name=discount_data['discount_name'],
            defaults={
                'discount_rate': discount_data['discount_rate'],
                'description': discount_data['description'],
                'requires_id': discount_data['requires_id']
            }
        )
post_migrate.connect(create_default_discount_types)

# Post-migrate signal to create default payment methods
def create_default_payment_methods(sender, **kwargs):
    """Create default payment methods on first migrate"""
    if sender.name != 'base':
        return
    
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.tables 
            WHERE table_schema = DATABASE()
            AND table_name = 'base_paymentmethod'
        """)
        table_exists = cursor.fetchone()[0] > 0
    
    if not table_exists:
        return
    
    PaymentMethod = apps.get_model('base', 'PaymentMethod')
    default_methods = [
        {
            'method_name': 'Cash',
            'description': 'Cash payment',
            'requires_reference': False
        },
        {
            'method_name': 'Credit Card',
            'description': 'Credit/Debit card payment',
            'requires_reference': True
        },
        {
            'method_name': 'GCash',
            'description': 'GCash e-wallet payment',
            'requires_reference': True
        },
        {
            'method_name': 'PayMaya',
            'description': 'PayMaya e-wallet payment',
            'requires_reference': True
        },
        {
            'method_name': 'Bank Transfer',
            'description': 'Online bank transfer',
            'requires_reference': True
        },
    ]
    for method_data in default_methods:
        PaymentMethod.objects.get_or_create(
            method_name=method_data['method_name'],
            defaults={
                'description': method_data['description'],
                'requires_reference': method_data['requires_reference']
            }
        )
post_migrate.connect(create_default_payment_methods)

# --------------------------- STOCK MOVEMENT HELPERS ---------------------------
def log_stock_movement(batch, reason, quantity, remarks=None, to_location=None):
    StockMovement.objects.create(
        batch=batch,
        medicine=batch.medicine,
        quantity=quantity,
        movement_date=timezone.now(),
        movement_time=timezone.now().time(),
        reason=reason,
        from_location=batch.location,
        to_location=to_location,
        remarks=remarks or f"Automated stock-out for {reason}",
    )

def mark_as_expired(self):
    if self.quantity > 0:
        qty = self.quantity
        self.quantity = 0
        self.save()
        from base.models import log_stock_movement
        log_stock_movement(self, "expired", qty, remarks="Expired batch removed from inventory.")
        self.delete()
StockBatch.mark_as_expired = mark_as_expired

def mark_as_damaged(self, damaged_qty_pieces=None):
    # damaged_qty_pieces is in pieces
    if damaged_qty_pieces is None:
        damaged_qty_pieces = self.total_pieces
    if damaged_qty_pieces <= 0:
        return
    total = self.total_pieces
    removed = min(total, damaged_qty_pieces)
    remaining = total - removed
    ppb = self.pieces_per_box
    self.quantity = remaining // ppb
    self.loose_pieces = remaining % ppb
    self.save()
    log_stock_movement(self, "damaged", removed, remarks="Damaged stock removed from inventory.")
    if self.total_pieces <= 0:
        self.delete()
StockBatch.mark_as_damaged = mark_as_damaged

def return_stock(self, returned_qty_pieces=None):
    # returned_qty_pieces is in pieces
    if returned_qty_pieces is None:
        returned_qty_pieces = self.total_pieces
    if returned_qty_pieces <= 0:
        return
    total = self.total_pieces
    removed = min(total, returned_qty_pieces)
    remaining = total - removed
    ppb = self.pieces_per_box
    self.quantity = remaining // ppb
    self.loose_pieces = remaining % ppb
    self.save()
    log_stock_movement(self, "returned", removed, remarks="Stock returned to supplier.")
    if self.total_pieces <= 0:
        self.delete()
StockBatch.return_stock = return_stock

def transfer_stock(self, to_location, transfer_qty_pieces=None):
    # transfer_qty_pieces is in pieces
    if transfer_qty_pieces is None:
        transfer_qty_pieces = self.total_pieces
    if transfer_qty_pieces <= 0:
        return
    total = self.total_pieces
    moved = min(total, transfer_qty_pieces)
    remaining = total - moved
    ppb = self.pieces_per_box
    self.quantity = remaining // ppb
    self.loose_pieces = remaining % ppb
    self.save()
    log_stock_movement(self, "transfer", moved, remarks=f"Transferred to {to_location}.", to_location=to_location)
    if self.total_pieces <= 0:
        self.delete()
StockBatch.transfer_stock = transfer_stock

def adjust_stock(self, adjustment_qty_pieces, reason="adjustment", remarks=None):
    # adjustment_qty_pieces can be positive (add) or negative (remove), in pieces
    if adjustment_qty_pieces == 0:
        return
    total = self.total_pieces
    new_total = total + adjustment_qty_pieces
    if new_total < 0:
        adjustment_qty_pieces = -total
        new_total = 0
    ppb = self.pieces_per_box
    self.quantity = new_total // ppb
    self.loose_pieces = new_total % ppb
    self.save()
    log_stock_movement(self, reason, abs(adjustment_qty_pieces), remarks or f"Manual adjustment ({reason}).")
    if self.total_pieces <= 0:
        self.delete()
StockBatch.adjust_stock = adjust_stock

def process_all_expired_batches():
    today = timezone.now().date()
    expired_batches = StockBatch.objects.filter(expiry_date__lte=today)
    for batch in expired_batches:
        if batch.quantity > 0:
            batch.mark_as_expired()


# ========================================
# SUPPLIER & PURCHASE ORDER MODELS  
# ========================================

class Supplier(models.Model):
    """Suppliers for purchasing medicines"""
    STATUS_CHOICES = [('Active', 'Active'), ('Inactive', 'Inactive')]
    is_deleted = models.BooleanField(default=False)
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=200, blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    email = models.CharField(max_length=200, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.name
    class Meta: ordering = ['name']

class PurchaseOrder(models.Model):
    """Purchase orders for ordering stock from suppliers."""
    STATUS_CHOICES = [('Draft', 'Draft'), ('Ordered', 'Ordered'), ('In Delivery', 'In Delivery'), ('Received', 'Received'), ('Cancelled', 'Cancelled')]
    is_deleted = models.BooleanField(default=False)
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='purchase_orders')
    po_date = models.DateField(default=now)
    expected_delivery_date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_purchase_orders')
    class Meta: ordering = ['-created_at']
    def __str__(self): return f"PO #{self.id} - {self.supplier.name} ({self.status})"
    def total_cost(self): return sum(line.line_total() for line in self.lines.all())

class PurchaseOrderLine(models.Model):
    """Individual line items in a purchase order"""
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='lines')
    medicine = models.ForeignKey(Medicine, on_delete=models.CASCADE, related_name='purchase_order_lines')
    quantity_ordered = models.PositiveIntegerField(help_text="Quantity ordered")
    quantity_received = models.PositiveIntegerField(default=0, help_text="Quantity received into stock")
    unit = models.CharField(max_length=50, default='box', help_text="Unit type: box, pack, piece")
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, help_text="Cost per unit")
    manufactured_date = models.DateField(blank=True, null=True, help_text="Manufacturing date of the medicine")
    expiration_date = models.DateField(blank=True, null=True, help_text="Expiration date of the medicine")
    remarks = models.TextField(blank=True, null=True)
    def line_total(self): return self.quantity_ordered * self.unit_cost
    def is_fully_received(self): return self.quantity_received >= self.quantity_ordered
    def __str__(self): return f"{self.medicine.name} - {self.quantity_ordered} {self.unit}"
