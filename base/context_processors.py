from base.models import Notification

def notifications_processor(request):
    """Add unread notifications count to template context"""
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(
            user=request.user,
            is_read=False
        ).count()
        return {'unread_notifications': unread_count}
    return {'unread_notifications': 0}
