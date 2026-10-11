from django import forms

from .models import FoodItem, PriceObservation


class FoodItemForm(forms.ModelForm):
    class Meta:
        model = FoodItem
        fields = [
            'name',
            'item_type',
            'brand',
            'nutrition_basis_unit',
            'calories_per_100',
            'protein_per_100',
            'carbohydrates_per_100',
            'fat_per_100',
            'nutrition_source',
        ]
        labels = {
            'name': 'Name',
            'item_type': 'Type',
            'brand': 'Brand',
            'nutrition_basis_unit': 'Nutrition basis',
            'calories_per_100': 'Calories per 100 g/ml',
            'protein_per_100': 'Protein per 100 g/ml',
            'carbohydrates_per_100': 'Carbohydrates per 100 g/ml',
            'fat_per_100': 'Fat per 100 g/ml',
            'nutrition_source': 'Nutrition source',
        }
        help_texts = {
            'nutrition_basis_unit': 'Choose grams or millilitres. Consumption and package units must match.',
            'calories_per_100': 'Leave blank when the value is unknown. Blank is not treated as zero.',
            'protein_per_100': 'Leave blank when the value is unknown. Blank is not treated as zero.',
            'carbohydrates_per_100': 'Leave blank when the value is unknown. Blank is not treated as zero.',
            'fat_per_100': 'Leave blank when the value is unknown. Blank is not treated as zero.',
            'nutrition_source': 'For example: package label, manual estimate, or imported source.',
        }
        widgets = {
            'calories_per_100': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'protein_per_100': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'carbohydrates_per_100': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'fat_per_100': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }


class PriceObservationForm(forms.ModelForm):
    observed_at = forms.DateTimeField(
        input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M'],
        widget=forms.DateTimeInput(
            format='%Y-%m-%dT%H:%M',
            attrs={'type': 'datetime-local'},
        ),
    )

    class Meta:
        model = PriceObservation
        fields = [
            'package_quantity',
            'package_unit',
            'paid_price',
            'reference_price',
            'currency',
            'observed_at',
            'source',
        ]
        labels = {
            'package_quantity': 'Package quantity',
            'package_unit': 'Package unit',
            'paid_price': 'Actual paid price',
            'reference_price': 'Reference price',
            'currency': 'Currency',
            'observed_at': 'Observed date and time',
            'source': 'Price source',
        }
        help_texts = {
            'package_quantity': 'Must use the same unit as the food item nutrition basis.',
            'paid_price': 'This is the actual price paid and is used for estimated consumption cost.',
            'reference_price': 'Optional normal or reference price for comparison.',
            'source': 'For example: supermarket, receipt, or manual observation.',
        }
        widgets = {
            'package_quantity': forms.NumberInput(attrs={'step': '0.001', 'min': '0.001'}),
            'paid_price': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'reference_price': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }

    def __init__(self, food_item, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.food_item = food_item
        self.instance.food_item = food_item
        self.fields['package_unit'].initial = food_item.nutrition_basis_unit

    def clean_package_unit(self):
        package_unit = self.cleaned_data['package_unit']
        if package_unit != self.food_item.nutrition_basis_unit:
            raise forms.ValidationError(
                'Package unit must match this food item nutrition basis.'
            )
        return package_unit
