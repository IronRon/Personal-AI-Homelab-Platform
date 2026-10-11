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
    estimated_cost: Decimal
    nutrition_complete: bool
    cost_complete: bool
    entry_count: int


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


def _sum_known(values: list[Optional[Decimal]]) -> Decimal:
    return _quantize(
        sum((value for value in values if value is not None), Decimal('0')),
        NUTRIENT_QUANTUM,
    )


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
    costs = [entry.estimated_cost for entry in matching_entries]

    return DailyTotals(
        calories=_sum_known(nutrition_values['calories']),
        protein=_sum_known(nutrition_values['protein']),
        carbohydrates=_sum_known(nutrition_values['carbohydrates']),
        fat=_sum_known(nutrition_values['fat']),
        estimated_cost=_quantize(
            sum((cost for cost in costs if cost is not None), Decimal('0')),
            MONEY_QUANTUM,
        ),
        nutrition_complete=all(
            value is not None
            for values in nutrition_values.values()
            for value in values
        ),
        cost_complete=all(cost is not None for cost in costs),
        entry_count=len(matching_entries),
    )
