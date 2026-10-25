from django import forms
from django.forms import formset_factory
from django.utils import timezone

from .models import (
    ConsumptionEntry,
    FoodItem,
    MealPrepBatch,
    PriceObservation,
    Recipe,
    RecipeIngredient,
)
from .services.calculations import select_price_observation


class MealPrepBatchForm(forms.ModelForm):
    cooked_at = forms.DateTimeField(
        input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M'],
        widget=forms.DateTimeInput(
            format='%Y-%m-%dT%H:%M',
            attrs={'type': 'datetime-local'},
        ),
    )

    class Meta:
        model = MealPrepBatch
        fields = ['name', 'recipe', 'cooked_at', 'yield_quantity', 'yield_unit']
        labels = {
            'name': 'Batch name',
            'recipe': 'Source Recipe',
            'cooked_at': 'Cooked date and time',
            'yield_quantity': 'Final yield',
            'yield_unit': 'Yield unit',
        }
        help_texts = {
            'recipe': 'Optional. Planned ingredients can be loaded and then adjusted below.',
            'yield_quantity': 'Enter the finished batch weight or volume.',
        }
        widgets = {
            'yield_quantity': forms.NumberInput(attrs={'step': '0.001', 'min': '0.001'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['recipe'].required = False
        self.fields['recipe'].queryset = Recipe.objects.order_by('name', 'id')
        if not self.is_bound and not self.initial.get('cooked_at'):
            self.initial['cooked_at'] = timezone.localtime(
                timezone.now(),
            ).strftime('%Y-%m-%dT%H:%M')


class BatchIngredientForm(forms.Form):
    """Collect actual batch inputs; snapshot values are created by the batch service."""

    food_item = forms.ModelChoiceField(
        queryset=FoodItem.objects.order_by('name', 'brand'),
        required=False,
        label='Food item',
        widget=forms.Select(attrs={'aria-label': 'Food item'}),
    )
    quantity = forms.DecimalField(
        required=False,
        max_digits=10,
        decimal_places=3,
        min_value=0.001,
        label='Actual quantity',
        widget=forms.NumberInput(attrs={
            'step': '0.001',
            'min': '0.001',
            'aria-label': 'Actual quantity',
        }),
    )
    unit = forms.ChoiceField(
        choices=FoodItem.BASIS_UNITS,
        required=False,
        label='Unit',
        widget=forms.Select(attrs={'aria-label': 'Unit'}),
    )
    price_observation = forms.ModelChoiceField(
        queryset=PriceObservation.objects.select_related('food_item').order_by(
            '-observed_at', '-id',
        ),
        required=False,
        empty_label='No price / unknown cost',
        label='Price observation',
        widget=forms.Select(attrs={'aria-label': 'Price observation'}),
    )

    def clean(self):
        cleaned_data = super().clean()
        food_item = cleaned_data.get('food_item')
        quantity = cleaned_data.get('quantity')
        unit = cleaned_data.get('unit')
        price_observation = cleaned_data.get('price_observation')
        has_other_values = any((quantity, unit, price_observation))

        if food_item is None:
            if has_other_values:
                self.add_error('food_item', 'Choose a food item for this ingredient row.')
            return cleaned_data

        if quantity is None:
            self.add_error('quantity', 'Enter a positive actual quantity.')
        if not unit:
            self.add_error('unit', 'Choose the ingredient unit.')
        elif unit != food_item.nutrition_basis_unit:
            self.add_error('unit', 'Unit must match the selected food item nutrition basis.')

        if unit == food_item.nutrition_basis_unit:
            try:
                cleaned_data['price_observation'] = select_price_observation(
                    food_item,
                    price_observation,
                )
            except ValueError as error:
                self.add_error('price_observation', str(error))

        return cleaned_data


BatchIngredientFormSet = formset_factory(
    BatchIngredientForm,
    extra=0,
    can_delete=True,
    min_num=1,
    validate_min=True,
)


class RecipeForm(forms.ModelForm):
    class Meta:
        model = Recipe
        fields = ['name', 'instructions']
        labels = {
            'name': 'Recipe name',
            'instructions': 'Instructions',
        }
        help_texts = {
            'instructions': 'Optional preparation notes for this reusable plan.',
        }
        widgets = {
            'instructions': forms.Textarea(attrs={'rows': 5}),
        }


class RecipeIngredientForm(forms.ModelForm):
    class Meta:
        model = RecipeIngredient
        fields = ['food_item', 'quantity', 'unit', 'price_observation']
        labels = {
            'food_item': 'Food item',
            'quantity': 'Planned quantity',
            'unit': 'Unit',
            'price_observation': 'Price observation',
        }
        help_texts = {
            'quantity': 'Use a positive quantity in grams or millilitres.',
            'unit': 'Must match the selected food item nutrition basis.',
            'price_observation': 'One price is used automatically; choose explicitly if several are available. Leave blank if cost is unknown.',
        }
        widgets = {
            'quantity': forms.NumberInput(attrs={'step': '0.001', 'min': '0.001'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['price_observation'].required = False
        self.fields['price_observation'].empty_label = 'No price / unknown cost'
        self.fields['price_observation'].queryset = PriceObservation.objects.select_related(
            'food_item',
        ).order_by('-observed_at', '-id')

    def clean(self):
        cleaned_data = super().clean()
        food_item = cleaned_data.get('food_item')
        if food_item is None:
            return cleaned_data

        try:
            # Reuse the shared zero/one/multiple-observation policy for saved recipe inputs.
            cleaned_data['price_observation'] = select_price_observation(
                food_item,
                cleaned_data.get('price_observation'),
            )
        except ValueError as error:
            self.add_error('price_observation', str(error))
        return cleaned_data


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
            'name': 'Use a clear name, such as Chicken breast, Lidl ready meal, or Workplace canteen curry.',
            'item_type': 'Ingredient is generic; Product is a specific branded, canteen, restaurant, takeaway, or ready-to-eat item.',
            'brand': 'Optional for a product. You can use a seller, workplace canteen, restaurant, or takeaway name.',
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
            'observed_at': 'When this price was seen or paid.',
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


class ConsumptionEntryForm(forms.ModelForm):
    consumed_at = forms.DateTimeField(
        input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M'],
        widget=forms.DateTimeInput(
            format='%Y-%m-%dT%H:%M',
            attrs={'type': 'datetime-local'},
        ),
    )
    unit = forms.ChoiceField(choices=FoodItem.BASIS_UNITS)
    price_observation = forms.ModelChoiceField(
        queryset=PriceObservation.objects.select_related('food_item'),
        required=False,
        empty_label='No price / unknown cost',
    )
    confirm_recalculation = forms.BooleanField(
        required=False,
        label='Confirm recalculation using current catalogue values',
    )

    class Meta:
        model = ConsumptionEntry
        fields = [
            'food_item',
            'quantity',
            'unit',
            'meal_category',
            'consumed_at',
            'price_observation',
        ]
        labels = {
            'food_item': 'Food item',
            'quantity': 'Consumed quantity',
            'unit': 'Unit',
            'meal_category': 'Meal category',
            'consumed_at': 'Consumed date and time',
            'price_observation': 'Price observation',
        }
        help_texts = {
            'quantity': 'Enter the amount consumed in grams or millilitres according to the selected food item. A complete meal with unknown weight may need an estimate.',
            'meal_category': 'Optional context such as breakfast, lunch, dinner, or snack.',
            'consumed_at': 'Defaults to the current Europe/Dublin local time.',
            'price_observation': 'One price is selected automatically; choose explicitly when several exist.',
        }
        widgets = {
            'quantity': forms.NumberInput(attrs={'step': '0.001', 'min': '0.001'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.consumed_at:
            local_time = timezone.localtime(self.instance.consumed_at)
            self.initial['consumed_at'] = local_time.strftime('%Y-%m-%dT%H:%M')
        elif not self.is_bound:
            self.initial['consumed_at'] = timezone.localtime(
                timezone.now(),
            ).strftime('%Y-%m-%dT%H:%M')

    def clean(self):
        cleaned_data = super().clean()
        food_item = cleaned_data.get('food_item')
        unit = cleaned_data.get('unit')
        price_observation = cleaned_data.get('price_observation')
        if food_item and unit and unit != food_item.nutrition_basis_unit:
            self.add_error('unit', 'Unit must match the selected food item nutrition basis.')
        if food_item and price_observation:
            if price_observation.food_item_id != food_item.pk:
                self.add_error(
                    'price_observation',
                    'Price observation must belong to the selected food item.',
                )
        if food_item and not price_observation:
            if food_item.price_observations.count() > 1:
                self.add_error(
                    'price_observation',
                    'Select a price observation when multiple prices are available.',
                )
        return cleaned_data
