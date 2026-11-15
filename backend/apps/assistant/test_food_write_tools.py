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

from decimal import Decimal
from django.test import TestCase
from apps.food.models import FoodItem, Recipe, RecipeIngredient, MealPrepBatch
from apps.assistant.services.food_write_tools import execute_food_write_tool


class FoodWriteToolEditDeleteTests(TestCase):
    def setUp(self):
        self.oats = FoodItem.objects.create(
            name="Test Oats", item_type=FoodItem.INGREDIENT,
            nutrition_basis_unit=FoodItem.GRAMS,
        )
        self.rice = FoodItem.objects.create(
            name="Basmati Rice", item_type=FoodItem.INGREDIENT,
            nutrition_basis_unit=FoodItem.GRAMS,
        )

    def test_update_food_item_changes_only_supplied_fields(self):
        result = execute_food_write_tool("update_food_item", {
            "food_item_id": self.oats.pk,
            "name": "Rolled Oats",
            "protein_per_100": "13.2",
        })
        self.oats.refresh_from_db()
        self.assertEqual(result["updated"], "food_item")
        self.assertEqual(self.oats.name, "Rolled Oats")
        self.assertEqual(self.oats.protein_per_100, Decimal("13.2"))
        self.assertIsNone(self.oats.calories_per_100)

    def test_delete_unused_food_item(self):
        result = execute_food_write_tool("delete_food_item", {"food_item_id": self.oats.pk})
        self.assertEqual(result["deleted"], "food_item")
        self.assertFalse(FoodItem.objects.filter(pk=self.oats.pk).exists())

    def test_delete_food_item_is_blocked_when_used_in_recipe(self):
        recipe = Recipe.objects.create(name="Porridge")
        RecipeIngredient.objects.create(recipe=recipe, food_item=self.oats, quantity=Decimal("50"), unit="g")
        with self.assertRaisesMessage(ValueError, "linked to existing records"):
            execute_food_write_tool("delete_food_item", {"food_item_id": self.oats.pk})
        self.assertTrue(FoodItem.objects.filter(pk=self.oats.pk).exists())

    def test_update_recipe_can_replace_ingredient_list(self):
        recipe = Recipe.objects.create(name="Rice bowl")
        RecipeIngredient.objects.create(recipe=recipe, food_item=self.oats, quantity=Decimal("30"), unit="g")
        result = execute_food_write_tool("update_recipe", {
            "recipe_id": recipe.pk,
            "name": "Basmati rice bowl",
            "ingredients": [{"food_item_id": self.rice.pk, "quantity": "100", "unit": "g"}],
        })
        recipe.refresh_from_db()
        self.assertEqual(result["updated"], "recipe")
        self.assertEqual(recipe.name, "Basmati rice bowl")
        self.assertEqual(list(recipe.ingredients.values_list("food_item_id", flat=True)), [self.rice.pk])

    def test_delete_recipe_is_blocked_when_linked_to_meal_prep_batch(self):
        recipe = Recipe.objects.create(name="Meal prep recipe")
        MealPrepBatch.objects.create(name="Four day batch", recipe=recipe, yield_quantity=Decimal("1600"), yield_unit="g")
        with self.assertRaisesMessage(ValueError, "linked to existing meal-prep batches"):
            execute_food_write_tool("delete_recipe", {"recipe_id": recipe.pk})
        self.assertTrue(Recipe.objects.filter(pk=recipe.pk).exists())
