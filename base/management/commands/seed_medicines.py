from django.core.management.base import BaseCommand
from django.db import transaction
from base.models import Category, ProductType, Medicine

# NOTE: Prices are illustrative approximate per-piece Philippine peso values for generic medicines.
# They are not official TGP price lists.

CATEGORIES = {
    "Analgesics": {
        "description": "Pain relievers and antipyretics",
        "product_types": ["Pain Relief", "Fever"]
    },
    "Antibiotics": {
        "description": "Common oral antimicrobial agents",
        "product_types": ["Systemic Antibiotic"]
    },
    "Antihistamines": {
        "description": "Allergy symptom relief",
        "product_types": ["Allergy"]
    },
    "Gastrointestinal": {
        "description": "GI symptom management",
        "product_types": ["Acid Reducer", "Antidiarrheal"]
    },
    "Cardiovascular": {
        "description": "Blood pressure and heart medications",
        "product_types": ["Hypertension"]
    },
    "Endocrine": {
        "description": "Blood sugar management",
        "product_types": ["Diabetes"]
    },
    "Respiratory": {
        "description": "Bronchodilators and respiratory relief",
        "product_types": ["Bronchodilator"]
    },
    "Vitamins": {
        "description": "Nutritional supplements",
        "product_types": ["Supplement"]
    }
}

MEDICINES = [
    # name, brand, category, product_type, dosage_form, strength, units_per_pack, packs_per_box, base_price, selling_price, description
    ("Paracetamol", "TGP", "Analgesics", "Pain Relief", "tablet", "500 mg", 10, 10, 1.20, 1.75, "Generic analgesic/antipyretic for mild to moderate pain and fever."),
    ("Ibuprofen", "TGP", "Analgesics", "Pain Relief", "tablet", "200 mg", 10, 10, 2.00, 2.75, "NSAID for pain, inflammation, and fever; take with food."),
    ("Amoxicillin", "TGP", "Antibiotics", "Systemic Antibiotic", "capsule", "500 mg", 10, 10, 5.00, 7.00, "Broad-spectrum penicillin-class antibiotic; complete full course."),
    ("Cetirizine", "TGP", "Antihistamines", "Allergy", "tablet", "10 mg", 10, 10, 3.00, 4.25, "Non-sedating antihistamine for allergic rhinitis and urticaria."),
    ("Loperamide", "TGP", "Gastrointestinal", "Antidiarrheal", "capsule", "2 mg", 10, 10, 2.00, 2.75, "Antidiarrheal for acute non-infectious diarrhea; hydrate adequately."),
    ("Omeprazole", "TGP", "Gastrointestinal", "Acid Reducer", "capsule", "20 mg", 10, 10, 6.00, 8.50, "Proton pump inhibitor for acid-related disorders; best before meals."),
    ("Amlodipine", "TGP", "Cardiovascular", "Hypertension", "tablet", "5 mg", 10, 10, 4.00, 5.50, "Calcium channel blocker for hypertension; once daily dosing."),
    ("Metformin", "TGP", "Endocrine", "Diabetes", "tablet", "500 mg", 10, 10, 2.50, 3.50, "First-line biguanide for type 2 diabetes; take with meals."),
    ("Salbutamol", "TGP", "Respiratory", "Bronchodilator", "tablet", "2 mg", 10, 10, 2.80, 3.80, "Short-acting bronchodilator for reversible airway obstruction."),
    ("Vitamin C", "TGP", "Vitamins", "Supplement", "tablet", "500 mg", 10, 10, 1.00, 1.50, "Ascorbic acid supplement supporting immune function.")
]

class Command(BaseCommand):
    help = "Seed base categories, product types, and generic medicines with realistic per-piece pricing."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Starting medicine seeding..."))
        created_categories = 0
        created_product_types = 0
        created_medicines = 0
        skipped_medicines = 0
        failed_medicines = 0

        with transaction.atomic():
            # Categories and Product Types
            category_objs = {}
            product_type_map = {}
            for cat_name, meta in CATEGORIES.items():
                cat_obj, cat_created = Category.objects.get_or_create(name=cat_name, defaults={"description": meta.get("description", "")})
                if cat_created:
                    created_categories += 1
                category_objs[cat_name] = cat_obj
                for pt_name in meta.get("product_types", []):
                    pt_obj, pt_created = ProductType.objects.get_or_create(category=cat_obj, name=pt_name)
                    if pt_created:
                        created_product_types += 1
                    product_type_map[(cat_name, pt_name)] = pt_obj

            # Medicines
            from decimal import Decimal
            for (name, brand, cat_name, pt_name, dosage_form, strength, units_per_pack, packs_per_box, base_price, selling_price, description) in MEDICINES:
                cat_obj = category_objs.get(cat_name)
                pt_obj = product_type_map.get((cat_name, pt_name))
                if not cat_obj or not pt_obj:
                    self.stdout.write(self.style.WARNING(f"Skipping {name}: missing category/product type."))
                    skipped_medicines += 1
                    continue
                existing = Medicine.objects.filter(name=name, strength=strength, brand=brand).first()
                if existing:
                    skipped_medicines += 1
                    continue
                try:
                    Medicine.objects.create(
                        name=name,
                        brand=brand,
                        category=cat_obj,
                        product_type=pt_obj,
                        dosage_form=dosage_form,
                        strength=strength,
                        units_per_pack=units_per_pack,
                        packs_per_box=packs_per_box,
                        base_price=Decimal(str(base_price)),
                        selling_price=Decimal(str(selling_price)),
                        description=description
                    )
                    created_medicines += 1
                except Exception as e:
                    failed_medicines += 1
                    self.stdout.write(self.style.ERROR(f"Failed to create {name}: {e}"))

        self.stdout.write(self.style.SUCCESS("Seeding complete."))
        self.stdout.write(f"Categories created: {created_categories}")
        self.stdout.write(f"Product types created: {created_product_types}")
        self.stdout.write(f"Medicines created: {created_medicines}")
        self.stdout.write(f"Medicines skipped (already existed): {skipped_medicines}")
        self.stdout.write(f"Medicines failed: {failed_medicines}")
        self.stdout.write("NOTE: Prices are illustrative generic per-piece values, not official TGP pricing.")
