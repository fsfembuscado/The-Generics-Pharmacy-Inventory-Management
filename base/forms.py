from django import forms
from .models import Medicine, Category, ProductType, StockBatch

class MedicineForm(forms.ModelForm):
    class Meta:
        model = Medicine
        fields = [
            "name", "brand", "category", "product_type",
            "dosage_form", "strength",
            "units_per_pack", "packs_per_box",
            "base_price", "selling_price", "description"
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add placeholders to all fields
        self.fields['name'].widget.attrs.update({'placeholder': 'Enter medicine name (e.g., Paracetamol)'})
        self.fields['brand'].widget.attrs.update({'placeholder': 'Enter brand name (e.g., Biogesic)'})
        self.fields['dosage_form'].widget.attrs.update({'placeholder': 'Enter dosage form (e.g., Tablet, Capsule, Syrup)'})
        self.fields['strength'].widget.attrs.update({'placeholder': 'Enter strength (e.g., 500mg, 250mg/5mL)'})
        self.fields['units_per_pack'].widget.attrs.update({'placeholder': 'Number of pieces per pack'})
        self.fields['packs_per_box'].widget.attrs.update({'placeholder': 'Number of packs per box'})
        self.fields['base_price'].widget.attrs.update({'placeholder': 'Enter base price (e.g., 5.50)'})
        self.fields['selling_price'].widget.attrs.update({'placeholder': 'Enter selling price (e.g., 7.00)'})
        self.fields['description'].widget.attrs.update({'placeholder': 'Enter product description (optional)'})

        # Show all product types initially, will be filtered by JavaScript when category changes
        self.fields['product_type'].queryset = ProductType.objects.filter(is_deleted=False).order_by('name')
        self.fields['product_type'].required = False  # Make optional since it depends on category

        if 'category' in self.data:
            try:
                category_id = int(self.data.get('category'))
                self.fields['product_type'].queryset = ProductType.objects.filter(category_id=category_id, is_deleted=False).order_by('name')
            except (ValueError, TypeError):
                pass  # invalid input; ignore
        elif self.instance.pk and self.instance.category:
            # When editing an existing instance
            self.fields['product_type'].queryset = ProductType.objects.filter(category=self.instance.category, is_deleted=False).order_by('name')

class StockTransferForm(forms.ModelForm):
    quantity = forms.IntegerField(
        min_value=0,
        required=True,
        label="Quantity to Transfer",
        widget=forms.NumberInput(attrs={'placeholder': 'Enter quantity'})
    )
    destination = forms.CharField(
        max_length=255,
        required=True,
        label="Destination Location",
        widget=forms.TextInput(attrs={'placeholder': 'Enter destination (e.g., Branch 2, Warehouse A)'})
    )

    class Meta:
        model = StockBatch
        fields = ['batch', 'quantity', 'destination']

    batch = forms.ModelChoiceField(
        queryset=StockBatch.objects.filter(quantity__gt=0).select_related('medicine'),
        label="Batch",
    )