from django.test import SimpleTestCase
from apps.assistant.services.food_write_tools import validate_food_write_tool


class FoodWriteToolValidationTests(SimpleTestCase):
    def test_rejects_unknown_write_function(self):
        with self.assertRaises(ValueError):
            validate_food_write_tool("delete_all", {})

    def test_create_food_item_allows_unknown_nutrition_to_remain_null(self):
        preview = validate_food_write_tool("create_food_item", {"name": "Basmati rice", "item_type": "ingredient", "nutrition_basis_unit": "g"})
        self.assertEqual(preview["nutrition"]["calories_per_100"], None)

    def test_create_food_item_rejects_negative_nutrition(self):
        with self.assertRaises(ValueError):
            validate_food_write_tool("create_food_item", {"name": "Rice", "item_type": "ingredient", "nutrition_basis_unit": "g", "calories_per_100": -1})

    def test_recipe_requires_at_least_one_ingredient(self):
        with self.assertRaises(ValueError):
            validate_food_write_tool("create_recipe", {"name": "Chicken curry", "ingredients": []})
