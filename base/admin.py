from django.contrib import admin
from django import forms
from .models import (
    Task, ActivityLog, Category, Medicine, StockBatch, PriceHistory, ProductType,
    Role, Employee, EmployeeDesignation, DiscountType, PaymentMethod, Refund, Sale, SaleLineItem,
    Ordering, OrderedProduct, Notification
)

# ---------------------------
# TASK ADMIN
# ---------------------------
@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "complete", "created", "is_deleted")
    list_filter = ("complete", "is_deleted")
    search_fields = ("title", "description", "user__username")

# ---------------------------
# ACTIVITY LOG ADMIN
# ---------------------------
@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("user", "action", "timestamp")
    list_filter = ("timestamp",)
    search_fields = ("user__username", "action")

# ---------------------------
# CATEGORY ADMIN
# ---------------------------
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "is_deleted")
    list_filter = ("is_deleted",)
    search_fields = ("name",)

# ---------------------------
# PRODUCT TYPE ADMIN
# ---------------------------
@admin.register(ProductType)
class ProductTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "is_deleted")
    list_filter = ("category", "is_deleted")
    search_fields = ("name", "category__name")
    ordering = ("category__name", "name")

# ---------------------------
# MEDICINE ADMIN
# ---------------------------

class MedicineForm(forms.ModelForm):
    class Meta:
        model = Medicine
        # Exclude legacy field; stock is managed via StockBatch
        exclude = ("box_quantity",)

    class Media:
        js = ("js/medicine_unit_logic.js",)

@admin.register(Medicine)
class MedicineAdmin(admin.ModelAdmin):
    form = MedicineForm

    list_display = (
        "name",
        "brand",
        "category",
        "product_type",
        "dosage_form",
        "strength",
        "units_per_pack",
        "packs_per_box",
        "stock_boxes",
        "stock_packs",
        "stock_pieces",
        "base_price",
        "selling_price",
        "is_deleted",
    )

    list_filter = ("category", "product_type", "dosage_form", "is_deleted")
    search_fields = ("name", "brand", "description")

    # No legacy computed fields; stock shown via batch aggregates above
    readonly_fields = ()

    # Batch-aggregated stock display
    def stock_boxes(self, obj):
        from django.db.models import Sum
        total_boxes = obj.batches.filter(is_deleted=False, is_recalled=False).aggregate(Sum("quantity"))['quantity__sum'] or 0
        return total_boxes

    def stock_packs(self, obj):
        boxes = self.stock_boxes(obj)
        packs_per_box = obj.packs_per_box or 1
        return boxes * packs_per_box

    def stock_pieces(self, obj):
        boxes = self.stock_boxes(obj)
        packs_per_box = obj.packs_per_box or 1
        units_per_pack = obj.units_per_pack or 1
        return boxes * packs_per_box * units_per_pack

    stock_boxes.short_description = "Boxes (batches)"
    stock_packs.short_description = "Packs"
    stock_pieces.short_description = "Pieces"

# ---------------------------
# STOCK BATCH ADMIN
# ---------------------------
@admin.register(StockBatch)
class StockBatchAdmin(admin.ModelAdmin):
    list_display = (
        "medicine",
        "get_unit",
        "quantity",
        "location",
        "date_received",
        "expiry_date",
        "is_deleted",
    )
    list_filter = ("location", "is_deleted")
    search_fields = ("medicine__name", "medicine__brand")

    def get_unit(self, obj):
        """Show the medicine's unit in admin list."""
        # Just display "piece" as the smallest selling unit
        return "piece"

    get_unit.short_description = "Unit"

# ---------------------------
# PRICE HISTORY ADMIN
# ---------------------------
@admin.register(PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    list_display = ("medicine", "old_selling_price", "new_selling_price", "changed_by", "change_date")
    list_filter = ("change_date", "changed_by")
    search_fields = ("medicine__name", "reason")
    readonly_fields = ("medicine", "old_base_price", "new_base_price", "old_selling_price", "new_selling_price", "changed_by", "change_date")
    
    def has_add_permission(self, request):
        # Prevent manual addition - price history should be created automatically
        return False
    
    def has_delete_permission(self, request, obj=None):
        # Allow deletion only for superusers
        return request.user.is_superuser

# ---------------------------
# ROLE ADMIN
# ---------------------------
@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("role_name", "description", "created_at")
    search_fields = ("role_name", "description")
    readonly_fields = ("created_at",)
    ordering = ("role_name",)

# ---------------------------
# EMPLOYEE ADMIN
# ---------------------------
@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("employee_number", "full_name", "user", "hire_date", "is_deleted")
    list_filter = ("hire_date", "is_deleted")
    search_fields = ("employee_number", "first_name", "last_name", "user__username")
    readonly_fields = ("employee_number",)
    ordering = ("employee_number",)
    
    fieldsets = (
        ("Employee Information", {
            "fields": ("employee_number", "first_name", "last_name", "contact_number", "address", "hire_date")
        }),
        ("User Account", {
            "fields": ("user",)
        }),
        ("Status", {
            "fields": ("is_deleted",)
        }),
    )

# ---------------------------
# EMPLOYEE DESIGNATION ADMIN
# ---------------------------
class EmployeeDesignationInline(admin.TabularInline):
    model = EmployeeDesignation
    extra = 1
    fields = ("role", "assigned_date", "is_primary")

@admin.register(EmployeeDesignation)
class EmployeeDesignationAdmin(admin.ModelAdmin):
    list_display = ("employee", "role", "assigned_date", "is_primary")
    list_filter = ("role", "is_primary", "assigned_date")
    search_fields = ("employee__first_name", "employee__last_name", "role__role_name")
    ordering = ("-assigned_date",)

# ---------------------------
# DISCOUNT TYPE ADMIN
# ---------------------------
@admin.register(DiscountType)
class DiscountTypeAdmin(admin.ModelAdmin):
    list_display = ("discount_name", "discount_rate", "is_active", "requires_id", "created_at")
    list_filter = ("is_active", "requires_id")
    search_fields = ("discount_name", "description")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("discount_name",)
    
    fieldsets = (
        ("Discount Information", {
            "fields": ("discount_name", "discount_rate", "description")
        }),
        ("Settings", {
            "fields": ("is_active", "requires_id")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )

# ---------------------------
# PAYMENT METHOD ADMIN
# ---------------------------
@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ("method_name", "is_active", "requires_reference", "created_at")
    list_filter = ("is_active", "requires_reference")
    search_fields = ("method_name", "description")
    readonly_fields = ("created_at",)
    ordering = ("method_name",)
    
    fieldsets = (
        ("Payment Method Information", {
            "fields": ("method_name", "description")
        }),
        ("Settings", {
            "fields": ("is_active", "requires_reference")
        }),
        ("Timestamp", {
            "fields": ("created_at",),
            "classes": ("collapse",)
        }),
    )

# ---------------------------
# SALE ADMIN WITH LINE ITEMS INLINE
# ---------------------------
class SaleLineItemInline(admin.TabularInline):
    model = SaleLineItem
    extra = 0
    readonly_fields = ('line_item_id', 'medicine', 'quantity', 'unit_type', 'unit_price', 'pieces_dispensed', 'line_total')
    can_delete = False
    max_num = 0  # Prevent adding new items via admin

@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = (
        'invoice_number', 'sale_id', 'sale_date', 'user',
        'discount_type_fk', 'discount_rate', 'final_amount',
        'payment_method', 'cash_received', 'change_amount'
    )
    list_filter = ('sale_date', 'payment_method', 'discount_type_fk')
    search_fields = ('invoice_number', 'sale_id', 'user__username')
    readonly_fields = ('sale_id', 'sale_date', 'discount_rate', 'discount_amount', 'final_amount', 'change_amount', 'total_amount')
    ordering = ('-sale_date',)
    inlines = [SaleLineItemInline]
    
    fieldsets = (
        ('Identifiers', {'fields': ('invoice_number', 'sale_id')}),
        ('User & Timing', {'fields': ('user', 'sale_date')}),
        ('Amounts', {'fields': ('total_amount', 'discount_type_fk', 'discount_rate', 'discount_amount', 'final_amount')}),
        ('Payment', {'fields': ('payment_method', 'cash_received', 'change_amount')}),
    )

# ---------------------------
# SALE LINE ITEM ADMIN
# ---------------------------
@admin.register(SaleLineItem)
class SaleLineItemAdmin(admin.ModelAdmin):
    list_display = ('line_item_id', 'sale', 'medicine', 'quantity', 'unit_type', 'pieces_dispensed', 'unit_price', 'line_total')
    list_filter = ('unit_type', 'sale__sale_date')
    search_fields = ('medicine__name', 'sale__invoice_number')
    readonly_fields = ('line_item_id', 'pieces_dispensed', 'line_total')
    ordering = ('-sale__sale_date', 'line_item_id')

# ---------------------------
# REFUND ADMIN
# ---------------------------
@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ("refund_id", "sale", "refund_date", "amount_refunded", "reason", "processed_by", "approved_by")
    list_filter = ("reason", "refund_date", "payment_method")
    search_fields = ("sale__sale_id", "reason_details", "reference_number", "processed_by__username", "approved_by__username")
    readonly_fields = ("refund_date",)
    ordering = ("-refund_date",)
    
    fieldsets = (
        ("Refund Information", {
            "fields": ("sale", "refund_date", "amount_refunded")
        }),
        ("Reason Details", {
            "fields": ("reason", "reason_details")
        }),
        ("Processing Information", {
            "fields": ("processed_by", "approved_by")
        }),
        ("Payment Details", {
            "fields": ("payment_method", "reference_number")
        }),
    )


# ---------------------------
# ORDERING ADMIN (Customer Orders)
# ---------------------------
class OrderedProductInline(admin.TabularInline):
    model = OrderedProduct
    extra = 0
    fields = ("medicine", "quantity", "unit_type", "unit_price", "pieces_needed", "line_total", "batch")
    readonly_fields = ("pieces_needed", "line_total")

@admin.register(Ordering)
class OrderingAdmin(admin.ModelAdmin):
    list_display = ("ordering_id", "customer_name", "order_date", "status", "user", "get_total_display")
    list_filter = ("status", "order_date")
    search_fields = ("customer_name", "customer_contact", "ordering_id")
    readonly_fields = ("order_date", "confirmed_date", "completed_date")
    ordering = ("-order_date",)
    inlines = [OrderedProductInline]
    
    fieldsets = (
        ("Customer Information", {
            "fields": ("customer_name", "customer_contact", "expected_pickup_date", "notes")
        }),
        ("Order Status", {
            "fields": ("status", "order_date", "user")
        }),
        ("Tracking", {
            "fields": ("confirmed_by", "confirmed_date", "completed_date", "sale")
        }),
    )
    
    def get_total_display(self, obj):
        return f"₱{obj.get_total_amount():.2f}"
    get_total_display.short_description = "Total Amount"

@admin.register(OrderedProduct)
class OrderedProductAdmin(admin.ModelAdmin):
    list_display = ("ordered_product_id", "ordering", "medicine", "quantity", "unit_type", "unit_price", "line_total")
    list_filter = ("unit_type", "ordering__status")
    search_fields = ("medicine__name", "ordering__customer_name", "ordering__ordering_id")
    readonly_fields = ("pieces_needed", "line_total")
    ordering = ("-ordering__order_date",)

# ---------------------------
# NOTIFICATION ADMIN
# ---------------------------
@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("notification_id", "user", "notification_type", "title", "is_read", "created_at")
    list_filter = ("notification_type", "is_read", "created_at")
    search_fields = ("title", "message", "user__username", "related_medicine__name")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)
