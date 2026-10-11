from datetime import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

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
