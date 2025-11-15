from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.timezone import now

from base.models import Sale, OrderedProduct, Ordering


class Command(BaseCommand):
    help = "Backfill Ordering and OrderedProduct from historical Sale and SaleLineItem records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate the backfill without writing to the database",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of sales to process (useful for batches)",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options["limit"]

        # Select sales that do NOT already have an associated Ordering via reverse OneToOne 'customer_order'
        sales_qs = Sale.objects.all().order_by("sale_id").filter(customer_order__isnull=True)
        if limit:
            sales_qs = sales_qs[:limit]

        total_sales = sales_qs.count()
        if total_sales == 0:
            self.stdout.write(self.style.WARNING("No sales found that require backfill."))
            return

        created_orders = 0
        created_items = 0

        self.stdout.write(
            f"Starting backfill for {total_sales} sale(s). Dry run: {'YES' if dry_run else 'NO'}"
        )

        for sale in sales_qs.iterator():
            line_items = sale.line_items.select_related("medicine").all()
            if not line_items:
                # Skip empty sales to avoid creating empty orders
                continue

            # Determine an appropriate order status mapped from sale status
            order_status = "Completed" if (sale.status or "").lower() == "completed" else "Confirmed"

            def create_order_and_items():
                order = Ordering.objects.create(
                    user=sale.user,
                    customer_name=sale.customer_name or "",
                    customer_contact="",
                    status=order_status,
                    notes="Backfilled from historical Sale",
                    sale=sale,
                    completed_date=now() if order_status == "Completed" else None,
                )

                nonlocal created_items
                for line in line_items:
                    OrderedProduct.objects.create(
                        ordering=order,
                        medicine=line.medicine,
                        quantity=line.quantity,
                        unit_type=line.unit_type,
                        unit_price=line.unit_price,
                    )
                    created_items += 1

                return order

            if dry_run:
                # Simulate only
                created_orders += 1
                created_items += line_items.count()
            else:
                with transaction.atomic():
                    create_order_and_items()
                    created_orders += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Backfill complete. Orders created: {created_orders}; OrderedProducts created: {created_items}."
            )
        )
