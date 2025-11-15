# Notification System Implementation

## Overview
A comprehensive notification system has been implemented to alert managers and admins about:
1. **Near-Expiry Products** - Medicines expiring within 30 days
2. **Low Stock** - Products with less than 7 days of stock or below 20 pieces
3. **Out of Stock** - Products with zero inventory

## Features

### Automatic Notification Generation
- Notifications are automatically generated when managers/admins access the dashboard
- System checks for:
  - Batches expiring within 30 days
  - Medicines with less than 7 days of stock based on sales velocity
  - Medicines with less than 20 pieces in stock
  - Medicines that are completely out of stock

### Notification Types
1. **Near Expiry (⚠️)** - Orange badge
   - Shows batch number, medicine name, days until expiry, and current stock
   - Example: "Batch #123 of Amoxicillin will expire in 15 days"

2. **Low Stock (📦)** - Red badge
   - Shows medicine name, current stock, and reorder recommendation
   - Calculates based on 30-day sales velocity
   - Example: "Paracetamol has only 3.5 days of stock remaining"

3. **Out of Stock (🚫)** - Dark red badge
   - Alerts when medicine inventory reaches zero
   - Example: "Ibuprofen is currently out of stock. Please reorder immediately"

### User Interface
- **Notification Bell Icon** in sidebar (only visible to managers/admins)
- **Red Badge** showing unread notification count
- **Notification List Page** with:
  - Color-coded notification cards
  - Unread notifications highlighted in blue
  - Mark as read / Delete actions
  - "Mark All as Read" bulk action
  - Timestamp for each notification

### Access Control
- Notifications are only generated for Manager and Admin users
- Staff users do not see notifications
- Each user only sees their own notifications

### Database Schema
**Notification Model Fields:**
- `notification_id` - Primary key
- `user` - Foreign key to User
- `notification_type` - Choice field (expiry, low_stock, out_of_stock)
- `title` - Notification title
- `message` - Detailed message
- `related_medicine` - Optional foreign key to Medicine
- `related_batch` - Optional foreign key to StockBatch
- `is_read` - Boolean flag
- `created_at` - Timestamp

## URLs
- `/notifications/` - View all notifications
- `/notifications/<id>/mark-read/` - Mark notification as read
- `/notifications/mark-all-read/` - Mark all as read
- `/notifications/<id>/delete/` - Delete notification

## Technical Implementation
- **Context Processor**: `base.context_processors.notifications_processor`
  - Adds `unread_notifications` count to all templates
- **Helper Function**: `generate_notifications()`
  - Called from DashboardView for managers
  - Prevents duplicate notifications
- **Views**: NotificationListView, mark_notification_read, mark_all_notifications_read, delete_notification
- **Template**: `base/templates/notifications/notification_list.html`

## Stock Calculation Logic
**Low Stock Determination:**
1. Calculate daily sales rate: (last 30 days sales) / 30
2. Calculate days of stock: current_stock / daily_sales
3. Trigger notification if:
   - Days of stock < 7 AND has sales history, OR
   - Current stock < 20 pieces

**Near Expiry:**
- Checks batches with expiration_date <= 30 days from now
- Only includes batches with quantity > 0

## Usage
Managers/admins will see:
1. Notification bell icon in sidebar with unread count badge
2. Notifications automatically generated on dashboard visit
3. Click bell icon to view all notifications
4. Take action based on notification type (reorder, transfer stock, etc.)

## Future Enhancements
- Email notifications for critical alerts
- Configurable threshold settings (days, quantities)
- Notification preferences per user
- Push notifications
- Notification history/archive
