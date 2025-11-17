from django import forms
from django.utils import timezone
from base.models import Sale, PaymentMethod, Refund, StockMovement, Ordering, OrderedProduct, SaleLineItem
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import FormView, ListView, DetailView, View, CreateView
from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404
from django.db.models import Q

class RefundCreateForm(forms.Form):
    # Only allow sales that have no existing refunds
    sale = forms.ModelChoiceField(
        queryset=Sale.objects.filter(refunds__isnull=True).order_by('-sale_id'),
        label="Sale",
        help_text="Select sale to refund (unrefunded only)"
    )
    reason = forms.ChoiceField(choices=[
        ('expired', 'Expired Product'),
        ('damaged', 'Damaged Product'),
        ('wrong_item', 'Wrong Item Sold'),
        ('customer_request', 'Customer Request'),
        ('overcharge', 'Overcharge/Pricing Error'),
        ('other', 'Other Reason'),
    ], label="Reason")
    reason_details = forms.CharField(
        widget=forms.Textarea(attrs={'placeholder': 'Explain the situation...', 'rows': 3}),
        required=False,
        label="Details"
    )
    payment_method = forms.ModelChoiceField(
        queryset=PaymentMethod.objects.filter(is_active=True),
        required=False,
        label="Refund Method"
    )
    reference_number = forms.CharField(
        max_length=100,
        required=False,
        label="Reference Number",
        widget=forms.TextInput(attrs={'placeholder': 'Optional for cash'})
    )
    confirm_full_refund = forms.BooleanField(required=True, label="Confirm full refund of sale amount")

class RefundCreateView(LoginRequiredMixin, FormView):
    template_name = 'sales/refund_form.html'
    form_class = RefundCreateForm
    success_url = reverse_lazy('refund-list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['is_manager_or_admin'] = is_manager_or_admin(self.request.user)
        ctx['user_role'] = get_user_role_display(self.request.user)
        return ctx

    def form_valid(self, form):
        sale = form.cleaned_data['sale']
        # Guard against race condition or stale queryset allowing duplicate refund
        if Refund.objects.filter(sale=sale).exists():
            form.add_error('sale', 'This sale already has a refund.')
            return self.form_invalid(form)
        reason = form.cleaned_data['reason']
        reason_details = form.cleaned_data.get('reason_details')
        payment_method = form.cleaned_data.get('payment_method') or sale.payment_method
        reference_number = form.cleaned_data.get('reference_number')

        amount = sale.final_amount
        if amount <= 0:
            form.add_error(None, 'Sale has zero amount; cannot refund.')
            return self.form_invalid(form)

        # Inventory reversal: add quantities back to original batches
        movements = sale.movements.select_related('batch', 'medicine').all()
        restored_total = 0
        for m in movements:
            if m.batch and m.quantity > 0:
                m.batch.quantity += m.quantity
                m.batch.save()
                restored_total += m.quantity
                # Log stock movement reversal
                StockMovement.objects.create(
                    medicine=m.medicine,
                    batch=m.batch,
                    from_location='',
                    to_location=m.batch.location,
                    quantity=m.quantity,
                    reason='returned',
                    remarks=f'Refund reversal of Sale #{sale.sale_id}',
                    user=self.request.user
                )

        # All new refunds start as Pending; require explicit approval
        status = 'Pending'
        refund = Refund.objects.create(
            sale=sale,
            amount_refunded=amount,
            reason=reason,
            reason_details=reason_details,
            processed_by=self.request.user,
            payment_method=payment_method,
            reference_number=reference_number,
            status=status,
            approved_by=None,
            approved_date=None
        )

        log_activity(self.request.user, f"Processed refund #{refund.refund_id} for Sale #{sale.sale_id} amount ₱{amount}")
        messages.success(self.request, f"Refund submitted and marked Pending. Restored {restored_total} units to inventory.")

        # AJAX response
        if self.request.headers.get('x-requested-with') == 'XMLHttpRequest' or self.request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'refund_id': refund.refund_id,
                'status': refund.status,
                'message': f"Refund processed. Restored {restored_total} units to inventory.",
            })
        return super().form_valid(form)

    def form_invalid(self, form):
        if self.request.headers.get('x-requested-with') == 'XMLHttpRequest' or self.request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'errors': form.errors}, status=400)
        return super().form_invalid(form)

class RefundListView(LoginRequiredMixin, ListView):
    model = Refund
    template_name = 'sales/refund_list.html'
    context_object_name = 'refunds'
    ordering = ['-refund_date']

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['total_refunds'] = self.get_queryset().count()
        ctx['pending_count'] = self.get_queryset().filter(status='Pending').count()
        ctx['approved_count'] = self.get_queryset().filter(status='Approved').count()
        # Add recent sales and payment methods for the modal
        ctx['recent_sales'] = Sale.objects.order_by('-sale_id')[:50]
        ctx['payment_methods'] = PaymentMethod.objects.filter(is_active=True)
        ctx['refund_form'] = RefundCreateForm()
        ctx['is_manager_or_admin'] = is_manager_or_admin(self.request.user)
        ctx['user_role'] = get_user_role_display(self.request.user)
        return ctx

class RefundDetailView(LoginRequiredMixin, DetailView):
    model = Refund
    template_name = 'sales/refund_detail.html'
    context_object_name = 'refund'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['user'] = self.request.user
        ctx['is_manager_or_admin'] = is_manager_or_admin(self.request.user)
        ctx['user_role'] = get_user_role_display(self.request.user)
        return ctx

def refund_detail_modal(request, pk):
    refund = get_object_or_404(Refund, pk=pk)
    ctx = {
        'refund': refund,
        'is_manager_or_admin': is_manager_or_admin(request.user),
    }
    html = render_to_string('sales/partials/refund_detail_modal.html', ctx, request=request)
    return JsonResponse({'success': True, 'html': html})

class RefundApproveView(LoginRequiredMixin, View):
    def post(self, request, pk):
        refund = get_object_or_404(Refund, pk=pk, status='Pending')
        if not is_manager_or_admin(request.user):
            # AJAX or standard form: return JSON if XHR
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': 'Not authorized'}, status=403)
            messages.error(request, 'Not authorized to approve refunds.')
            return redirect('refund-detail', pk=refund.pk)
        refund.status = 'Approved'
        refund.approved_by = request.user
        refund.approved_date = timezone.now()
        refund.save(update_fields=['status', 'approved_by', 'approved_date'])
        log_activity(request.user, f"Approved refund #{refund.refund_id}")
        messages.success(request, f"Refund #{refund.refund_id} approved.")
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'refund_id': refund.refund_id, 'status': 'Approved'})
        return redirect('refund-detail', pk=refund.pk)
from django import forms
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import (TemplateView, ListView, DetailView,CreateView, UpdateView, DeleteView, FormView)
from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from base.models import Task, ActivityLog, Medicine, StockBatch, StockMovement, Sale, Employee, Role, DiscountType, PaymentMethod, Refund, Ordering, OrderedProduct, SaleLineItem, Notification
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.timezone import now
from .models import process_all_expired_batches
from django.forms import formset_factory
from django.db import transaction

# --------------------------- HELPER FUNCTIONS ---------------------------
def is_manager_or_admin(user):
    """
    Check if user is a manager or admin using the new Role system.
    Falls back to Django's is_superuser/groups if Employee profile doesn't exist.
    """
    if user.is_superuser:
        return True
    
    # Check new Role system via Employee
    try:
        employee = user.employee_profile
        return employee.has_role('Manager')
    except Employee.DoesNotExist:
        # Fallback to old Django Groups system during migration
        return user.groups.filter(name='Manager').exists()

def get_user_role_display(user):
    """Get user's primary role name for display"""
    try:
        employee = user.employee_profile
        primary_role = employee.get_primary_role()
        return primary_role.role_name if primary_role else 'Staff'
    except Employee.DoesNotExist:
        if user.is_superuser:
            return 'Manager'
        return 'Staff'

# --------------------------- NOTIFICATION HELPERS ---------------------------
def generate_notifications():
    """Generate notifications for near-expiry and low stock items"""
    from datetime import timedelta
    from django.db.models import Sum
    from django.contrib.auth.models import User
    
    # Get all manager/admin users to notify
    manager_users = User.objects.filter(
        Q(employee_profile__designations__role__role_name='Manager') | Q(is_superuser=True)
    ).distinct()
    
    # Check for near-expiry items (within 30 days)
    thirty_days = timezone.now().date() + timedelta(days=30)
    expiring_batches = StockBatch.objects.filter(
        is_deleted=False,
        quantity__gt=0,
        expiration_date__lte=thirty_days,
        expiration_date__gte=timezone.now().date()
    )
    
    for batch in expiring_batches:
        days_until_expiry = (batch.expiration_date - timezone.now().date()).days
        # Check if notification already exists
        existing = Notification.objects.filter(
            notification_type='expiry',
            related_batch=batch,
            is_read=False
        ).exists()
        
        if not existing:
            for user in manager_users:
                Notification.objects.create(
                    user=user,
                    notification_type='expiry',
                    title=f'Near Expiry Alert: {batch.medicine.name}',
                    message=f'Batch #{batch.batch_id} of {batch.medicine.name} will expire in {days_until_expiry} days (on {batch.expiration_date.strftime("%Y-%m-%d")}). Current stock: {batch.quantity} {batch.medicine.unit}',
                    related_medicine=batch.medicine,
                    related_batch=batch
                )
    
    # Check for low stock items (below 20 pieces or less than 7 days of stock)
    from django.db.models import F
    medicines = Medicine.objects.filter(is_deleted=False).annotate(
        total_stock=Sum('batches__quantity', filter=Q(batches__is_deleted=False))
    )
    
    # Calculate daily sales rate
    thirty_days_ago = timezone.now() - timedelta(days=30)
    for medicine in medicines:
        if medicine.total_stock is not None:
            # Get sales in last 30 days
            sales_last_30 = SaleLineItem.objects.filter(
                medicine=medicine,
                sale__sale_date__gte=thirty_days_ago
            ).aggregate(total=Sum('pieces_dispensed'))['total'] or 0
            
            daily_sales = sales_last_30 / 30 if sales_last_30 > 0 else 0
            days_of_stock = medicine.total_stock / daily_sales if daily_sales > 0 else 999
            
            # Low stock: less than 7 days OR less than 20 pieces
            if (days_of_stock < 7 and daily_sales > 0) or medicine.total_stock < 20:
                # Check if notification already exists
                existing = Notification.objects.filter(
                    notification_type='low_stock',
                    related_medicine=medicine,
                    is_read=False
                ).exists()
                
                if not existing:
                    for user in manager_users:
                        if days_of_stock < 7 and daily_sales > 0:
                            message = f'{medicine.name} has only {days_of_stock:.1f} days of stock remaining ({medicine.total_stock} {medicine.unit}). Average daily sales: {daily_sales:.1f}. Please reorder soon.'
                        else:
                            message = f'{medicine.name} is low in stock ({medicine.total_stock} {medicine.unit}). Please reorder soon.'
                        
                        Notification.objects.create(
                            user=user,
                            notification_type='low_stock',
                            title=f'Low Stock Alert: {medicine.name}',
                            message=message,
                            related_medicine=medicine
                        )
        elif medicine.total_stock == 0 or medicine.total_stock is None:
            # Out of stock
            existing = Notification.objects.filter(
                notification_type='out_of_stock',
                related_medicine=medicine,
                is_read=False
            ).exists()
            
            if not existing:
                for user in manager_users:
                    Notification.objects.create(
                        user=user,
                        notification_type='out_of_stock',
                        title=f'Out of Stock: {medicine.name}',
                        message=f'{medicine.name} is currently out of stock. Please reorder immediately.',
                        related_medicine=medicine
                    )

# --------------------------- DASHBOARD ---------------------------
class DashboardView(LoginRequiredMixin, ListView):
    model = Task
    context_object_name = 'dashboard'
    template_name = 'dashboard/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['dashboard'] = context['dashboard'].filter(user=self.request.user)
        context['count'] = context['dashboard'].filter(complete=False).count()
        search_input = self.request.GET.get('search-area') or ''

        if search_input:
            context['dashboard'] = context['dashboard'].filter(title__icontains=search_input)
        context['search_input'] = search_input
        try:
            latest_sale = Sale.objects.latest("sale_id")
            # latest_sale = Sale.objects.latest("id")
        except Sale.DoesNotExist:
            latest_sale = None
        context["sale"] = latest_sale
        user = self.request.user
        context["is_manager_or_admin"] = is_manager_or_admin(user)
        context["user_role"] = get_user_role_display(user)
        
        # Generate notifications for managers
        if is_manager_or_admin(user):
            try:
                generate_notifications()
            except Exception as e:
                print(f"Error generating notifications: {e}")
        
        # Get unread notification count
        context['unread_notifications'] = Notification.objects.filter(
            user=user,
            is_read=False
        ).count()
        
        # Stock Analysis - available to all users
        context['stock_analysis'] = self.get_stock_analysis()
        
        return context
    
    def get_stock_analysis(self):
        """Calculate stock analysis metrics."""
        from django.db.models import Sum, Count, F, Q
        from datetime import timedelta
        from django.utils.timezone import now
        
        # Calculate sales velocity (last 30 days)
        thirty_days_ago = now() - timedelta(days=30)
        
        # Fast Selling: Top medicines by sales volume in last 30 days
        fast_selling = (
            SaleLineItem.objects
            .filter(sale__sale_date__gte=thirty_days_ago)
            .values('medicine__name', 'medicine__id')
            .annotate(
                total_sold=Sum('pieces_dispensed'),
                total_sales=Count('line_item_id')
            )
            .order_by('-total_sold')[:5]
        )
        
        # Slow Selling: Medicines with low or no sales in last 30 days
        medicines_with_sales = (
            SaleLineItem.objects
            .filter(sale__sale_date__gte=thirty_days_ago)
            .values_list('medicine__id', flat=True)
            .distinct()
        )
        
        slow_selling = (
            Medicine.objects
            .filter(is_deleted=False)
            .exclude(id__in=medicines_with_sales)
            .annotate(
                current_stock=Sum('batches__quantity', filter=Q(batches__is_deleted=False))
            )
            .filter(current_stock__gt=0)
            .order_by('-current_stock')[:5]
        )
        
        # Overstock: Medicines with high inventory relative to sales
        overstock = []
        for medicine in Medicine.objects.filter(is_deleted=False).annotate(
            current_stock=Sum('batches__quantity', filter=Q(batches__is_deleted=False)),
            sales_last_30=Sum(
                'sale_lines__pieces_dispensed',
                filter=Q(sale_lines__sale__sale_date__gte=thirty_days_ago)
            )
        ):
            if medicine.current_stock and medicine.current_stock > 0:
                daily_sales = (medicine.sales_last_30 or 0) / 30
                if daily_sales > 0:
                    days_of_stock = medicine.current_stock / daily_sales
                    if days_of_stock > 90:  # More than 3 months of stock
                        overstock.append({
                            'name': medicine.name,
                            'id': medicine.id,
                            'current_stock': medicine.current_stock,
                            'days_of_stock': round(days_of_stock, 1)
                        })
        overstock = sorted(overstock, key=lambda x: x['days_of_stock'], reverse=True)[:5]
        
        # Understock: Medicines with low inventory relative to sales
        understock = []
        for medicine in Medicine.objects.filter(is_deleted=False).annotate(
            current_stock=Sum('batches__quantity', filter=Q(batches__is_deleted=False)),
            sales_last_30=Sum(
                'sale_lines__pieces_dispensed',
                filter=Q(sale_lines__sale__sale_date__gte=thirty_days_ago)
            )
        ):
            if medicine.sales_last_30 and medicine.sales_last_30 > 0:
                daily_sales = medicine.sales_last_30 / 30
                current = medicine.current_stock or 0
                days_of_stock = current / daily_sales if daily_sales > 0 else 999
                if days_of_stock < 7:  # Less than a week of stock
                    understock.append({
                        'name': medicine.name,
                        'id': medicine.id,
                        'current_stock': current,
                        'days_of_stock': round(days_of_stock, 1),
                        'daily_sales': round(daily_sales, 1)
                    })
        understock = sorted(understock, key=lambda x: x['days_of_stock'])[:5]
        
        return {
            'fast_selling': fast_selling,
            'slow_selling': slow_selling,
            'overstock': overstock,
            'understock': understock,
        }

# --------------------------- ACTIVITY LOG ---------------------------
class ActivityLogListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = ActivityLog
    template_name = "dashboard/activity_logs.html"
    context_object_name = "logs"
    paginate_by = 100

    def test_func(self):
        return is_manager_or_admin(self.request.user)
    
    def handle_no_permission(self):
        from django.shortcuts import render
        context = {
            'user_role': get_user_role_display(self.request.user),
            'is_manager_or_admin': False
        }
        return render(self.request, 'shared/access_denied.html', context, status=403)

    def get_queryset(self):
        queryset = ActivityLog.objects.select_related('user').all()
        
        # Filter by date range
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')
        if start_date:
            queryset = queryset.filter(timestamp__gte=start_date)
        if end_date:
            queryset = queryset.filter(timestamp__lte=end_date)
        
        # Filter by user
        user_id = self.request.GET.get('user')
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        # Filter by action type (keyword search)
        action_type = self.request.GET.get('action_type')
        if action_type:
            queryset = queryset.filter(action__icontains=action_type)
        
        return queryset.order_by('-timestamp')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['users'] = User.objects.filter(is_active=True).order_by('username')
        context['selected_user'] = self.request.GET.get('user', '')
        context['start_date'] = self.request.GET.get('start_date', '')
        context['end_date'] = self.request.GET.get('end_date', '')
        context['action_type'] = self.request.GET.get('action_type', '')
        user = self.request.user
        context["is_manager_or_admin"] = is_manager_or_admin(user)
        return context

def log_activity(user, action):
    ActivityLog.objects.create(user=user, action=action)

# Decorator to restrict access to manager/admin only
def manager_required(view_func):
    """Decorator to restrict access to managers and admins only"""
    from functools import wraps
    from django.shortcuts import render
    
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not is_manager_or_admin(request.user):
            context = {
                'user_role': get_user_role_display(request.user),
                'is_manager_or_admin': False
            }
            return render(request, 'shared/access_denied.html', context, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper

# --------------------------- USER LIST ---------------------------
class UserListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = User
    template_name = "registration/userlist.html"
    context_object_name = "users"    

    def test_func(self):
        return is_manager_or_admin(self.request.user)
    
    def handle_no_permission(self):
        from django.shortcuts import render
        context = {
            'user_role': get_user_role_display(self.request.user),
            'is_manager_or_admin': False
        }
        return render(self.request, 'shared/access_denied.html', context, status=403)

    def get_queryset(self):
        queryset = super().get_queryset()
        search_input = self.request.GET.get("search") or ""
        if search_input:
            queryset = queryset.filter(username__icontains=search_input)
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["is_manager_or_admin"] = is_manager_or_admin(user)
        return context

# --------------------------- CREATE USER (AJAX) ---------------------------
@login_required
def create_user_ajax(request):
    """Handle user creation via AJAX for modal"""
    if not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        is_staff = request.POST.get('is_staff') == 'on'
        is_superuser = request.POST.get('is_superuser') == 'on'
        
        # Validation
        if not username or not password:
            return JsonResponse({'success': False, 'error': 'Username and password are required'})
        
        if User.objects.filter(username=username).exists():
            return JsonResponse({'success': False, 'error': 'Username already exists'})
        
        try:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                is_staff=is_staff,
                is_superuser=is_superuser
            )
            
            # Log the activity
            role = "Manager" if is_superuser else "Staff" if is_staff else "User"
            ActivityLog.objects.create(
                user=request.user,
                action=f"Created new user account: {username} (Role: {role})"
            )
            
            messages.success(request, f"User '{username}' created successfully as {role}.")
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

# --------------------------- UPDATE USER ACCOUNT (AJAX) ---------------------------
@login_required
def update_user_account_ajax(request, user_id):
    """Handle user account update via AJAX for modal"""
    if not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    
    user = get_object_or_404(User, pk=user_id)
    
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        is_staff = request.POST.get('is_staff') == 'on'
        is_superuser = request.POST.get('is_superuser') == 'on'
        
        # Check if username already exists (excluding current user)
        if User.objects.filter(username=username).exclude(pk=user_id).exists():
            return JsonResponse({'success': False, 'error': 'Username already exists'})
        
        changes = []
        if user.username != username:
            changes.append(f"username from '{user.username}' to '{username}'")
            user.username = username
        if user.email != email:
            changes.append(f"email from '{user.email}' to '{email}'")
            user.email = email
        if user.is_staff != is_staff:
            changes.append(f"staff status to {'Yes' if is_staff else 'No'}")
            user.is_staff = is_staff
        if user.is_superuser != is_superuser:
            changes.append(f"manager status to {'Yes' if is_superuser else 'No'}")
            user.is_superuser = is_superuser
        
        user.save()
        
        if changes:
            ActivityLog.objects.create(
                user=request.user,
                action=f"Updated user account '{username}': {', '.join(changes)}"
            )
            messages.success(request, f"User '{username}' updated successfully.")
        
        return JsonResponse({'success': True})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

# --------------------------- UPDATE USER PASSWORD (AJAX) ---------------------------
@login_required
def update_user_password_ajax(request, user_id):
    """Handle user password update via AJAX for modal"""
    if not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    
    user = get_object_or_404(User, pk=user_id)
    
    if request.method == 'POST':
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        if not new_password:
            return JsonResponse({'success': False, 'error': 'Password is required'})
        
        if new_password != confirm_password:
            return JsonResponse({'success': False, 'error': 'Passwords do not match'})
        
        user.set_password(new_password)
        user.save()
        
        ActivityLog.objects.create(
            user=request.user,
            action=f"Changed password for user: {user.username}"
        )
        
        messages.success(request, f"Password updated for user '{user.username}'.")
        return JsonResponse({'success': True})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

# --------------------------- UPDATE ACCOUNT ---------------------------
class UpdateAccountView(LoginRequiredMixin,UpdateView):
    model = User
    fields = ['username', 'email'] #Editable fields when updating user info
    template_name = 'registration/updateaccount.html'
    success_url = reverse_lazy('dashboard')
    
    def get_object(self):
        return self.request.user

    def form_valid(self, form):
        user = self.get_object()
        changes = []

        if form.cleaned_data['username'] != user.username:
            changes.append(f"username from '{user.username}' to '{form.cleaned_data['username']}'")
        if form.cleaned_data['email'] != user.email:
            changes.append(f"email from '{user.email}' to '{form.cleaned_data['email']}'")

        response = super().form_valid(form)

        if changes:
            action_text = f"Updated account: {', '.join(changes)}"
        else:
            action_text = "Visited account update page but made no changes"

        ActivityLog.objects.create(user=self.request.user,action=action_text)
        return response

# --------------------------- UPDATE PASSWORD ---------------------------
class UpdatePasswordView(LoginRequiredMixin, PasswordChangeView):
    template_name = 'registration/updatepassword.html'
    success_url = reverse_lazy('dashboard')

    def form_valid(self, form):
        response = super().form_valid(form)
        update_session_auth_hash(self.request, form.user) # Keep the user logged in after password change

        ActivityLog.objects.create(user=self.request.user,action="Changed password")
        return response

# --------------------------- BLOCK / UNBLOCK USERS ---------------------------
class BlockUnblockUserView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        
        if user == request.user:
            messages.error(request, "You cannot block yourself.")
            return redirect("user-list")

        user.is_active = not user.is_active
        user.save()

        action = "unblocked" if user.is_active else "blocked"
        ActivityLog.objects.create(user=request.user,action=f"{action.capitalize()} account: {user.username}")

        messages.success(request, f"User {user.username} has been {action}.")
        return redirect("user-list")

# --------------------------- LANDING PAGE ---------------------------
class LandingPageView(TemplateView):
    template_name = 'landingpage/landingpage.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)

# --------------------------- LOGIN PAGE ---------------------------
class CustomLoginView(LoginView):
    template_name = 'registration/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        # Redirect staff to dispense page, managers/admins to dashboard
        if is_manager_or_admin(self.request.user):
            return reverse_lazy('dashboard')
        else:
            return reverse_lazy('dispense')

    def form_valid(self, form):
        # Call parent form_valid to handle login
        response = super().form_valid(form)
        
        # Log the login activity
        ActivityLog.objects.create(
            user=self.request.user,
            action=f"User logged in"
        )
        
        return response

    def form_invalid(self, form):
        messages.error(self.request, "Incorrect username or password.")
        return super().form_invalid(form)
    
# --------------------------- REGISTRATION PAGE ---------------------------
class RegsiterPage(FormView):
    template_name = 'registration/register.html'
    form_class = UserCreationForm
    redirect_authenticated_user = True
    success_url = reverse_lazy('dashboard')

    def form_valid(self, form):
        user = form.save()
        if user is not None:
            login(self.request, user)
        return super(RegsiterPage, self).form_valid(form)

    def get(self,*args,**kwargs):
        if self.request.user.is_authenticated:
            return redirect('dashboard') 
        return super(RegsiterPage, self).get(*args, **kwargs)

def about(request):
    return render(request, "landingpage/about.html")
def services(request):
    return render(request, "landingpage/services.html")
def contact(request):
    return render(request, "landingpage/contact.html")

# --------------------------- MEDICINE ---------------------------
class MedicineListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Medicine
    context_object_name = "medicines"
    template_name = "medicine/medicine_list.html"
    
    def test_func(self):
        return is_manager_or_admin(self.request.user)
    
    def handle_no_permission(self):
        from django.shortcuts import render
        context = {
            'user_role': get_user_role_display(self.request.user),
            'is_manager_or_admin': False
        }
        return render(self.request, 'shared/access_denied.html', context, status=403)
    
    def get_queryset(self):
        queryset = Medicine.objects.filter(is_deleted=False)
        search_query = self.request.GET.get('search', '')
        
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(brand__icontains=search_query) |
                Q(category__name__icontains=search_query) |
                Q(product_type__name__icontains=search_query) |
                Q(dosage_form__icontains=search_query) |
                Q(strength__icontains=search_query)
            )
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["is_manager_or_admin"] = is_manager_or_admin(user)
        return context

class MedicineCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Medicine
    fields = ['name','brand','category','product_type','dosage_form','strength','units_per_pack','packs_per_box','base_price','selling_price','description']
    
    def test_func(self):
        return is_manager_or_admin(self.request.user)
    
    def handle_no_permission(self):
        from django.shortcuts import render
        context = {
            'user_role': get_user_role_display(self.request.user),
            'is_manager_or_admin': False
        }
        return render(self.request, 'shared/access_denied.html', context, status=403)
    template_name = "medicine/medicine_form.html"
    success_url = reverse_lazy("medicine-list")

    def form_valid(self, form):
        response = super().form_valid(form)
        log_activity(self.request.user, f"Added medicine: {form.instance.name}")
        return response

class MedicineUpdateView(LoginRequiredMixin, UpdateView):
    model = Medicine
    # Removed price fields - prices should only be updated via MedicinePriceUpdateView
    fields = ['name','brand','category','product_type','dosage_form','strength','units_per_pack','packs_per_box','description']
    template_name = "medicine/medicine_form.html"
    success_url = reverse_lazy("medicine-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pass a flag to show price notice in template
        context['is_update'] = True
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        log_activity(self.request.user, f"Updated medicine: {form.instance.name}")
        messages.success(self.request, f"Medicine '{form.instance.name}' updated successfully.")
        return response

# --------------------------- MODAL: MEDICINE UPDATE (AJAX) ---------------------------
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.template.loader import render_to_string
from django.middleware import csrf

@login_required
def medicine_update_modal(request, pk):
    medicine = get_object_or_404(Medicine, pk=pk)

    class MedicineModalForm(forms.ModelForm):
        class Meta:
            model = Medicine
            fields = ['name','brand','category','product_type','dosage_form','strength','units_per_pack','packs_per_box','description']
        
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # Add placeholders
            self.fields['name'].widget.attrs.update({'placeholder': 'Enter medicine name'})
            self.fields['brand'].widget.attrs.update({'placeholder': 'Enter brand name'})
            self.fields['dosage_form'].widget.attrs.update({'placeholder': 'e.g., Tablet, Capsule, Syrup'})
            self.fields['strength'].widget.attrs.update({'placeholder': 'e.g., 500mg, 250mg/5mL'})
            self.fields['units_per_pack'].widget.attrs.update({'placeholder': 'Pieces per pack'})
            self.fields['packs_per_box'].widget.attrs.update({'placeholder': 'Packs per box'})
            self.fields['description'].widget.attrs.update({'placeholder': 'Product description (optional)'})

    if request.method == 'POST':
        form = MedicineModalForm(request.POST, instance=medicine)
        if form.is_valid():
            form.save()
            log_activity(request.user, f"Updated medicine (modal): {medicine.name}")
            messages.success(request, f"Medicine '{medicine.name}' updated successfully.")
            return JsonResponse({'success': True})
        html = render_to_string('medicine/partials/medicine_form_modal.html', {'form': form, 'medicine': medicine, 'is_update': True}, request=request)
        return JsonResponse({'success': False, 'html': html}, status=400)
    else:
        form = MedicineModalForm(instance=medicine)
        html = render_to_string('medicine/partials/medicine_form_modal.html', {'form': form, 'medicine': medicine, 'is_update': True}, request=request)
        return JsonResponse({'success': True, 'html': html})

# --------------------------- MODAL: MEDICINE PRICE UPDATE (AJAX) ---------------------------
@login_required
def medicine_price_update_modal(request, pk):
    medicine = get_object_or_404(Medicine, pk=pk)
    if not is_manager_or_admin(request.user):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    class MedicinePriceModalForm(forms.ModelForm):
        class Meta:
            model = Medicine
            fields = ['base_price','selling_price']
        
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # Add placeholders
            self.fields['base_price'].widget.attrs.update({'placeholder': 'Enter base price (e.g., 5.50)'})
            self.fields['selling_price'].widget.attrs.update({'placeholder': 'Enter selling price (e.g., 7.00)'})

    if request.method == 'POST':
        form = MedicinePriceModalForm(request.POST, instance=medicine)
        reason = request.POST.get('reason', 'Price adjustment via modal')
        if form.is_valid():
            old = Medicine.objects.get(pk=medicine.pk)
            old_base, old_sell = old.base_price, old.selling_price
            updated = form.save()
            new_base, new_sell = updated.base_price, updated.selling_price
            if old_base != new_base or old_sell != new_sell:
                from base.models import PriceHistory
                PriceHistory.objects.create(
                    medicine=medicine,
                    old_base_price=old_base,
                    new_base_price=new_base,
                    old_selling_price=old_sell,
                    new_selling_price=new_sell,
                    changed_by=request.user,
                    reason=reason
                )
                log_activity(request.user, f"Updated prices (modal): {medicine.name} Base ₱{old_base}→₱{new_base} Sell ₱{old_sell}→₱{new_sell}")
                messages.success(request, f"Price updated for {medicine.name}")
            else:
                messages.info(request, "No price changes detected.")
            return JsonResponse({'success': True})
        html = render_to_string('medicine/partials/medicine_price_form_modal.html', {'form': form, 'medicine': medicine}, request=request)
        return JsonResponse({'success': False, 'html': html}, status=400)
    else:
        form = MedicinePriceModalForm(instance=medicine)
        html = render_to_string('medicine/partials/medicine_price_form_modal.html', {'form': form, 'medicine': medicine}, request=request)
        return JsonResponse({'success': True, 'html': html})

# --------------------------- MODAL: BATCH UPDATE (AJAX) ---------------------------
@login_required
def batch_update_modal(request, pk):
    batch = get_object_or_404(StockBatch, pk=pk)

    class StockBatchModalForm(forms.ModelForm):
        class Meta:
            model = StockBatch
            fields = ["medicine", "quantity", "expiry_date", "location"]

    if request.method == 'POST':
        form = StockBatchModalForm(request.POST, instance=batch)
        if form.is_valid():
            form.save()
            log_activity(request.user, f"Updated batch (modal) for {batch.medicine.name}")
            messages.success(request, f"Batch updated: {batch.medicine.name}")
            return JsonResponse({'success': True})
        html = render_to_string('medicine/partials/batch_form_modal.html', {'form': form, 'batch': batch}, request=request)
        return JsonResponse({'success': False, 'html': html}, status=400)
    else:
        form = StockBatchModalForm(instance=batch)
        html = render_to_string('medicine/partials/batch_form_modal.html', {'form': form, 'batch': batch}, request=request)
        return JsonResponse({'success': True, 'html': html})

# --------------------------- MODAL: MEDICINE CREATE (AJAX) ---------------------------
@login_required
def medicine_create_modal(request):
    class MedicineCreateModalForm(forms.ModelForm):
        class Meta:
            model = Medicine
            fields = ['name','brand','category','product_type','dosage_form','strength','units_per_pack','packs_per_box','base_price','selling_price','description']
        
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            
            # Add placeholders
            self.fields['name'].widget.attrs.update({'placeholder': 'Enter medicine name (e.g., Paracetamol)'})
            self.fields['brand'].widget.attrs.update({'placeholder': 'Enter brand name (e.g., Biogesic)'})
            self.fields['dosage_form'].widget.attrs.update({'placeholder': 'e.g., Tablet, Capsule, Syrup'})
            self.fields['strength'].widget.attrs.update({'placeholder': 'e.g., 500mg, 250mg/5mL'})
            self.fields['units_per_pack'].widget.attrs.update({'placeholder': 'Pieces per pack'})
            self.fields['packs_per_box'].widget.attrs.update({'placeholder': 'Packs per box'})
            self.fields['base_price'].widget.attrs.update({'placeholder': 'Enter base price (e.g., 5.50)'})
            self.fields['selling_price'].widget.attrs.update({'placeholder': 'Enter selling price (e.g., 7.00)'})
            self.fields['description'].widget.attrs.update({'placeholder': 'Product description (optional)'})
            
            # Show all product types initially (user will select category first)
            self.fields['product_type'].queryset = ProductType.objects.filter(is_deleted=False).order_by('name')
            self.fields['product_type'].required = False  # Make optional since it depends on category
            
            if 'category' in self.data:
                try:
                    category_id = int(self.data.get('category'))
                    self.fields['product_type'].queryset = ProductType.objects.filter(category_id=category_id, is_deleted=False).order_by('name')
                except (ValueError, TypeError):
                    pass

    if request.method == 'POST':
        try:
            form = MedicineCreateModalForm(request.POST)
            if form.is_valid():
                medicine = form.save()
                log_activity(request.user, f"Added medicine (modal): {medicine.name}")
                messages.success(request, f"Medicine '{medicine.name}' added successfully.")
                return JsonResponse({'success': True})
            html = render_to_string('medicine/partials/medicine_create_modal.html', {'form': form}, request=request)
            return JsonResponse({'success': False, 'html': html}, status=400)
        except Exception as e:
            # Ensure JSON is always returned to prevent client-side JSON parse errors
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    else:
        form = MedicineCreateModalForm()
        html = render_to_string('medicine/partials/medicine_create_modal.html', {'form': form}, request=request)
        return JsonResponse({'success': True, 'html': html})

# --------------------------- MODAL: BATCH CREATE (AJAX) ---------------------------
@login_required
def batch_create_modal(request):
    from base.models import PurchaseOrder, PurchaseOrderLine
    
    class StockBatchCreateModalForm(forms.ModelForm):
        # Override to show only PO field and medicine will be selected from PO
        purchase_order = forms.ModelChoiceField(
            queryset=PurchaseOrder.objects.filter(is_deleted=False, status='Received').order_by('-created_at'),
            required=True,
            label="Select Received Purchase Order",
            empty_label="-- Select Purchase Order --"
        )
        po_line = forms.ModelChoiceField(
            queryset=PurchaseOrderLine.objects.none(),
            required=True,
            label="Select Medicine from Order",
            empty_label="-- Select Medicine --"
        )
        
        class Meta:
            model = StockBatch
            fields = ["quantity", "date_received", "is_recalled"]
        
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if 'purchase_order' in self.data:
                try:
                    po_id = int(self.data.get('purchase_order'))
                    self.fields['po_line'].queryset = PurchaseOrderLine.objects.filter(purchase_order_id=po_id)
                except (ValueError, TypeError):
                    pass

    if request.method == 'POST':
        form = StockBatchCreateModalForm(request.POST)
        if form.is_valid():
            batch = form.save(commit=False)
            
            # Get medicine and dates from selected PO line
            po_line = form.cleaned_data['po_line']
            batch.medicine = po_line.medicine
            
            # Get damaged boxes
            damaged_boxes = int(request.POST.get('damaged_boxes', 0))
            
            # Validate: quantity received + damaged should not exceed ordered quantity
            total_received = batch.quantity + damaged_boxes
            if total_received > po_line.quantity_ordered:
                return JsonResponse({
                    'success': False, 
                    'error': f'Total received ({total_received} boxes) exceeds ordered quantity ({po_line.quantity_ordered} boxes)'
                }, status=400)
            
            # Use manufactured date and expiration date from PO line
            if po_line.manufactured_date:
                batch.manufactured_date = po_line.manufactured_date
            if po_line.expiration_date:
                batch.expiry_date = po_line.expiration_date
            
            # Auto-assign location: first batch to 'front', subsequent to 'back'
            has_front = StockBatch.objects.filter(medicine=batch.medicine, is_deleted=False, is_recalled=False, location="front").exists()
            batch.location = "back" if has_front else "front"
            batch.save()
            medicine = batch.medicine
            unit_label = "boxes"
            total_pieces = (
                batch.quantity *
                medicine.packs_per_box *
                medicine.units_per_pack
            )
            
            # Log activity with damaged info
            activity_msg = f"Added batch from PO #{po_line.purchase_order.id}: {medicine.name} — {batch.quantity} {unit_label} ({total_pieces} total pieces)"
            if damaged_boxes > 0:
                activity_msg += f" | Damaged: {damaged_boxes} boxes"
            log_activity(request.user, activity_msg)
            
            try:
                remarks = f"Stock-in from PO #{po_line.purchase_order.id} ({batch.quantity} {unit_label})"
                if damaged_boxes > 0:
                    remarks += f" | Damaged: {damaged_boxes} boxes"
                
                StockMovement.objects.create(
                    medicine=medicine,
                    batch=batch,
                    from_location="",
                    to_location=batch.location,
                    quantity=total_pieces,
                    reason="transfer",
                    remarks=remarks,
                    user=request.user
                )
            except Exception:
                pass
            
            success_msg = f"Batch added successfully for {medicine.name} from PO #{po_line.purchase_order.id}"
            if damaged_boxes > 0:
                success_msg += f" ({damaged_boxes} boxes damaged)"
            messages.success(request, success_msg)
            return JsonResponse({'success': True})
        html = render_to_string('medicine/partials/batch_create_modal.html', {'form': form}, request=request)
        return JsonResponse({'success': False, 'html': html}, status=400)
    else:
        form = StockBatchCreateModalForm()
        html = render_to_string('medicine/partials/batch_create_modal.html', {'form': form}, request=request)
        return JsonResponse({'success': True, 'html': html})

# --------------------------- BATCH RECEIVE FROM PO (FULL PAGE) ---------------------------
@login_required
def batch_receive_form(request):
    """Receive batch from purchase order - full page with all medicines"""
    from base.models import PurchaseOrder, PurchaseOrderLine, StockBatch, StockMovement
    
    # Get all received purchase orders that still have items to receive
    from django.db.models import Q, F
    all_received_pos = PurchaseOrder.objects.filter(
        is_deleted=False, 
        status='Received'
    ).prefetch_related('lines__medicine').order_by('-created_at')
    
    # Filter out POs where all lines are fully received
    purchase_orders = []
    for po in all_received_pos:
        has_unreceived = any(
            line.quantity_received < line.quantity_ordered 
            for line in po.lines.all()
        )
        if has_unreceived:
            purchase_orders.append(po)
    
    selected_po = None
    if request.GET.get('po'):
        try:
            selected_po = PurchaseOrder.objects.prefetch_related('lines__medicine').get(
                id=request.GET.get('po'),
                is_deleted=False,
                status='Received'
            )
        except PurchaseOrder.DoesNotExist:
            messages.error(request, "Purchase order not found")
    
    if request.method == 'POST':
        try:
            po_id = request.POST.get('purchase_order')
            date_received_str = request.POST.get('date_received')
            line_ids = request.POST.getlist('line_id[]')
            
            if not po_id or not date_received_str or not line_ids:
                messages.error(request, "Missing required fields")
                return redirect(f'batch-receive?po={po_id}')
            
            from datetime import datetime
            date_received = datetime.strptime(date_received_str, '%Y-%m-%d').date()
            selected_po = PurchaseOrder.objects.get(id=po_id, is_deleted=False, status='Received')
            
            batches_created = 0
            total_damaged = 0
            
            # Process each line item
            for line_id in line_ids:
                quantity_received = int(request.POST.get(f'quantity_received_{line_id}', 0))
                quantity_damaged = int(request.POST.get(f'quantity_damaged_{line_id}', 0))
                
                if quantity_received <= 0:
                    continue  # Skip if no quantity received
                
                po_line = PurchaseOrderLine.objects.get(id=line_id, purchase_order=selected_po)
                
                # Validate total doesn't exceed ordered
                total = quantity_received + quantity_damaged
                if total > po_line.quantity_ordered:
                    messages.error(request, f"Total received + damaged ({total}) exceeds ordered quantity ({po_line.quantity_ordered}) for {po_line.medicine.name}")
                    return redirect(f'batch-receive?po={po_id}')
                
                # Create batch for received (good) boxes
                has_front = StockBatch.objects.filter(
                    medicine=po_line.medicine, 
                    is_deleted=False, 
                    is_recalled=False, 
                    location="front"
                ).exists()
                
                batch = StockBatch.objects.create(
                    medicine=po_line.medicine,
                    quantity=quantity_received,
                    loose_pieces=0,
                    date_received=date_received,
                    manufactured_date=po_line.manufactured_date,
                    expiry_date=po_line.expiration_date,
                    location="back" if has_front else "front",
                    is_recalled=False
                )
                
                # Calculate pieces for stock movement
                medicine = batch.medicine
                total_pieces = quantity_received * medicine.packs_per_box * medicine.units_per_pack
                
                # Create stock movement
                remarks = f"Stock-in from PO #{selected_po.id} ({quantity_received} boxes)"
                if quantity_damaged > 0:
                    remarks += f" | Damaged: {quantity_damaged} boxes"
                    total_damaged += quantity_damaged
                
                StockMovement.objects.create(
                    medicine=medicine,
                    batch=batch,
                    from_location="",
                    to_location=batch.location,
                    quantity=total_pieces,
                    reason="transfer",
                    remarks=remarks,
                    user=request.user
                )
                
                # Update quantity received on the PO line
                po_line.quantity_received += quantity_received + quantity_damaged
                po_line.save()
                
                # Log activity
                activity_msg = f"Added batch from PO #{selected_po.id}: {medicine.name} — {quantity_received} boxes ({total_pieces} pieces)"
                if quantity_damaged > 0:
                    activity_msg += f" | Damaged: {quantity_damaged} boxes"
                log_activity(request.user, activity_msg)
                
                batches_created += 1
            
            if batches_created > 0:
                success_msg = f"Successfully received {batches_created} batch(es) from PO #{selected_po.id}"
                if total_damaged > 0:
                    success_msg += f" (Total damaged: {total_damaged} boxes)"
                messages.success(request, success_msg)
                return redirect('batch-list')
            else:
                messages.warning(request, "No batches were created. Please enter at least one quantity received.")
                return redirect(f'batch-receive?po={po_id}')
                
        except Exception as e:
            messages.error(request, f"Error receiving batch: {str(e)}")
            return redirect('batch-receive')
    
    context = {
        'purchase_orders': purchase_orders,
        'selected_po': selected_po,
        'is_manager_or_admin': is_manager_or_admin(request.user),
        'user_role': get_user_role_display(request.user)
    }
    return render(request, 'medicine/batch_receive_form.html', context)

# --------------------------- MODAL: BATCH RECALL (AJAX) ---------------------------
@login_required
def batch_recall_modal(request, pk):
    batch = get_object_or_404(StockBatch, pk=pk)
    
    if request.method == 'POST':
        try:
            recall_quantity = int(request.POST.get('recall_quantity', 0))
            reason = request.POST.get('reason', 'Damaged/Defective product')
            
            if recall_quantity <= 0:
                return JsonResponse({'success': False, 'error': 'Recall quantity must be greater than 0'}, status=400)
            
            if recall_quantity > batch.quantity:
                return JsonResponse({'success': False, 'error': f'Cannot recall {recall_quantity} boxes. Only {batch.quantity} boxes available in this batch.'}, status=400)
            
            # Calculate pieces recalled
            medicine = batch.medicine
            pieces_recalled = recall_quantity * medicine.packs_per_box * medicine.units_per_pack
            
            # Create stock movement for recall
            StockMovement.objects.create(
                medicine=medicine,
                batch=batch,
                from_location=batch.location,
                to_location="",
                quantity=pieces_recalled,
                reason="recall",
                remarks=f"Recalled {recall_quantity} box(es) - Reason: {reason}",
                user=request.user
            )
            
            # Update batch quantity
            batch.quantity -= recall_quantity
            
            # If entire batch recalled, mark as recalled
            if batch.quantity <= 0:
                batch.is_recalled = True
                batch.quantity = 0
            
            batch.save()
            # Auto-promote back to front if front is empty after recall
            try:
                from base.models import StockBatch as SB
                has_front = SB.objects.filter(medicine=medicine, is_deleted=False, is_recalled=False, location='front').exists()
                if not has_front:
                    back_batch = SB.objects.filter(medicine=medicine, is_deleted=False, is_recalled=False, location='back').order_by('date_received').first()
                    if back_batch:
                        total_pieces_move = back_batch.quantity * (medicine.packs_per_box or 1) * (medicine.units_per_pack or 1)
                        back_batch.location = 'front'
                        back_batch.save()
                        try:
                            StockMovement.objects.create(
                                medicine=medicine,
                                batch=back_batch,
                                from_location='back',
                                to_location='front',
                                quantity=total_pieces_move,
                                reason='transfer',
                                remarks='Auto-promotion to Store Shelf after recall',
                                user=request.user
                            )
                        except Exception:
                            pass
            except Exception:
                pass
            
            log_activity(
                request.user, 
                f"Recalled {recall_quantity} box(es) from batch (ID: {batch.id}) of {medicine.name} - {pieces_recalled} pieces total"
            )
            messages.success(request, f"Successfully recalled {recall_quantity} box(es) from {medicine.name}")
            return JsonResponse({'success': True})
            
        except ValueError:
            return JsonResponse({'success': False, 'error': 'Invalid quantity value'}, status=400)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    else:
        # GET request - return form HTML
        context = {
            'batch': batch,
            'medicine': batch.medicine,
            'max_quantity': batch.quantity,
            'total_pieces': batch.quantity * batch.medicine.packs_per_box * batch.medicine.units_per_pack
        }
        html = render_to_string('medicine/partials/batch_recall_modal.html', context, request=request)
        return JsonResponse({'success': True, 'html': html})

class MedicineDeleteView(LoginRequiredMixin, DeleteView):
    model = Medicine
    context_object_name = "medicine"
    template_name = "medicine/medicine_delete.html"
    success_url = reverse_lazy("medicine-list")

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        log_activity(request.user, f"Deleted medicine: {obj.name}")
        return super().delete(request, *args, **kwargs)

# --------------------------- MEDICINE PRICE UPDATE (SEPARATE FOR DATA INTEGRITY) ---------------------------
class MedicinePriceUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Medicine
    fields = ['base_price', 'selling_price']
    template_name = "medicine/medicine_price_form.html"
    success_url = reverse_lazy("price-history")

    def test_func(self):
        # Only managers and admins can update prices
        return is_manager_or_admin(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['medicine'] = self.object
        # Get price history for this medicine
        from base.models import PriceHistory
        context['price_history'] = PriceHistory.objects.filter(
            medicine=self.object
        ).order_by('-change_date')[:5]  # Last 5 changes
        return context

    def form_valid(self, form):
        # Get the original object before saving changes
        old_medicine = Medicine.objects.get(pk=self.object.pk)
        
        # Check if prices have changed
        old_base = old_medicine.base_price
        new_base = form.cleaned_data['base_price']
        old_selling = old_medicine.selling_price
        new_selling = form.cleaned_data['selling_price']
        
        # Get reason from form if provided
        reason = self.request.POST.get('reason', 'Price adjustment via price update form')
        
        # Save the form
        response = super().form_valid(form)
        
        # Record price change if prices changed
        if old_base != new_base or old_selling != new_selling:
            from base.models import PriceHistory
            PriceHistory.objects.create(
                medicine=self.object,
                old_base_price=old_base,
                new_base_price=new_base,
                old_selling_price=old_selling,
                new_selling_price=new_selling,
                changed_by=self.request.user,
                reason=reason
            )
            log_activity(
                self.request.user, 
                f"Updated medicine prices: {self.object.name} - "
                f"Base: ₱{old_base} → ₱{new_base}, "
                f"Selling: ₱{old_selling} → ₱{new_selling}"
            )
            messages.success(self.request, f"Price updated successfully for {self.object.name}")
        else:
            messages.info(self.request, "No price changes detected.")
        
        return response

# --------------------------- STOCK BATCH MODEL ---------------------------
class StockBatchListView(LoginRequiredMixin, ListView):
    model = StockBatch
    context_object_name = "batches"
    template_name = "medicine/batch_list.html"
    success_url = reverse_lazy("batch-list")
    
    def get_queryset(self):
        # Show only active batches with positive stock (boxes or loose pieces)
        from django.db.models import Q
        return (
            StockBatch.objects
            .filter(is_deleted=False, is_recalled=False)
            .filter(Q(quantity__gt=0) | Q(loose_pieces__gt=0))
            .select_related('medicine')
            .order_by('medicine__name', 'date_received')
        )
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["is_manager_or_admin"] = is_manager_or_admin(user)
        return context

class StockBatchCreateView(LoginRequiredMixin, CreateView):
    model = StockBatch
    fields = ["medicine", "quantity", "date_received", "is_recalled"]
    template_name = "medicine/batch_form.html"
    success_url = reverse_lazy("batch-list")

    def form_valid(self, form):
        # Auto-assign location: first batch to 'front', subsequent to 'back'
        instance = form.save(commit=False)
        medicine = instance.medicine
        has_front = StockBatch.objects.filter(medicine=medicine, is_deleted=False, is_recalled=False, location="front").exists()
        instance.location = "back" if has_front else "front"
        instance.save()

        response = redirect(self.success_url)
        unit_label = "boxes"
        total_pieces = (
            instance.quantity *
            medicine.packs_per_box *
            medicine.units_per_pack
        )
        log_activity(self.request.user,f"Added batch: {medicine.name} — "f"{form.instance.quantity} {unit_label} "f"({total_pieces} total pieces)")

        try:
            StockMovement.objects.create(
                medicine=medicine,
                batch=instance,
                from_location="",
                to_location=instance.location,
                quantity=total_pieces,
                reason="transfer",
                remarks=f"Stock-in via batch creation ({instance.quantity} {unit_label})",
                user=self.request.user
            )
        except Exception:
            pass
        return response

class StockBatchUpdateView(LoginRequiredMixin, UpdateView):
    model = StockBatch
    fields = ["medicine", "quantity", "expiry_date", "location"]
    template_name = "medicine/batch_form.html"
    success_url = reverse_lazy("batch-list")

    def form_valid(self, form):
        response = super().form_valid(form)
        medicine = form.instance.medicine
        log_activity(self.request.user,f"Updated batch for {medicine.name} — "f"Qty: {form.instance.quantity} boxes")
        return response

class StockBatchDeleteView(LoginRequiredMixin, DeleteView):
    model = StockBatch
    context_object_name = "batch"
    template_name = "medicine/batch_delete.html"
    success_url = reverse_lazy("batch-list")

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        log_activity(request.user, f"Deleted batch: {obj.medicine.name} ({obj.quantity} units)")
        return super().delete(request, *args, **kwargs)

# --------------------------- STOCK OUT EXPIRED BATCH ---------------------------
@login_required
@manager_required
def batch_stockout_expired(request, pk):
    """Stock out expired batch with proper movement tracking"""
    from base.models import StockBatch, StockMovement
    from datetime import date
    from django.template.loader import render_to_string
    
    batch = get_object_or_404(StockBatch, pk=pk, is_deleted=False)
    
    # Verify batch is expired or expiring within 6 months (store policy)
    from datetime import timedelta
    six_months_from_now = date.today() + timedelta(days=180)
    if batch.expiry_date and batch.expiry_date > six_months_from_now:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'error': 'This batch is not within the 6-month expiry window per store policy.'}, status=400)
        messages.warning(request, "This batch is not within the 6-month expiry window per store policy.")
        return redirect('expiration-monitor')
    
    if request.method == 'POST':
        try:
            # Get reason from JSON body
            reason = ""
            if request.content_type == 'application/json':
                import json
                data = json.loads(request.body)
                reason = data.get('reason', '').strip()
            else:
                reason = request.POST.get('reason', '').strip()
            
            if not reason:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'error': 'Reason for removal is required.'}, status=400)
                messages.error(request, "Reason for removal is required.")
                return redirect('expiration-monitor')
            
            # Calculate total pieces being removed (including loose pieces)
            medicine = batch.medicine
            total_pieces = batch.total_pieces

            # Create stock movement for the removal
            StockMovement.objects.create(
                medicine=medicine,
                batch=batch,
                from_location=batch.location,
                to_location="",
                quantity=total_pieces,
                reason="expired",
                remarks=f"Expired batch removed from inventory. Batch ID #{batch.id}, Expiry: {batch.expiry_date}. Reason: {reason}",
                user=request.user
            )

            log_activity(
                request.user,
                f"Stocked out expired batch #{batch.id}: {medicine.name} — "
                f"{total_pieces} pieces expired on {batch.expiry_date}"
            )

            # Soft delete the batch
            batch.delete()
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True})
            messages.success(request, f"Expired batch #{batch.id} successfully removed from inventory.")
            return redirect('expiration-monitor')
            
        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': str(e)}, status=400)
            messages.error(request, f"Error removing expired batch: {str(e)}")
            return redirect('expiration-monitor')
    
    # GET request - show confirmation (modal or page)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string('medicine/partials/batch_stockout_modal.html', {'batch': batch}, request=request)
        return JsonResponse({'html': html})
    
    context = {
        'batch': batch,
        'is_manager_or_admin': is_manager_or_admin(request.user),
        'user_role': get_user_role_display(request.user)
    }
    return render(request, 'medicine/batch_stockout_confirm.html', context)

# --------------------------- MULTI-ITEM DISPENSE FORM & VIEW ---------------------------
class DispenseLineItemForm(forms.Form):
    """Single line form for one medicine in a multi-item sale."""
    # Only show medicines that actually have stock in batches
    medicine = forms.ModelChoiceField(
        queryset=Medicine.objects.filter(
            Q(batches__quantity__gt=0) | Q(batches__loose_pieces__gt=0),
            is_deleted=False,
            batches__is_deleted=False,
            batches__is_recalled=False,
        ).distinct().order_by('name'),
        label="Medicine",
        widget=forms.Select(attrs={'class': 'form-control medicine-select'})
    )
    quantity = forms.IntegerField(
        min_value=1,
        label="Quantity",
        widget=forms.NumberInput(attrs={
            'class': 'form-control quantity-input',
            'placeholder': 'Enter quantity'
        })
    )
    UNIT_CHOICES = [("piece", "Piece"), ("pack", "Pack"), ("box", "Box")]
    unit_type = forms.ChoiceField(
        choices=UNIT_CHOICES,
        initial="peice",
        label="Unit",
        widget=forms.Select(attrs={'class': 'form-control unit-select'})
    )

# Create formset factory for multiple line items
DispenseLineItemFormSet = formset_factory(
    DispenseLineItemForm,
    extra=1,  # Start with 1 empty form
    can_delete=True
)

class DispenseView(LoginRequiredMixin, FormView):
    """
    Multi-item dispensing view.
    Allows user to add multiple medicines to one transaction with proper unit pricing.
    """
    template_name = "medicine/dispense_form.html"
    form_class = DispenseLineItemFormSet
    success_url = reverse_lazy("batch-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if 'formset' not in context:
            context['formset'] = self.get_form()
        
        # Add discount and payment forms as separate forms
        discount_types = DiscountType.objects.filter(is_active=True).order_by('discount_name')
        payment_methods = PaymentMethod.objects.filter(is_active=True).order_by('method_name')
        
        context['discount_types'] = discount_types
        context['payment_methods'] = payment_methods
        context['is_manager_or_admin'] = is_manager_or_admin(self.request.user)
        
        # Add medicine data for JavaScript price calculation
        # Convert Decimal to float for JSON serialization
        import json
        from decimal import Decimal
        
        medicines = Medicine.objects.filter(is_deleted=False).values(
            'id', 'name', 'selling_price', 'units_per_pack', 'packs_per_box'
        )
        # Restrict to medicines with available batch stock
        medicines = Medicine.objects.filter(
            Q(batches__quantity__gt=0) | Q(batches__loose_pieces__gt=0),
            is_deleted=False,
            batches__is_deleted=False,
            batches__is_recalled=False,
        ).distinct().values('id', 'name', 'selling_price', 'units_per_pack', 'packs_per_box')
        
        # Convert Decimal fields to float
        medicines_list = []
        for med in medicines:
            medicine_obj = Medicine.objects.get(pk=med['id'])
            stock_info = medicine_obj.get_available_stock()
            
            medicines_list.append({
                'id': med['id'],
                'name': med['name'],
                'selling_price': float(med['selling_price']) if med['selling_price'] else 0,
                'units_per_pack': med['units_per_pack'] or 1,
                'packs_per_box': med['packs_per_box'] or 1,
                'available_pieces': stock_info['total_pieces'],
                'available_boxes': stock_info['boxes'],
                'available_packs': stock_info['packs'],
                'available_loose_pieces': stock_info['pieces']
            })
        
        context['medicines_json'] = json.dumps(medicines_list)
        
        return context

    def post(self, request, *args, **kwargs):
        formset = self.get_form()
        discount_type_id = request.POST.get('discount_type_fk')
        payment_method_id = request.POST.get('payment_method')
        cash_received = request.POST.get('cash_received')
        
        if formset.is_valid():
            return self.form_valid(formset, discount_type_id, payment_method_id, cash_received)
        else:
            return self.form_invalid(formset)

    def form_valid(self, formset, discount_type_id, payment_method_id, cash_received):
        from decimal import Decimal
        from base.models import Sale, SaleLineItem, StockBatch, StockMovement, DiscountType, PaymentMethod, Ordering, OrderedProduct
        
        # Validate we have at least one item
        line_data = []
        for form in formset:
            if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                line_data.append(form.cleaned_data)
        
        if not line_data:
            messages.error(self.request, "Please add at least one medicine to dispense.")
            return self.form_invalid(formset)
        
        # Get discount and payment method
        discount_type = None
        if discount_type_id:
            try:
                discount_type = DiscountType.objects.get(pk=discount_type_id, is_active=True)
            except DiscountType.DoesNotExist:
                pass
        
        payment_method = None
        if payment_method_id:
            try:
                payment_method = PaymentMethod.objects.get(pk=payment_method_id, is_active=True)
            except PaymentMethod.DoesNotExist:
                pass
        
        # Validate cash received
        try:
            cash_received = Decimal(str(cash_received or 0))
        except:
            messages.error(self.request, "Invalid cash amount received.")
            return self.form_invalid(formset)
        
        # Create Sale header
        sale = Sale.objects.create(
            user=self.request.user,
            discount_type_fk=discount_type,
            payment_method=payment_method,
            status='Pending'  # Will be updated after successful dispense
        )
        
        try:
            # Process each line item
            before_dispense = timezone.now()
            
            for line in line_data:
                medicine = line['medicine']
                quantity = line['quantity']
                unit_type = line['unit_type']
                
                # Get per-piece price
                unit_price = medicine.selling_price or Decimal('0.00')
                
                # Create line item (will auto-calculate pieces_dispensed and line_total)
                line_item = SaleLineItem.objects.create(
                    sale=sale,
                    medicine=medicine,
                    quantity=quantity,
                    unit_type=unit_type,
                    unit_price=unit_price
                )
                
                # Dispense stock via FIFO (returns leftover if insufficient stock)
                leftover = StockBatch.dispense(
                    medicine.id, 
                    line_item.pieces_dispensed,  # Already converted to pieces
                    unit_type='piece',  # Already in pieces
                    user=self.request.user
                )
                
                if leftover > 0:
                    # Rollback: delete sale and all line items
                    sale.delete()
                    messages.error(
                        self.request,
                        f"Insufficient stock for {medicine.name}! "
                        f"Needed {line_item.pieces_dispensed} pieces, short by {leftover} pieces."
                    )
                    log_activity(
                        self.request.user,
                        f"Failed dispense: {medicine.name}, insufficient stock."
                    )
                    return self.form_invalid(formset)
                
                # Link stock movements to this line item
                movements = StockMovement.objects.filter(
                    user=self.request.user,
                    reason='sale',
                    medicine=medicine,
                    sale__isnull=True,
                    line_item__isnull=True,
                    movement_date__gte=before_dispense
                ).order_by('movement_date')
                
                for movement in movements:
                    movement.sale = sale
                    movement.line_item = line_item
                    movement.save()
            
            # Calculate totals with discount
            sale.apply_discount()
            
            # Validate and finalize payment
            if cash_received < sale.final_amount:
                sale.delete()
                messages.error(
                    self.request,
                    f"Cash received (₱{cash_received}) is insufficient. "
                    f"Total amount due: ₱{sale.final_amount}"
                )
                return self.form_invalid(formset)
            
            sale.finalize_payment(cash_received)
            sale.status = 'Completed'
            sale.save(update_fields=['status'])

            # Create an Ordering record to track this dispense in ORDERING/ORDERED_PRODUCT tables
            order = Ordering.objects.create(
                user=self.request.user,
                customer_name=sale.customer_name or '',
                customer_contact='',
                status='Completed',
                notes='Recorded from Dispense workflow',
                sale=sale,
                completed_date=now()
            )

            # Create corresponding OrderedProduct records
            for line in sale.line_items.select_related('medicine').all():
                OrderedProduct.objects.create(
                    ordering=order,
                    medicine=line.medicine,
                    quantity=line.quantity,
                    unit_type=line.unit_type,
                    unit_price=line.unit_price
                )
            
            # Log activity
            item_count = sale.line_items.count()
            log_activity(
                self.request.user,
                f"Completed sale #{sale.sale_id}: {item_count} item(s), Total ₱{sale.final_amount}"
            )

            # Log order creation for audit trail
            log_activity(
                self.request.user,
                f"Recorded order #{order.ordering_id} from dispense → linked to Sale #{sale.sale_id}"
            )
            
            messages.success(
                self.request,
                f"Sale completed successfully! {item_count} item(s) dispensed."
            )
            
            return redirect(reverse('view_invoice', args=[sale.sale_id]))
            
        except Exception as e:
            # Rollback on any error
            if sale.pk:
                sale.delete()
            messages.error(self.request, f"Error processing sale: {str(e)}")
            return self.form_invalid(formset)

# --------------------------- VIEW INVOICE (UPDATED FOR LINE ITEMS) ---------------------------
@login_required
def view_invoice(request, sale_id):
    sale = get_object_or_404(Sale, pk=sale_id)
    line_items = sale.line_items.select_related("medicine").all()

    items = []
    subtotal = Decimal('0.00')
    
    for line in line_items:
        items.append({
            'medicine_name': line.medicine.name,
            'quantity': line.quantity,
            'unit_type': line.get_unit_type_display(),
            'pieces_dispensed': line.pieces_dispensed,
            'unit_price': line.unit_price,  # per-piece price
            'line_total': line.line_total,
        })
        subtotal += line.line_total

    discount_amount = sale.discount_amount
    discount_rate = sale.discount_rate
    discount_label = sale.effective_discount_label()
    total = sale.final_amount

    context = {
        "sale": sale,
        "line_items": line_items,
        "items": items,
        "subtotal": subtotal,
        "discount": discount_amount,
        "discount_amount": discount_amount,
        "discount_percentage": discount_rate,
        "discount_type": discount_label,
        "payment_method": sale.payment_method.method_name if sale.payment_method else 'Cash',
        "cash_received": sale.cash_received,
        "change_amount": sale.change_amount,
        "invoice_number": sale.invoice_number or f"INV-{sale.sale_id:06d}",
        "total": total,
        "transaction_id": sale.sale_id,
        "date": sale.sale_date,
        "pharmacist": sale.user,
        "customer_type": discount_label,
        # Static placeholders
        "pharmacy_name": "TGP Pharmacy – Ilustre Branch",
        "pharmacy_address": "TGP The Generics Pharmacy, Door 4, Pioneer Building, Gov Duterte St, Poblacion District, Davao City, 8000 Davao del Sur",
        "pharmacy_contact": "(02) 123-4567",
    }
    return render(request, 'sales/invoice.html', context)

# --------------------------- PRODUCT TYPES ---------------------------
from django.http import JsonResponse
from .models import ProductType, Category

def load_product_types(request):
    category_id = request.GET.get('category')
    product_types = ProductType.objects.filter(category_id=category_id, is_deleted=False).order_by('name')
    data = [{"id": pt.id, "name": pt.name} for pt in product_types]
    return JsonResponse(data, safe=False)

# --------------------------- STOCK MOVEMENT ---------------------------
class StockMovementListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = StockMovement
    template_name = "medicine/movement_list.html"
    context_object_name = "movements"
    ordering = ["-movement_date"]

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def get_queryset(self):
        queryset = super().get_queryset().select_related("medicine", "batch", "user")
        search = self.request.GET.get("search")
        if search:
            queryset = queryset.filter(medicine__name__icontains=search)
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["is_manager_or_admin"] = is_manager_or_admin(user)
        return context

def invoice_view(request, sale_id):
    sale = get_object_or_404(Sale, pk=sale_id)
    movements = sale.movements.select_related("medicine", "batch").all()

    items = []
    subtotal = Decimal('0.00')
    for m in movements:
        unit_price = m.medicine.selling_price or Decimal('0.00')
        qty = Decimal(m.quantity)
        line_total = unit_price * qty
        items.append({
            'medicine_name': m.medicine.name,
            'batch': getattr(m.batch, 'id', 'N/A'),
            'quantity': int(m.quantity),
            'unit_price': unit_price,
            'line_total': line_total,
        })
        subtotal += line_total

    discount_amount = sale.discount_amount
    discount_rate = sale.discount_rate
    discount_type = sale.get_discount_type_display() if sale.discount_type else "Regular"
    total = sale.final_amount

    context = {
        'pharmacy': {
            'name': 'The Generics Pharmacy',
            'address': '123 Pharmacy Lane, Cityville',
            'contact': 'Tel: (012) 345-6789 | Email: info@example.com'
        },
        'transaction_id': sale.sale_id,
        'date': sale.sale_date,
        'pharmacist': sale.user,
        'customer_type': discount_type,
        'items': items,
        'subtotal': subtotal,
        'discount': discount_amount,
        'discount_percentage': discount_rate,
        'total': total,
        'movements': movements,
    }
    return render(request, 'medicine/invoice.html', context)


# --------------------------- VIEW SALES REPORT ---------------------------
class ManagerOrAdminRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def handle_no_permission(self):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("You do not have permission to view this page.")

class SalesReportView(LoginRequiredMixin, ManagerOrAdminRequiredMixin, ListView):
    model = Sale
    template_name = "sales/sales_report.html"
    context_object_name = "sales"

    def get_queryset(self):
        queryset = Sale.objects.select_related('user').prefetch_related('movements__medicine').all().order_by("-sale_date")
        
        # Date range filter
        start_date = self.request.GET.get("start_date")
        end_date = self.request.GET.get("end_date")
        if start_date and end_date:
            queryset = queryset.filter(sale_date__range=[start_date, end_date])
        
        # Medicine filter
        medicine_id = self.request.GET.get("medicine")
        if medicine_id:
            queryset = queryset.filter(movements__medicine_id=medicine_id).distinct()
        
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["is_manager_or_admin"] = is_manager_or_admin(user)
        
        sales = context["sales"]
        
        # Calculate totals
        total_sales = sum(s.total_amount for s in sales)  # Before discount
        total_discounts = sum(s.discount_amount for s in sales)
        net_sales = sum(s.final_amount for s in sales)  # After discount
        
        context["total_sales"] = total_sales
        context["total_discounts"] = total_discounts
        context["net_sales"] = net_sales
        context["start_date"] = self.request.GET.get("start_date", "")
        context["end_date"] = self.request.GET.get("end_date", "")
        context["medicine_id"] = self.request.GET.get("medicine", "")
        
        # Get all medicines for the filter dropdown
        context["medicines"] = Medicine.objects.filter(is_deleted=False).order_by('name')
        
        return context

# --------------------------- Expired Stock ---------------------------
def process_expired_stock_view(request):
    if not request.user.is_staff:
        messages.error(request, "You do not have permission to perform this action.")
        return redirect('dashboard')

    processed = process_all_expired_batches()
    messages.success(request, f"Processed expired stock batches at {now().strftime('%Y-%m-%d %H:%M')}.")
    return redirect('dashboard')

# --------------------------- ADDED: STOCK TRANSFER (STOCK OUT VIA TRANSFER) WORKFLOW ---------------------------
class TransferItemForm(forms.Form):
    # Only show medicines that have available stock in batches
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Get medicines with available stock
        from django.db.models import Sum, Q
        medicines_with_stock = StockBatch.objects.filter(
            is_deleted=False,
            is_recalled=False,
            quantity__gt=0
        ).values_list('medicine_id', flat=True).distinct()
        
        self.fields['medicine'].queryset = Medicine.objects.filter(
            id__in=medicines_with_stock
        ).order_by('name')
    
    medicine = forms.ModelChoiceField(queryset=Medicine.objects.none(), empty_label="-- Select medicine --")
    quantity = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={'placeholder': 'Enter quantity to transfer'})
    )
    UNIT_CHOICES = (
        ("piece", "Piece"),
        ("pack", "Pack"),
        ("box", "Box"),
    )
    unit_type = forms.ChoiceField(choices=UNIT_CHOICES, initial="box")

def _pieces_from_unit(medicine, qty, unit_type):
    units_per_pack = medicine.units_per_pack or 1
    packs_per_box = medicine.packs_per_box or 1
    if unit_type == "piece":
        return qty
    elif unit_type == "pack":
        return qty * units_per_pack
    elif unit_type == "box":
        return qty * packs_per_box * units_per_pack
    return qty

@transaction.atomic
def fifo_transfer(medicine_id, pieces_needed, user, destination=""):
    created_movements = []
    try:
        medicine = Medicine.objects.get(pk=medicine_id)
    except Medicine.DoesNotExist:
        return pieces_needed, created_movements

    batches = StockBatch.objects.filter(
        medicine_id=medicine_id,
        is_deleted=False,
        is_recalled=False
    ).select_related("medicine").order_by("date_received")

    for batch in batches:
        if pieces_needed <= 0:
            break
        batch_total_pieces = batch.quantity * (batch.medicine.packs_per_box or 1) * (batch.medicine.units_per_pack or 1)
        if batch_total_pieces <= pieces_needed:
            consumed = batch_total_pieces
            pieces_needed -= consumed
            try:
                mv = StockMovement.objects.create(
                    medicine=batch.medicine,
                    batch=batch,
                    from_location=batch.location,
                    to_location=destination,
                    quantity=consumed,
                    reason="transfer",
                    remarks=f"Stock transfer out (full batch) via FIFO to {destination}" if destination else "Stock transfer out (full batch) via FIFO",
                    user=user
                )
                created_movements.append(mv)
            except Exception:
                pass
            batch.delete()
        else:
            consumed = pieces_needed
            remaining_pieces = batch_total_pieces - consumed
            units_per_pack = batch.medicine.units_per_pack or 1
            packs_per_box = batch.medicine.packs_per_box or 1
            pieces_per_box = units_per_pack * packs_per_box
            batch.quantity = remaining_pieces // pieces_per_box
            batch.save()
            try:
                mv = StockMovement.objects.create(
                    medicine=batch.medicine,
                    batch=batch,
                    from_location=batch.location,
                    to_location=destination,
                    quantity=consumed,
                    reason="transfer",
                    remarks=f"Stock transfer out (partial batch) via FIFO to {destination}" if destination else "Stock transfer out (partial batch) via FIFO",
                    user=user
                )
                created_movements.append(mv)
            except Exception:
                pass
            pieces_needed = 0

    return pieces_needed, created_movements

class TransferView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return is_manager_or_admin(self.request.user)
    
    def handle_no_permission(self):
        from django.shortcuts import render
        context = {
            'user_role': get_user_role_display(self.request.user),
            'is_manager_or_admin': False
        }
        return render(self.request, 'shared/access_denied.html', context, status=403)

    def get(self, request, *args, **kwargs):
        import json
        TransferFormSet = formset_factory(TransferItemForm, extra=4)
        formset = TransferFormSet()
        
        # Get all medicines with available stock and their detailed info
        medicines_with_stock = StockBatch.objects.filter(
            is_deleted=False,
            is_recalled=False,
            quantity__gt=0
        ).values_list('medicine_id', flat=True).distinct()
        
        medicines_data = []
        for med_id in medicines_with_stock:
            try:
                medicine = Medicine.objects.get(pk=med_id)
                stock_info = medicine.get_available_stock()
                medicines_data.append({
                    'id': med_id,
                    'name': medicine.name,
                    'available_pieces': stock_info['total_pieces'],
                    'available_boxes': stock_info['boxes'],
                    'available_packs': stock_info['packs'],
                    'available_loose_pieces': stock_info['pieces'],
                    'units_per_pack': stock_info['units_per_pack'],
                    'packs_per_box': stock_info['packs_per_box']
                })
            except Medicine.DoesNotExist:
                pass
        
        return render(request, "transfer/transfer_form.html", {
            "formset": formset,
            "medicines_json": json.dumps(medicines_data),
            "is_manager_or_admin": is_manager_or_admin(request.user),
            "user_role": get_user_role_display(request.user)
        })

    def post(self, request, *args, **kwargs):
        TransferFormSet = formset_factory(TransferItemForm)
        formset = TransferFormSet(request.POST)
        if not formset.is_valid():
            messages.error(request, "Please correct the errors below.")
            return render(request, "transfer/transfer_form.html", {"formset": formset})

        # Get the selected branch destination
        transfer_branch = request.POST.get('transfer_branch', '')
        if not transfer_branch:
            messages.error(request, "Please select a destination branch.")
            return render(request, "transfer/transfer_form.html", {"formset": formset})

        summary = []  # per-medicine summary for confirmation
        overall_leftover = False
        movements_collect = []

        for form in formset:
            if not form.cleaned_data:
                continue  # skip empty rows
            medicine = form.cleaned_data.get("medicine")
            qty = form.cleaned_data.get("quantity")
            unit_type = form.cleaned_data.get("unit_type", "box")
            if not medicine or not qty:
                continue

            pieces_needed = _pieces_from_unit(medicine, qty, unit_type)
            leftover, created_movements = fifo_transfer(medicine.id, pieces_needed, user=request.user, destination=transfer_branch)

            if leftover > 0:
                overall_leftover = True
                log_activity(request.user, f"Partial transfer attempt (insufficient): {medicine.name}, requested {qty} {unit_type}, leftover {leftover} pieces.")
                messages.warning(request, f"Insufficient stock for {medicine.name}. {leftover} piece(s) could not be transferred.")
            else:
                log_activity(request.user, f"Transferred out {qty} {unit_type}(s) of {medicine.name} via FIFO to {transfer_branch}")

            summary.append({
                "medicine": medicine,
                "requested_qty": qty,
                "unit": unit_type,
                "leftover_pieces": leftover,
                "created_movements": created_movements,
            })
            movements_collect.extend(created_movements)

        return render(request, "transfer/transfer_confirmation.html", {
            "summary": summary,
            "overall_leftover": overall_leftover,
            "movements": movements_collect,
            "transfer_branch": transfer_branch,
            # Ensure sidebar shows full manager/admin items
            "is_manager_or_admin": is_manager_or_admin(request.user),
            "user_role": get_user_role_display(request.user),
        })

# --------------------------- PRICE HISTORY VIEW ---------------------------
class PriceHistoryView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = None  # Will be set dynamically
    template_name = "medicine/price_history.html"
    context_object_name = "price_changes"
    paginate_by = 50

    def test_func(self):
        return is_manager_or_admin(self.request.user)

    def get_queryset(self):
        from base.models import PriceHistory
        queryset = PriceHistory.objects.select_related('medicine', 'changed_by').all()
        
        # Filter by medicine
        medicine_id = self.request.GET.get('medicine')
        if medicine_id:
            queryset = queryset.filter(medicine_id=medicine_id)
        
        # Filter by date range
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')
        if start_date:
            queryset = queryset.filter(change_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(change_date__lte=end_date)
        
        # Filter by user
        user_id = self.request.GET.get('user')
        if user_id:
            queryset = queryset.filter(changed_by_id=user_id)
        
        return queryset.order_by('-change_date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["is_manager_or_admin"] = is_manager_or_admin(user)
        
        context['medicines'] = Medicine.objects.all().order_by('name')
        context['users'] = User.objects.filter(is_active=True).order_by('username')
        context['selected_medicine'] = self.request.GET.get('medicine', '')
        context['selected_user'] = self.request.GET.get('user', '')
        context['start_date'] = self.request.GET.get('start_date', '')
        context['end_date'] = self.request.GET.get('end_date', '')
        return context

# --------------------------- ACTUAL INVENTORY VIEW (SHELF STOCK) ---------------------------
class ActualInventoryView(LoginRequiredMixin, ListView):
    model = StockBatch
    template_name = "medicine/actual_inventory.html"
    context_object_name = "inventory_items"

    def get_queryset(self):
        # Only show batches in "front" (Store Shelf) location
        from django.db.models import Q
        queryset = (StockBatch.objects
            .filter(
                location='front',
                is_deleted=False,
                is_recalled=False,
            )
            .filter(Q(quantity__gt=0) | Q(loose_pieces__gt=0))
            .select_related('medicine')
            .order_by('medicine__name', 'date_received')
        )
        
        # Search filter
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(medicine__name__icontains=search)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        from datetime import date, timedelta
        
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["is_manager_or_admin"] = is_manager_or_admin(user)
        
        # Add date references for expiry status calculation
        today = date.today()
        six_months_from_now = today + timedelta(days=180)
        context['today'] = today
        context['six_months_from_now'] = six_months_from_now
        
        # Get status filter
        status_filter = self.request.GET.get('status', 'all')
        context['status_filter'] = status_filter
        
        # Calculate totals and filter by status
        all_batches = context['inventory_items']
        total_value = Decimal('0.00')
        total_items = 0
        low_stock_count = 0
        medium_stock_count = 0
        in_stock_count = 0
        
        # Filter batches by status if needed
        filtered_batches = []
        for batch in all_batches:
            total_pieces = batch.total_pieces
            value = total_pieces * (batch.medicine.selling_price or 0)
            total_value += value
            total_items += total_pieces
            
            # Determine status
            if total_pieces < 50:
                batch_status = 'low'
                low_stock_count += 1
            elif total_pieces < 200:
                batch_status = 'medium'
                medium_stock_count += 1
            else:
                batch_status = 'good'
                in_stock_count += 1
            
            # Apply filter
            if status_filter == 'all' or status_filter == batch_status:
                filtered_batches.append(batch)
        
        context['inventory_items'] = filtered_batches
        context['total_value'] = total_value
        context['total_items'] = total_items
        context['search'] = self.request.GET.get('search', '')
        context['low_stock_count'] = low_stock_count
        context['medium_stock_count'] = medium_stock_count
        context['in_stock_count'] = in_stock_count
        
        return context

# --------------------------- EXPIRATION MONITOR VIEW ---------------------------
class ExpirationMonitorView(LoginRequiredMixin, ListView):
    model = StockBatch
    template_name = "medicine/expiration_monitor.html"
    context_object_name = "batches"

    def get_queryset(self):
        from datetime import date, timedelta
        
        today = date.today()
        from django.db.models import Q
        queryset = (StockBatch.objects
            .filter(
                is_deleted=False,
                is_recalled=False,
            )
            .filter(Q(quantity__gt=0) | Q(loose_pieces__gt=0))
            .select_related('medicine')
            .order_by('expiry_date')
        )
        
    # Filter options - Changed to 6 months window
        filter_type = self.request.GET.get('filter', 'all')
        
        if filter_type == 'expired':
            queryset = queryset.filter(expiry_date__lt=today)
        elif filter_type == 'expiring_soon':
            # Expiring within 6 months
            end_date = today + timedelta(days=180)
            queryset = queryset.filter(expiry_date__gte=today, expiry_date__lte=end_date)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        from datetime import date, timedelta
        
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["is_manager_or_admin"] = is_manager_or_admin(user)
        
        today = date.today()
        six_months_from_now = today + timedelta(days=180)
        
        # Count statistics - 6 months window
        from django.db.models import Q
        all_batches = StockBatch.objects.filter(is_deleted=False, is_recalled=False).filter(Q(quantity__gt=0) | Q(loose_pieces__gt=0))
        context['expired_count'] = all_batches.filter(expiry_date__lt=today).count()
        context['expiring_6months_count'] = all_batches.filter(
            expiry_date__gte=today, 
            expiry_date__lte=six_months_from_now
        ).count()
        
        context['filter'] = self.request.GET.get('filter', 'all')
        context['today'] = today
        context['six_months_from_now'] = six_months_from_now
        
        return context


# ========================================
# ORDERING VIEWS - Customer Order Management
# ========================================

class OrderingListView(LoginRequiredMixin, ListView):
    """List all customer orders with filtering by status"""
    model = Ordering
    template_name = "ordering/ordering_list.html"
    context_object_name = "orders"
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Ordering.objects.select_related(
            'user', 'confirmed_by', 'sale'
        ).prefetch_related('ordered_products__medicine')
        
        # Filter by status if provided
        status_filter = self.request.GET.get('status', '')
        if status_filter and status_filter != 'All':
            queryset = queryset.filter(status=status_filter)
        
        # Search by customer name or order ID
        search = self.request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(customer_name__icontains=search) |
                Q(ordering_id__icontains=search)
            )
        
        return queryset.order_by('-order_date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_filter'] = self.request.GET.get('status', 'All')
        context['search_query'] = self.request.GET.get('search', '')
        context['status_choices'] = Ordering.STATUS_CHOICES
        
        # Count by status
        context['pending_count'] = Ordering.objects.filter(status='Pending').count()
        context['confirmed_count'] = Ordering.objects.filter(status='Confirmed').count()
        context['ready_count'] = Ordering.objects.filter(status='Ready').count()
        
        return context


class OrderingCreateView(LoginRequiredMixin, CreateView):
    """Create a new customer order"""
    model = Ordering
    template_name = "ordering/ordering_form.html"
    fields = ['customer_name', 'customer_contact', 'expected_pickup_date', 'notes']
    success_url = reverse_lazy('ordering-list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get all active medicines with stock
        medicines = Medicine.objects.filter(
            is_deleted=False
        ).select_related('category', 'product_type')
        
        # Add stock info for each medicine
        medicine_data = []
        for med in medicines:
            total_pieces = sum(
                batch.available_pieces 
                for batch in med.stockbatch_set.filter(
                    is_deleted=False,
                    is_recalled=False,
                    is_expired=False
                )
            )
            if total_pieces > 0:
                medicine_data.append({
                    'id': med.medicine_id,
                    'name': med.name,
                    'category': med.category.category_name if med.category else '',
                    'price': float(med.price),
                    'available_pieces': total_pieces,
                    'units_per_pack': med.units_per_pack or 1,
                    'packs_per_box': med.packs_per_box or 1,
                })
        
        context['medicines'] = medicine_data
        return context
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        form.instance.status = 'Pending'
        
        # Save the order first
        self.object = form.save()
        
        # Process ordered products from POST data
        medicines = self.request.POST.getlist('medicine[]')
        quantities = self.request.POST.getlist('quantity[]')
        unit_types = self.request.POST.getlist('unit_type[]')
        
        from decimal import Decimal
        
        for med_id, qty, unit in zip(medicines, quantities, unit_types):
            if med_id and qty:
                medicine = Medicine.objects.get(medicine_id=med_id)
                OrderedProduct.objects.create(
                    ordering=self.object,
                    medicine=medicine,
                    quantity=int(qty),
                    unit_type=unit,
                    unit_price=Decimal(str(medicine.price))
                )
        
        messages.success(self.request, f"Order #{self.object.ordering_id} created successfully!")
        log_activity(self.request.user, f"Created customer order #{self.object.ordering_id} for {self.object.customer_name}")
        
        return redirect(self.success_url)


class OrderingDetailView(LoginRequiredMixin, DetailView):
    """View order details with items"""
    model = Ordering
    template_name = "ordering/ordering_detail.html"
    context_object_name = "order"
    pk_url_kwarg = 'ordering_id'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.object
        
        # Get ordered products
        items = order.ordered_products.select_related('medicine', 'batch').all()
        context['items'] = items
        context['total_amount'] = order.get_total_amount()
        
        # Check stock availability for each item
        availability = []
        for item in items:
            available = sum(
                batch.available_pieces 
                for batch in item.medicine.stockbatch_set.filter(
                    is_deleted=False,
                    is_recalled=False,
                    is_expired=False
                )
            )
            availability.append({
                'item': item,
                'available': available,
                'sufficient': available >= item.pieces_needed
            })
        context['availability'] = availability
        
        return context


class OrderingConfirmView(LoginRequiredMixin, View):
    """Confirm an order (change status to Confirmed)"""
    
    def post(self, request, ordering_id):
        order = get_object_or_404(Ordering, ordering_id=ordering_id)
        
        if order.status != 'Pending':
            messages.error(request, "Only pending orders can be confirmed.")
            return redirect('ordering-detail', ordering_id=ordering_id)
        
        # Check stock availability
        insufficient = []
        for item in order.ordered_products.all():
            available = sum(
                batch.available_pieces 
                for batch in item.medicine.stockbatch_set.filter(
                    is_deleted=False,
                    is_recalled=False,
                    is_expired=False
                )
            )
            if available < item.pieces_needed:
                insufficient.append(f"{item.medicine.name} (need {item.pieces_needed}, have {available})")
        
        if insufficient:
            messages.error(request, f"Insufficient stock: {', '.join(insufficient)}")
            return redirect('ordering-detail', ordering_id=ordering_id)
        
        # Confirm order
        if order.confirm_order(request.user):
            messages.success(request, f"Order #{ordering_id} confirmed!")
            log_activity(request.user, f"Confirmed customer order #{ordering_id}")
        else:
            messages.error(request, "Failed to confirm order.")
        
        return redirect('ordering-detail', ordering_id=ordering_id)


class OrderingReadyView(LoginRequiredMixin, View):
    """Mark order as ready for pickup"""
    
    def post(self, request, ordering_id):
        order = get_object_or_404(Ordering, ordering_id=ordering_id)
        
        if order.mark_ready():
            messages.success(request, f"Order #{ordering_id} marked as ready for pickup!")
            log_activity(request.user, f"Marked order #{ordering_id} as ready")
        else:
            messages.error(request, "Only confirmed orders can be marked as ready.")
        
        return redirect('ordering-detail', ordering_id=ordering_id)


class OrderingCancelView(LoginRequiredMixin, View):
    """Cancel an order"""
    
    def post(self, request, ordering_id):
        order = get_object_or_404(Ordering, ordering_id=ordering_id)
        
        if order.cancel_order():
            messages.success(request, f"Order #{ordering_id} cancelled.")
            log_activity(request.user, f"Cancelled customer order #{ordering_id}")
        else:
            messages.error(request, "Cannot cancel completed orders.")
        
        return redirect('ordering-detail', ordering_id=ordering_id)


class OrderingFulfillView(LoginRequiredMixin, FormView):
    """Fulfill an order by creating a sale and dispensing stock"""
    template_name = "ordering/ordering_fulfill.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ordering_id = self.kwargs['ordering_id']
        order = get_object_or_404(Ordering, ordering_id=ordering_id)
        
        context['order'] = order
        context['items'] = order.ordered_products.select_related('medicine').all()
        context['total_amount'] = order.get_total_amount()
        context['discount_types'] = DiscountType.objects.filter(is_active=True)
        context['payment_methods'] = PaymentMethod.objects.filter(is_active=True)
        
        return context
    
    def post(self, request, ordering_id):
        order = get_object_or_404(Ordering, ordering_id=ordering_id)
        
        if order.status != 'Ready':
            messages.error(request, "Only ready orders can be fulfilled.")
            return redirect('ordering-detail', ordering_id=ordering_id)
        
        from decimal import Decimal
        
        # Get payment details
        discount_type_id = request.POST.get('discount_type')
        payment_method_id = request.POST.get('payment_method')
        cash_received = request.POST.get('cash_received', '0')
        
        # Create sale
        sale = Sale.objects.create(
            user=request.user,
            customer_name=order.customer_name,
            discount_type_fk_id=discount_type_id if discount_type_id else None,
            payment_method_id=payment_method_id if payment_method_id else None,
            status='Completed'
        )
        
        # Create sale line items and dispense stock
        for item in order.ordered_products.all():
            # Dispense stock using FIFO
            pieces_to_dispense = item.pieces_needed
            batches = item.medicine.stockbatch_set.filter(
                is_deleted=False,
                is_recalled=False,
                is_expired=False,
                available_pieces__gt=0
            ).order_by('expiry_date')
            
            for batch in batches:
                if pieces_to_dispense <= 0:
                    break
                
                dispense_qty = min(pieces_to_dispense, batch.available_pieces)
                
                # Create stock movement
                movement = StockMovement.objects.create(
                    batch=batch,
                    movement_type='Sale',
                    quantity=dispense_qty,
                    user=request.user,
                    reference_number=f"ORDER-{ordering_id}"
                )
                
                # Update batch stock
                batch.available_pieces -= dispense_qty
                batch.save(update_fields=['available_pieces'])
                
                pieces_to_dispense -= dispense_qty
            
            # Create sale line item
            SaleLineItem.objects.create(
                sale=sale,
                medicine=item.medicine,
                quantity=item.quantity,
                unit_type=item.unit_type,
                unit_price=item.unit_price,
                line_total=item.line_total,
                pieces_dispensed=item.pieces_needed
            )
        
        # Apply discount and finalize payment
        sale.apply_discount()
        sale.finalize_payment(Decimal(cash_received))
        
        # Link sale to order
        order.sale = sale
        order.status = 'Completed'
        order.completed_date = now()
        order.save(update_fields=['sale', 'status', 'completed_date'])
        
        messages.success(request, f"Order #{ordering_id} fulfilled! Invoice: {sale.invoice_number}")
        log_activity(request.user, f"Fulfilled customer order #{ordering_id} -> Sale #{sale.sale_id}")
        
        return redirect('invoice', pk=sale.sale_id)


# ========================================
# PURCHASE ORDER VIEWS
# ========================================

class PurchaseOrderForm(forms.ModelForm):
    expected_delivery_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        label='Expected Delivery Date'
    )
    po_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        label='PO Date'
    )
    
    class Meta:
        from base.models import PurchaseOrder
        model = PurchaseOrder
        fields = ['supplier', 'po_date', 'expected_delivery_date', 'status', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

@login_required
def purchase_order_list_modal(request):
    """Display all purchase orders in modal"""
    from base.models import PurchaseOrder
    purchase_orders = PurchaseOrder.objects.filter(is_deleted=False).select_related('supplier', 'created_by').prefetch_related('lines__medicine').all()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        from django.template.loader import render_to_string
        html = render_to_string('medicine/partials/purchase_order_list_modal.html', {
            'purchase_orders': purchase_orders
        })
        return JsonResponse({'html': html})
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
@manager_required
def purchase_order_list(request):
    """List all purchase orders"""
    from base.models import PurchaseOrder
    purchase_orders = PurchaseOrder.objects.filter(is_deleted=False).select_related('supplier', 'created_by').prefetch_related('lines__medicine').order_by('-created_at')
    
    context = {
        'purchase_orders': purchase_orders,
        'is_manager_or_admin': is_manager_or_admin(request.user),
        'user_role': get_user_role_display(request.user)
    }
    return render(request, 'medicine/purchase_order_list.html', context)

@login_required
@manager_required
def purchase_order_add(request):
    """Create new purchase order - regular page"""
    from base.models import PurchaseOrder, PurchaseOrderLine, Supplier, Medicine
    
    if request.method == 'POST':
        try:
            # Get or create default supplier
            supplier = Supplier.objects.filter(is_deleted=False, status='Active').first()
            if not supplier:
                supplier = Supplier.objects.create(
                    name='Default Supplier',
                    contact_person='',
                    phone='',
                    email='',
                    address='',
                    status='Active'
                )
            
            # Create purchase order
            po = PurchaseOrder.objects.create(
                supplier=supplier,
                po_date=timezone.now().date(),
                expected_delivery_date=timezone.now().date(),
                status='Draft',
                notes=request.POST.get('notes', ''),
                created_by=request.user
            )
            
            # Create line items
            medicine_ids = request.POST.getlist('medicine[]')
            quantities = request.POST.getlist('quantity[]')
            manufactured_dates = request.POST.getlist('manufactured_date[]')
            expiration_dates = request.POST.getlist('expiration_date[]')
            
            for i, medicine_id in enumerate(medicine_ids):
                if medicine_id:
                    medicine = Medicine.objects.get(id=medicine_id)
                    PurchaseOrderLine.objects.create(
                        purchase_order=po,
                        medicine=medicine,
                        quantity_ordered=int(quantities[i]),
                        unit='box',
                        unit_cost=0,
                        manufactured_date=manufactured_dates[i] if i < len(manufactured_dates) else None,
                        expiration_date=expiration_dates[i] if i < len(expiration_dates) else None,
                        remarks=''
                    )
            
            log_activity(request.user, f"Created purchase order #{po.id} with {len(medicine_ids)} items")
            messages.success(request, f"Purchase order #{po.id} created successfully!")
            return redirect('purchase-order-list')
            
        except Exception as e:
            messages.error(request, f"Error creating purchase order: {str(e)}")
            return redirect('purchase-order-add')
    
    # GET request - show form
    medicines = Medicine.objects.filter(is_deleted=False).order_by('name')
    context = {
        'medicines': medicines,
        'is_manager_or_admin': is_manager_or_admin(request.user),
        'user_role': get_user_role_display(request.user)
    }
    return render(request, 'medicine/purchase_order_form.html', context)

@login_required
def purchase_order_add_modal(request):
    """Create new purchase order via modal"""
    from base.models import PurchaseOrder, PurchaseOrderLine, Supplier, Medicine
    
    if request.method == 'POST':
        try:
            # Get or create default supplier
            supplier = Supplier.objects.filter(is_deleted=False, status='Active').first()
            if not supplier:
                supplier = Supplier.objects.create(
                    name='Default Supplier',
                    contact_person='',
                    phone='',
                    email='',
                    address='',
                    status='Active'
                )
            
            # Create purchase order
            po = PurchaseOrder.objects.create(
                supplier=supplier,
                po_date=timezone.now().date(),
                expected_delivery_date=timezone.now().date(),
                status='Draft',
                notes=request.POST.get('notes', ''),
                created_by=request.user
            )
            
            # Create line items
            medicine_ids = request.POST.getlist('medicine[]')
            quantities = request.POST.getlist('quantity[]')
            
            for i, medicine_id in enumerate(medicine_ids):
                if medicine_id:
                    medicine = Medicine.objects.get(id=medicine_id)
                    PurchaseOrderLine.objects.create(
                        purchase_order=po,
                        medicine=medicine,
                        quantity_ordered=int(quantities[i]),
                        unit='box',
                        unit_cost=0,
                        remarks=''
                    )
            
            log_activity(request.user, f"Created purchase order #{po.id} with {len(medicine_ids)} items")
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True})
        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': str(e)}, status=400)
    
    # GET request - show form
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        from django.template.loader import render_to_string
        medicines = Medicine.objects.filter(is_deleted=False).order_by('name')
        html = render_to_string('medicine/partials/purchase_order_form_modal.html', {
            'medicines': medicines
        })
        return JsonResponse({'html': html})
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def purchase_order_update_modal(request, pk):
    """Update existing purchase order via modal"""
    from base.models import PurchaseOrder
    po = get_object_or_404(PurchaseOrder, pk=pk, is_deleted=False)
    
    if request.method == 'POST':
        form = PurchaseOrderForm(request.POST, instance=po)
        if form.is_valid():
            po = form.save()
            log_activity(request.user, f"Updated purchase order #{po.id} - Status: {po.status}")
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True})
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                from django.template.loader import render_to_string
                html = render_to_string('medicine/partials/purchase_order_form_modal.html', {
                    'form': form,
                    'purchase_order': po
                })
                return JsonResponse({'html': html})
    else:
        form = PurchaseOrderForm(instance=po)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        from django.template.loader import render_to_string
        html = render_to_string('medicine/partials/purchase_order_form_modal.html', {
            'form': form,
            'purchase_order': po
        })
        return JsonResponse({'html': html})
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def purchase_order_delete(request, pk):
    """Delete purchase order"""
    from base.models import PurchaseOrder
    po = get_object_or_404(PurchaseOrder, pk=pk)
    
    if request.method == 'POST':
        po.is_deleted = True
        po.save()
        log_activity(request.user, f"Deleted purchase order #{po.id}")
        messages.success(request, f"Purchase order #{po.id} deleted successfully.")
    
    return redirect('batch-list')

@login_required
def purchase_order_update_status(request, pk):
    """Quick update purchase order status"""
    from base.models import PurchaseOrder
    
    if request.method == 'POST':
        po = get_object_or_404(PurchaseOrder, pk=pk, is_deleted=False)
        
        # Handle both form POST and JSON
        if request.content_type == 'application/json':
            import json
            data = json.loads(request.body)
            new_status = data.get('status', '')
        else:
            new_status = request.POST.get('status', '')
        
        valid_statuses = ['Draft', 'Ordered', 'Received']
        if new_status in valid_statuses:
            po.status = new_status
            po.save()
            log_activity(request.user, f"Updated PO #{po.id} status to {new_status}")
            
            if request.content_type == 'application/json':
                return JsonResponse({'success': True})
            else:
                messages.success(request, f"Order #{po.id} status updated to {new_status}")
                return redirect('purchase-order-list')
        
        if request.content_type == 'application/json':
            return JsonResponse({'error': 'Invalid status'}, status=400)
        else:
            messages.error(request, 'Invalid status')
            return redirect('purchase-order-list')
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def purchase_order_lines(request, pk):
    """Get lines for a purchase order (for batch creation)"""
    from base.models import PurchaseOrder
    po = get_object_or_404(PurchaseOrder, pk=pk, is_deleted=False, status='Received')
    
    lines_data = []
    for line in po.lines.all():
        lines_data.append({
            'id': line.id,
            'medicine_name': line.medicine.name,
            'quantity': line.quantity_ordered
        })
    
    return JsonResponse({'lines': lines_data})

# --------------------------- NOTIFICATIONS ---------------------------
class NotificationListView(LoginRequiredMixin, ListView):
    """View all notifications for the current user"""
    model = Notification
    template_name = 'notifications/notification_list.html'
    context_object_name = 'notifications'
    paginate_by = 20
    
    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_manager_or_admin'] = is_manager_or_admin(self.request.user)
        context['user_role'] = get_user_role_display(self.request.user)
        context['unread_count'] = Notification.objects.filter(
            user=self.request.user,
            is_read=False
        ).count()
        return context

@login_required
def mark_notification_read(request, pk):
    """Mark a notification as read"""
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.is_read = True
    notification.save()
    
    # Redirect to related page if available
    next_url = request.GET.get('next', 'notification-list')
    return redirect(next_url)

@login_required
def mark_all_notifications_read(request):
    """Mark all notifications as read for current user"""
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    messages.success(request, "All notifications marked as read")
    return redirect('notification-list')

@login_required
def delete_notification(request, pk):
    """Delete a notification"""
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.delete()
    messages.success(request, "Notification deleted")
    return redirect('notification-list')
