from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone

from ..models import FoodPurchase
from .calculations import aggregate_purchase_costs


def _date_bounds(reporting_date: date, tz):
    start = timezone.make_aware(datetime.combine(reporting_date, time.min), timezone=tz)
    end = timezone.make_aware(datetime.combine(reporting_date, time.max), timezone=tz)
    return start, end


@transaction.atomic
def create_food_purchase(
    *,
    description: str,
    amount_paid: Decimal,
    currency: str = 'EUR',
    purchased_at=None,
    food_item=None,
    quantity=None,
    unit: str = '',
    source: str = '',
) -> FoodPurchase:
    """Record actual Food spending independently of consumption estimates."""
    if purchased_at is None:
        purchased_at = timezone.now()
    elif timezone.is_naive(purchased_at):
        purchased_at = timezone.make_aware(
            purchased_at,
            timezone=timezone.get_current_timezone(),
        )

    purchase = FoodPurchase(
        description=description,
        food_item=food_item,
        purchased_at=purchased_at,
        amount_paid=amount_paid,
        currency=currency,
        quantity=quantity,
        unit=unit,
        source=source,
    )
    purchase.full_clean()
    purchase.save()
    return purchase


def get_food_purchases_for_date(reporting_date: date, tz=None):
    tz = tz or timezone.get_current_timezone()
    start, end = _date_bounds(reporting_date, tz)
    return FoodPurchase.objects.filter(
        purchased_at__gte=start,
        purchased_at__lte=end,
    ).select_related('food_item')


def get_purchase_totals_for_date(reporting_date: date, tz=None) -> dict[str, Decimal]:
    return aggregate_purchase_costs(get_food_purchases_for_date(reporting_date, tz=tz))
