from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Optional

from django.utils import timezone


NUTRIENT_QUANTUM = Decimal('0.01')
MONEY_QUANTUM = Decimal('0.01')


@dataclass(frozen=True)
class NutritionSnapshot:
    calories: Optional[Decimal]
    protein: Optional[Decimal]
    carbohydrates: Optional[Decimal]
    fat: Optional[Decimal]


@dataclass(frozen=True)
class DailyTotals:
    calories: Decimal
    protein: Decimal
    carbohydrates: Decimal
    fat: Decimal
    estimated_cost: Optional[Decimal]
    currency: Optional[str]
    costs_by_currency: dict[str, Decimal]
    nutrition_complete: bool
    cost_complete: bool
    entry_count: int
    calories_complete: bool
    protein_complete: bool
    carbohydrates_complete: bool
    fat_complete: bool


@dataclass(frozen=True)
class RecipeEstimate:
    calories: Decimal
    protein: Decimal
    carbohydrates: Decimal
    fat: Decimal
    estimated_cost: Optional[Decimal]
    currency: Optional[str]
    calories_complete: bool
    protein_complete: bool
    carbohydrates_complete: bool
    fat_complete: bool
    cost_complete: bool
    ingredient_count: int

    @property
    def nutrition_complete(self) -> bool:
        return all((
            self.calories_complete,
            self.protein_complete,
            self.carbohydrates_complete,
            self.fat_complete,
        ))


@dataclass(frozen=True)
class BatchTotals:
    calories: Decimal
    protein: Decimal
    carbohydrates: Decimal
    fat: Decimal
    estimated_cost: Decimal
    currency: Optional[str]
    calories_complete: bool
    protein_complete: bool
    carbohydrates_complete: bool
    fat_complete: bool
    cost_complete: bool
    ingredient_count: int

    @property
    def nutrition_complete(self) -> bool:
        return all((
            self.calories_complete,
            self.protein_complete,
            self.carbohydrates_complete,
            self.fat_complete,
        ))


def _quantize(value: Decimal, quantum: Decimal) -> Decimal:
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def _validate_quantity(quantity: Decimal) -> Decimal:
    quantity = Decimal(quantity)
    if quantity <= 0:
        raise ValueError('Quantity must be greater than zero.')
    return quantity


def _scale_value(value: Optional[Decimal], quantity: Decimal) -> Optional[Decimal]:
    if value is None:
        return None
    return _quantize(Decimal(value) * quantity / Decimal('100'), NUTRIENT_QUANTUM)


def scale_nutrition(food_item, quantity: Decimal, unit: str) -> NutritionSnapshot:
    """Scale a FoodItem's per-100 nutrition values to a consumed quantity."""
    quantity = _validate_quantity(quantity)
    if unit != food_item.nutrition_basis_unit:
        raise ValueError('Consumption unit must match the food item nutrition basis.')

    return NutritionSnapshot(
        calories=_scale_value(food_item.calories_per_100, quantity),
        protein=_scale_value(food_item.protein_per_100, quantity),
        carbohydrates=_scale_value(food_item.carbohydrates_per_100, quantity),
        fat=_scale_value(food_item.fat_per_100, quantity),
    )


def calculate_allocated_cost(
    consumed_quantity: Decimal,
    consumed_unit: str,
    price_observation,
) -> Optional[Decimal]:
    """Calculate the proportional cost of a consumed package quantity."""
    if price_observation is None:
        return None

    consumed_quantity = _validate_quantity(consumed_quantity)
    if consumed_unit != price_observation.package_unit:
        raise ValueError('Consumption unit must match the price package unit.')
    if price_observation.package_quantity <= 0:
        raise ValueError('Package quantity must be greater than zero.')

    return _quantize(
        price_observation.paid_price
        * consumed_quantity
        / price_observation.package_quantity,
        MONEY_QUANTUM,
    )


def calculate_consumption(food_item, quantity: Decimal, unit: str, price_observation=None):
    """Return nutrition and allocated cost for a planned consumption entry."""
    nutrition = scale_nutrition(food_item, quantity, unit)
    cost = calculate_allocated_cost(quantity, unit, price_observation)
    return nutrition, cost


def select_price_observation(food_item, selected_price_observation=None):
    """Apply the Food price policy: none, auto-select one, require choice for many."""
    if selected_price_observation is not None:
        if selected_price_observation.food_item_id != food_item.pk:
            raise ValueError('Price observation must belong to the selected food item.')
        if selected_price_observation.package_unit != food_item.nutrition_basis_unit:
            raise ValueError('Price observation package unit must match the food item basis.')
        return selected_price_observation

    observations = list(food_item.price_observations.all())
    if len(observations) > 1:
        raise ValueError('Select a price observation when multiple prices are available.')
    return observations[0] if observations else None


def _sum_component(values: list[Optional[Decimal]], quantum: Decimal):
    """Return the known subtotal and flag unknown inputs instead of masking them as zero."""
    subtotal = _quantize(
        sum((value for value in values if value is not None), Decimal('0')),
        quantum,
    )
    complete = bool(values) and all(value is not None for value in values)
    return subtotal, complete


def calculate_recipe_estimate(recipe) -> RecipeEstimate:
    """Estimate from live catalogue data; unlike a batch, a recipe is not historical."""
    ingredient_rows = list(
        recipe.ingredients.select_related('food_item', 'price_observation')
    )
    nutrition_values = {key: [] for key in ('calories', 'protein', 'carbohydrates', 'fat')}
    costs = []
    cost_currencies = set()

    for ingredient in ingredient_rows:
        ingredient.full_clean()
        price_observation = select_price_observation(
            ingredient.food_item,
            ingredient.price_observation,
        )
        nutrition, cost = calculate_consumption(
            ingredient.food_item,
            ingredient.quantity,
            ingredient.unit,
            price_observation,
        )
        for key in nutrition_values:
            nutrition_values[key].append(getattr(nutrition, key))
        costs.append(cost)
        if cost is not None:
            cost_currencies.add(price_observation.currency)

    calories, calories_complete = _sum_component(nutrition_values['calories'], NUTRIENT_QUANTUM)
    protein, protein_complete = _sum_component(nutrition_values['protein'], NUTRIENT_QUANTUM)
    carbohydrates, carbohydrates_complete = _sum_component(
        nutrition_values['carbohydrates'],
        NUTRIENT_QUANTUM,
    )
    fat, fat_complete = _sum_component(nutrition_values['fat'], NUTRIENT_QUANTUM)

    if len(cost_currencies) > 1:
        # A monetary subtotal across currencies is meaningless without an FX policy.
        estimated_cost = None
        currency = None
        cost_complete = False
    else:
        estimated_cost, cost_complete = _sum_component(costs, MONEY_QUANTUM)
        currency = next(iter(cost_currencies), None)

    return RecipeEstimate(
        calories=calories,
        protein=protein,
        carbohydrates=carbohydrates,
        fat=fat,
        estimated_cost=estimated_cost,
        currency=currency,
        calories_complete=calories_complete,
        protein_complete=protein_complete,
        carbohydrates_complete=carbohydrates_complete,
        fat_complete=fat_complete,
        cost_complete=cost_complete,
        ingredient_count=len(ingredient_rows),
    )


def calculate_batch_totals(batch) -> BatchTotals:
    """Aggregate snapshots only, so later catalogue or recipe edits cannot rewrite history."""
    ingredient_rows = list(batch.ingredients.all())
    cost_currencies = {
        ingredient.currency
        for ingredient in ingredient_rows
        if ingredient.estimated_cost is not None
    }
    if len(cost_currencies) > 1:
        # A cooked batch has one reporting currency; never add unlike currencies.
        raise ValueError('Batch ingredient costs must use a single currency.')

    calories, calories_complete = _sum_component(
        [ingredient.calories for ingredient in ingredient_rows],
        NUTRIENT_QUANTUM,
    )
    protein, protein_complete = _sum_component(
        [ingredient.protein for ingredient in ingredient_rows],
        NUTRIENT_QUANTUM,
    )
    carbohydrates, carbohydrates_complete = _sum_component(
        [ingredient.carbohydrates for ingredient in ingredient_rows],
        NUTRIENT_QUANTUM,
    )
    fat, fat_complete = _sum_component(
        [ingredient.fat for ingredient in ingredient_rows],
        NUTRIENT_QUANTUM,
    )
    estimated_cost, cost_complete = _sum_component(
        [ingredient.estimated_cost for ingredient in ingredient_rows],
        MONEY_QUANTUM,
    )

    return BatchTotals(
        calories=calories,
        protein=protein,
        carbohydrates=carbohydrates,
        fat=fat,
        estimated_cost=estimated_cost,
        currency=next(iter(cost_currencies), None),
        calories_complete=calories_complete,
        protein_complete=protein_complete,
        carbohydrates_complete=carbohydrates_complete,
        fat_complete=fat_complete,
        cost_complete=cost_complete,
        ingredient_count=len(ingredient_rows),
    )


def scale_batch_totals(
    totals: BatchTotals,
    consumed_quantity: Decimal,
    yield_quantity: Decimal,
) -> dict[str, Optional[Decimal]]:
    """Scale complete historical components; incomplete subtotals stay null, not misleading partial values."""
    consumed_quantity = Decimal(consumed_quantity)
    yield_quantity = Decimal(yield_quantity)
    if not consumed_quantity.is_finite() or consumed_quantity <= 0:
        raise ValueError('Consumed quantity must be greater than zero.')
    if not yield_quantity.is_finite() or yield_quantity <= 0:
        raise ValueError('Batch yield must be greater than zero.')

    proportion = consumed_quantity / yield_quantity

    def scale(value: Decimal, complete: bool, quantum: Decimal):
        if not complete:
            return None
        return _quantize(value * proportion, quantum)

    return {
        'calories': scale(totals.calories, totals.calories_complete, NUTRIENT_QUANTUM),
        'protein': scale(totals.protein, totals.protein_complete, NUTRIENT_QUANTUM),
        'carbohydrates': scale(
            totals.carbohydrates,
            totals.carbohydrates_complete,
            NUTRIENT_QUANTUM,
        ),
        'fat': scale(totals.fat, totals.fat_complete, NUTRIENT_QUANTUM),
        'estimated_cost': scale(totals.estimated_cost, totals.cost_complete, MONEY_QUANTUM),
    }


def _sum_known(values: list[Optional[Decimal]]) -> Decimal:
    return _quantize(
        sum((value for value in values if value is not None), Decimal('0')),
        NUTRIENT_QUANTUM,
    )


def _all_known(values: list[Optional[Decimal]]) -> bool:
    return all(value is not None for value in values)


def aggregate_daily(entries: Iterable, target_date: date, tz=None) -> DailyTotals:
    """Aggregate entries whose aware timestamp falls on target_date in tz."""
    tz = tz or timezone.get_current_timezone()
    matching_entries = []
    for entry in entries:
        consumed_at = entry.consumed_at
        if timezone.is_naive(consumed_at):
            consumed_at = timezone.make_aware(consumed_at, timezone=tz)
        if timezone.localtime(consumed_at, timezone=tz).date() == target_date:
            matching_entries.append(entry)

    nutrition_values = {
        'calories': [entry.calories for entry in matching_entries],
        'protein': [entry.protein for entry in matching_entries],
        'carbohydrates': [entry.carbohydrates for entry in matching_entries],
        'fat': [entry.fat for entry in matching_entries],
    }
    costs_by_currency: dict[str, list[Decimal]] = {}
    for entry in matching_entries:
        if entry.estimated_cost is not None and entry.currency:
            costs_by_currency.setdefault(entry.currency, []).append(entry.estimated_cost)
    currency_totals = {
        currency: _quantize(sum(values, Decimal('0')), MONEY_QUANTUM)
        for currency, values in sorted(costs_by_currency.items())
    }
    # A daily total across currencies has no defined meaning without conversion.
    if len(currency_totals) == 1:
        currency, estimated_cost = next(iter(currency_totals.items()))
    elif not currency_totals:
        currency = None
        estimated_cost = Decimal('0')
    else:
        currency = None
        estimated_cost = None

    return DailyTotals(
        calories=_sum_known(nutrition_values['calories']),
        protein=_sum_known(nutrition_values['protein']),
        carbohydrates=_sum_known(nutrition_values['carbohydrates']),
        fat=_sum_known(nutrition_values['fat']),
        estimated_cost=estimated_cost,
        currency=currency,
        costs_by_currency=currency_totals,
        nutrition_complete=all(_all_known(values) for values in nutrition_values.values()),
        cost_complete=all(
            entry.estimated_cost is not None and bool(entry.currency)
            for entry in matching_entries
        ),
        entry_count=len(matching_entries),
        calories_complete=_all_known(nutrition_values['calories']),
        protein_complete=_all_known(nutrition_values['protein']),
        carbohydrates_complete=_all_known(nutrition_values['carbohydrates']),
        fat_complete=_all_known(nutrition_values['fat']),
    )
