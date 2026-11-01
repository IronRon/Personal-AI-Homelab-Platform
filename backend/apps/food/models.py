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


class FoodPurchase(models.Model):
	"""A simple record of money actually spent on food."""

	description = models.CharField(max_length=200)
	food_item = models.ForeignKey(
		FoodItem,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='purchases',
	)
	purchased_at = models.DateTimeField(default=timezone.now)
	amount_paid = models.DecimalField(
		max_digits=10,
		decimal_places=2,
		validators=[MinValueValidator(Decimal('0'))],
	)
	currency = models.CharField(max_length=3, default='EUR')
	quantity = models.DecimalField(
		max_digits=10,
		decimal_places=3,
		null=True,
		blank=True,
		validators=[MinValueValidator(Decimal('0.001'))],
	)
	unit = models.CharField(max_length=2, choices=FoodItem.BASIS_UNITS, blank=True)
	source = models.CharField(max_length=120, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ('-purchased_at', '-id')
		constraints = [
			models.CheckConstraint(
				condition=Q(amount_paid__gte=0),
				name='food_purchase_amount_non_negative',
			),
			models.CheckConstraint(
				condition=(
					Q(quantity__isnull=True, unit='')
					| Q(quantity__gt=0, unit__in=[FoodItem.GRAMS, FoodItem.MILLILITRES])
				),
				name='food_purchase_quantity_unit_pair',
			),
		]

	def clean(self):
		if (self.quantity is None) != (self.unit == ''):
			raise ValidationError({
				'quantity': 'Purchase quantity and unit must be provided together.',
			})
		if self.food_item_id and self.unit and self.unit != self.food_item.nutrition_basis_unit:
			raise ValidationError({
				'unit': 'Purchase unit must match the selected food item nutrition basis.',
			})

	def __str__(self):
		return self.description


class Recipe(models.Model):
	"""Reusable plan whose nutrition and cost estimates follow current catalogue data."""

	name = models.CharField(max_length=200)
	instructions = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ('name', 'id')

	def __str__(self):
		return self.name


class RecipeIngredient(models.Model):
	recipe = models.ForeignKey(
		Recipe,
		on_delete=models.CASCADE,
		related_name='ingredients',
	)
	food_item = models.ForeignKey(
		FoodItem,
		on_delete=models.PROTECT,
		related_name='recipe_ingredients',
	)
	quantity = models.DecimalField(
		max_digits=10,
		decimal_places=3,
		validators=[MinValueValidator(Decimal('0.001'))],
	)
	unit = models.CharField(max_length=2, choices=FoodItem.BASIS_UNITS)
	price_observation = models.ForeignKey(
		PriceObservation,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='recipe_ingredients',
	)

	class Meta:
		ordering = ('id',)
		constraints = [
			models.CheckConstraint(
				condition=Q(quantity__gt=0),
				name='recipe_ingredient_quantity_positive',
			),
		]

	def clean(self):
		if self.food_item_id and self.unit != self.food_item.nutrition_basis_unit:
			raise ValidationError({
				'unit': 'Recipe ingredient unit must match the food item nutrition basis.',
			})
		if self.price_observation_id:
			if self.food_item_id != self.price_observation.food_item_id:
				raise ValidationError({
					'price_observation': 'Price observation must belong to the selected food item.',
				})
			if self.unit != self.price_observation.package_unit:
				raise ValidationError({
					'price_observation': 'Price observation package unit must match the ingredient unit.',
				})


class MealPrepBatch(models.Model):
	"""A cooked event whose actual contents are recorded by its ingredient rows."""

	name = models.CharField(max_length=200)
	recipe = models.ForeignKey(
		Recipe,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='meal_prep_batches',
	)
	cooked_at = models.DateTimeField(default=timezone.now)
	yield_quantity = models.DecimalField(
		max_digits=10,
		decimal_places=3,
		validators=[MinValueValidator(Decimal('0.001'))],
	)
	yield_unit = models.CharField(max_length=2, choices=FoodItem.BASIS_UNITS)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ('-cooked_at', '-id')
		constraints = [
			models.CheckConstraint(
				condition=Q(yield_quantity__gt=0),
				name='meal_prep_batch_yield_positive',
			),
		]

	def __str__(self):
		return self.name


class BatchIngredient(models.Model):
	"""Historical ingredient contribution; catalogue FKs are provenance, not its values."""

	batch = models.ForeignKey(
		MealPrepBatch,
		on_delete=models.CASCADE,
		related_name='ingredients',
	)
	food_item = models.ForeignKey(
		FoodItem,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='batch_ingredients',
	)
	food_item_name_snapshot = models.CharField(max_length=200)
	price_observation = models.ForeignKey(
		PriceObservation,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='batch_ingredients',
	)
	quantity = models.DecimalField(
		max_digits=10,
		decimal_places=3,
		validators=[MinValueValidator(Decimal('0.001'))],
	)
	unit = models.CharField(max_length=2, choices=FoodItem.BASIS_UNITS)
	calories = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
	protein = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
	carbohydrates = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
	fat = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
	estimated_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
	currency = models.CharField(max_length=3, blank=True)
	nutrition_source = models.CharField(max_length=120, blank=True)
	cost_source = models.CharField(max_length=120, blank=True)

	class Meta:
		ordering = ('id',)
		constraints = [
			models.CheckConstraint(
				condition=Q(quantity__gt=0),
				name='batch_ingredient_quantity_positive',
			),
			models.CheckConstraint(
				condition=Q(estimated_cost__gte=0) | Q(estimated_cost__isnull=True),
				name='batch_ingredient_cost_non_negative',
			),
			models.CheckConstraint(
				condition=Q(calories__gte=0) | Q(calories__isnull=True),
				name='batch_ingredient_calories_non_negative',
			),
			models.CheckConstraint(
				condition=Q(protein__gte=0) | Q(protein__isnull=True),
				name='batch_ingredient_protein_non_negative',
			),
			models.CheckConstraint(
				condition=Q(carbohydrates__gte=0) | Q(carbohydrates__isnull=True),
				name='batch_ingredient_carbohydrates_non_negative',
			),
			models.CheckConstraint(
				condition=Q(fat__gte=0) | Q(fat__isnull=True),
				name='batch_ingredient_fat_non_negative',
			),
		]

	def clean(self):
		if self.food_item_id and self.unit != self.food_item.nutrition_basis_unit:
			raise ValidationError({
				'unit': 'Batch ingredient unit must match the food item nutrition basis.',
			})
		if self.price_observation_id:
			if self.food_item_id != self.price_observation.food_item_id:
				raise ValidationError({
					'price_observation': 'Price observation must belong to the selected food item.',
				})
			if self.unit != self.price_observation.package_unit:
				raise ValidationError({
					'price_observation': 'Price observation package unit must match the ingredient unit.',
				})
		if self.estimated_cost is None and self.currency:
			raise ValidationError({'currency': 'Currency is only stored when cost is known.'})
		if self.estimated_cost is not None and not self.currency:
			raise ValidationError({'currency': 'Currency is required when cost is known.'})


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
	meal_prep_batch = models.ForeignKey(
		MealPrepBatch,
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
	is_quick_add = models.BooleanField(default=False)
	source_name = models.CharField(max_length=200)
	quantity = models.DecimalField(
		max_digits=10,
		decimal_places=3,
		null=True,
		blank=True,
		validators=[MinValueValidator(Decimal('0.001'))],
	)
	unit = models.CharField(max_length=2, choices=FoodItem.BASIS_UNITS, blank=True)
	consumed_at = models.DateTimeField(default=timezone.now)
	meal_category = models.CharField(max_length=20, choices=MEAL_CATEGORIES, blank=True)
	calories = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
	protein = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
	carbohydrates = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
	fat = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
	estimated_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
	currency = models.CharField(max_length=3, default='EUR', blank=True)
	nutrition_source = models.CharField(max_length=120, blank=True)
	cost_source = models.CharField(max_length=120, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ('-consumed_at', '-id')
		constraints = [
			models.CheckConstraint(
				condition=(
					Q(is_quick_add=True, quantity__isnull=True, unit='')
					| Q(quantity__gt=0, unit__in=[FoodItem.GRAMS, FoodItem.MILLILITRES])
				),
				name='consumption_entry_quantity_unit_valid',
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
			models.CheckConstraint(
				# Historical rows may have neither source after SET_NULL; creation requires one.
				condition=Q(food_item__isnull=True) | Q(meal_prep_batch__isnull=True),
				name='consumption_entry_single_source',
			),
			models.CheckConstraint(
				condition=Q(meal_prep_batch__isnull=True) | Q(price_observation__isnull=True),
				name='consumption_entry_batch_no_price_observation',
			),
			models.CheckConstraint(
				condition=(
					Q(is_quick_add=False)
					| Q(food_item__isnull=True, meal_prep_batch__isnull=True, price_observation__isnull=True)
				),
				name='consumption_entry_quick_add_no_catalogue_source',
			),
		]

	def clean(self):
		# Require a source only for new rows so SET_NULL can preserve historical entries.
		if (
			self._state.adding
			and not self.is_quick_add
			and not self.food_item_id
			and not self.meal_prep_batch_id
		):
			raise ValidationError({
				'food_item': 'Select a food item or a meal-prep batch for a new entry.',
			})
		if self.is_quick_add and (
			self.food_item_id or self.meal_prep_batch_id or self.price_observation_id
		):
			raise ValidationError({
				'is_quick_add': 'Quick Add entries cannot reference catalogue items, batches, or prices.',
			})
		if self.food_item_id and self.meal_prep_batch_id:
			raise ValidationError({
				'meal_prep_batch': 'An entry cannot reference both a food item and a meal-prep batch.',
			})
		if (
			self._state.adding
			and self.meal_prep_batch_id
			and self.unit != self.meal_prep_batch.yield_unit
		):
			raise ValidationError({
				'unit': 'Consumption unit must match the meal-prep batch yield unit.',
			})
		if self.food_item and self.unit != self.food_item.nutrition_basis_unit:
			raise ValidationError({
				'unit': 'Consumption unit must match the food item nutrition basis.',
			})
		if self.meal_prep_batch_id and self.price_observation_id:
			raise ValidationError({
				'price_observation': 'Batch-backed entries cannot reference a price observation.',
			})
		if self.price_observation and self.food_item_id != self.price_observation.food_item_id:
			raise ValidationError({
				'price_observation': 'Price observation must belong to the selected food item.',
			})
		if not self.is_quick_add and self._state.adding and self.quantity is None:
			raise ValidationError({'quantity': 'A measured quantity is required for catalogue or batch entries.'})
		if self.is_quick_add and self.estimated_cost is None and self.currency:
			raise ValidationError({'currency': 'Currency is only stored when a Quick Add cost is known.'})
		if self.is_quick_add and self.estimated_cost is not None and not self.currency:
			raise ValidationError({'currency': 'Choose a currency when entering a Quick Add cost.'})

	def __str__(self):
		return f'{self.source_name} - {self.quantity}{self.unit}'
