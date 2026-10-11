from datetime import date, datetime, time
from typing import Optional

from django.db import transaction
from django.utils import timezone

from ..models import ConsumptionEntry, FoodItem, PriceObservation
from .calculations import DailyTotals, aggregate_daily, calculate_consumption


UNSET = object()


def _as_aware(value):
    if value is None:
        return timezone.now()
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone=timezone.get_current_timezone())
    return value


def _validate_price_observation(
    food_item: FoodItem,
    price_observation: Optional[PriceObservation],
) -> Optional[PriceObservation]:
    observations = list(food_item.price_observations.all())
    if price_observation is not None:
        if price_observation.food_item_id != food_item.pk:
            raise ValueError('Price observation must belong to the selected food item.')
        return price_observation
    if len(observations) == 1:
        return observations[0]
    if len(observations) > 1:
        raise ValueError('Select a price observation when multiple prices are available.')
    return None


def _snapshot_values(food_item, quantity, unit, price_observation):
    nutrition, estimated_cost = calculate_consumption(
        food_item,
        quantity,
        unit,
        price_observation,
    )
    return {
        'calories': nutrition.calories,
        'protein': nutrition.protein,
        'carbohydrates': nutrition.carbohydrates,
        'fat': nutrition.fat,
        'estimated_cost': estimated_cost,
        'currency': price_observation.currency if price_observation else 'EUR',
        'nutrition_source': food_item.nutrition_source,
        'cost_source': price_observation.source if price_observation else '',
    }


@transaction.atomic
def create_consumption_entry(
    *,
    food_item: FoodItem,
    quantity,
    unit: str,
    consumed_at=None,
    meal_category: str = '',
    price_observation: Optional[PriceObservation] = None,
) -> ConsumptionEntry:
    """Create an entry and populate its historical nutrition/cost snapshots."""
    if food_item is None:
        raise ValueError('A food item is required.')

    price_observation = _validate_price_observation(food_item, price_observation)
    snapshots = _snapshot_values(food_item, quantity, unit, price_observation)
    entry = ConsumptionEntry(
        food_item=food_item,
        price_observation=price_observation,
        source_name=str(food_item),
        quantity=quantity,
        unit=unit,
        consumed_at=_as_aware(consumed_at),
        meal_category=meal_category,
        **snapshots,
    )
    entry.full_clean()
    entry.save()
    return entry


@transaction.atomic
def recalculate_consumption_entry(
    entry: ConsumptionEntry,
    *,
    food_item=UNSET,
    quantity=UNSET,
    unit=UNSET,
    price_observation=UNSET,
    consumed_at=UNSET,
    meal_category=UNSET,
    confirmed: bool = False,
) -> ConsumptionEntry:
    """Explicitly replace snapshots using current catalogue values."""
    if not confirmed:
        raise ValueError('Explicit confirmation is required before recalculation.')

    food_item = entry.food_item if food_item is UNSET else food_item
    quantity = entry.quantity if quantity is UNSET else quantity
    unit = entry.unit if unit is UNSET else unit
    price_observation = (
        entry.price_observation
        if price_observation is UNSET
        else price_observation
    )
    if food_item is None:
        raise ValueError('A food item is required for recalculation.')

    price_observation = _validate_price_observation(food_item, price_observation)
    snapshots = _snapshot_values(food_item, quantity, unit, price_observation)
    entry.food_item = food_item
    entry.price_observation = price_observation
    entry.source_name = str(food_item)
    entry.quantity = quantity
    entry.unit = unit
    entry.consumed_at = (
        entry.consumed_at if consumed_at is UNSET else _as_aware(consumed_at)
    )
    if meal_category is not UNSET:
        entry.meal_category = meal_category
    for field, value in snapshots.items():
        setattr(entry, field, value)
    entry.full_clean()
    entry.save()
    return entry


@transaction.atomic
def update_consumption_entry(
    entry: ConsumptionEntry,
    *,
    consumed_at=UNSET,
    meal_category=UNSET,
    food_item=UNSET,
    quantity=UNSET,
    unit=UNSET,
    price_observation=UNSET,
    recalculate: bool = False,
) -> ConsumptionEntry:
    """Update metadata, or require an explicit recalculation for source changes."""
    source_changed = any(
        value is not UNSET
        for value in (food_item, quantity, unit, price_observation)
    )
    if source_changed:
        if not recalculate:
            raise ValueError(
                'Changing food, quantity, unit, or price requires explicit recalculation.'
            )
        return recalculate_consumption_entry(
            entry,
            food_item=food_item,
            quantity=quantity,
            unit=unit,
            price_observation=price_observation,
            consumed_at=consumed_at,
            meal_category=meal_category,
            confirmed=True,
        )

    if consumed_at is not UNSET:
        entry.consumed_at = _as_aware(consumed_at)
    if meal_category is not UNSET:
        entry.meal_category = meal_category
    entry.full_clean()
    entry.save(update_fields=['consumed_at', 'meal_category', 'updated_at'])
    return entry


def get_consumption_entries_for_date(reporting_date: date, tz=None):
    """Return entries whose timestamps fall on a local reporting date."""
    tz = tz or timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(reporting_date, time.min), timezone=tz)
    end = timezone.make_aware(datetime.combine(reporting_date, time.max), timezone=tz)
    return ConsumptionEntry.objects.filter(
        consumed_at__gte=start,
        consumed_at__lte=end,
    ).select_related('food_item', 'price_observation')


def get_daily_summary(reporting_date: Optional[date] = None, tz=None) -> DailyTotals:
    """Return totals for a local reporting date without treating unknowns as zero."""
    tz = tz or timezone.get_current_timezone()
    reporting_date = reporting_date or timezone.localdate()
    entries = get_consumption_entries_for_date(reporting_date, tz=tz)
    return aggregate_daily(entries, reporting_date, tz=tz)
