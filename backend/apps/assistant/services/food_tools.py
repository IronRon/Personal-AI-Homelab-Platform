"""Read-only tools exposing a small, validated surface of the Food module."""

from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.food.models import ConsumptionEntry, FoodItem, MealPrepBatch, PriceObservation
from apps.food.services.calculations import calculate_batch_totals
from apps.food.services.consumption import get_daily_summary


MAX_HISTORY_DAYS = 31
MAX_HISTORY_RESULTS = 30
MAX_CATALOGUE_RESULTS = 20
MAX_BATCH_RESULTS = 15


def _decimal(value):
    return str(value) if value is not None else None


def _parse_date(value, field_name):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"'{field_name}' must be a date in YYYY-MM-DD format.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"'{field_name}' must be a valid date in YYYY-MM-DD format.") from exc


def _positive_int(value, field_name, maximum):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > maximum:
        raise ValueError(f"'{field_name}' must be a whole number between 1 and {maximum}.")
    return value


def _summary_payload(reporting_date):
    totals = get_daily_summary(reporting_date, tz=timezone.get_default_timezone())
    cost_aggregate_complete = totals.cost_complete and (
        totals.estimated_cost is not None or totals.entry_count == 0
    )
    return {
        "date": reporting_date.isoformat(),
        "entry_count": totals.entry_count,
        "calories": _decimal(totals.calories) if totals.calories_complete else None,
        "protein_g": _decimal(totals.protein) if totals.protein_complete else None,
        "carbohydrates_g": _decimal(totals.carbohydrates) if totals.carbohydrates_complete else None,
        "fat_g": _decimal(totals.fat) if totals.fat_complete else None,
        "estimated_consumed_cost": (
            _decimal(totals.estimated_cost)
            if cost_aggregate_complete else None
        ),
        "currency": totals.currency if totals.estimated_cost is not None else None,
        "estimated_consumed_cost_by_currency": {
            currency: _decimal(amount)
            for currency, amount in totals.costs_by_currency.items()
        },
        "completeness": {
            "calories": totals.calories_complete,
            "protein": totals.protein_complete,
            "carbohydrates": totals.carbohydrates_complete,
            "fat": totals.fat_complete,
            "cost": cost_aggregate_complete,
        },
        "note": "A null value means the data is incomplete or unavailable; it does not mean zero.",
    }


def get_daily_food_summary(arguments):
    reporting_date = _parse_date(arguments.get("date"), "date") or timezone.localdate()
    return _summary_payload(reporting_date)


def get_food_history(arguments):
    today = timezone.localdate()
    end_date = _parse_date(arguments.get("end_date"), "end_date") or today
    start_date = _parse_date(arguments.get("start_date"), "start_date") or (end_date - timedelta(days=6))
    if start_date > end_date:
        raise ValueError("'start_date' cannot be later than 'end_date'.")
    if (end_date - start_date).days >= MAX_HISTORY_DAYS:
        raise ValueError(f"Date range cannot exceed {MAX_HISTORY_DAYS} days.")
    limit = _positive_int(arguments.get("limit", 20), "limit", MAX_HISTORY_RESULTS)

    entries = ConsumptionEntry.objects.filter(
        consumed_at__date__gte=start_date,
        consumed_at__date__lte=end_date,
    ).select_related("food_item", "meal_prep_batch").order_by("-consumed_at", "-id")[:limit]

    rows = []
    for entry in entries:
        local_time = timezone.localtime(entry.consumed_at)
        rows.append({
            "id": entry.pk,
            "consumed_at": local_time.isoformat(),
            "date": local_time.date().isoformat(),
            "meal_category": entry.meal_category or None,
            "source_name": entry.source_name,
            "source_type": "quick_add" if entry.is_quick_add else (
                "meal_prep_batch" if entry.meal_prep_batch_id else "catalogue_item"
            ),
            "quantity": _decimal(entry.quantity),
            "unit": entry.unit or None,
            "calories": _decimal(entry.calories),
            "protein_g": _decimal(entry.protein),
            "carbohydrates_g": _decimal(entry.carbohydrates),
            "fat_g": _decimal(entry.fat),
            "estimated_cost": _decimal(entry.estimated_cost),
            "currency": entry.currency or None,
            "nutrition_source": entry.nutrition_source or None,
        })
    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "returned_count": len(rows),
        "limit": limit,
        "entries": rows,
        "note": "Null nutrition or cost values are unknown/unavailable, not zero. This is consumption history, not grocery spending.",
    }


def search_food_catalogue(arguments):
    query = arguments.get("query", "")
    if not isinstance(query, str):
        raise ValueError("'query' must be text.")
    query = query.strip()
    if len(query) > 100:
        raise ValueError("'query' must be 100 characters or fewer.")
    limit = _positive_int(arguments.get("limit", 10), "limit", MAX_CATALOGUE_RESULTS)
    items = FoodItem.objects.all()
    if query:
        items = items.filter(name__icontains=query) | items.filter(brand__icontains=query)
    items = items.order_by("name", "brand", "id")[:limit]
    return {
        "query": query,
        "returned_count": len(items),
        "items": [
            {
                "id": item.pk,
                "name": item.name,
                "brand": item.brand or None,
                "item_type": item.item_type,
                "nutrition_basis_unit": item.nutrition_basis_unit,
                "calories_per_100": _decimal(item.calories_per_100),
                "protein_per_100": _decimal(item.protein_per_100),
                "carbohydrates_per_100": _decimal(item.carbohydrates_per_100),
                "fat_per_100": _decimal(item.fat_per_100),
                "nutrition_source": item.nutrition_source or None,
            }
            for item in items
        ],
        "note": "Null nutrition fields mean the catalogue does not contain that value.",
    }


def get_food_item_details(arguments):
    item_id = _positive_int(arguments.get("food_item_id"), "food_item_id", 2_147_483_647)
    try:
        item = FoodItem.objects.get(pk=item_id)
    except FoodItem.DoesNotExist as exc:
        raise ValueError("No Food catalogue item exists with that ID.") from exc
    prices = PriceObservation.objects.filter(food_item=item).order_by("-observed_at", "-id")[:5]
    return {
        "id": item.pk,
        "name": item.name,
        "brand": item.brand or None,
        "item_type": item.item_type,
        "nutrition_basis_unit": item.nutrition_basis_unit,
        "nutrition_per_100": {
            "calories": _decimal(item.calories_per_100),
            "protein_per_100": _decimal(item.protein_per_100),
            "carbohydrates_per_100": _decimal(item.carbohydrates_per_100),
            "fat_per_100": _decimal(item.fat_per_100),
        },
        "nutrition_source": item.nutrition_source or None,
        "recent_price_observations": [
            {
                "observed_at": timezone.localtime(price.observed_at).isoformat(),
                "package_quantity": _decimal(price.package_quantity),
                "package_unit": price.package_unit,
                "paid_price": _decimal(price.paid_price),
                "currency": price.currency,
                "source": price.source or None,
            }
            for price in prices
        ],
    }


def get_meal_prep_batches(arguments):
    limit = _positive_int(arguments.get("limit", 10), "limit", MAX_BATCH_RESULTS)
    batches = MealPrepBatch.objects.prefetch_related("ingredients").order_by("-cooked_at", "-id")[:limit]
    rows = []
    for batch in batches:
        try:
            totals = calculate_batch_totals(batch)
        except ValueError:
            totals = None
        rows.append({
            "id": batch.pk,
            "name": batch.name,
            "cooked_at": timezone.localtime(batch.cooked_at).isoformat(),
            "yield_quantity": _decimal(batch.yield_quantity),
            "yield_unit": batch.yield_unit,
            "ingredient_count": len(batch.ingredients.all()),
            "nutrition": None if totals is None else {
                "calories": _decimal(totals.calories) if totals.calories_complete else None,
                "protein_g": _decimal(totals.protein) if totals.protein_complete else None,
                "carbohydrates_g": _decimal(totals.carbohydrates) if totals.carbohydrates_complete else None,
                "fat_g": _decimal(totals.fat) if totals.fat_complete else None,
            },
            "estimated_total_cost": (
                _decimal(totals.estimated_cost)
                if totals is not None and totals.cost_complete else None
            ),
            "currency": totals.currency if totals is not None and totals.cost_complete else None,
        })
    return {
        "returned_count": len(rows),
        "batches": rows,
        "note": "Nutrition and cost values are historical batch snapshots. Null values mean incomplete or unavailable.",
    }


FOOD_TOOL_ALLOWED_ARGUMENTS = {
    "get_daily_food_summary": {"date"},
    "get_food_history": {"start_date", "end_date", "limit"},
    "search_food_catalogue": {"query", "limit"},
    "get_food_item_details": {"food_item_id"},
    "get_meal_prep_batches": {"limit"},
}

FOOD_TOOL_FUNCTIONS = {
    "get_daily_food_summary": get_daily_food_summary,
    "get_food_history": get_food_history,
    "search_food_catalogue": search_food_catalogue,
    "get_food_item_details": get_food_item_details,
    "get_meal_prep_batches": get_meal_prep_batches,
}

FOOD_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_daily_food_summary",
            "description": "Read the user's Food consumption totals for a date. Use this for today's calories, protein and macros.",
            "parameters": {"type": "object", "properties": {
                "date": {"type": "string", "description": "Optional local date in YYYY-MM-DD format; defaults to today."},
            }, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_food_history",
            "description": "Read individual food consumption entries over a date range, up to 31 days.",
            "parameters": {"type": "object", "properties": {
                "start_date": {"type": "string", "description": "Optional start date YYYY-MM-DD; defaults to 7 days before end_date."},
                "end_date": {"type": "string", "description": "Optional end date YYYY-MM-DD; defaults to today."},
                "limit": {"type": "integer", "description": "Maximum entries, 1 to 30; defaults to 20."},
            }, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_food_catalogue",
            "description": "Search the user's Food catalogue by food name or brand. An empty query lists catalogue items.",
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string", "description": "Food name or brand search text."},
                "limit": {"type": "integer", "description": "Maximum items, 1 to 20; defaults to 10."},
            }, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_food_item_details",
            "description": "Read nutrition details and recent price observations for one catalogue item using its ID.",
            "parameters": {"type": "object", "properties": {
                "food_item_id": {"type": "integer", "description": "ID returned by search_food_catalogue."},
            }, "required": ["food_item_id"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_meal_prep_batches",
            "description": "Read recent meal-prep batches, yields, and their saved nutrition and cost totals.",
            "parameters": {"type": "object", "properties": {
                "limit": {"type": "integer", "description": "Maximum batches, 1 to 15; defaults to 10."},
            }, "required": []},
        },
    },
]


def execute_food_tool(name, arguments):
    """Execute only registered read-only Food tools with validated arguments."""
    if name not in FOOD_TOOL_FUNCTIONS:
        raise ValueError("That tool is not available.")
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be an object.")
    unexpected = set(arguments) - FOOD_TOOL_ALLOWED_ARGUMENTS[name]
    if unexpected:
        raise ValueError("Unexpected tool argument(s): " + ", ".join(sorted(unexpected)))
    return FOOD_TOOL_FUNCTIONS[name](arguments)
