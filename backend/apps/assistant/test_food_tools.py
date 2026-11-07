from django.test import TestCase
from django.utils import timezone

from apps.food.models import FoodItem
from apps.food.services.consumption import create_quick_add_entry
from apps.assistant.services.food_tools import execute_food_tool


class ReadOnlyFoodToolTests(TestCase):
    def test_daily_summary_preserves_unknown_nutrients_as_null(self):
        today = timezone.localdate()
        create_quick_add_entry(
            source_name="Test lunch",
            consumed_at=timezone.now(),
            calories=500,
            protein=None,
            carbohydrates=60,
            fat=15,
        )

        result = execute_food_tool("get_daily_food_summary", {"date": today.isoformat()})

        self.assertEqual(result["entry_count"], 1)
        self.assertEqual(result["calories"], "500.00")
        self.assertIsNone(result["protein_g"])
        self.assertFalse(result["completeness"]["protein"])

    def test_catalogue_search_returns_food_item_details(self):
        item = FoodItem.objects.create(
            name="Chicken breast",
            item_type=FoodItem.INGREDIENT,
            nutrition_basis_unit=FoodItem.GRAMS,
            calories_per_100="165.00",
            protein_per_100="31.00",
        )

        result = execute_food_tool("search_food_catalogue", {"query": "chicken"})

        self.assertEqual(result["returned_count"], 1)
        self.assertEqual(result["items"][0]["id"], item.pk)
        self.assertEqual(result["items"][0]["protein_per_100"], "31.00")

    def test_history_rejects_ranges_over_31_days(self):
        with self.assertRaises(ValueError):
            execute_food_tool("get_food_history", {
                "start_date": "2026-01-01",
                "end_date": "2026-02-02",
            })

    def test_unknown_tool_is_rejected(self):
        with self.assertRaises(ValueError):
            execute_food_tool("delete_all_food", {})

    def test_unexpected_arguments_are_rejected(self):
        with self.assertRaises(ValueError):
            execute_food_tool("get_daily_food_summary", {"date": "2026-11-07", "delete": True})

    def test_tool_arguments_must_be_an_object(self):
        with self.assertRaises(ValueError):
            execute_food_tool("get_meal_prep_batches", [])
