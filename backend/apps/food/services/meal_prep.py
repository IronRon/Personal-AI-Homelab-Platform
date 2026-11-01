from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable, Optional

from django.db import transaction
from django.utils import timezone

from ..models import BatchIngredient, FoodItem, MealPrepBatch, PriceObservation, Recipe
from .calculations import calculate_consumption, select_price_observation


@dataclass(frozen=True)
class BatchIngredientInput:
    food_item: FoodItem
    quantity: Decimal
    unit: str
    price_observation: Optional[PriceObservation] = None


def _snapshot_ingredient(item: BatchIngredientInput) -> dict:
    """Read persisted catalogue values once, then copy their contribution into the batch."""
    if item.food_item is None or item.food_item.pk is None:
        raise ValueError('A saved food item is required for each batch ingredient.')

    try:
        food_item = FoodItem.objects.get(pk=item.food_item.pk)
    except FoodItem.DoesNotExist as error:
        raise ValueError('The selected food item no longer exists.') from error

    selected_price = item.price_observation
    if selected_price is not None:
        if selected_price.pk is None:
            raise ValueError('A saved price observation is required.')
        try:
            selected_price = PriceObservation.objects.get(pk=selected_price.pk)
        except PriceObservation.DoesNotExist as error:
            raise ValueError('The selected price observation no longer exists.') from error

    selected_price = select_price_observation(food_item, selected_price)
    nutrition, estimated_cost = calculate_consumption(
        food_item,
        item.quantity,
        item.unit,
        selected_price,
    )

    snapshot = {
        'food_item': food_item,
        'food_item_name_snapshot': str(food_item),
        'price_observation': selected_price,
        'quantity': item.quantity,
        'unit': item.unit,
        'calories': nutrition.calories,
        'protein': nutrition.protein,
        'carbohydrates': nutrition.carbohydrates,
        'fat': nutrition.fat,
        'estimated_cost': estimated_cost,
        'currency': selected_price.currency if estimated_cost is not None else '',
        'nutrition_source': food_item.nutrition_source,
        'cost_source': selected_price.source if estimated_cost is not None else '',
    }

    ingredient = BatchIngredient(**snapshot)
    ingredient.full_clean(exclude=['batch'])
    return snapshot


@transaction.atomic
def create_meal_prep_batch(
    *,
    name: str,
    yield_quantity: Decimal,
    yield_unit: str,
    ingredients: Iterable[BatchIngredientInput],
    recipe: Optional[Recipe] = None,
    cooked_at: Optional[datetime] = None,
) -> MealPrepBatch:
    """Create a batch atomically; save() does not run full_clean() for either model."""
    ingredient_inputs = list(ingredients)
    if not ingredient_inputs:
        raise ValueError('A meal-prep batch must contain at least one ingredient.')

    snapshots = [_snapshot_ingredient(item) for item in ingredient_inputs]
    known_currencies = {
        snapshot['currency']
        for snapshot in snapshots
        if snapshot['estimated_cost'] is not None
    }
    if len(known_currencies) > 1:
        raise ValueError('Batch ingredient costs must use a single currency.')

    if cooked_at is None:
        cooked_at = timezone.now()
    elif timezone.is_naive(cooked_at):
        cooked_at = timezone.make_aware(
            cooked_at,
            timezone=timezone.get_current_timezone(),
        )

    batch = MealPrepBatch(
        name=name,
        recipe=recipe,
        cooked_at=cooked_at,
        yield_quantity=yield_quantity,
        yield_unit=yield_unit,
    )
    batch.full_clean()
    batch.save()

    for snapshot in snapshots:
        ingredient = BatchIngredient(batch=batch, **snapshot)
        ingredient.full_clean()
        ingredient.save()

    return batch