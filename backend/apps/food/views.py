from datetime import date

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from .forms import (
    BatchIngredientFormSet,
    BatchConsumptionForm,
    ConsumptionMetadataForm,
    ConsumptionEntryForm,
    FoodItemForm,
    MealPrepBatchForm,
    PriceObservationForm,
    RecipeForm,
    RecipeIngredientForm,
)
from .models import (
    ConsumptionEntry,
    FoodItem,
    MealPrepBatch,
    PriceObservation,
    Recipe,
    RecipeIngredient,
)
from .services.calculations import (
    calculate_batch_totals,
    calculate_recipe_estimate,
    select_price_observation,
)
from .services.consumption import (
    create_batch_consumption_entry,
    create_consumption_entry,
    get_consumption_entries_for_date,
    get_daily_summary,
    recalculate_consumption_entry,
    update_consumption_entry,
)
from .services.meal_prep import BatchIngredientInput, create_meal_prep_batch


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


def recipe_list(request):
    recipes = Recipe.objects.prefetch_related('ingredients')
    return render(request, 'food/recipe_list.html', {'recipes': recipes})


def recipe_create(request):
    form = RecipeForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        recipe = form.save()
        messages.success(request, f'{recipe.name} was added to Recipes.')
        return redirect('recipe_detail', pk=recipe.pk)

    return render(request, 'food/recipe_form.html', {'form': form, 'is_edit': False})


def recipe_edit(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk)
    form = RecipeForm(request.POST or None, instance=recipe)
    if request.method == 'POST' and form.is_valid():
        recipe = form.save()
        messages.success(request, f'{recipe.name} was updated.')
        return redirect('recipe_detail', pk=recipe.pk)

    return render(
        request,
        'food/recipe_form.html',
        {'form': form, 'recipe': recipe, 'is_edit': True},
    )


def recipe_detail(request, pk):
    recipe = get_object_or_404(
        Recipe.objects.prefetch_related('ingredients__food_item', 'ingredients__price_observation'),
        pk=pk,
    )
    ingredients = list(recipe.ingredients.select_related('food_item', 'price_observation'))
    estimate = None
    estimate_error = False
    mixed_currency = False
    if ingredients:
        try:
            estimate = calculate_recipe_estimate(recipe)
            selected_currencies = set()
            # The estimate marks mixed-currency cost incomplete; the template also explains why.
            for ingredient in ingredients:
                selected_price = select_price_observation(
                    ingredient.food_item,
                    ingredient.price_observation,
                )
                if selected_price:
                    selected_currencies.add(selected_price.currency)
            mixed_currency = len(selected_currencies) > 1
        except (ValueError, ValidationError):
            # Catalogue edits can invalidate saved ingredient selections; keep detail usable.
            estimate_error = True

    return render(
        request,
        'food/recipe_detail.html',
        {
            'recipe': recipe,
            'ingredients': ingredients,
            'estimate': estimate,
            'estimate_error': estimate_error,
            'mixed_currency': mixed_currency,
        },
    )


@require_GET
def meal_prep_list(request):
    batches = MealPrepBatch.objects.select_related('recipe').prefetch_related('ingredients')
    return render(request, 'food/meal_prep_batch_list.html', {'batches': batches})


def _recipe_batch_initial(recipe):
    return [
        {
            'food_item': ingredient.food_item_id,
            'quantity': ingredient.quantity,
            'unit': ingredient.unit,
            'price_observation': ingredient.price_observation_id or '',
        }
        for ingredient in recipe.ingredients.all()
    ]


def _render_meal_prep_form(request, form, formset):
    return render(
        request,
        'food/meal_prep_batch_form.html',
        {
            'form': form,
            'formset': formset,
            'recipe_choices': Recipe.objects.order_by('name', 'id'),
        },
    )


def meal_prep_create(request):
    prefix = 'ingredients'
    if request.method != 'POST':
        recipe_id = request.GET.get('recipe')
        try:
            recipe = Recipe.objects.filter(pk=int(recipe_id)).first() if recipe_id else None
        except ValueError:
            recipe = None
        initial = {'recipe': recipe.pk} if recipe else None
        form = MealPrepBatchForm(initial=initial)
        formset = BatchIngredientFormSet(
            initial=_recipe_batch_initial(recipe) if recipe else None,
            prefix=prefix,
        )
        return _render_meal_prep_form(request, form, formset)

    form = MealPrepBatchForm(request.POST)
    action = request.POST.get('action', 'create')
    if 'remove_index' in request.POST:
        action = 'remove_ingredient'

    if action == 'load_recipe':
        form.is_valid()
        recipe = form.cleaned_data.get('recipe')
        if recipe is None:
            form.add_error('recipe', 'Choose a Recipe before loading its planned ingredients.')
            initial = None
        else:
            initial = _recipe_batch_initial(recipe)
        formset = BatchIngredientFormSet(initial=initial, prefix=prefix)
        return _render_meal_prep_form(request, form, formset)

    post_data = request.POST.copy()
    if action == 'add_ingredient':
        try:
            total_forms = int(post_data.get(f'{prefix}-TOTAL_FORMS', '0'))
        except ValueError:
            total_forms = 0
        post_data[f'{prefix}-TOTAL_FORMS'] = str(total_forms + 1)
    elif action == 'remove_ingredient':
        try:
            row_index = int(request.POST.get('remove_index', '-1'))
            total_forms = int(post_data.get(f'{prefix}-TOTAL_FORMS', '0'))
        except ValueError:
            row_index = -1
            total_forms = 0
        if 0 <= row_index < total_forms:
            post_data[f'{prefix}-{row_index}-DELETE'] = 'on'

    formset = BatchIngredientFormSet(post_data, prefix=prefix)
    if action in ('add_ingredient', 'remove_ingredient'):
        form.is_valid()
        formset.is_valid()
        # Interim POSTs retain submitted rows in the bound formset without saving a draft batch.
        return _render_meal_prep_form(request, form, formset)

    if form.is_valid() and formset.is_valid():
        ingredient_inputs = [
            BatchIngredientInput(
                food_item=ingredient['food_item'],
                quantity=ingredient['quantity'],
                unit=ingredient['unit'],
                price_observation=ingredient['price_observation'],
            )
            for ingredient_form in formset.forms
            if (ingredient := ingredient_form.cleaned_data)
            and not ingredient.get('DELETE')
            and ingredient.get('food_item') is not None
        ]
        try:
            # Keep snapshot construction and transactional persistence in the domain service.
            batch = create_meal_prep_batch(
                name=form.cleaned_data['name'],
                recipe=form.cleaned_data['recipe'],
                cooked_at=form.cleaned_data['cooked_at'],
                yield_quantity=form.cleaned_data['yield_quantity'],
                yield_unit=form.cleaned_data['yield_unit'],
                ingredients=ingredient_inputs,
            )
        except ValidationError as error:
            if hasattr(error, 'error_dict'):
                for field, errors in error.error_dict.items():
                    target = field if field in form.fields else None
                    for field_error in errors:
                        form.add_error(target, field_error)
            else:
                for message in error.messages:
                    form.add_error(None, message)
        except ValueError as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, f'{batch.name} was added to Meal Prep.')
            return redirect('meal_prep_detail', pk=batch.pk)

    return _render_meal_prep_form(request, form, formset)


@require_GET
def meal_prep_detail(request, pk):
    batch = get_object_or_404(
        MealPrepBatch.objects.select_related('recipe').prefetch_related('ingredients'),
        pk=pk,
    )
    totals = None
    totals_error = False
    try:
        # Batch totals must remain historical and never reread live catalogue values.
        totals = calculate_batch_totals(batch)
    except ValueError:
        totals_error = True
    return render(
        request,
        'food/meal_prep_batch_detail.html',
        {
            'batch': batch,
            'ingredients': batch.ingredients.all(),
            'totals': totals,
            'totals_error': totals_error,
        },
    )


def batch_consumption_create(request, batch_pk):
    batch = get_object_or_404(
        MealPrepBatch.objects.select_related('recipe').prefetch_related('ingredients'),
        pk=batch_pk,
    )
    form = BatchConsumptionForm(batch, request.POST or None)
    totals = None
    totals_error = False
    try:
        totals = calculate_batch_totals(batch)
    except ValueError:
        totals_error = True

    if request.method == 'POST' and form.is_valid():
        if totals_error:
            form.add_error(
                None,
                'This batch has conflicting stored cost currencies and cannot be logged.',
            )
        elif batch.yield_quantity <= 0:
            form.add_error(None, 'This batch has an invalid yield and cannot be logged.')
        else:
            data = form.cleaned_data
            try:
                entry = create_batch_consumption_entry(
                    batch,
                    consumed_quantity=data['quantity'],
                    unit=data['unit'],
                    consumed_at=data['consumed_at'],
                    meal_category=data.get('meal_category', ''),
                )
            except (ValueError, ValidationError):
                form.add_error(
                    None,
                    'This batch could not be logged. Check the amount and batch details, then try again.',
                )
            else:
                messages.success(request, f'{entry.source_name} was added to your food log.')
                reporting_date = timezone.localtime(entry.consumed_at).date().isoformat()
                return redirect(f'{reverse("food_today")}?date={reporting_date}')

    return render(
        request,
        'food/meal_prep_consumption_form.html',
        {
            'batch': batch,
            'form': form,
            'totals': totals,
            'totals_error': totals_error,
        },
    )


def recipe_ingredient_create(request, recipe_pk):
    recipe = get_object_or_404(Recipe, pk=recipe_pk)
    form = RecipeIngredientForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        ingredient = form.save(commit=False)
        ingredient.recipe = recipe
        try:
            # Model.save() skips clean(); validate cross-model unit and price rules explicitly.
            ingredient.full_clean()
            ingredient.save()
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, f'{ingredient.food_item} was added to {recipe.name}.')
            return redirect('recipe_detail', pk=recipe.pk)

    return render(
        request,
        'food/recipe_ingredient_form.html',
        {'form': form, 'recipe': recipe, 'is_edit': False},
    )


def recipe_ingredient_edit(request, recipe_pk, pk):
    recipe = get_object_or_404(Recipe, pk=recipe_pk)
    # Constrain the lookup to its parent so another Recipe cannot edit this row by ID.
    ingredient = get_object_or_404(RecipeIngredient, pk=pk, recipe=recipe)
    form = RecipeIngredientForm(request.POST or None, instance=ingredient)
    if request.method == 'POST' and form.is_valid():
        ingredient = form.save(commit=False)
        try:
            ingredient.full_clean()
            ingredient.save()
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, f'{ingredient.food_item} was updated in {recipe.name}.')
            return redirect('recipe_detail', pk=recipe.pk)

    return render(
        request,
        'food/recipe_ingredient_form.html',
        {'form': form, 'recipe': recipe, 'is_edit': True},
    )


def recipe_ingredient_delete(request, recipe_pk, pk):
    # Keep destructive ingredient removal out of safe GET requests.
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    recipe = get_object_or_404(Recipe, pk=recipe_pk)
    # Enforce the same parent scope as ingredient editing.
    ingredient = get_object_or_404(RecipeIngredient, pk=pk, recipe=recipe)
    ingredient.delete()
    messages.success(request, f'An ingredient was removed from {recipe.name}.')
    return redirect('recipe_detail', pk=recipe.pk)


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
    metadata_only = entry.meal_prep_batch_id is not None or entry.food_item_id is None
    if metadata_only:
        form = ConsumptionMetadataForm(request.POST or None, instance=entry)
        if request.method == 'POST' and form.is_valid():
            # Metadata-only edits preserve the already-recorded historical snapshots.
            entry = update_consumption_entry(
                entry,
                consumed_at=form.cleaned_data['consumed_at'],
                meal_category=form.cleaned_data.get('meal_category', ''),
            )
            messages.success(request, 'Food log entry updated.')
            return redirect(
                f'{reverse("food_history")}?date={timezone.localtime(entry.consumed_at).date().isoformat()}'
            )
        return render(
            request,
            'food/consumption_form.html',
            {
                'form': form,
                'entry': entry,
                'is_edit': True,
                'metadata_only': True,
            },
        )

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
