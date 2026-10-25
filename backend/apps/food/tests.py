from datetime import date, datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from .forms import (
    BatchIngredientForm,
    BatchIngredientFormSet,
    ConsumptionEntryForm,
    FoodItemForm,
    FoodPurchaseForm,
    MealPrepBatchForm,
    PriceObservationForm,
    RecipeForm,
    RecipeIngredientForm,
)
from .models import (
    BatchIngredient,
    ConsumptionEntry,
    FoodItem,
    FoodPurchase,
    FoodPurchase,
    MealPrepBatch,
    PriceObservation,
    Recipe,
    RecipeIngredient,
)
from .services.calculations import (
    aggregate_daily,
    calculate_allocated_cost,
    calculate_batch_totals,
    calculate_recipe_estimate,
    scale_batch_totals,
    scale_nutrition,
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
from .services.purchases import create_food_purchase, get_purchase_totals_for_date
from .services.cost_history import get_food_cost_events_for_date


class FoodModelTests(TestCase):
    def setUp(self):
        self.food_item = FoodItem.objects.create(
            name='Oats',
            item_type=FoodItem.INGREDIENT,
            nutrition_basis_unit=FoodItem.GRAMS,
            calories_per_100=Decimal('380'),
            protein_per_100=Decimal('13.20'),
            carbohydrates_per_100=Decimal('67.00'),
            fat_per_100=Decimal('6.50'),
            nutrition_source='manual',
        )

    def test_price_observation_requires_matching_package_unit(self):
        price = PriceObservation(
            food_item=self.food_item,
            package_quantity=Decimal('1000'),
            package_unit=FoodItem.MILLILITRES,
            paid_price=Decimal('2.50'),
        )

        with self.assertRaises(ValidationError):
            price.full_clean()

    def test_consumption_entry_requires_matching_food_unit(self):
        entry = ConsumptionEntry(
            food_item=self.food_item,
            source_name='Oats',
            quantity=Decimal('50'),
            unit=FoodItem.MILLILITRES,
        )

        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_consumption_entry_can_preserve_unknown_values(self):
        entry = ConsumptionEntry(
            food_item=self.food_item,
            source_name='Oats',
            quantity=Decimal('50'),
            unit=FoodItem.GRAMS,
            calories=None,
            protein=None,
            carbohydrates=None,
            fat=None,
            estimated_cost=None,
        )

        entry.full_clean()
        entry.save()
        self.assertIsNone(entry.calories)
        self.assertIsNone(entry.estimated_cost)

    def test_food_item_rejects_negative_nutrition(self):
        self.food_item.protein_per_100 = Decimal('-1')

        with self.assertRaises(ValidationError):
            self.food_item.full_clean()

    def test_consumption_snapshot_does_not_change_when_catalogue_changes(self):
        entry = ConsumptionEntry.objects.create(
            food_item=self.food_item,
            source_name='Oats',
            quantity=Decimal('250'),
            unit=FoodItem.GRAMS,
            calories=Decimal('950.00'),
            protein=Decimal('33.00'),
            carbohydrates=Decimal('167.50'),
            fat=Decimal('16.25'),
            estimated_cost=Decimal('0.63'),
        )

        self.food_item.protein_per_100 = Decimal('20.00')
        self.food_item.save(update_fields=['protein_per_100', 'updated_at'])
        entry.refresh_from_db()

        self.assertEqual(entry.protein, Decimal('33.00'))
        self.assertEqual(entry.estimated_cost, Decimal('0.63'))


class FoodCalculationTests(TestCase):
    def setUp(self):
        self.food_item = FoodItem.objects.create(
            name='Oats',
            item_type=FoodItem.INGREDIENT,
            nutrition_basis_unit=FoodItem.GRAMS,
            calories_per_100=Decimal('380'),
            protein_per_100=Decimal('13.20'),
            carbohydrates_per_100=Decimal('67.00'),
            fat_per_100=Decimal('6.50'),
        )

    def test_scale_nutrition_by_consumed_quantity(self):
        snapshot = scale_nutrition(self.food_item, Decimal('250'), FoodItem.GRAMS)

        self.assertEqual(snapshot.calories, Decimal('950.00'))
        self.assertEqual(snapshot.protein, Decimal('33.00'))
        self.assertEqual(snapshot.carbohydrates, Decimal('167.50'))
        self.assertEqual(snapshot.fat, Decimal('16.25'))

    def test_scale_nutrition_preserves_unknown_values(self):
        self.food_item.fat_per_100 = None

        snapshot = scale_nutrition(self.food_item, Decimal('250'), FoodItem.GRAMS)

        self.assertIsNone(snapshot.fat)
        self.assertEqual(snapshot.protein, Decimal('33.00'))

    def test_scale_nutrition_rejects_incompatible_units(self):
        with self.assertRaises(ValueError):
            scale_nutrition(self.food_item, Decimal('250'), FoodItem.MILLILITRES)

    def test_scale_nutrition_rejects_non_positive_quantity(self):
        with self.assertRaises(ValueError):
            scale_nutrition(self.food_item, Decimal('0'), FoodItem.GRAMS)

    def test_allocated_cost_uses_proportional_package_cost(self):
        price = PriceObservation(
            food_item=self.food_item,
            package_quantity=Decimal('1000'),
            package_unit=FoodItem.GRAMS,
            paid_price=Decimal('2.50'),
        )

        cost = calculate_allocated_cost(Decimal('250'), FoodItem.GRAMS, price)

        self.assertEqual(cost, Decimal('0.63'))

    def test_allocated_cost_is_unknown_without_price(self):
        self.assertIsNone(
            calculate_allocated_cost(Decimal('250'), FoodItem.GRAMS, None),
        )

    def test_allocated_cost_rejects_incompatible_units(self):
        price = PriceObservation(
            food_item=self.food_item,
            package_quantity=Decimal('1000'),
            package_unit=FoodItem.GRAMS,
            paid_price=Decimal('2.50'),
        )

        with self.assertRaises(ValueError):
            calculate_allocated_cost(Decimal('250'), FoodItem.MILLILITRES, price)

    def test_daily_aggregation_uses_configured_timezone(self):
        dublin = timezone.get_current_timezone()
        first_entry = ConsumptionEntry.objects.create(
            food_item=self.food_item,
            source_name='Oats',
            quantity=Decimal('250'),
            unit=FoodItem.GRAMS,
            consumed_at=timezone.make_aware(datetime(2026, 10, 11, 23, 30), dublin),
            calories=Decimal('950.00'),
            protein=Decimal('33.00'),
            carbohydrates=Decimal('167.50'),
            fat=Decimal('16.25'),
            estimated_cost=Decimal('0.63'),
        )
        second_entry = ConsumptionEntry.objects.create(
            food_item=self.food_item,
            source_name='Oats',
            quantity=Decimal('100'),
            unit=FoodItem.GRAMS,
            consumed_at=timezone.make_aware(datetime(2026, 10, 12, 0, 30), dublin),
            calories=Decimal('380.00'),
            protein=Decimal('13.20'),
            carbohydrates=Decimal('67.00'),
            fat=Decimal('6.50'),
            estimated_cost=Decimal('0.25'),
        )

        totals = aggregate_daily(
            [first_entry, second_entry],
            first_entry.consumed_at.date(),
            tz=dublin,
        )

        self.assertEqual(totals.entry_count, 1)
        self.assertEqual(totals.calories, Decimal('950.00'))
        self.assertEqual(totals.estimated_cost, Decimal('0.63'))
        self.assertTrue(totals.nutrition_complete)
        self.assertTrue(totals.cost_complete)

    def test_daily_aggregation_marks_missing_values_incomplete(self):
        entry = ConsumptionEntry.objects.create(
            food_item=self.food_item,
            source_name='Oats',
            quantity=Decimal('250'),
            unit=FoodItem.GRAMS,
            consumed_at=timezone.now(),
            calories=Decimal('950.00'),
            protein=None,
            carbohydrates=Decimal('167.50'),
            fat=Decimal('16.25'),
            estimated_cost=None,
        )

        totals = aggregate_daily(
            [entry],
            timezone.localdate(),
        )

        self.assertEqual(totals.calories, Decimal('950.00'))
        self.assertEqual(totals.protein, Decimal('0.00'))
        self.assertFalse(totals.nutrition_complete)
        self.assertFalse(totals.cost_complete)

    def test_daily_costs_are_grouped_by_currency_without_combining(self):
        first = ConsumptionEntry.objects.create(
            source_name='EUR meal',
            quantity=Decimal('100'),
            unit=FoodItem.GRAMS,
            calories=Decimal('100'),
            estimated_cost=Decimal('2.00'),
            currency='EUR',
        )
        second = ConsumptionEntry.objects.create(
            source_name='GBP meal',
            quantity=Decimal('100'),
            unit=FoodItem.GRAMS,
            calories=Decimal('100'),
            estimated_cost=Decimal('3.00'),
            currency='GBP',
        )

        totals = aggregate_daily([first, second], timezone.localdate())

        self.assertEqual(totals.costs_by_currency, {
            'EUR': Decimal('2.00'),
            'GBP': Decimal('3.00'),
        })
        self.assertIsNone(totals.estimated_cost)
        self.assertIsNone(totals.currency)
        self.assertTrue(totals.cost_complete)

    def test_daily_zero_cost_keeps_currency_and_unknown_cost_is_incomplete(self):
        known_zero = ConsumptionEntry.objects.create(
            source_name='Free sample',
            quantity=Decimal('100'),
            unit=FoodItem.GRAMS,
            estimated_cost=Decimal('0.00'),
            currency='GBP',
        )
        unknown = ConsumptionEntry.objects.create(
            source_name='Unknown cost',
            quantity=Decimal('100'),
            unit=FoodItem.GRAMS,
            estimated_cost=None,
            currency='',
        )

        totals = aggregate_daily([known_zero, unknown], timezone.localdate())

        self.assertEqual(totals.costs_by_currency, {'GBP': Decimal('0.00')})
        self.assertEqual(totals.currency, 'GBP')
        self.assertEqual(totals.estimated_cost, Decimal('0.00'))
        self.assertFalse(totals.cost_complete)


class CatalogueWorkflowTests(TestCase):
    def setUp(self):
        self.food_item = FoodItem.objects.create(
            name='Rolled Oats',
            item_type=FoodItem.INGREDIENT,
            brand='',
            nutrition_basis_unit=FoodItem.GRAMS,
            calories_per_100=Decimal('380'),
            protein_per_100=Decimal('13.20'),
            carbohydrates_per_100=Decimal('67.00'),
            fat_per_100=Decimal('6.50'),
            nutrition_source='package label',
        )

    def test_food_item_form_creates_item_with_optional_nutrition(self):
        form = FoodItemForm(data={
            'name': 'Sparkling Water',
            'item_type': FoodItem.PRODUCT,
            'brand': 'Example',
            'nutrition_basis_unit': FoodItem.MILLILITRES,
            'calories_per_100': '',
            'protein_per_100': '',
            'carbohydrates_per_100': '',
            'fat_per_100': '',
            'nutrition_source': '',
        })

        self.assertTrue(form.is_valid(), form.errors)
        item = form.save()

        self.assertEqual(item.item_type, FoodItem.PRODUCT)
        self.assertIsNone(item.calories_per_100)
        self.assertEqual(item.nutrition_basis_unit, FoodItem.MILLILITRES)

    def test_food_item_form_rejects_negative_nutrition(self):
        form = FoodItemForm(data={
            'name': 'Invalid Food',
            'item_type': FoodItem.INGREDIENT,
            'brand': '',
            'nutrition_basis_unit': FoodItem.GRAMS,
            'calories_per_100': '-1',
            'protein_per_100': '',
            'carbohydrates_per_100': '',
            'fat_per_100': '',
            'nutrition_source': '',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('calories_per_100', form.errors)

    def test_catalogue_lists_type_and_nutrition(self):
        response = self.client.get(reverse('catalogue'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Rolled Oats')
        self.assertContains(response, 'Ingredient')
        self.assertContains(response, '13.20')

    def test_food_pages_share_module_navigation(self):
        response = self.client.get(reverse('catalogue'))

        self.assertContains(response, 'Food Catalogue')
        self.assertContains(response, reverse('food_today'))
        self.assertContains(response, reverse('consumption_create'))
        self.assertContains(response, reverse('food_history'))

    def test_forms_explain_food_types_and_unknown_values(self):
        food_form = FoodItemForm()
        consumption_form = ConsumptionEntryForm()

        self.assertIn('Ingredient is generic', food_form.fields['item_type'].help_text)
        self.assertIn('Leave blank when the value is unknown', food_form.fields['protein_per_100'].help_text)
        self.assertIn('grams or millilitres', consumption_form.fields['quantity'].help_text)

    def test_catalogue_search_matches_name_or_brand(self):
        FoodItem.objects.create(
            name='Milk',
            item_type=FoodItem.PRODUCT,
            brand='Example Dairy',
            nutrition_basis_unit=FoodItem.MILLILITRES,
        )

        response = self.client.get(reverse('catalogue'), {'q': 'dairy'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Milk')
        self.assertNotContains(response, 'Rolled Oats')

    def test_create_view_saves_food_item_and_redirects(self):
        response = self.client.post(reverse('food_item_create'), {
            'name': 'Greek Yogurt',
            'item_type': FoodItem.PRODUCT,
            'brand': 'Example',
            'nutrition_basis_unit': FoodItem.GRAMS,
            'calories_per_100': '59',
            'protein_per_100': '10.00',
            'carbohydrates_per_100': '3.60',
            'fat_per_100': '0.40',
            'nutrition_source': 'package label',
        })

        self.assertRedirects(
            response,
            reverse('food_item_detail', kwargs={'pk': FoodItem.objects.latest('id').pk}),
        )
        self.assertTrue(FoodItem.objects.filter(name='Greek Yogurt').exists())

    def test_edit_view_updates_food_item(self):
        response = self.client.post(
            reverse('food_item_edit', kwargs={'pk': self.food_item.pk}),
            {
                'name': 'Steel Cut Oats',
                'item_type': FoodItem.INGREDIENT,
                'brand': '',
                'nutrition_basis_unit': FoodItem.GRAMS,
                'calories_per_100': '375',
                'protein_per_100': '13.00',
                'carbohydrates_per_100': '66.00',
                'fat_per_100': '6.00',
                'nutrition_source': 'updated label',
            },
        )

        self.assertRedirects(response, reverse('food_item_detail', kwargs={'pk': self.food_item.pk}))
        self.food_item.refresh_from_db()
        self.assertEqual(self.food_item.name, 'Steel Cut Oats')
        self.assertEqual(self.food_item.calories_per_100, Decimal('375.00'))

    def test_price_form_requires_matching_unit(self):
        form = PriceObservationForm(self.food_item, data={
            'package_quantity': '1000',
            'package_unit': FoodItem.MILLILITRES,
            'paid_price': '2.50',
            'reference_price': '',
            'currency': 'EUR',
            'observed_at': '2026-10-11T12:00',
            'source': 'shop',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('package_unit', form.errors)

    def test_price_create_and_edit_are_visible_in_history(self):
        response = self.client.post(
            reverse('price_observation_create', kwargs={'food_item_pk': self.food_item.pk}),
            {
                'package_quantity': '1000',
                'package_unit': FoodItem.GRAMS,
                'paid_price': '2.50',
                'reference_price': '3.00',
                'currency': 'EUR',
                'observed_at': '2026-10-11T12:00',
                'source': 'shop',
            },
        )

        self.assertRedirects(response, reverse('food_item_detail', kwargs={'pk': self.food_item.pk}))
        price = self.food_item.price_observations.get()
        detail = self.client.get(reverse('food_item_detail', kwargs={'pk': self.food_item.pk}))
        self.assertContains(detail, '2.50')
        self.assertContains(detail, 'shop')

        response = self.client.post(
            reverse(
                'price_observation_edit',
                kwargs={'food_item_pk': self.food_item.pk, 'pk': price.pk},
            ),
            {
                'package_quantity': '1000',
                'package_unit': FoodItem.GRAMS,
                'paid_price': '2.25',
                'reference_price': '3.00',
                'currency': 'EUR',
                'observed_at': '2026-10-11T12:00',
                'source': 'updated shop',
            },
        )

        self.assertRedirects(response, reverse('food_item_detail', kwargs={'pk': self.food_item.pk}))
        price.refresh_from_db()
        self.assertEqual(price.paid_price, Decimal('2.25'))
        self.assertEqual(price.source, 'updated shop')


class FoodPurchaseModelTests(TestCase):
    def setUp(self):
        self.food_item = FoodItem.objects.create(
            name='Oats',
            item_type=FoodItem.INGREDIENT,
            nutrition_basis_unit=FoodItem.GRAMS,
        )

    def test_purchase_accepts_description_without_catalogue_item_or_quantity(self):
        purchase = FoodPurchase(
            description='Canteen lunch',
            purchased_at=timezone.now(),
            amount_paid=Decimal('7.00'),
            currency='EUR',
            source='Work canteen',
        )
        purchase.full_clean()

        self.assertIsNone(purchase.food_item)
        self.assertIsNone(purchase.quantity)
        self.assertEqual(purchase.unit, '')

    def test_purchase_quantity_and_unit_must_be_provided_together(self):
        purchase = FoodPurchase(
            description='Oats',
            amount_paid=Decimal('4.50'),
            currency='EUR',
            food_item=self.food_item,
            quantity=Decimal('1000'),
        )

        with self.assertRaises(ValidationError):
            purchase.full_clean()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                FoodPurchase.objects.create(
                    description='Invalid quantity',
                    amount_paid=Decimal('1.00'),
                    currency='EUR',
                    quantity=Decimal('1000'),
                    unit='',
                )

    def test_purchase_unit_matches_catalogue_basis_when_item_is_selected(self):
        purchase = FoodPurchase(
            description='Oats',
            amount_paid=Decimal('4.50'),
            currency='EUR',
            food_item=self.food_item,
            quantity=Decimal('1000'),
            unit=FoodItem.MILLILITRES,
        )

        with self.assertRaises(ValidationError):
            purchase.full_clean()

    def test_purchase_form_accepts_actual_spend_and_rejects_unpaired_quantity(self):
        valid = FoodPurchaseForm(data={
            'description': 'KFC meal',
            'food_item': '',
            'purchased_at': '2026-10-25T12:30',
            'amount_paid': '12.00',
            'currency': 'EUR',
            'quantity': '',
            'unit': '',
            'source': 'KFC',
        })
        self.assertTrue(valid.is_valid(), valid.errors)

        invalid = FoodPurchaseForm(data={
            'description': 'Oats',
            'food_item': str(self.food_item.pk),
            'purchased_at': '2026-10-25T12:30',
            'amount_paid': '4.50',
            'currency': 'EUR',
            'quantity': '1000',
            'unit': '',
            'source': 'Shop',
        })
        self.assertFalse(invalid.is_valid())
        self.assertIn('quantity', invalid.errors)


class FoodPurchaseServiceTests(TestCase):
    def test_purchase_service_records_actual_spend_without_creating_consumption(self):
        purchase = create_food_purchase(
            description='Canteen lunch',
            amount_paid=Decimal('7.00'),
            currency='EUR',
            purchased_at=timezone.make_aware(
                datetime(2026, 10, 25, 12, 30),
                timezone.get_current_timezone(),
            ),
            source='Work canteen',
        )

        self.assertEqual(purchase.description, 'Canteen lunch')
        self.assertEqual(purchase.amount_paid, Decimal('7.00'))
        self.assertEqual(purchase.currency, 'EUR')
        self.assertFalse(ConsumptionEntry.objects.exists())
        self.assertFalse(PriceObservation.objects.exists())

    def test_purchase_totals_are_grouped_per_currency_and_local_date(self):
        local_tz = timezone.get_current_timezone()
        create_food_purchase(
            description='Groceries',
            amount_paid=Decimal('20.00'),
            currency='EUR',
            purchased_at=timezone.make_aware(datetime(2026, 10, 25, 10, 0), local_tz),
        )
        create_food_purchase(
            description='Meal',
            amount_paid=Decimal('12.00'),
            currency='GBP',
            purchased_at=timezone.make_aware(datetime(2026, 10, 25, 11, 0), local_tz),
        )
        create_food_purchase(
            description='Yesterday',
            amount_paid=Decimal('5.00'),
            currency='EUR',
            purchased_at=timezone.make_aware(datetime(2026, 10, 24, 11, 0), local_tz),
        )

        totals = get_purchase_totals_for_date(date(2026, 10, 25))

        self.assertEqual(totals, {'EUR': Decimal('20.00'), 'GBP': Decimal('12.00')})


class FoodCostHistoryWorkflowTests(TestCase):
    def setUp(self):
        self.food_item = FoodItem.objects.create(
            name='Chicken',
            item_type=FoodItem.INGREDIENT,
            nutrition_basis_unit=FoodItem.GRAMS,
            calories_per_100=Decimal('200'),
        )
        self.price = PriceObservation.objects.create(
            food_item=self.food_item,
            package_quantity=Decimal('1000'),
            package_unit=FoodItem.GRAMS,
            paid_price=Decimal('10.00'),
            currency='EUR',
            source='Grocery receipt',
        )

    def test_purchase_form_view_creates_purchase_without_consumption_or_price_change(self):
        response = self.client.post(reverse('food_purchase_create'), {
            'description': 'KFC Meal',
            'food_item': '',
            'purchased_at': '2026-10-25T09:00',
            'amount_paid': '12.00',
            'currency': 'EUR',
            'quantity': '',
            'unit': '',
            'source': 'KFC',
        })

        purchase = FoodPurchase.objects.get(description='KFC Meal')
        self.assertRedirects(
            response,
            f'{reverse("food_cost_history")}?date=2026-10-25',
        )
        self.assertEqual(purchase.amount_paid, Decimal('12.00'))
        self.assertEqual(purchase.source, 'KFC')
        self.assertFalse(ConsumptionEntry.objects.exists())
        self.assertEqual(self.food_item.price_observations.get(), self.price)

    def test_cost_history_distinguishes_purchase_batch_and_batch_consumption(self):
        local_tz = timezone.get_current_timezone()
        create_food_purchase(
            description='Canteen lunch',
            amount_paid=Decimal('7.00'),
            currency='EUR',
            purchased_at=timezone.make_aware(datetime(2026, 10, 25, 9, 0), local_tz),
            source='Work canteen',
        )
        batch = create_meal_prep_batch(
            name='Chicken & Rice',
            cooked_at=timezone.make_aware(datetime(2026, 10, 25, 10, 0), local_tz),
            yield_quantity=Decimal('1000'),
            yield_unit=FoodItem.GRAMS,
            ingredients=[BatchIngredientInput(
                food_item=self.food_item,
                quantity=Decimal('1000'),
                unit=FoodItem.GRAMS,
                price_observation=self.price,
            )],
        )
        create_batch_consumption_entry(
            batch,
            consumed_quantity=Decimal('250'),
            unit=FoodItem.GRAMS,
            consumed_at=timezone.make_aware(datetime(2026, 10, 25, 12, 0), local_tz),
        )

        events = get_food_cost_events_for_date(date(2026, 10, 25))
        self.assertEqual([event.event_type for event in events], [
            'ATE FROM BATCH', 'MEAL PREP', 'PURCHASE',
        ])
        self.assertEqual(events[0].amount, Decimal('2.50'))
        self.assertEqual(events[1].amount, Decimal('10.00'))
        self.assertEqual(events[2].amount, Decimal('7.00'))
        self.assertEqual(FoodPurchase.objects.count(), 1)

        response = self.client.get(reverse('food_cost_history'), {'date': '2026-10-25'})
        self.assertContains(response, 'ATE FROM BATCH')
        self.assertContains(response, 'MEAL PREP')
        self.assertContains(response, 'PURCHASE')
        self.assertContains(response, '10.00 EUR')
        self.assertContains(response, '2.50 EUR')
        self.assertContains(response, '7.00 EUR')

    def test_cost_history_excludes_other_dates(self):
        create_food_purchase(
            description='Yesterday purchase',
            amount_paid=Decimal('5.00'),
            currency='EUR',
            purchased_at=timezone.make_aware(
                datetime(2026, 10, 24, 9, 0),
                timezone.get_current_timezone(),
            ),
        )

        response = self.client.get(reverse('food_cost_history'), {'date': '2026-10-25'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No purchases, batch preparations, or consumption costs')
        self.assertNotContains(response, 'Yesterday purchase')

    def test_food_item_consumption_is_a_consumption_event_not_a_purchase(self):
        entry = create_consumption_entry(
            food_item=self.food_item,
            quantity=Decimal('250'),
            unit=FoodItem.GRAMS,
            consumed_at=timezone.make_aware(
                datetime(2026, 10, 25, 13, 0),
                timezone.get_current_timezone(),
            ),
            price_observation=self.price,
        )

        events = get_food_cost_events_for_date(date(2026, 10, 25))

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, 'CONSUMPTION')
        self.assertEqual(events[0].amount, entry.estimated_cost)
        self.assertFalse(FoodPurchase.objects.exists())

    def test_today_shows_purchases_separately_from_estimated_consumption(self):
        local_tz = timezone.get_current_timezone()
        create_food_purchase(
            description='KFC Meal',
            amount_paid=Decimal('12.00'),
            currency='EUR',
            purchased_at=timezone.make_aware(datetime(2026, 10, 25, 9, 0), local_tz),
        )
        create_consumption_entry(
            food_item=self.food_item,
            quantity=Decimal('250'),
            unit=FoodItem.GRAMS,
            consumed_at=timezone.make_aware(datetime(2026, 10, 25, 12, 0), local_tz),
            price_observation=self.price,
        )

        response = self.client.get(reverse('food_today'), {'date': '2026-10-25'})

        self.assertContains(response, 'Food purchased')
        self.assertContains(response, 'Estimated consumed cost')
        self.assertContains(response, '12.00 EUR')
        self.assertContains(response, '2.50 EUR')


class ConsumptionWorkflowTests(TestCase):
    def setUp(self):
        self.food_item = FoodItem.objects.create(
            name='Oats',
            item_type=FoodItem.INGREDIENT,
            nutrition_basis_unit=FoodItem.GRAMS,
            calories_per_100=Decimal('380'),
            protein_per_100=Decimal('13.20'),
            carbohydrates_per_100=Decimal('67.00'),
            fat_per_100=Decimal('6.50'),
            nutrition_source='label',
        )
        self.price = PriceObservation.objects.create(
            food_item=self.food_item,
            package_quantity=Decimal('1000'),
            package_unit=FoodItem.GRAMS,
            paid_price=Decimal('2.50'),
            currency='EUR',
            source='shop',
        )

    def test_create_service_populates_historical_snapshots(self):
        entry = create_consumption_entry(
            food_item=self.food_item,
            quantity=Decimal('250'),
            unit=FoodItem.GRAMS,
            price_observation=self.price,
            meal_category='breakfast',
        )

        self.assertEqual(entry.source_name, 'Oats')
        self.assertEqual(entry.calories, Decimal('950.00'))
        self.assertEqual(entry.protein, Decimal('33.00'))
        self.assertEqual(entry.carbohydrates, Decimal('167.50'))
        self.assertEqual(entry.fat, Decimal('16.25'))
        self.assertEqual(entry.estimated_cost, Decimal('0.63'))
        self.assertEqual(entry.currency, 'EUR')
        self.assertEqual(entry.nutrition_source, 'label')
        self.assertEqual(entry.cost_source, 'shop')

    def test_create_service_auto_selects_the_only_price(self):
        entry = create_consumption_entry(
            food_item=self.food_item,
            quantity=Decimal('100'),
            unit=FoodItem.GRAMS,
        )

        self.assertEqual(entry.price_observation, self.price)
        self.assertEqual(entry.estimated_cost, Decimal('0.25'))

    def test_create_service_requires_selection_when_multiple_prices_exist(self):
        second_price = PriceObservation.objects.create(
            food_item=self.food_item,
            package_quantity=Decimal('1000'),
            package_unit=FoodItem.GRAMS,
            paid_price=Decimal('3.00'),
            currency='EUR',
            source='another shop',
        )

        with self.assertRaisesMessage(ValueError, 'Select a price observation'):
            create_consumption_entry(
                food_item=self.food_item,
                quantity=Decimal('100'),
                unit=FoodItem.GRAMS,
            )

        entry = create_consumption_entry(
            food_item=self.food_item,
            quantity=Decimal('100'),
            unit=FoodItem.GRAMS,
            price_observation=second_price,
        )
        self.assertEqual(entry.price_observation, second_price)
        self.assertEqual(entry.estimated_cost, Decimal('0.30'))

    def test_create_service_preserves_unknown_nutrition_and_cost(self):
        self.food_item.calories_per_100 = None
        self.food_item.protein_per_100 = None
        self.food_item.carbohydrates_per_100 = None
        self.food_item.fat_per_100 = None
        self.food_item.save()
        self.price.delete()

        entry = create_consumption_entry(
            food_item=self.food_item,
            quantity=Decimal('100'),
            unit=FoodItem.GRAMS,
        )

        self.assertIsNone(entry.calories)
        self.assertIsNone(entry.protein)
        self.assertIsNone(entry.estimated_cost)

    def test_create_service_rejects_invalid_quantity_and_unit(self):
        with self.assertRaises(ValueError):
            create_consumption_entry(
                food_item=self.food_item,
                quantity=Decimal('0'),
                unit=FoodItem.GRAMS,
                price_observation=self.price,
            )
        with self.assertRaises(ValueError):
            create_consumption_entry(
                food_item=self.food_item,
                quantity=Decimal('100'),
                unit=FoodItem.MILLILITRES,
                price_observation=self.price,
            )

    def test_catalogue_changes_do_not_change_snapshot(self):
        entry = create_consumption_entry(
            food_item=self.food_item,
            quantity=Decimal('250'),
            unit=FoodItem.GRAMS,
            price_observation=self.price,
        )
        self.food_item.protein_per_100 = Decimal('20.00')
        self.food_item.save()
        self.price.paid_price = Decimal('4.00')
        self.price.save()
        entry.refresh_from_db()

        self.assertEqual(entry.protein, Decimal('33.00'))
        self.assertEqual(entry.estimated_cost, Decimal('0.63'))

    def test_metadata_update_does_not_recalculate_snapshots(self):
        entry = create_consumption_entry(
            food_item=self.food_item,
            quantity=Decimal('250'),
            unit=FoodItem.GRAMS,
            price_observation=self.price,
        )
        original_calories = entry.calories
        original_cost = entry.estimated_cost
        consumed_at = timezone.make_aware(
            datetime(2026, 10, 12, 8, 30),
            timezone.get_current_timezone(),
        )

        update_consumption_entry(
            entry,
            consumed_at=consumed_at,
            meal_category='breakfast',
        )
        entry.refresh_from_db()

        self.assertEqual(entry.consumed_at, consumed_at)
        self.assertEqual(entry.meal_category, 'breakfast')
        self.assertEqual(entry.calories, original_calories)
        self.assertEqual(entry.estimated_cost, original_cost)

    def test_source_update_requires_explicit_recalculation(self):
        entry = create_consumption_entry(
            food_item=self.food_item,
            quantity=Decimal('250'),
            unit=FoodItem.GRAMS,
            price_observation=self.price,
        )

        with self.assertRaisesMessage(ValueError, 'requires explicit recalculation'):
            update_consumption_entry(entry, quantity=Decimal('300'))

    def test_recalculation_requires_confirmation_and_refreshes_snapshots(self):
        entry = create_consumption_entry(
            food_item=self.food_item,
            quantity=Decimal('250'),
            unit=FoodItem.GRAMS,
            price_observation=self.price,
        )
        self.food_item.protein_per_100 = Decimal('20.00')
        self.food_item.save()

        with self.assertRaisesMessage(ValueError, 'confirmation'):
            recalculate_consumption_entry(entry, confirmed=False)

        recalculate_consumption_entry(
            entry,
            quantity=Decimal('300'),
            confirmed=True,
        )
        entry.refresh_from_db()

        self.assertEqual(entry.quantity, Decimal('300.000'))
        self.assertEqual(entry.protein, Decimal('60.00'))
        self.assertEqual(entry.estimated_cost, Decimal('0.75'))

    def test_daily_summary_and_local_date_entries(self):
        dublin = timezone.get_current_timezone()
        first = create_consumption_entry(
            food_item=self.food_item,
            quantity=Decimal('100'),
            unit=FoodItem.GRAMS,
            consumed_at=timezone.make_aware(datetime(2026, 10, 11, 23, 30), dublin),
            price_observation=self.price,
        )
        create_consumption_entry(
            food_item=self.food_item,
            quantity=Decimal('100'),
            unit=FoodItem.GRAMS,
            consumed_at=timezone.make_aware(datetime(2026, 10, 12, 0, 30), dublin),
            price_observation=self.price,
        )

        entries = get_consumption_entries_for_date(first.consumed_at.date())
        summary = get_daily_summary(first.consumed_at.date())

        self.assertEqual(entries.count(), 1)
        self.assertEqual(summary.entry_count, 1)
        self.assertEqual(summary.calories, Decimal('380.00'))
        self.assertEqual(summary.estimated_cost, Decimal('0.25'))

    def test_consumption_form_validates_unit_and_multiple_price_selection(self):
        PriceObservation.objects.create(
            food_item=self.food_item,
            package_quantity=Decimal('1000'),
            package_unit=FoodItem.GRAMS,
            paid_price=Decimal('3.00'),
            currency='EUR',
            source='another shop',
        )
        form = ConsumptionEntryForm(data={
            'food_item': self.food_item.pk,
            'quantity': '100',
            'unit': FoodItem.MILLILITRES,
            'meal_category': 'breakfast',
            'consumed_at': '2026-10-11T08:00',
            'price_observation': '',
            'confirm_recalculation': '',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('unit', form.errors)
        self.assertIn('price_observation', form.errors)

    def test_consumption_routes_and_views(self):
        self.assertEqual(self.client.get(reverse('food_today')).status_code, 200)
        self.assertEqual(self.client.get(reverse('consumption_create')).status_code, 200)
        self.assertEqual(self.client.get(reverse('food_history')).status_code, 200)
        response = self.client.post(reverse('consumption_create'), {
            'food_item': self.food_item.pk,
            'quantity': '250',
            'unit': FoodItem.GRAMS,
            'meal_category': 'breakfast',
            'consumed_at': '2026-10-11T08:00',
            'price_observation': self.price.pk,
            'confirm_recalculation': '',
        })

        self.assertEqual(response.status_code, 302)
        entry = ConsumptionEntry.objects.get()
        today = self.client.get(reverse('food_today'), {'date': '2026-10-11'})
        self.assertContains(today, '950.00')
        self.assertContains(today, '33.00')
        history = self.client.get(reverse('food_history'), {'date': '2026-10-11'})
        self.assertContains(history, 'Oats')
        self.assertContains(history, '0.63')

        edit = self.client.post(reverse('consumption_edit', kwargs={'pk': entry.pk}), {
            'food_item': self.food_item.pk,
            'quantity': '250',
            'unit': FoodItem.GRAMS,
            'meal_category': 'lunch',
            'consumed_at': '2026-10-11T09:00',
            'price_observation': self.price.pk,
            'confirm_recalculation': '',
            'action': 'save',
        })
        self.assertEqual(edit.status_code, 302)
        entry.refresh_from_db()
        self.assertEqual(entry.meal_category, 'lunch')
        self.assertEqual(entry.calories, Decimal('950.00'))

        delete_get = self.client.get(reverse('consumption_delete', kwargs={'pk': entry.pk}))
        self.assertEqual(delete_get.status_code, 405)
        delete_post = self.client.post(reverse('consumption_delete', kwargs={'pk': entry.pk}))
        self.assertEqual(delete_post.status_code, 302)
        self.assertFalse(ConsumptionEntry.objects.filter(pk=entry.pk).exists())


class BatchConsumptionServiceTests(TestCase):
    def setUp(self):
        self.food_item = FoodItem.objects.create(
            name='Meal base',
            item_type=FoodItem.INGREDIENT,
            nutrition_basis_unit=FoodItem.GRAMS,
            calories_per_100=Decimal('200'),
            protein_per_100=Decimal('10'),
            carbohydrates_per_100=None,
            fat_per_100=Decimal('4'),
            nutrition_source='label data',
        )
        self.price = PriceObservation.objects.create(
            food_item=self.food_item,
            package_quantity=Decimal('1200'),
            package_unit=FoodItem.GRAMS,
            paid_price=Decimal('12.00'),
            currency='EUR',
            source='receipt record',
        )
        self.recipe = Recipe.objects.create(name='Meal plan')
        self.batch = create_meal_prep_batch(
            name='Cooked meal',
            recipe=self.recipe,
            yield_quantity=Decimal('1200'),
            yield_unit=FoodItem.GRAMS,
            ingredients=[BatchIngredientInput(
                food_item=self.food_item,
                quantity=Decimal('1200'),
                unit=FoodItem.GRAMS,
                price_observation=self.price,
            )],
        )

    def test_create_batch_entry_scales_complete_components_and_keeps_unknowns(self):
        entry = create_batch_consumption_entry(
            self.batch,
            consumed_quantity=Decimal('300'),
            unit=FoodItem.GRAMS,
            meal_category='lunch',
        )

        self.assertEqual(entry.calories, Decimal('600.00'))
        self.assertEqual(entry.protein, Decimal('30.00'))
        self.assertIsNone(entry.carbohydrates)
        self.assertEqual(entry.fat, Decimal('12.00'))
        self.assertEqual(entry.estimated_cost, Decimal('3.00'))
        self.assertEqual(entry.currency, 'EUR')
        self.assertEqual(entry.source_name, 'Meal Prep Batch: Cooked meal')
        self.assertEqual(entry.nutrition_source, 'label data')
        self.assertEqual(entry.cost_source, 'receipt record')
        self.assertIsNone(entry.food_item)
        self.assertIsNone(entry.price_observation)
        self.assertEqual(entry.meal_prep_batch, self.batch)
        self.assertEqual(self.batch.yield_quantity, Decimal('1200.000'))
        self.assertEqual(self.batch.ingredients.get().calories, Decimal('2400.00'))

    def test_batch_entry_rejects_invalid_quantity_unit_and_amount_over_yield(self):
        for quantity in (Decimal('0'), Decimal('-1')):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                create_batch_consumption_entry(
                    self.batch,
                    consumed_quantity=quantity,
                    unit=FoodItem.GRAMS,
                )

        with self.assertRaisesMessage(ValueError, 'cannot exceed'):
            create_batch_consumption_entry(
                self.batch,
                consumed_quantity=Decimal('1200.001'),
                unit=FoodItem.GRAMS,
            )
        with self.assertRaisesMessage(ValueError, 'match'):
            create_batch_consumption_entry(
                self.batch,
                consumed_quantity=Decimal('100'),
                unit=FoodItem.MILLILITRES,
            )

        self.assertEqual(ConsumptionEntry.objects.count(), 0)

    def test_batch_entry_keeps_cost_unknown_without_currency(self):
        self.price.delete()
        batch = create_meal_prep_batch(
            name='Unknown cost meal',
            yield_quantity=Decimal('1200'),
            yield_unit=FoodItem.GRAMS,
            ingredients=[BatchIngredientInput(
                food_item=self.food_item,
                quantity=Decimal('1200'),
                unit=FoodItem.GRAMS,
            )],
        )

        entry = create_batch_consumption_entry(
            batch,
            consumed_quantity=Decimal('300'),
            unit=FoodItem.GRAMS,
        )

        self.assertIsNone(entry.estimated_cost)
        self.assertEqual(entry.currency, '')
        self.assertEqual(entry.calories, Decimal('600.00'))

    def test_batch_entry_snapshots_survive_catalogue_recipe_and_batch_deletion(self):
        entry = create_batch_consumption_entry(
            self.batch,
            consumed_quantity=Decimal('300'),
            unit=FoodItem.GRAMS,
        )
        self.food_item.calories_per_100 = Decimal('999')
        self.food_item.save()
        self.price.paid_price = Decimal('99.00')
        self.price.save()
        self.recipe.delete()
        self.batch.refresh_from_db()
        self.batch.name = 'Renamed batch'
        self.batch.yield_quantity = Decimal('600')
        self.batch.save()
        self.food_item.delete()
        self.batch.refresh_from_db()

        self.assertIsNone(self.batch.recipe)
        self.assertEqual(self.batch.ingredients.get().calories, Decimal('2400.00'))
        entry.refresh_from_db()
        self.assertEqual(entry.calories, Decimal('600.00'))
        self.assertEqual(entry.estimated_cost, Decimal('3.00'))
        self.assertEqual(entry.source_name, 'Meal Prep Batch: Cooked meal')

        self.batch.delete()
        entry.refresh_from_db()
        self.assertIsNone(entry.meal_prep_batch)
        self.assertEqual(entry.source_name, 'Meal Prep Batch: Cooked meal')
        self.assertEqual(entry.calories, Decimal('600.00'))
        self.assertEqual(entry.estimated_cost, Decimal('3.00'))
        with self.assertRaisesMessage(ValueError, 'Batch-backed'):
            recalculate_consumption_entry(entry, confirmed=True)

    def test_catalogue_recalculation_is_rejected_for_batch_entries(self):
        entry = create_batch_consumption_entry(
            self.batch,
            consumed_quantity=Decimal('300'),
            unit=FoodItem.GRAMS,
        )

        with self.assertRaisesMessage(ValueError, 'Batch-backed'):
            recalculate_consumption_entry(entry, confirmed=True)

    def test_scale_batch_totals_rejects_nonpositive_yield(self):
        totals = calculate_batch_totals(self.batch)
        with self.assertRaisesMessage(ValueError, 'yield'):
            scale_batch_totals(totals, Decimal('100'), Decimal('0'))


class RecipeAndMealPrepModelTests(TestCase):
    def setUp(self):
        self.oats = FoodItem.objects.create(
            name='Oats',
            item_type=FoodItem.INGREDIENT,
            nutrition_basis_unit=FoodItem.GRAMS,
            calories_per_100=Decimal('380'),
            protein_per_100=Decimal('13.20'),
            carbohydrates_per_100=Decimal('67.00'),
            fat_per_100=Decimal('6.50'),
            nutrition_source='label',
        )
        self.price = PriceObservation.objects.create(
            food_item=self.oats,
            package_quantity=Decimal('1000'),
            package_unit=FoodItem.GRAMS,
            paid_price=Decimal('2.50'),
            currency='EUR',
            source='shop label',
        )
        self.recipe = Recipe.objects.create(name='Overnight oats')

    def test_recipe_ingredient_requires_positive_quantity_and_matching_unit(self):
        ingredient = RecipeIngredient(
            recipe=self.recipe,
            food_item=self.oats,
            quantity=Decimal('0'),
            unit=FoodItem.MILLILITRES,
        )

        with self.assertRaises(ValidationError):
            ingredient.full_clean()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RecipeIngredient.objects.create(
                    recipe=self.recipe,
                    food_item=self.oats,
                    quantity=Decimal('0'),
                    unit=FoodItem.GRAMS,
                )

    def test_recipe_ingredient_validates_price_ownership(self):
        other_item = FoodItem.objects.create(
            name='Milk',
            item_type=FoodItem.INGREDIENT,
            nutrition_basis_unit=FoodItem.GRAMS,
        )
        other_price = PriceObservation.objects.create(
            food_item=other_item,
            package_quantity=Decimal('1000'),
            package_unit=FoodItem.GRAMS,
            paid_price=Decimal('1.50'),
        )
        ingredient = RecipeIngredient(
            recipe=self.recipe,
            food_item=self.oats,
            quantity=Decimal('100'),
            unit=FoodItem.GRAMS,
            price_observation=other_price,
        )

        with self.assertRaises(ValidationError):
            ingredient.full_clean()

    def test_recipe_ingredient_protects_food_item_from_deletion(self):
        RecipeIngredient.objects.create(
            recipe=self.recipe,
            food_item=self.oats,
            quantity=Decimal('100'),
            unit=FoodItem.GRAMS,
        )

        with self.assertRaises(ProtectedError):
            self.oats.delete()

    def test_batch_requires_positive_yield_and_ingredient_quantity(self):
        with self.assertRaises(ValidationError):
            MealPrepBatch(
                name='Batch',
                yield_quantity=Decimal('0'),
                yield_unit=FoodItem.GRAMS,
            ).full_clean()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                MealPrepBatch.objects.create(
                    name='Invalid yield',
                    yield_quantity=Decimal('0'),
                    yield_unit=FoodItem.GRAMS,
                )

        batch = MealPrepBatch.objects.create(
            name='Valid batch',
            yield_quantity=Decimal('500'),
            yield_unit=FoodItem.GRAMS,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BatchIngredient.objects.create(
                    batch=batch,
                    food_item=self.oats,
                    food_item_name_snapshot='Oats',
                    price_observation=self.price,
                    quantity=Decimal('0'),
                    unit=FoodItem.GRAMS,
                    calories=Decimal('0'),
                    protein=Decimal('0'),
                    carbohydrates=Decimal('0'),
                    fat=Decimal('0'),
                    estimated_cost=Decimal('0'),
                    currency='EUR',
                )

    def test_batch_ingredient_validates_unit_price_owner_and_snapshot_currency(self):
        other_item = FoodItem.objects.create(
            name='Milk',
            item_type=FoodItem.INGREDIENT,
            nutrition_basis_unit=FoodItem.MILLILITRES,
        )
        batch = MealPrepBatch(
            name='Batch',
            yield_quantity=Decimal('500'),
            yield_unit=FoodItem.GRAMS,
        )
        batch.full_clean()

        ingredient = BatchIngredient(
            batch=batch,
            food_item=self.oats,
            food_item_name_snapshot='Oats',
            price_observation=self.price,
            quantity=Decimal('100'),
            unit=FoodItem.MILLILITRES,
            estimated_cost=Decimal('0.25'),
            currency='EUR',
        )
        with self.assertRaises(ValidationError):
            ingredient.full_clean(exclude=['batch'])

        ingredient.food_item = other_item
        with self.assertRaises(ValidationError):
            ingredient.full_clean(exclude=['batch'])

        ingredient.food_item = self.oats
        ingredient.estimated_cost = None
        ingredient.currency = 'EUR'
        with self.assertRaises(ValidationError):
            ingredient.full_clean(exclude=['batch'])

    def test_deleting_catalogue_records_preserves_batch_snapshots(self):
        batch = create_meal_prep_batch(
            name='Sunday oats',
            yield_quantity=Decimal('500'),
            yield_unit=FoodItem.GRAMS,
            ingredients=[BatchIngredientInput(
                food_item=self.oats,
                quantity=Decimal('250'),
                unit=FoodItem.GRAMS,
                price_observation=self.price,
            )],
        )
        ingredient = batch.ingredients.get()

        self.oats.delete()
        ingredient.refresh_from_db()

        self.assertIsNone(ingredient.food_item)
        self.assertIsNone(ingredient.price_observation)
        self.assertEqual(ingredient.food_item_name_snapshot, 'Oats')
        self.assertEqual(ingredient.calories, Decimal('950.00'))
        self.assertEqual(ingredient.estimated_cost, Decimal('0.63'))
        self.assertEqual(calculate_batch_totals(batch).calories, Decimal('950.00'))

    def test_deleting_recipe_does_not_delete_batch(self):
        batch = create_meal_prep_batch(
            name='My named batch',
            recipe=self.recipe,
            yield_quantity=Decimal('500'),
            yield_unit=FoodItem.GRAMS,
            ingredients=[BatchIngredientInput(
                food_item=self.oats,
                quantity=Decimal('250'),
                unit=FoodItem.GRAMS,
                price_observation=self.price,
            )],
        )

        self.recipe.delete()
        batch.refresh_from_db()

        self.assertIsNone(batch.recipe)
        self.assertEqual(batch.name, 'My named batch')
        self.assertEqual(batch.ingredients.count(), 1)

    def test_consumption_entry_source_validation_preserves_orphans(self):
        batch = MealPrepBatch.objects.create(
            name='Oats batch',
            yield_quantity=Decimal('500'),
            yield_unit=FoodItem.GRAMS,
        )
        legacy_orphan = ConsumptionEntry.objects.create(
            source_name='Historical meal',
            quantity=Decimal('100'),
            unit=FoodItem.GRAMS,
        )
        legacy_orphan.full_clean()

        batch_entry = ConsumptionEntry(
            meal_prep_batch=batch,
            source_name='Meal Prep Batch: Oats batch',
            quantity=Decimal('100'),
            unit=FoodItem.GRAMS,
        )
        batch_entry.full_clean()

        both_sources = ConsumptionEntry(
            food_item=self.oats,
            meal_prep_batch=batch,
            source_name='Invalid source',
            quantity=Decimal('100'),
            unit=FoodItem.GRAMS,
        )
        with self.assertRaises(ValidationError):
            both_sources.full_clean()

        batch_entry.price_observation = self.price
        with self.assertRaises(ValidationError):
            batch_entry.full_clean()

        batch_entry.price_observation = None
        batch_entry.unit = FoodItem.MILLILITRES
        with self.assertRaises(ValidationError):
            batch_entry.full_clean()

    def test_consumption_entry_source_database_constraints(self):
        batch = MealPrepBatch.objects.create(
            name='Oats batch',
            yield_quantity=Decimal('500'),
            yield_unit=FoodItem.GRAMS,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ConsumptionEntry.objects.create(
                    food_item=self.oats,
                    meal_prep_batch=batch,
                    source_name='Invalid source',
                    quantity=Decimal('100'),
                    unit=FoodItem.GRAMS,
                )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ConsumptionEntry.objects.create(
                    meal_prep_batch=batch,
                    price_observation=self.price,
                    source_name='Invalid price source',
                    quantity=Decimal('100'),
                    unit=FoodItem.GRAMS,
                )


class RecipeAndMealPrepCalculationTests(TestCase):
    def setUp(self):
        self.oats = FoodItem.objects.create(
            name='Oats',
            item_type=FoodItem.INGREDIENT,
            nutrition_basis_unit=FoodItem.GRAMS,
            calories_per_100=Decimal('380'),
            protein_per_100=Decimal('13.20'),
            carbohydrates_per_100=Decimal('67.00'),
            fat_per_100=Decimal('6.50'),
            nutrition_source='label',
        )
        self.price = PriceObservation.objects.create(
            food_item=self.oats,
            package_quantity=Decimal('1000'),
            package_unit=FoodItem.GRAMS,
            paid_price=Decimal('2.50'),
            currency='EUR',
            source='shop',
        )
        self.recipe = Recipe.objects.create(name='Overnight oats')
        self.recipe_ingredient = RecipeIngredient.objects.create(
            recipe=self.recipe,
            food_item=self.oats,
            quantity=Decimal('250'),
            unit=FoodItem.GRAMS,
            price_observation=self.price,
        )

    def test_recipe_estimate_uses_current_catalogue_and_price_data(self):
        estimate = calculate_recipe_estimate(self.recipe)
        self.assertEqual(estimate.calories, Decimal('950.00'))
        self.assertEqual(estimate.protein, Decimal('33.00'))
        self.assertEqual(estimate.estimated_cost, Decimal('0.63'))
        self.assertEqual(estimate.currency, 'EUR')
        self.assertTrue(estimate.calories_complete)
        self.assertTrue(estimate.cost_complete)

        self.oats.protein_per_100 = Decimal('20.00')
        self.oats.save()
        self.price.paid_price = Decimal('4.00')
        self.price.save()
        estimate = calculate_recipe_estimate(self.recipe)

        self.assertEqual(estimate.protein, Decimal('50.00'))
        self.assertEqual(estimate.estimated_cost, Decimal('1.00'))

    def test_recipe_estimate_reuses_zero_one_many_price_policy(self):
        self.recipe_ingredient.price_observation = None
        self.recipe_ingredient.save()
        self.assertEqual(
            calculate_recipe_estimate(self.recipe).estimated_cost,
            Decimal('0.63'),
        )

        PriceObservation.objects.create(
            food_item=self.oats,
            package_quantity=Decimal('1000'),
            package_unit=FoodItem.GRAMS,
            paid_price=Decimal('3.00'),
            currency='EUR',
        )
        with self.assertRaisesMessage(ValueError, 'Select a price observation'):
            calculate_recipe_estimate(self.recipe)

    def test_recipe_estimate_keeps_missing_values_incomplete(self):
        self.oats.fat_per_100 = None
        self.oats.save()
        self.price.delete()

        estimate = calculate_recipe_estimate(self.recipe)

        self.assertEqual(estimate.calories, Decimal('950.00'))
        self.assertTrue(estimate.calories_complete)
        self.assertFalse(estimate.fat_complete)
        self.assertEqual(estimate.estimated_cost, Decimal('0.00'))
        self.assertFalse(estimate.cost_complete)
        self.assertIsNone(estimate.currency)

    def test_recipe_estimate_does_not_sum_different_currencies(self):
        other_item = FoodItem.objects.create(
            name='Milk',
            item_type=FoodItem.INGREDIENT,
            nutrition_basis_unit=FoodItem.GRAMS,
            calories_per_100=Decimal('60'),
            protein_per_100=Decimal('3'),
            carbohydrates_per_100=Decimal('5'),
            fat_per_100=Decimal('3'),
        )
        sterling_price = PriceObservation.objects.create(
            food_item=other_item,
            package_quantity=Decimal('1000'),
            package_unit=FoodItem.GRAMS,
            paid_price=Decimal('1.00'),
            currency='GBP',
        )
        RecipeIngredient.objects.create(
            recipe=self.recipe,
            food_item=other_item,
            quantity=Decimal('100'),
            unit=FoodItem.GRAMS,
            price_observation=sterling_price,
        )

        estimate = calculate_recipe_estimate(self.recipe)

        self.assertIsNone(estimate.estimated_cost)
        self.assertIsNone(estimate.currency)
        self.assertFalse(estimate.cost_complete)

    def test_batch_totals_use_only_stored_snapshots(self):
        batch = create_meal_prep_batch(
            name='Sunday oats',
            recipe=self.recipe,
            yield_quantity=Decimal('400'),
            yield_unit=FoodItem.GRAMS,
            ingredients=[BatchIngredientInput(
                food_item=self.oats,
                quantity=Decimal('250'),
                unit=FoodItem.GRAMS,
                price_observation=self.price,
            )],
        )
        totals_before = calculate_batch_totals(batch)

        self.oats.name = 'Renamed oats'
        self.oats.protein_per_100 = Decimal('20.00')
        self.oats.save()
        self.price.paid_price = Decimal('4.00')
        self.price.save()
        self.recipe.name = 'Changed recipe'
        self.recipe.save()
        self.recipe_ingredient.quantity = Decimal('900')
        self.recipe_ingredient.save()

        totals_after = calculate_batch_totals(batch)
        ingredient = batch.ingredients.get()

        self.assertEqual(totals_after, totals_before)
        self.assertEqual(ingredient.food_item_name_snapshot, 'Oats')
        self.assertEqual(ingredient.protein, Decimal('33.00'))
        self.assertEqual(ingredient.estimated_cost, Decimal('0.63'))

    def test_batch_totals_report_completeness_independently(self):
        self.price.delete()
        batch = create_meal_prep_batch(
            name='Partial batch',
            yield_quantity=Decimal('300'),
            yield_unit=FoodItem.GRAMS,
            ingredients=[BatchIngredientInput(
                food_item=self.oats,
                quantity=Decimal('100'),
                unit=FoodItem.GRAMS,
            )],
        )

        totals = calculate_batch_totals(batch)

        self.assertTrue(totals.calories_complete)
        self.assertTrue(totals.protein_complete)
        self.assertFalse(totals.cost_complete)
        self.assertEqual(totals.estimated_cost, Decimal('0.00'))
        self.assertIsNone(totals.currency)

    def test_batch_totals_reject_mixed_snapshot_currencies(self):
        batch = MealPrepBatch.objects.create(
            name='Invalid mixed-currency batch',
            yield_quantity=Decimal('300'),
            yield_unit=FoodItem.GRAMS,
        )
        BatchIngredient.objects.create(
            batch=batch,
            food_item_name_snapshot='Oats',
            quantity=Decimal('100'),
            unit=FoodItem.GRAMS,
            estimated_cost=Decimal('1.00'),
            currency='EUR',
        )
        BatchIngredient.objects.create(
            batch=batch,
            food_item_name_snapshot='Other food',
            quantity=Decimal('100'),
            unit=FoodItem.GRAMS,
            estimated_cost=Decimal('1.00'),
            currency='GBP',
        )

        with self.assertRaisesMessage(ValueError, 'single currency'):
            calculate_batch_totals(batch)


class MealPrepServiceTests(TestCase):
    def setUp(self):
        self.oats = FoodItem.objects.create(
            name='Oats',
            item_type=FoodItem.INGREDIENT,
            nutrition_basis_unit=FoodItem.GRAMS,
            calories_per_100=Decimal('380'),
            protein_per_100=Decimal('13.20'),
            carbohydrates_per_100=Decimal('67.00'),
            fat_per_100=Decimal('6.50'),
            nutrition_source='package label',
        )
        self.price = PriceObservation.objects.create(
            food_item=self.oats,
            package_quantity=Decimal('1000'),
            package_unit=FoodItem.GRAMS,
            paid_price=Decimal('2.50'),
            currency='EUR',
            source='shop receipt',
        )

    def test_create_batch_snapshots_actual_ingredients_and_totals(self):
        batch = create_meal_prep_batch(
            name='Sunday oats',
            yield_quantity=Decimal('400'),
            yield_unit=FoodItem.GRAMS,
            ingredients=[BatchIngredientInput(
                food_item=self.oats,
                quantity=Decimal('250'),
                unit=FoodItem.GRAMS,
                price_observation=self.price,
            )],
        )
        ingredient = batch.ingredients.get()
        totals = calculate_batch_totals(batch)

        self.assertEqual(batch.name, 'Sunday oats')
        self.assertEqual(ingredient.food_item_name_snapshot, 'Oats')
        self.assertEqual(ingredient.calories, Decimal('950.00'))
        self.assertEqual(ingredient.protein, Decimal('33.00'))
        self.assertEqual(ingredient.estimated_cost, Decimal('0.63'))
        self.assertEqual(ingredient.currency, 'EUR')
        self.assertEqual(ingredient.nutrition_source, 'package label')
        self.assertEqual(ingredient.cost_source, 'shop receipt')
        self.assertEqual(totals.calories, Decimal('950.00'))
        self.assertEqual(totals.estimated_cost, Decimal('0.63'))
        self.assertTrue(totals.nutrition_complete)
        self.assertTrue(totals.cost_complete)

    def test_create_batch_rejects_invalid_inputs_without_persisting(self):
        with self.assertRaises(ValidationError):
            create_meal_prep_batch(
                name='Bad yield',
                yield_quantity=Decimal('0'),
                yield_unit=FoodItem.GRAMS,
                ingredients=[BatchIngredientInput(
                    food_item=self.oats,
                    quantity=Decimal('100'),
                    unit=FoodItem.GRAMS,
                )],
            )

        with self.assertRaises(ValueError):
            create_meal_prep_batch(
                name='Bad amount',
                yield_quantity=Decimal('300'),
                yield_unit=FoodItem.GRAMS,
                ingredients=[BatchIngredientInput(
                    food_item=self.oats,
                    quantity=Decimal('0'),
                    unit=FoodItem.GRAMS,
                )],
            )

        self.assertEqual(MealPrepBatch.objects.count(), 0)

    def test_create_batch_uses_existing_zero_one_many_price_policy(self):
        batch = create_meal_prep_batch(
            name='Single-price batch',
            yield_quantity=Decimal('300'),
            yield_unit=FoodItem.GRAMS,
            ingredients=[BatchIngredientInput(
                food_item=self.oats,
                quantity=Decimal('100'),
                unit=FoodItem.GRAMS,
            )],
        )
        self.assertEqual(batch.ingredients.get().price_observation, self.price)

        PriceObservation.objects.create(
            food_item=self.oats,
            package_quantity=Decimal('1000'),
            package_unit=FoodItem.GRAMS,
            paid_price=Decimal('3.00'),
            currency='EUR',
        )
        with self.assertRaisesMessage(ValueError, 'Select a price observation'):
            create_meal_prep_batch(
                name='Ambiguous-price batch',
                yield_quantity=Decimal('300'),
                yield_unit=FoodItem.GRAMS,
                ingredients=[BatchIngredientInput(
                    food_item=self.oats,
                    quantity=Decimal('100'),
                    unit=FoodItem.GRAMS,
                )],
            )
        self.assertEqual(MealPrepBatch.objects.count(), 1)

    def test_create_batch_rejects_wrong_price_item_or_unit(self):
        other_item = FoodItem.objects.create(
            name='Milk',
            item_type=FoodItem.INGREDIENT,
            nutrition_basis_unit=FoodItem.MILLILITRES,
        )
        other_price = PriceObservation.objects.create(
            food_item=other_item,
            package_quantity=Decimal('1000'),
            package_unit=FoodItem.MILLILITRES,
            paid_price=Decimal('1.50'),
        )

        with self.assertRaisesMessage(ValueError, 'belong'):
            create_meal_prep_batch(
                name='Wrong price item',
                yield_quantity=Decimal('300'),
                yield_unit=FoodItem.GRAMS,
                ingredients=[BatchIngredientInput(
                    food_item=self.oats,
                    quantity=Decimal('100'),
                    unit=FoodItem.GRAMS,
                    price_observation=other_price,
                )],
            )

        with self.assertRaises(ValueError):
            create_meal_prep_batch(
                name='Wrong unit',
                yield_quantity=Decimal('300'),
                yield_unit=FoodItem.GRAMS,
                ingredients=[BatchIngredientInput(
                    food_item=self.oats,
                    quantity=Decimal('100'),
                    unit=FoodItem.MILLILITRES,
                    price_observation=self.price,
                )],
            )
        self.assertEqual(MealPrepBatch.objects.count(), 0)

    def test_create_batch_rejects_mixed_known_cost_currencies(self):
        milk = FoodItem.objects.create(
            name='Milk',
            item_type=FoodItem.INGREDIENT,
            nutrition_basis_unit=FoodItem.GRAMS,
            calories_per_100=Decimal('60'),
            protein_per_100=Decimal('3'),
            carbohydrates_per_100=Decimal('5'),
            fat_per_100=Decimal('3'),
        )
        sterling_price = PriceObservation.objects.create(
            food_item=milk,
            package_quantity=Decimal('1000'),
            package_unit=FoodItem.GRAMS,
            paid_price=Decimal('1.00'),
            currency='GBP',
        )

        with self.assertRaisesMessage(ValueError, 'single currency'):
            create_meal_prep_batch(
                name='Mixed currency batch',
                yield_quantity=Decimal('300'),
                yield_unit=FoodItem.GRAMS,
                ingredients=[
                    BatchIngredientInput(
                        food_item=self.oats,
                        quantity=Decimal('100'),
                        unit=FoodItem.GRAMS,
                        price_observation=self.price,
                    ),
                    BatchIngredientInput(
                        food_item=milk,
                        quantity=Decimal('100'),
                        unit=FoodItem.GRAMS,
                        price_observation=sterling_price,
                    ),
                ],
            )

        self.assertEqual(MealPrepBatch.objects.count(), 0)

    def test_missing_nutrition_and_price_are_snapshotted_as_incomplete(self):
        self.oats.protein_per_100 = None
        self.oats.save()
        self.price.delete()

        batch = create_meal_prep_batch(
            name='Incomplete batch',
            yield_quantity=Decimal('300'),
            yield_unit=FoodItem.GRAMS,
            ingredients=[BatchIngredientInput(
                food_item=self.oats,
                quantity=Decimal('100'),
                unit=FoodItem.GRAMS,
            )],
        )
        ingredient = batch.ingredients.get()
        totals = calculate_batch_totals(batch)

        self.assertIsNone(ingredient.protein)
        self.assertIsNone(ingredient.estimated_cost)
        self.assertFalse(totals.protein_complete)
        self.assertFalse(totals.cost_complete)
        self.assertEqual(totals.calories, Decimal('380.00'))

    def test_batch_creation_is_atomic_when_a_later_snapshot_cannot_validate(self):
        from unittest.mock import patch

        original_save = BatchIngredient.save
        call_count = 0

        def fail_on_second_save(instance, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError('simulated persistence failure')
            return original_save(instance, *args, **kwargs)

        with patch.object(BatchIngredient, 'save', fail_on_second_save):
            with self.assertRaisesMessage(RuntimeError, 'simulated persistence failure'):
                create_meal_prep_batch(
                    name='Atomic batch',
                    yield_quantity=Decimal('300'),
                    yield_unit=FoodItem.GRAMS,
                    ingredients=[
                        BatchIngredientInput(
                            food_item=self.oats,
                            quantity=Decimal('100'),
                            unit=FoodItem.GRAMS,
                            price_observation=self.price,
                        ),
                        BatchIngredientInput(
                            food_item=self.oats,
                            quantity=Decimal('50'),
                            unit=FoodItem.GRAMS,
                            price_observation=self.price,
                        ),
                    ],
                )

        self.assertEqual(MealPrepBatch.objects.count(), 0)
        self.assertEqual(BatchIngredient.objects.count(), 0)


class RecipeWorkflowTests(TestCase):
    def setUp(self):
        self.food_item = FoodItem.objects.create(
            name='Rolled Oats',
            item_type=FoodItem.INGREDIENT,
            nutrition_basis_unit=FoodItem.GRAMS,
            calories_per_100=Decimal('380'),
            protein_per_100=Decimal('13.20'),
            carbohydrates_per_100=Decimal('67.00'),
            fat_per_100=Decimal('6.50'),
            nutrition_source='label',
        )
        self.price = PriceObservation.objects.create(
            food_item=self.food_item,
            package_quantity=Decimal('1000'),
            package_unit=FoodItem.GRAMS,
            paid_price=Decimal('2.50'),
            currency='EUR',
            source='shop',
        )
        self.recipe = Recipe.objects.create(
            name='Overnight oats',
            instructions='Mix and chill overnight.',
        )

    def _ingredient_post_data(self, **overrides):
        data = {
            'food_item': self.food_item.pk,
            'quantity': '250',
            'unit': FoodItem.GRAMS,
            'price_observation': str(self.price.pk),
        }
        data.update(overrides)
        return data

    def test_recipe_list_empty_state_and_existing_recipes(self):
        self.recipe.delete()
        empty_response = self.client.get(reverse('recipe_list'))

        self.assertEqual(empty_response.status_code, 200)
        self.assertContains(empty_response, 'No recipes yet')
        self.assertContains(empty_response, reverse('recipe_create'))

        Recipe.objects.create(name='Overnight oats')
        other_recipe = Recipe.objects.create(name='Apple porridge')
        response = self.client.get(reverse('recipe_list'))

        self.assertContains(response, 'Apple porridge')
        self.assertContains(response, 'Overnight oats')
        self.assertLess(
            response.content.index(b'Apple porridge'),
            response.content.index(b'Overnight oats'),
        )
        self.assertIsNotNone(other_recipe.pk)

    def test_recipe_navigation_is_present(self):
        response = self.client.get(reverse('catalogue'))

        self.assertContains(response, 'Recipes')
        self.assertContains(response, reverse('recipe_list'))

    def test_recipe_create_invalid_and_valid_submission(self):
        invalid_response = self.client.post(reverse('recipe_create'), {
            'name': '',
            'instructions': 'Some notes',
        })

        self.assertEqual(invalid_response.status_code, 200)
        self.assertContains(invalid_response, 'This field is required.')
        self.assertFalse(Recipe.objects.filter(instructions='Some notes').exists())

        response = self.client.post(reverse('recipe_create'), {
            'name': 'Apple porridge',
            'instructions': 'Cook gently.',
        })

        recipe = Recipe.objects.get(name='Apple porridge')
        self.assertRedirects(response, reverse('recipe_detail', kwargs={'pk': recipe.pk}))
        self.assertContains(self.client.get(response.url), 'Cook gently.')

    def test_recipe_edit_updates_metadata_and_redirects_to_detail(self):
        response = self.client.post(
            reverse('recipe_edit', kwargs={'pk': self.recipe.pk}),
            {
                'name': 'Updated oats',
                'instructions': 'Add fruit before serving.',
            },
        )

        self.assertRedirects(response, reverse('recipe_detail', kwargs={'pk': self.recipe.pk}))
        self.recipe.refresh_from_db()
        self.assertEqual(self.recipe.name, 'Updated oats')
        self.assertEqual(self.recipe.instructions, 'Add fruit before serving.')

    def test_recipe_detail_empty_state_and_instructions(self):
        response = self.client.get(reverse('recipe_detail', kwargs={'pk': self.recipe.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mix and chill overnight.')
        self.assertContains(response, 'This recipe has no planned ingredients yet')
        self.assertContains(response, 'Add at least one to see its estimate')
        self.assertContains(response, 'Create batch')

    def test_recipe_ingredient_create_and_detail_estimate(self):
        response = self.client.post(
            reverse('recipe_ingredient_create', kwargs={'recipe_pk': self.recipe.pk}),
            self._ingredient_post_data(),
        )

        ingredient = self.recipe.ingredients.get()
        self.assertRedirects(response, reverse('recipe_detail', kwargs={'pk': self.recipe.pk}))
        detail = self.client.get(response.url)
        self.assertContains(detail, 'Rolled Oats')
        self.assertContains(detail, '250.000 g')
        self.assertContains(detail, '950.00 kcal')
        self.assertContains(detail, '33.00 g')
        self.assertContains(detail, '0.63 EUR')
        self.assertContains(detail, 'current estimates based on catalogue data')
        self.assertIsNotNone(ingredient.pk)
        self.assertEqual(MealPrepBatch.objects.count(), 0)
        self.assertEqual(ConsumptionEntry.objects.count(), 0)

    def test_recipe_estimate_refreshes_from_current_catalogue_values(self):
        RecipeIngredient.objects.create(
            recipe=self.recipe,
            food_item=self.food_item,
            quantity=Decimal('250'),
            unit=FoodItem.GRAMS,
            price_observation=self.price,
        )

        first_response = self.client.get(reverse('recipe_detail', kwargs={'pk': self.recipe.pk}))
        self.assertContains(first_response, '950.00 kcal')
        self.assertContains(first_response, '0.63 EUR')

        self.food_item.calories_per_100 = Decimal('400')
        self.food_item.save()
        self.price.paid_price = Decimal('4.00')
        self.price.save()

        updated_response = self.client.get(reverse('recipe_detail', kwargs={'pk': self.recipe.pk}))
        self.assertContains(updated_response, '1000.00 kcal')
        self.assertContains(updated_response, '1.00 EUR')

    def test_recipe_ingredient_edit_updates_planned_values(self):
        ingredient = RecipeIngredient.objects.create(
            recipe=self.recipe,
            food_item=self.food_item,
            quantity=Decimal('100'),
            unit=FoodItem.GRAMS,
            price_observation=self.price,
        )

        response = self.client.post(
            reverse(
                'recipe_ingredient_edit',
                kwargs={'recipe_pk': self.recipe.pk, 'pk': ingredient.pk},
            ),
            self._ingredient_post_data(quantity='300'),
        )

        self.assertRedirects(response, reverse('recipe_detail', kwargs={'pk': self.recipe.pk}))
        ingredient.refresh_from_db()
        self.assertEqual(ingredient.quantity, Decimal('300.000'))

    def test_recipe_ingredient_delete_is_post_only_and_scoped_to_recipe(self):
        other_recipe = Recipe.objects.create(name='Other recipe')
        ingredient = RecipeIngredient.objects.create(
            recipe=self.recipe,
            food_item=self.food_item,
            quantity=Decimal('100'),
            unit=FoodItem.GRAMS,
        )
        delete_url = reverse(
            'recipe_ingredient_delete',
            kwargs={'recipe_pk': self.recipe.pk, 'pk': ingredient.pk},
        )

        get_response = self.client.get(delete_url)
        self.assertEqual(get_response.status_code, 405)
        self.assertTrue(RecipeIngredient.objects.filter(pk=ingredient.pk).exists())

        wrong_recipe_edit = self.client.get(reverse(
            'recipe_ingredient_edit',
            kwargs={'recipe_pk': other_recipe.pk, 'pk': ingredient.pk},
        ))
        self.assertEqual(wrong_recipe_edit.status_code, 404)

        wrong_recipe_delete = self.client.post(reverse(
            'recipe_ingredient_delete',
            kwargs={'recipe_pk': other_recipe.pk, 'pk': ingredient.pk},
        ))
        self.assertEqual(wrong_recipe_delete.status_code, 404)
        self.assertTrue(RecipeIngredient.objects.filter(pk=ingredient.pk).exists())

        response = self.client.post(delete_url)
        self.assertRedirects(response, reverse('recipe_detail', kwargs={'pk': self.recipe.pk}))
        self.assertFalse(RecipeIngredient.objects.filter(pk=ingredient.pk).exists())

    def test_recipe_ingredient_form_rejects_quantity_unit_and_price_mismatch(self):
        invalid_quantity = RecipeIngredientForm(data=self._ingredient_post_data(quantity='0'))
        self.assertFalse(invalid_quantity.is_valid())
        self.assertIn('quantity', invalid_quantity.errors)

        invalid_unit = RecipeIngredientForm(data=self._ingredient_post_data(unit=FoodItem.MILLILITRES))
        self.assertFalse(invalid_unit.is_valid())
        self.assertIn('unit', invalid_unit.errors)

        unsupported_unit = RecipeIngredientForm(data=self._ingredient_post_data(unit='oz'))
        self.assertFalse(unsupported_unit.is_valid())
        self.assertIn('unit', unsupported_unit.errors)

        other_item = FoodItem.objects.create(
            name='Milk',
            item_type=FoodItem.INGREDIENT,
            nutrition_basis_unit=FoodItem.GRAMS,
        )
        other_price = PriceObservation.objects.create(
            food_item=other_item,
            package_quantity=Decimal('1000'),
            package_unit=FoodItem.GRAMS,
            paid_price=Decimal('1.50'),
        )
        wrong_price = RecipeIngredientForm(
            data=self._ingredient_post_data(price_observation=str(other_price.pk)),
        )
        self.assertFalse(wrong_price.is_valid())
        self.assertIn('price_observation', wrong_price.errors)

    def test_invalid_ingredient_post_preserves_values_and_shows_errors(self):
        response = self.client.post(
            reverse('recipe_ingredient_create', kwargs={'recipe_pk': self.recipe.pk}),
            self._ingredient_post_data(quantity='0'),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ensure this value is greater than or equal to 0.001.')
        self.assertContains(response, 'value="0"')
        self.assertEqual(self.recipe.ingredients.count(), 0)

    def test_recipe_ingredient_form_reuses_zero_one_multiple_price_policy(self):
        omitted_single = RecipeIngredientForm(
            data=self._ingredient_post_data(price_observation=''),
        )
        self.assertTrue(omitted_single.is_valid(), omitted_single.errors)
        self.assertEqual(omitted_single.cleaned_data['price_observation'], self.price)

        self.price.delete()
        no_price = RecipeIngredientForm(
            data=self._ingredient_post_data(price_observation=''),
        )
        self.assertTrue(no_price.is_valid(), no_price.errors)
        self.assertIsNone(no_price.cleaned_data['price_observation'])

        first_price = PriceObservation.objects.create(
            food_item=self.food_item,
            package_quantity=Decimal('1000'),
            package_unit=FoodItem.GRAMS,
            paid_price=Decimal('2.00'),
        )
        PriceObservation.objects.create(
            food_item=self.food_item,
            package_quantity=Decimal('1000'),
            package_unit=FoodItem.GRAMS,
            paid_price=Decimal('3.00'),
        )
        multiple_without_selection = RecipeIngredientForm(
            data=self._ingredient_post_data(price_observation=''),
        )
        self.assertFalse(multiple_without_selection.is_valid())
        self.assertIn('price_observation', multiple_without_selection.errors)

        explicit_price = RecipeIngredientForm(
            data=self._ingredient_post_data(price_observation=str(first_price.pk)),
        )
        self.assertTrue(explicit_price.is_valid(), explicit_price.errors)

    def test_recipe_estimate_components_render_incomplete_independently(self):
        self.food_item.fat_per_100 = None
        self.food_item.save()
        self.price.delete()
        RecipeIngredient.objects.create(
            recipe=self.recipe,
            food_item=self.food_item,
            quantity=Decimal('250'),
            unit=FoodItem.GRAMS,
        )

        response = self.client.get(reverse('recipe_detail', kwargs={'pk': self.recipe.pk}))

        self.assertContains(response, '950.00 kcal')
        self.assertContains(response, '33.00 g')
        self.assertContains(response, 'Carbohydrates')
        self.assertContains(response, 'Fat')
        self.assertContains(response, 'Estimated cost')
        self.assertContains(response, 'Incomplete')
        self.assertContains(response, 'Nutrition information is missing')
        self.assertContains(response, 'Price information is missing')
        self.assertNotContains(response, '0.00 EUR')

    def test_recipe_mixed_currency_estimate_is_not_rendered_as_a_total(self):
        other_item = FoodItem.objects.create(
            name='Milk',
            item_type=FoodItem.INGREDIENT,
            nutrition_basis_unit=FoodItem.GRAMS,
            calories_per_100=Decimal('60'),
            protein_per_100=Decimal('3'),
            carbohydrates_per_100=Decimal('5'),
            fat_per_100=Decimal('3'),
        )
        sterling_price = PriceObservation.objects.create(
            food_item=other_item,
            package_quantity=Decimal('1000'),
            package_unit=FoodItem.GRAMS,
            paid_price=Decimal('1.00'),
            currency='GBP',
        )
        RecipeIngredient.objects.create(
            recipe=self.recipe,
            food_item=self.food_item,
            quantity=Decimal('100'),
            unit=FoodItem.GRAMS,
            price_observation=self.price,
        )
        RecipeIngredient.objects.create(
            recipe=self.recipe,
            food_item=other_item,
            quantity=Decimal('100'),
            unit=FoodItem.GRAMS,
            price_observation=sterling_price,
        )

        response = self.client.get(reverse('recipe_detail', kwargs={'pk': self.recipe.pk}))

        self.assertContains(response, 'Costs use different currencies and cannot be combined')
        self.assertContains(response, 'Incomplete')
        self.assertNotContains(response, '1.50 EUR')

    def test_recipe_detail_handles_stale_price_reference_gracefully(self):
        ingredient = RecipeIngredient.objects.create(
            recipe=self.recipe,
            food_item=self.food_item,
            quantity=Decimal('100'),
            unit=FoodItem.GRAMS,
            price_observation=self.price,
        )
        self.food_item.nutrition_basis_unit = FoodItem.MILLILITRES
        self.food_item.save()

        response = self.client.get(reverse('recipe_detail', kwargs={'pk': self.recipe.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'The estimate is unavailable')
        self.assertNotContains(response, 'Traceback')


class MealPrepFormTests(TestCase):
    def setUp(self):
        self.food_item = FoodItem.objects.create(
            name='Rolled Oats',
            item_type=FoodItem.INGREDIENT,
            nutrition_basis_unit=FoodItem.GRAMS,
        )
        self.price = PriceObservation.objects.create(
            food_item=self.food_item,
            package_quantity=Decimal('1000'),
            package_unit=FoodItem.GRAMS,
            paid_price=Decimal('2.50'),
        )

    def _ingredient_data(self, **overrides):
        data = {
            'food_item': self.food_item.pk,
            'quantity': '250',
            'unit': FoodItem.GRAMS,
            'price_observation': '',
        }
        data.update(overrides)
        return data

    def test_batch_form_defaults_cooked_time_and_rejects_invalid_yield(self):
        form = MealPrepBatchForm()

        self.assertEqual(form.fields['cooked_at'].widget.input_type, 'datetime-local')
        self.assertTrue(form['cooked_at'].value())

        invalid = MealPrepBatchForm(data={
            'name': 'Oats',
            'recipe': '',
            'cooked_at': '2026-10-25T12:30',
            'yield_quantity': '0',
            'yield_unit': FoodItem.GRAMS,
        })
        self.assertFalse(invalid.is_valid())
        self.assertIn('yield_quantity', invalid.errors)

    def test_ingredient_form_matches_unit_and_reuses_price_policy(self):
        single_price = BatchIngredientForm(data=self._ingredient_data())
        self.assertTrue(single_price.is_valid(), single_price.errors)
        self.assertEqual(single_price.cleaned_data['price_observation'], self.price)

        second_price = PriceObservation.objects.create(
            food_item=self.food_item,
            package_quantity=Decimal('500'),
            package_unit=FoodItem.GRAMS,
            paid_price=Decimal('1.50'),
        )
        ambiguous = BatchIngredientForm(data=self._ingredient_data())
        self.assertFalse(ambiguous.is_valid())
        self.assertIn('price_observation', ambiguous.errors)

        explicit = BatchIngredientForm(data=self._ingredient_data(
            price_observation=str(second_price.pk),
        ))
        self.assertTrue(explicit.is_valid(), explicit.errors)
        self.assertEqual(explicit.cleaned_data['price_observation'], second_price)

    def test_ingredient_form_rejects_unit_and_price_ownership_mismatch(self):
        wrong_unit = BatchIngredientForm(data=self._ingredient_data(unit=FoodItem.MILLILITRES))
        self.assertFalse(wrong_unit.is_valid())
        self.assertIn('unit', wrong_unit.errors)

        other_item = FoodItem.objects.create(
            name='Milk',
            item_type=FoodItem.INGREDIENT,
            nutrition_basis_unit=FoodItem.GRAMS,
        )
        other_price = PriceObservation.objects.create(
            food_item=other_item,
            package_quantity=Decimal('1000'),
            package_unit=FoodItem.GRAMS,
            paid_price=Decimal('1.50'),
        )
        wrong_price = BatchIngredientForm(data=self._ingredient_data(
            price_observation=str(other_price.pk),
        ))
        self.assertFalse(wrong_price.is_valid())
        self.assertIn('price_observation', wrong_price.errors)

    def test_formset_requires_one_non_deleted_ingredient_and_ignores_blank_extra_row(self):
        blank = {
            'ingredients-TOTAL_FORMS': '1',
            'ingredients-INITIAL_FORMS': '0',
            'ingredients-MIN_NUM_FORMS': '1',
            'ingredients-MAX_NUM_FORMS': '1000',
        }
        self.assertFalse(BatchIngredientFormSet(data=blank, prefix='ingredients').is_valid())

        valid_with_blank_extra = {
            'ingredients-TOTAL_FORMS': '2',
            'ingredients-INITIAL_FORMS': '0',
            'ingredients-MIN_NUM_FORMS': '1',
            'ingredients-MAX_NUM_FORMS': '1000',
            'ingredients-0-food_item': str(self.food_item.pk),
            'ingredients-0-quantity': '250',
            'ingredients-0-unit': FoodItem.GRAMS,
            'ingredients-0-price_observation': str(self.price.pk),
        }
        formset = BatchIngredientFormSet(data=valid_with_blank_extra, prefix='ingredients')
        self.assertTrue(formset.is_valid(), formset.errors)

        valid_with_blank_extra['ingredients-0-DELETE'] = 'on'
        deleted_formset = BatchIngredientFormSet(
            data=valid_with_blank_extra,
            prefix='ingredients',
        )
        self.assertFalse(deleted_formset.is_valid())


class MealPrepWorkflowTests(TestCase):
    def setUp(self):
        self.food_item = FoodItem.objects.create(
            name='Rolled Oats',
            item_type=FoodItem.INGREDIENT,
            nutrition_basis_unit=FoodItem.GRAMS,
            calories_per_100=Decimal('380'),
            protein_per_100=Decimal('13.20'),
            carbohydrates_per_100=Decimal('67.00'),
            fat_per_100=Decimal('6.50'),
            nutrition_source='package label',
        )
        self.price = PriceObservation.objects.create(
            food_item=self.food_item,
            package_quantity=Decimal('1000'),
            package_unit=FoodItem.GRAMS,
            paid_price=Decimal('2.50'),
            currency='EUR',
            source='shop receipt',
        )
        self.recipe = Recipe.objects.create(name='Overnight oats')

    def _batch_post_data(self, **overrides):
        data = {
            'name': 'Sunday oats',
            'recipe': '',
            'cooked_at': '2026-10-25T12:30',
            'yield_quantity': '400',
            'yield_unit': FoodItem.GRAMS,
            'ingredients-TOTAL_FORMS': '1',
            'ingredients-INITIAL_FORMS': '0',
            'ingredients-MIN_NUM_FORMS': '1',
            'ingredients-MAX_NUM_FORMS': '1000',
            'ingredients-0-food_item': str(self.food_item.pk),
            'ingredients-0-quantity': '250',
            'ingredients-0-unit': FoodItem.GRAMS,
            'ingredients-0-price_observation': str(self.price.pk),
            'action': 'create',
        }
        data.update(overrides)
        return data

    def test_batch_list_empty_state_and_navigation(self):
        response = self.client.get(reverse('meal_prep_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No batches yet')
        self.assertContains(response, reverse('meal_prep_create'))
        self.assertContains(response, 'Meal Prep')

    def test_batch_list_orders_newest_cooked_first(self):
        older = create_meal_prep_batch(
            name='Older batch',
            cooked_at=timezone.datetime(2026, 10, 20, 12, tzinfo=timezone.get_current_timezone()),
            yield_quantity=Decimal('300'),
            yield_unit=FoodItem.GRAMS,
            ingredients=[BatchIngredientInput(
                food_item=self.food_item,
                quantity=Decimal('100'),
                unit=FoodItem.GRAMS,
                price_observation=self.price,
            )],
        )
        newer = create_meal_prep_batch(
            name='Newer batch',
            cooked_at=timezone.datetime(2026, 10, 24, 12, tzinfo=timezone.get_current_timezone()),
            yield_quantity=Decimal('350'),
            yield_unit=FoodItem.GRAMS,
            ingredients=[BatchIngredientInput(
                food_item=self.food_item,
                quantity=Decimal('120'),
                unit=FoodItem.GRAMS,
                price_observation=self.price,
            )],
        )

        response = self.client.get(reverse('meal_prep_list'))

        self.assertLess(response.content.index(b'Newer batch'), response.content.index(b'Older batch'))
        self.assertEqual(older.ingredients.count(), 1)
        self.assertEqual(newer.ingredients.count(), 1)

    def test_create_direct_batch_persists_through_service_and_redirects(self):
        response = self.client.post(reverse('meal_prep_create'), self._batch_post_data())

        batch = MealPrepBatch.objects.get(name='Sunday oats')
        ingredient = batch.ingredients.get()
        self.assertRedirects(response, reverse('meal_prep_detail', kwargs={'pk': batch.pk}))
        self.assertEqual(ingredient.food_item_name_snapshot, 'Rolled Oats')
        self.assertEqual(ingredient.calories, Decimal('950.00'))
        self.assertEqual(ingredient.estimated_cost, Decimal('0.63'))
        self.assertIsNone(batch.recipe)

    def test_recipe_detail_and_create_form_prefill_planned_ingredients(self):
        planned = RecipeIngredient.objects.create(
            recipe=self.recipe,
            food_item=self.food_item,
            quantity=Decimal('180'),
            unit=FoodItem.GRAMS,
            price_observation=self.price,
        )

        recipe_detail = self.client.get(reverse('recipe_detail', kwargs={'pk': self.recipe.pk}))
        self.assertContains(recipe_detail, f"{reverse('meal_prep_create')}?recipe={self.recipe.pk}")

        response = self.client.get(reverse('meal_prep_create'), {'recipe': self.recipe.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="180.000"')
        self.assertContains(response, f'value="{planned.food_item_id}" selected')
        self.assertContains(response, f'value="{self.recipe.pk}" selected')

    def test_load_recipe_round_trip_preserves_batch_fields_and_prefills_rows(self):
        RecipeIngredient.objects.create(
            recipe=self.recipe,
            food_item=self.food_item,
            quantity=Decimal('180'),
            unit=FoodItem.GRAMS,
            price_observation=self.price,
        )
        response = self.client.post(reverse('meal_prep_create'), {
            'name': 'Cooked oats',
            'recipe': str(self.recipe.pk),
            'cooked_at': '2026-10-25T12:30',
            'yield_quantity': '300',
            'yield_unit': FoodItem.GRAMS,
            'action': 'load_recipe',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Cooked oats"')
        self.assertContains(response, 'value="180.000"')
        self.assertEqual(MealPrepBatch.objects.count(), 0)

    def test_invalid_recipe_query_falls_back_to_direct_batch_form(self):
        response = self.client.get(reverse('meal_prep_create'), {'recipe': 'not-a-number'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Create Meal Prep Batch')
        self.assertEqual(len(response.context['formset'].forms), 1)

    def test_add_and_remove_rows_use_post_round_trips(self):
        add_data = self._batch_post_data(action='add_ingredient')
        added = self.client.post(reverse('meal_prep_create'), add_data)
        self.assertEqual(added.status_code, 200)
        self.assertContains(added, 'name="ingredients-1-food_item"')
        self.assertEqual(MealPrepBatch.objects.count(), 0)

        remove_data = self._batch_post_data(
            **{
                'ingredients-TOTAL_FORMS': '2',
                'ingredients-1-food_item': str(self.food_item.pk),
                'ingredients-1-quantity': '50',
                'ingredients-1-unit': FoodItem.GRAMS,
                'ingredients-1-price_observation': str(self.price.pk),
                'remove_index': '0',
            },
        )
        removed = self.client.post(reverse('meal_prep_create'), remove_data)
        self.assertEqual(removed.status_code, 200)
        self.assertNotContains(removed, 'name="ingredients-0-food_item"')
        self.assertContains(removed, 'name="ingredients-1-food_item"')
        self.assertTrue(removed.context['formset'].forms[0]['DELETE'].value())
        self.assertEqual(MealPrepBatch.objects.count(), 0)

    def test_invalid_submission_preserves_values_and_empty_rows_are_rejected(self):
        invalid = self.client.post(
            reverse('meal_prep_create'),
            self._batch_post_data(name='Still entered', yield_quantity='0'),
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertContains(invalid, 'value="Still entered"')
        self.assertContains(invalid, 'value="0"')
        self.assertEqual(MealPrepBatch.objects.count(), 0)

        empty_data = self._batch_post_data(**{
            'ingredients-0-food_item': '',
            'ingredients-0-quantity': '',
            'ingredients-0-unit': '',
            'ingredients-0-price_observation': '',
        })
        empty = self.client.post(reverse('meal_prep_create'), empty_data)
        self.assertEqual(empty.status_code, 200)
        self.assertContains(empty, 'at least 1 form')
        self.assertEqual(MealPrepBatch.objects.count(), 0)

    def test_mixed_currency_service_error_preserves_submitted_ingredients(self):
        milk = FoodItem.objects.create(
            name='Milk',
            item_type=FoodItem.INGREDIENT,
            nutrition_basis_unit=FoodItem.MILLILITRES,
        )
        milk_price = PriceObservation.objects.create(
            food_item=milk,
            package_quantity=Decimal('1000'),
            package_unit=FoodItem.MILLILITRES,
            paid_price=Decimal('1.50'),
            currency='GBP',
        )
        data = self._batch_post_data(**{
            'ingredients-TOTAL_FORMS': '2',
            'ingredients-1-food_item': str(milk.pk),
            'ingredients-1-quantity': '100',
            'ingredients-1-unit': FoodItem.MILLILITRES,
            'ingredients-1-price_observation': str(milk_price.pk),
        })

        response = self.client.post(reverse('meal_prep_create'), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'single currency')
        self.assertContains(response, 'value="100"')
        self.assertEqual(MealPrepBatch.objects.count(), 0)

    def test_batch_detail_uses_historical_snapshots_and_is_read_only(self):
        batch = create_meal_prep_batch(
            name='Snapshot oats',
            recipe=self.recipe,
            yield_quantity=Decimal('400'),
            yield_unit=FoodItem.GRAMS,
            ingredients=[BatchIngredientInput(
                food_item=self.food_item,
                quantity=Decimal('250'),
                unit=FoodItem.GRAMS,
                price_observation=self.price,
            )],
        )
        self.food_item.calories_per_100 = Decimal('100')
        self.food_item.save()
        self.recipe.name = 'Renamed recipe'
        self.recipe.save()

        response = self.client.get(reverse('meal_prep_detail', kwargs={'pk': batch.pk}))
        self.assertContains(response, '950.00 kcal')
        self.assertContains(response, 'Rolled Oats')
        self.assertContains(response, 'Snapshot oats')
        self.assertContains(response, 'Renamed recipe')
        self.assertNotContains(response, 'Edit batch')
        self.assertEqual(
            self.client.post(reverse('meal_prep_detail', kwargs={'pk': batch.pk})).status_code,
            405,
        )

    def test_batch_detail_marks_missing_snapshot_values_incomplete(self):
        self.food_item.protein_per_100 = None
        self.food_item.save()
        self.price.delete()
        batch = create_meal_prep_batch(
            name='Incomplete oats',
            yield_quantity=Decimal('300'),
            yield_unit=FoodItem.GRAMS,
            ingredients=[BatchIngredientInput(
                food_item=self.food_item,
                quantity=Decimal('100'),
                unit=FoodItem.GRAMS,
            )],
        )

        response = self.client.get(reverse('meal_prep_detail', kwargs={'pk': batch.pk}))

        self.assertContains(response, 'Nutrition is incomplete')
        self.assertContains(response, 'Cost is incomplete')
        self.assertContains(response, 'Unknown')
        self.assertContains(response, 'Incomplete')


class BatchConsumptionWorkflowTests(TestCase):
    def setUp(self):
        self.food_item = FoodItem.objects.create(
            name='Meal base',
            item_type=FoodItem.INGREDIENT,
            nutrition_basis_unit=FoodItem.GRAMS,
            calories_per_100=Decimal('200'),
            protein_per_100=Decimal('10'),
            carbohydrates_per_100=Decimal('20'),
            fat_per_100=Decimal('4'),
            nutrition_source='label',
        )
        self.price = PriceObservation.objects.create(
            food_item=self.food_item,
            package_quantity=Decimal('1200'),
            package_unit=FoodItem.GRAMS,
            paid_price=Decimal('12.00'),
            currency='GBP',
            source='receipt',
        )
        self.batch = create_meal_prep_batch(
            name='Lunch batch',
            yield_quantity=Decimal('1200'),
            yield_unit=FoodItem.GRAMS,
            ingredients=[BatchIngredientInput(
                food_item=self.food_item,
                quantity=Decimal('1200'),
                unit=FoodItem.GRAMS,
                price_observation=self.price,
            )],
        )

    def _post_data(self, **overrides):
        data = {
            'quantity': '300',
            'unit': FoodItem.GRAMS,
            'consumed_at': '2026-10-25T12:30',
            'meal_category': 'lunch',
        }
        data.update(overrides)
        return data

    def test_batch_detail_action_and_context_page(self):
        detail = self.client.get(reverse('meal_prep_detail', kwargs={'pk': self.batch.pk}))
        self.assertContains(
            detail,
            reverse('batch_consumption_create', kwargs={'batch_pk': self.batch.pk}),
        )
        self.assertContains(detail, 'Log as eaten')

        response = self.client.get(reverse(
            'batch_consumption_create',
            kwargs={'batch_pk': self.batch.pk},
        ))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Lunch batch')
        self.assertContains(response, '1200.000 g')
        self.assertContains(response, '2400.00 kcal')
        self.assertContains(response, '12.00 GBP')
        self.assertNotContains(response, 'name="calories"')
        self.assertNotContains(response, 'name="estimated_cost"')
        self.assertEqual(set(response.context['form'].fields), {
            'quantity', 'unit', 'consumed_at', 'meal_category',
        })

    def test_valid_batch_consumption_redirects_to_local_today_and_snapshots(self):
        response = self.client.post(
            reverse('batch_consumption_create', kwargs={'batch_pk': self.batch.pk}),
            self._post_data(),
        )

        entry = ConsumptionEntry.objects.get()
        self.assertRedirects(response, f'{reverse("food_today")}?date=2026-10-25')
        self.assertEqual(entry.calories, Decimal('600.00'))
        self.assertEqual(entry.protein, Decimal('30.00'))
        self.assertEqual(entry.carbohydrates, Decimal('60.00'))
        self.assertEqual(entry.fat, Decimal('12.00'))
        self.assertEqual(entry.estimated_cost, Decimal('3.00'))
        self.assertEqual(entry.currency, 'GBP')

    def test_invalid_amount_and_unit_preserve_form_values_without_internal_errors(self):
        url = reverse('batch_consumption_create', kwargs={'batch_pk': self.batch.pk})
        for data in (
            self._post_data(quantity='0'),
            self._post_data(quantity='1300'),
            self._post_data(unit=FoodItem.MILLILITRES),
        ):
            response = self.client.post(url, data)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Lunch batch')
            self.assertNotContains(response, 'Traceback')
        self.assertContains(
            self.client.post(url, self._post_data(unit=FoodItem.MILLILITRES)),
            'Select a valid choice',
        )
        self.assertEqual(ConsumptionEntry.objects.count(), 0)

    def test_batch_entry_appears_in_today_and_history_and_metadata_edit_preserves_snapshots(self):
        response = self.client.post(
            reverse('batch_consumption_create', kwargs={'batch_pk': self.batch.pk}),
            self._post_data(),
        )
        entry = ConsumptionEntry.objects.get()
        self.assertRedirects(response, f'{reverse("food_today")}?date=2026-10-25')

        today = self.client.get(reverse('food_today'), {'date': '2026-10-25'})
        history = self.client.get(reverse('food_history'), {'date': '2026-10-25'})
        self.assertContains(today, 'Meal Prep Batch: Lunch batch')
        self.assertContains(today, '600.00')
        self.assertContains(today, '3.00 GBP')
        self.assertContains(history, 'Meal Prep Batch: Lunch batch')
        self.assertContains(history, '3.00 GBP')

        edit_url = reverse('consumption_edit', kwargs={'pk': entry.pk})
        edit_page = self.client.get(edit_url)
        self.assertContains(edit_page, 'Only the consumed date, time, and meal category can be changed')
        self.assertNotContains(edit_page, 'Recalculate and save')
        self.assertNotContains(edit_page, 'name="food_item"')
        edited = self.client.post(edit_url, {
            'consumed_at': '2026-10-25T14:00',
            'meal_category': 'dinner',
        })
        self.assertEqual(edited.status_code, 302)
        entry.refresh_from_db()
        self.assertEqual(entry.meal_category, 'dinner')
        self.assertEqual(entry.calories, Decimal('600.00'))
        self.assertEqual(entry.estimated_cost, Decimal('3.00'))

    def test_today_groups_batch_costs_and_displays_known_zero_currency(self):
        create_batch_consumption_entry(
            self.batch,
            consumed_quantity=Decimal('300'),
            unit=FoodItem.GRAMS,
            consumed_at=timezone.make_aware(
                datetime(2026, 10, 25, 10, 0),
                timezone.get_current_timezone(),
            ),
        )
        euro_price = PriceObservation.objects.create(
            food_item=self.food_item,
            package_quantity=Decimal('1200'),
            package_unit=FoodItem.GRAMS,
            paid_price=Decimal('24.00'),
            currency='EUR',
            source='other receipt',
        )
        euro_batch = create_meal_prep_batch(
            name='Euro batch',
            yield_quantity=Decimal('1200'),
            yield_unit=FoodItem.GRAMS,
            ingredients=[BatchIngredientInput(
                food_item=self.food_item,
                quantity=Decimal('1200'),
                unit=FoodItem.GRAMS,
                price_observation=euro_price,
            )],
        )
        create_batch_consumption_entry(
            euro_batch,
            consumed_quantity=Decimal('300'),
            unit=FoodItem.GRAMS,
            consumed_at=timezone.make_aware(
                datetime(2026, 10, 25, 11, 0),
                timezone.get_current_timezone(),
            ),
        )
        zero_price = PriceObservation.objects.create(
            food_item=self.food_item,
            package_quantity=Decimal('1200'),
            package_unit=FoodItem.GRAMS,
            paid_price=Decimal('0.00'),
            currency='JPY',
            source='free sample',
        )
        zero_batch = create_meal_prep_batch(
            name='Zero-cost batch',
            yield_quantity=Decimal('1200'),
            yield_unit=FoodItem.GRAMS,
            ingredients=[BatchIngredientInput(
                food_item=self.food_item,
                quantity=Decimal('1200'),
                unit=FoodItem.GRAMS,
                price_observation=zero_price,
            )],
        )
        create_batch_consumption_entry(
            zero_batch,
            consumed_quantity=Decimal('300'),
            unit=FoodItem.GRAMS,
            consumed_at=timezone.make_aware(
                datetime(2026, 10, 25, 12, 0),
                timezone.get_current_timezone(),
            ),
        )

        today = self.client.get(reverse('food_today'), {'date': '2026-10-25'})
        history = self.client.get(reverse('food_history'), {'date': '2026-10-25'})
        self.assertContains(today, '3.00 GBP')
        self.assertContains(today, '6.00 EUR')
        self.assertContains(today, '0.00 JPY')
        self.assertContains(history, '0.00 JPY')
        self.assertNotContains(today, '9.00 EUR')

    def test_deleting_batch_entry_does_not_delete_batch_and_batch_deletion_preserves_entry(self):
        entry = create_batch_consumption_entry(
            self.batch,
            consumed_quantity=Decimal('300'),
            unit=FoodItem.GRAMS,
        )
        delete_url = reverse('consumption_delete', kwargs={'pk': entry.pk})
        self.assertEqual(self.client.get(delete_url).status_code, 405)
        self.assertEqual(self.client.post(delete_url).status_code, 302)
        self.assertFalse(ConsumptionEntry.objects.filter(pk=entry.pk).exists())
        self.assertTrue(MealPrepBatch.objects.filter(pk=self.batch.pk).exists())

        entry = create_batch_consumption_entry(
            self.batch,
            consumed_quantity=Decimal('300'),
            unit=FoodItem.GRAMS,
        )
        self.batch.delete()
        entry.refresh_from_db()
        self.assertIsNone(entry.meal_prep_batch)
        self.assertEqual(entry.calories, Decimal('600.00'))
        self.assertEqual(entry.estimated_cost, Decimal('3.00'))
        self.assertEqual(
            self.client.get(reverse('consumption_edit', kwargs={'pk': entry.pk})).status_code,
            200,
        )

    def test_individually_valid_entries_may_exceed_cumulative_yield(self):
        for _ in range(2):
            create_batch_consumption_entry(
                self.batch,
                consumed_quantity=Decimal('800'),
                unit=FoodItem.GRAMS,
            )

        self.assertEqual(self.batch.consumption_entries.count(), 2)


class ConsumptionBatchMigrationTests(TransactionTestCase):
    migrate_from = ('food', '0002_recipe_mealprepbatch_recipeingredient_and_more')
    migrate_to = ('food', '0004_foodpurchase')

    def tearDown(self):
        MigrationExecutor(connection).migrate([self.migrate_to])
        super().tearDown()

    def test_existing_item_entry_values_survive_nullable_batch_fk_migration(self):
        MigrationExecutor(connection).migrate([self.migrate_from])
        old_apps = MigrationExecutor(connection).loader.project_state(
            [self.migrate_from],
        ).apps
        FoodItem = old_apps.get_model('food', 'FoodItem')
        OldConsumptionEntry = old_apps.get_model('food', 'ConsumptionEntry')

        food_item = FoodItem.objects.create(
            name='Migration oats',
            item_type='ingredient',
            nutrition_basis_unit='g',
        )
        old_entry = OldConsumptionEntry.objects.create(
            food_item=food_item,
            source_name='Migration oats',
            quantity=Decimal('125'),
            unit='g',
            calories=Decimal('475.00'),
            protein=Decimal('16.50'),
            carbohydrates=Decimal('83.75'),
            fat=Decimal('8.13'),
            estimated_cost=Decimal('0.31'),
            currency='EUR',
            nutrition_source='label',
            cost_source='receipt',
        )

        MigrationExecutor(connection).migrate([self.migrate_to])
        migrated_entry = ConsumptionEntry.objects.get(pk=old_entry.pk)

        self.assertEqual(migrated_entry.food_item_id, food_item.pk)
        self.assertIsNone(migrated_entry.meal_prep_batch_id)
        self.assertEqual(migrated_entry.source_name, 'Migration oats')
        self.assertEqual(migrated_entry.quantity, Decimal('125.000'))
        self.assertEqual(migrated_entry.calories, Decimal('475.00'))
        self.assertEqual(migrated_entry.estimated_cost, Decimal('0.31'))
        self.assertEqual(migrated_entry.currency, 'EUR')
        self.assertEqual(migrated_entry.nutrition_source, 'label')
        self.assertEqual(migrated_entry.cost_source, 'receipt')
