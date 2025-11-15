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

        # Initially, no product types are shown until a category is selected
        self.fields['product_type'].queryset = ProductType.objects.none()

        if 'category' in self.data:
            try:
                category_id = int(self.data.get('category'))
                self.fields['product_type'].queryset = ProductType.objects.filter(category_id=category_id).order_by('name')
            except (ValueError, TypeError):
                pass  # invalid input; ignore
        elif self.instance.pk and self.instance.category:
            # When editing an existing instance
            self.fields['product_type'].queryset = ProductType.objects.filter(category=self.instance.category).order_by('name')

class StockTransferForm(forms.ModelForm):
    quantity = forms.IntegerField(
        min_value=0,
        required=True,
        label="Quantity to Transfer"
    )
    destination = forms.CharField(
        max_length=255,
        required=True,
        label="Destination Location"
    )

    class Meta:
        model = StockBatch
        fields = ['batch', 'quantity', 'destination']

    batch = forms.ModelChoiceField(
        queryset=StockBatch.objects.filter(quantity__gt=0).select_related('medicine'),
        label="Batch",
    )