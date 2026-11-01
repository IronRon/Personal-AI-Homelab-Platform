from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional

from django.utils import timezone

from ..models import MealPrepBatch
from .calculations import calculate_batch_totals
from .consumption import get_consumption_entries_for_date
from .purchases import get_food_purchases_for_date


@dataclass(frozen=True)
class FoodCostEvent:
    occurred_at: datetime
    event_type: str
    description: str
    amount: Optional[Decimal]
    currency: str
    amount_label: str
    complete: bool
    quantity: Optional[Decimal] = None
    unit: str = ''
    source: str = ''


def _batch_entries_for_date(reporting_date: date, tz):
    start = timezone.make_aware(datetime.combine(reporting_date, time.min), timezone=tz)
    end = timezone.make_aware(datetime.combine(reporting_date, time.max), timezone=tz)
    return MealPrepBatch.objects.filter(
        cooked_at__gte=start,
        cooked_at__lte=end,
    ).prefetch_related('ingredients')


def _is_batch_consumption(entry) -> bool:
    return bool(
        entry.meal_prep_batch_id
        or (
            entry.food_item_id is None
            and entry.price_observation_id is None
            and entry.source_name.startswith('Meal Prep Batch: ')
        )
    )


def get_food_cost_events_for_date(reporting_date: date, tz=None) -> list[FoodCostEvent]:
    """Build a dated view of spend and estimated food costs without summing them."""
    tz = tz or timezone.get_current_timezone()
    events = []

    for purchase in get_food_purchases_for_date(reporting_date, tz=tz):
        events.append(FoodCostEvent(
            occurred_at=purchase.purchased_at,
            event_type='PURCHASE',
            description=purchase.description,
            amount=purchase.amount_paid,
            currency=purchase.currency,
            amount_label='Paid',
            complete=True,
            quantity=purchase.quantity,
            unit=purchase.unit,
            source=purchase.source,
        ))

    for batch in _batch_entries_for_date(reporting_date, tz):
        try:
            totals = calculate_batch_totals(batch)
        except ValueError:
            amount = None
            currency = ''
            complete = False
        else:
            currency = totals.currency or ''
            amount = totals.estimated_cost if currency else None
            complete = totals.cost_complete
        events.append(FoodCostEvent(
            occurred_at=batch.cooked_at,
            event_type='MEAL PREP',
            description=batch.name,
            amount=amount,
            currency=currency,
            amount_label='Estimated batch cost' if complete else 'Estimated partial batch cost',
            complete=complete,
            quantity=batch.yield_quantity,
            unit=batch.yield_unit,
            source='Batch ingredient snapshots',
        ))

    for entry in get_consumption_entries_for_date(reporting_date, tz=tz):
        from_batch = not entry.is_quick_add and _is_batch_consumption(entry)
        description = entry.source_name
        if from_batch and description.startswith('Meal Prep Batch: '):
            description = description.removeprefix('Meal Prep Batch: ')
        event_type = (
            'QUICK ADD' if entry.is_quick_add
            else 'ATE FROM BATCH' if from_batch
            else 'CONSUMPTION'
        )
        events.append(FoodCostEvent(
            occurred_at=entry.consumed_at,
            event_type=event_type,
            description=description,
            amount=entry.estimated_cost,
            currency=entry.currency if entry.estimated_cost is not None else '',
            amount_label='Estimated consumed cost',
            complete=entry.estimated_cost is not None,
            quantity=entry.quantity,
            unit=entry.unit,
            source=entry.cost_source,
        ))

    return sorted(events, key=lambda event: (event.occurred_at, event.event_type, event.description), reverse=True)
