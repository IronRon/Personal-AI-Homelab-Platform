from datetime import date

from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import ConsumptionEntryForm, FoodItemForm, PriceObservationForm
from .models import ConsumptionEntry, FoodItem, PriceObservation
from .services.consumption import (
    create_consumption_entry,
    get_consumption_entries_for_date,
    get_daily_summary,
    recalculate_consumption_entry,
    update_consumption_entry,
)


def catalogue(request):
    search_query = request.GET.get('q', '').strip()
    food_items = FoodItem.objects.all()
    if search_query:
        food_items = food_items.filter(
            Q(name__icontains=search_query) | Q(brand__icontains=search_query)
        )

    return render(
        request,
        'food/index.html',
        {'food_items': food_items, 'search_query': search_query},
    )


def food_item_create(request):
    form = FoodItemForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        food_item = form.save()
        messages.success(request, f'{food_item} was added to the catalogue.')
        return redirect('food_item_detail', pk=food_item.pk)

    return render(request, 'food/food_item_form.html', {'form': form, 'is_edit': False})


def food_item_edit(request, pk):
    food_item = get_object_or_404(FoodItem, pk=pk)
    form = FoodItemForm(request.POST or None, instance=food_item)
    if request.method == 'POST' and form.is_valid():
        food_item = form.save()
        messages.success(request, f'{food_item} was updated.')
        return redirect('food_item_detail', pk=food_item.pk)

    return render(request, 'food/food_item_form.html', {'form': form, 'is_edit': True})


def food_item_detail(request, pk):
    food_item = get_object_or_404(FoodItem, pk=pk)
    return render(
        request,
        'food/food_item_detail.html',
        {
            'food_item': food_item,
            'price_observations': food_item.price_observations.all(),
        },
    )


def price_observation_create(request, food_item_pk):
    food_item = get_object_or_404(FoodItem, pk=food_item_pk)
    form = PriceObservationForm(food_item, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Price history for {food_item} was updated.')
        return redirect('food_item_detail', pk=food_item.pk)

    return render(
        request,
        'food/price_observation_form.html',
        {'form': form, 'food_item': food_item, 'is_edit': False},
    )


def price_observation_edit(request, food_item_pk, pk):
    food_item = get_object_or_404(FoodItem, pk=food_item_pk)
    price_observation = get_object_or_404(
        PriceObservation,
        pk=pk,
        food_item=food_item,
    )
    form = PriceObservationForm(food_item, request.POST or None, instance=price_observation)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Price history for {food_item} was updated.')
        return redirect('food_item_detail', pk=food_item.pk)

    return render(
        request,
        'food/price_observation_form.html',
        {'form': form, 'food_item': food_item, 'is_edit': True},
    )


def _reporting_date(request):
    value = request.GET.get('date', '').strip()
    if not value:
        return timezone.localdate()
    try:
        return date.fromisoformat(value)
    except ValueError:
        messages.warning(request, 'The requested date was invalid; showing today instead.')
        return timezone.localdate()


def food_today(request):
    reporting_date = _reporting_date(request)
    entries = get_consumption_entries_for_date(reporting_date)
    summary = get_daily_summary(reporting_date)
    return render(
        request,
        'food/today.html',
        {
            'entries': entries,
            'summary': summary,
            'reporting_date': reporting_date,
        },
    )


def consumption_create(request):
    form = ConsumptionEntryForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        try:
            entry = create_consumption_entry(
                food_item=data['food_item'],
                quantity=data['quantity'],
                unit=data['unit'],
                consumed_at=data['consumed_at'],
                meal_category=data.get('meal_category', ''),
                price_observation=data.get('price_observation'),
            )
        except ValueError as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, f'{entry.source_name} was added to your food log.')
            return redirect(
                f'{reverse("food_today")}?date={timezone.localtime(entry.consumed_at).date().isoformat()}'
            )

    return render(request, 'food/consumption_form.html', {'form': form, 'is_edit': False})


def consumption_edit(request, pk):
    entry = get_object_or_404(ConsumptionEntry, pk=pk)
    form = ConsumptionEntryForm(request.POST or None, instance=entry)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        action = request.POST.get('action', 'save')
        source_changed = any([
            data['food_item'].pk != entry.food_item_id,
            data['quantity'] != entry.quantity,
            data['unit'] != entry.unit,
            (data.get('price_observation').pk if data.get('price_observation') else None)
            != entry.price_observation_id,
        ])
        try:
            if action == 'recalculate':
                if not data.get('confirm_recalculation'):
                    form.add_error(None, 'Confirm recalculation before applying current catalogue values.')
                else:
                    entry = recalculate_consumption_entry(
                        entry,
                        food_item=data['food_item'],
                        quantity=data['quantity'],
                        unit=data['unit'],
                        consumed_at=data['consumed_at'],
                        meal_category=data.get('meal_category', ''),
                        price_observation=data.get('price_observation'),
                        confirmed=True,
                    )
            elif source_changed:
                form.add_error(
                    None,
                    'Changing food, quantity, unit, or price requires the recalculation action.',
                )
            else:
                entry = update_consumption_entry(
                    entry,
                    consumed_at=data['consumed_at'],
                    meal_category=data.get('meal_category', ''),
                )
        except ValueError as error:
            form.add_error(None, str(error))
        else:
            if not form.errors:
                messages.success(request, 'Food log entry updated.')
                return redirect(
                    f'{reverse("food_history")}?date={timezone.localtime(entry.consumed_at).date().isoformat()}'
                )

    return render(
        request,
        'food/consumption_form.html',
        {'form': form, 'entry': entry, 'is_edit': True},
    )


def food_history(request):
    reporting_date = _reporting_date(request)
    entries = get_consumption_entries_for_date(reporting_date)
    return render(
        request,
        'food/history.html',
        {'entries': entries, 'reporting_date': reporting_date},
    )


def consumption_delete(request, pk):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    entry = get_object_or_404(ConsumptionEntry, pk=pk)
    reporting_date = timezone.localtime(entry.consumed_at).date()
    entry.delete()
    messages.success(request, 'Food log entry deleted.')
    return redirect(f'{reverse("food_history")}?date={reporting_date.isoformat()}')
