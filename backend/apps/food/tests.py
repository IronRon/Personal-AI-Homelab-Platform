from datetime import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import FoodItemForm, PriceObservationForm
from .models import ConsumptionEntry, FoodItem, PriceObservation
from .services.calculations import (
    aggregate_daily,
    calculate_allocated_cost,
    scale_nutrition,
)


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
