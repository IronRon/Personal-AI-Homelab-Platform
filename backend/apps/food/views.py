from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .forms import FoodItemForm, PriceObservationForm
from .models import FoodItem, PriceObservation


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
