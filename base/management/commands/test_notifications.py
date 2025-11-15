from django.core.management.base import BaseCommand
from base.views import generate_notifications

class Command(BaseCommand):
    help = "Test notification generation by manually triggering the notification system"

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Testing notification generation..."))
        
        try:
            generate_notifications()
            self.stdout.write(self.style.SUCCESS("✓ Notification generation completed!"))
            self.stdout.write("")
            self.stdout.write("Next steps to verify:")
            self.stdout.write("1. Log in as a Manager/Admin user")
            self.stdout.write("2. Check the notification badge in the sidebar")
            self.stdout.write("3. Click 'Notifications' to see generated alerts")
            self.stdout.write("")
            self.stdout.write("Notifications are generated for:")
            self.stdout.write("  • Batches expiring within 30 days")
            self.stdout.write("  • Medicines with less than 7 days of stock")
            self.stdout.write("  • Medicines with less than 20 pieces")
            self.stdout.write("  • Medicines that are out of stock")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Error: {str(e)}"))
