from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


class FoodItem(models.Model):
	INGREDIENT = 'ingredient'
	PRODUCT = 'product'
	ITEM_TYPES = (
		(INGREDIENT, 'Ingredient'),
		(PRODUCT, 'Product'),
	)

	GRAMS = 'g'
	MILLILITRES = 'ml'
	BASIS_UNITS = (
		(GRAMS, 'Grams'),
		(MILLILITRES, 'Millilitres'),
	)

	name = models.CharField(max_length=200)
	item_type = models.CharField(max_length=20, choices=ITEM_TYPES)
	brand = models.CharField(max_length=120, blank=True)
	nutrition_basis_unit = models.CharField(max_length=2, choices=BASIS_UNITS)
	calories_per_100 = models.DecimalField(
		max_digits=8,
		decimal_places=2,
		null=True,
		blank=True,
		validators=[MinValueValidator(Decimal('0'))],
	)
	protein_per_100 = models.DecimalField(
		max_digits=8,
		decimal_places=2,
		null=True,
		blank=True,
		validators=[MinValueValidator(Decimal('0'))],
	)
	carbohydrates_per_100 = models.DecimalField(
		max_digits=8,
		decimal_places=2,
		null=True,
		blank=True,
		validators=[MinValueValidator(Decimal('0'))],
	)
	fat_per_100 = models.DecimalField(
		max_digits=8,
		decimal_places=2,
		null=True,
		blank=True,
		validators=[MinValueValidator(Decimal('0'))],
	)
	nutrition_source = models.CharField(max_length=120, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ('name', 'brand')
		constraints = [
			models.CheckConstraint(
				condition=Q(calories_per_100__gte=0) | Q(calories_per_100__isnull=True),
				name='food_item_calories_non_negative',
			),
			models.CheckConstraint(
				condition=Q(protein_per_100__gte=0) | Q(protein_per_100__isnull=True),
				name='food_item_protein_non_negative',
			),
			models.CheckConstraint(
				condition=Q(carbohydrates_per_100__gte=0) | Q(carbohydrates_per_100__isnull=True),
				name='food_item_carbohydrates_non_negative',
			),
			models.CheckConstraint(
				condition=Q(fat_per_100__gte=0) | Q(fat_per_100__isnull=True),
				name='food_item_fat_non_negative',
			),
		]

	def __str__(self):
		return f'{self.brand} {self.name}'.strip()


class PriceObservation(models.Model):
	food_item = models.ForeignKey(
		FoodItem,
		on_delete=models.CASCADE,
		related_name='price_observations',
	)
	package_quantity = models.DecimalField(
		max_digits=10,
		decimal_places=3,
		validators=[MinValueValidator(Decimal('0.001'))],
	)
	package_unit = models.CharField(max_length=2, choices=FoodItem.BASIS_UNITS)
	paid_price = models.DecimalField(
		max_digits=10,
		decimal_places=2,
		validators=[MinValueValidator(Decimal('0'))],
	)
	reference_price = models.DecimalField(
		max_digits=10,
		decimal_places=2,
		null=True,
		blank=True,
		validators=[MinValueValidator(Decimal('0'))],
	)
	currency = models.CharField(max_length=3, default='EUR')
	observed_at = models.DateTimeField(default=timezone.now)
	source = models.CharField(max_length=120, blank=True)

	class Meta:
		ordering = ('-observed_at', '-id')
		constraints = [
			models.CheckConstraint(
				condition=Q(package_quantity__gt=0),
				name='price_observation_package_quantity_positive',
			),
			models.CheckConstraint(
				condition=Q(paid_price__gte=0),
				name='price_observation_paid_price_non_negative',
			),
			models.CheckConstraint(
				condition=Q(reference_price__gte=0) | Q(reference_price__isnull=True),
				name='price_observation_reference_price_non_negative',
			),
		]

	def clean(self):
		if self.package_unit != self.food_item.nutrition_basis_unit:
			raise ValidationError({
				'package_unit': 'Package unit must match the food item nutrition basis.',
			})

	def __str__(self):
		return f'{self.food_item} - {self.paid_price} {self.currency}'


class ConsumptionEntry(models.Model):
	MEAL_CATEGORIES = (
		('breakfast', 'Breakfast'),
		('lunch', 'Lunch'),
		('dinner', 'Dinner'),
		('snack', 'Snack'),
	)

	food_item = models.ForeignKey(
		FoodItem,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='consumption_entries',
	)
	price_observation = models.ForeignKey(
		PriceObservation,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='consumption_entries',
	)
	source_name = models.CharField(max_length=200)
	quantity = models.DecimalField(
		max_digits=10,
		decimal_places=3,
		validators=[MinValueValidator(Decimal('0.001'))],
	)
	unit = models.CharField(max_length=2, choices=FoodItem.BASIS_UNITS)
	consumed_at = models.DateTimeField(default=timezone.now)
	meal_category = models.CharField(max_length=20, choices=MEAL_CATEGORIES, blank=True)
	calories = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
	protein = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
	carbohydrates = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
	fat = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
	estimated_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
	currency = models.CharField(max_length=3, default='EUR')
	nutrition_source = models.CharField(max_length=120, blank=True)
	cost_source = models.CharField(max_length=120, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ('-consumed_at', '-id')
		constraints = [
			models.CheckConstraint(
				condition=Q(quantity__gt=0),
				name='consumption_entry_quantity_positive',
			),
			models.CheckConstraint(
				condition=Q(calories__gte=0) | Q(calories__isnull=True),
				name='consumption_entry_calories_non_negative',
			),
			models.CheckConstraint(
				condition=Q(protein__gte=0) | Q(protein__isnull=True),
				name='consumption_entry_protein_non_negative',
			),
			models.CheckConstraint(
				condition=Q(carbohydrates__gte=0) | Q(carbohydrates__isnull=True),
				name='consumption_entry_carbohydrates_non_negative',
			),
			models.CheckConstraint(
				condition=Q(fat__gte=0) | Q(fat__isnull=True),
				name='consumption_entry_fat_non_negative',
			),
			models.CheckConstraint(
				condition=Q(estimated_cost__gte=0) | Q(estimated_cost__isnull=True),
				name='consumption_entry_cost_non_negative',
			),
		]

	def clean(self):
		if self.food_item and self.unit != self.food_item.nutrition_basis_unit:
			raise ValidationError({
				'unit': 'Consumption unit must match the food item nutrition basis.',
			})
		if self.price_observation and self.food_item_id != self.price_observation.food_item_id:
			raise ValidationError({
				'price_observation': 'Price observation must belong to the selected food item.',
			})

	def __str__(self):
		return f'{self.source_name} - {self.quantity}{self.unit}'
