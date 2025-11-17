from django.urls import path
# from . import views
from . views import (
    CustomLoginView, RegsiterPage, LandingPageView, UpdateAccountView, UpdatePasswordView,
    UserListView, BlockUnblockUserView, DashboardView, ActivityLogListView, MedicineListView, MedicineCreateView, MedicineDeleteView, MedicineUpdateView, 
    StockBatchListView, StockBatchCreateView, StockBatchDeleteView, StockBatchUpdateView, DispenseView, StockMovementListView, SalesReportView, process_expired_stock_view,
    PriceHistoryView, ActualInventoryView, ExpirationMonitorView, MedicinePriceUpdateView,
    medicine_update_modal, medicine_price_update_modal, batch_update_modal,
    medicine_create_modal, batch_create_modal, batch_recall_modal, load_product_types,
    RefundCreateView, RefundListView, RefundDetailView, RefundApproveView,
    OrderingListView, OrderingCreateView, OrderingDetailView, OrderingConfirmView, OrderingReadyView, OrderingCancelView, OrderingFulfillView,
    NotificationListView, mark_notification_read, mark_all_notifications_read, delete_notification
    )
from . import views
from django.urls import reverse_lazy
from django.contrib.auth.views import LogoutView

urlpatterns = [

    path('', LandingPageView.as_view(), name = 'landingpage'),
    path('about/', views.about, name='about'),
    path('services/', views.services, name='services'),
    path('contact/', views.contact, name='contact'),
    path('login/', CustomLoginView.as_view(), name = 'login'),
    # path('logout/', LogoutView.as_view(next_page = 'login'), name = 'logout'),
    path('logout/', LogoutView.as_view(next_page=reverse_lazy('landingpage')), name='logout'),
    path('register/', RegsiterPage.as_view(), name = 'register'),
    path('account/update/', UpdateAccountView.as_view(), name='update-account'),
    path('account/password/', UpdatePasswordView.as_view(), name='update-password'),
    path('users/', UserListView.as_view(), name='user-list'),
    path('users/create-ajax/', views.create_user_ajax, name='create-user-ajax'),
    path('users/<int:user_id>/update-account-ajax/', views.update_user_account_ajax, name='update-user-account-ajax'),
    path('users/<int:user_id>/update-password-ajax/', views.update_user_password_ajax, name='update-user-password-ajax'),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path("users/<int:pk>/toggle-block/", BlockUnblockUserView.as_view(), name="toggle-block"),
    path("activity-logs/", ActivityLogListView.as_view(), name="activity-logs"),
    path("medicines/", MedicineListView.as_view(), name="medicine-list"),
    path("medicines/add/", MedicineCreateView.as_view(), name="medicine-add"),
    path("medicines/add-modal/", medicine_create_modal, name="medicine-add-modal"),
    path("medicines/<int:pk>/update/", MedicineUpdateView.as_view(), name="medicine-update"),
    path("medicines/<int:pk>/update-price/", MedicinePriceUpdateView.as_view(), name="medicine-price-update"),
    path("medicines/<int:pk>/update-modal/", medicine_update_modal, name="medicine-update-modal"),
    path("medicines/<int:pk>/price-modal/", medicine_price_update_modal, name="medicine-price-update-modal"),
    path("medicines/<int:pk>/delete/", MedicineDeleteView.as_view(), name="medicine-delete"),
    path("api/product-types/", load_product_types, name="load-product-types"),
    path("batches/", StockBatchListView.as_view(), name="batch-list"),
    path("batches/add/", StockBatchCreateView.as_view(), name="batch-add"),
    path("batches/add-modal/", batch_create_modal, name="batch-add-modal"),
    path("batches/receive/", views.batch_receive_form, name="batch-receive"),
    path("batches/<int:pk>/update/", StockBatchUpdateView.as_view(), name="batch-update"),
    path("batches/<int:pk>/update-modal/", batch_update_modal, name="batch-update-modal"),
    path("batches/<int:pk>/recall-modal/", batch_recall_modal, name="batch-recall-modal"),
    path("batches/<int:pk>/delete/", StockBatchDeleteView.as_view(), name="batch-delete"),
    path("batches/<int:pk>/stockout-expired/", views.batch_stockout_expired, name="batch-stockout-expired"),
    path("dispense/", DispenseView.as_view(), name="dispense"),
    path("movements/", StockMovementListView.as_view(), name="movement-list"),
    path("invoice/<int:sale_id>/", views.view_invoice, name="view_invoice"),
    path("refunds/", RefundListView.as_view(), name="refund-list"),
    path("refunds/new/", RefundCreateView.as_view(), name="refund-create"),
    path("refunds/<int:pk>/", RefundDetailView.as_view(), name="refund-detail"),
    path("refunds/<int:pk>/modal/", views.refund_detail_modal, name="refund-detail-modal"),
    path("refunds/<int:pk>/approve/", RefundApproveView.as_view(), name="refund-approve"),
    path("report/", SalesReportView.as_view(), name="sales-report"),
    path('process-expired-stock/', process_expired_stock_view, name='process_expired_stock'),
    path('transfer/', views.TransferView.as_view(), name='transfer'),
    path('price-history/', PriceHistoryView.as_view(), name='price-history'),
    path('actual-inventory/', ActualInventoryView.as_view(), name='actual-inventory'),
    path('expiration-monitor/', ExpirationMonitorView.as_view(), name='expiration-monitor'),
    
    # Customer Ordering URLs
    path('orders/', OrderingListView.as_view(), name='ordering-list'),
    path('orders/new/', OrderingCreateView.as_view(), name='ordering-create'),
    path('orders/<int:ordering_id>/', OrderingDetailView.as_view(), name='ordering-detail'),
    path('orders/<int:ordering_id>/confirm/', OrderingConfirmView.as_view(), name='ordering-confirm'),
    path('orders/<int:ordering_id>/ready/', OrderingReadyView.as_view(), name='ordering-ready'),
    path('orders/<int:ordering_id>/cancel/', OrderingCancelView.as_view(), name='ordering-cancel'),
    path('orders/<int:ordering_id>/fulfill/', OrderingFulfillView.as_view(), name='ordering-fulfill'),
    
    # Purchase Order URLs
    path('purchase-order/', views.purchase_order_list, name='purchase-order-list'),
    path('purchase-order/add/', views.purchase_order_add, name='purchase-order-add'),
    path('purchase-order/<int:pk>/lines/', views.purchase_order_lines, name='purchase-order-lines'),
    path('purchase-order/list-modal/', views.purchase_order_list_modal, name='purchase-order-list-modal'),
    path('purchase-order/add-modal/', views.purchase_order_add_modal, name='purchase-order-add-modal'),
    path('purchase-order/<int:pk>/edit-modal/', views.purchase_order_update_modal, name='purchase-order-update-modal'),
    path('purchase-order/<int:pk>/update-status/', views.purchase_order_update_status, name='purchase-order-update-status'),
    path('purchase-order/<int:pk>/delete/', views.purchase_order_delete, name='purchase-order-delete'),
    
    # Notification URLs
    path('notifications/', NotificationListView.as_view(), name='notification-list'),
    path('notifications/<int:pk>/mark-read/', mark_notification_read, name='notification-mark-read'),
    path('notifications/mark-all-read/', mark_all_notifications_read, name='notification-mark-all-read'),
    path('notifications/<int:pk>/delete/', delete_notification, name='notification-delete'),
]
