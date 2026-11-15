"""Validated Food write operations. These are invoked only after UI confirmation."""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from apps.food.models import ConsumptionEntry, FoodItem, Recipe, RecipeIngredient, MealPrepBatch
from apps.food.services.consumption import create_consumption_entry, create_batch_consumption_entry
from apps.food.services.meal_prep import BatchIngredientInput, create_meal_prep_batch


def _text(args, key, *, required=True, maximum=200):
    value = args.get(key, "")
    if not isinstance(value, str):
        raise ValueError(f"'{key}' must be text.")
    value = value.strip()
    if required and not value:
        raise ValueError(f"'{key}' is required.")
    if len(value) > maximum:
        raise ValueError(f"'{key}' must be {maximum} characters or fewer.")
    return value


def _decimal(args, key, *, required=True):
    value = args.get(key)
    if value is None and not required:
        return None
    if isinstance(value, bool) or value is None:
        raise ValueError(f"'{key}' must be a non-negative number.")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"'{key}' must be a valid number.") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"'{key}' must be a non-negative finite number.")
    return result


def _positive_quantity(args, key="quantity"):
    value = _decimal(args, key)
    if value <= 0:
        raise ValueError(f"'{key}' must be greater than zero.")
    return value


def _id(args, key):
    value = args.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"'{key}' must be a valid catalogue ID.")
    return value


def _food_item(item_id):
    try:
        return FoodItem.objects.get(pk=item_id)
    except FoodItem.DoesNotExist as exc:
        raise ValueError(f"Food item {item_id} does not exist.") from exc



def _recipe(recipe_id):
    try:
        return Recipe.objects.get(pk=recipe_id)
    except Recipe.DoesNotExist as exc:
        raise ValueError(f"Recipe {recipe_id} does not exist.") from exc


def _validate_recipe_ingredients(rows):
    if not isinstance(rows, list) or not rows or len(rows) > 30:
        raise ValueError("A recipe needs between 1 and 30 ingredients.")
    preview = []
    for row in rows:
        if not isinstance(row, dict) or set(row) - {"food_item_id", "quantity", "unit"}:
            raise ValueError("Each ingredient needs food_item_id, quantity and unit only.")
        item = _food_item(_id(row, "food_item_id"))
        quantity = _positive_quantity(row)
        unit = row.get("unit")
        if unit != item.nutrition_basis_unit:
            raise ValueError(f"Unit for {item} must be {item.nutrition_basis_unit}.")
        preview.append({"food_item_id": item.pk, "name": str(item), "quantity": str(quantity), "unit": unit})
    return preview


def validate_food_write_tool(name, args):
    if not isinstance(args, dict):
        raise ValueError("Tool arguments must be an object.")
    if name == "create_food_item":
        allowed = {"name", "item_type", "brand", "nutrition_basis_unit", "calories_per_100", "protein_per_100", "carbohydrates_per_100", "fat_per_100", "nutrition_source"}
        if set(args) - allowed:
            raise ValueError("Unexpected arguments for create_food_item.")
        _text(args, "name")
        if args.get("item_type") not in (FoodItem.INGREDIENT, FoodItem.PRODUCT):
            raise ValueError("item_type must be 'ingredient' or 'product'.")
        if args.get("nutrition_basis_unit") not in (FoodItem.GRAMS, FoodItem.MILLILITRES):
            raise ValueError("nutrition_basis_unit must be 'g' or 'ml'.")
        for key in ("calories_per_100", "protein_per_100", "carbohydrates_per_100", "fat_per_100"):
            _decimal(args, key, required=False)
        _text(args, "brand", required=False, maximum=120)
        _text(args, "nutrition_source", required=False, maximum=120)
        return {"name": _text(args, "name"), "brand": args.get("brand", "").strip(), "type": args["item_type"], "unit": args["nutrition_basis_unit"], "nutrition": {k: args.get(k) for k in ("calories_per_100", "protein_per_100", "carbohydrates_per_100", "fat_per_100")}}

    if name == "create_recipe":
        if set(args) - {"name", "instructions", "ingredients"}:
            raise ValueError("Unexpected arguments for create_recipe.")
        name_value = _text(args, "name")
        _text(args, "instructions", required=False, maximum=4000)
        ingredients = args.get("ingredients")
        if not isinstance(ingredients, list) or not ingredients or len(ingredients) > 30:
            raise ValueError("A recipe needs between 1 and 30 ingredients.")
        preview = []
        for row in ingredients:
            if not isinstance(row, dict) or set(row) - {"food_item_id", "quantity", "unit"}:
                raise ValueError("Each ingredient needs food_item_id, quantity and unit only.")
            item = _food_item(_id(row, "food_item_id"))
            quantity = _positive_quantity(row)
            unit = row.get("unit")
            if unit != item.nutrition_basis_unit:
                raise ValueError(f"Unit for {item} must be {item.nutrition_basis_unit}.")
            preview.append({"food_item_id": item.pk, "name": str(item), "quantity": str(quantity), "unit": unit})
        return {"name": name_value, "ingredients": preview}

    if name == "create_meal_prep_batch":
        if set(args) - {"name", "recipe_id", "yield_quantity", "yield_unit"}:
            raise ValueError("Unexpected arguments for create_meal_prep_batch.")
        recipe_id = _id(args, "recipe_id")
        try:
            recipe = Recipe.objects.prefetch_related("ingredients__food_item", "ingredients__price_observation").get(pk=recipe_id)
        except Recipe.DoesNotExist as exc:
            raise ValueError("That recipe does not exist.") from exc
        quantity = _positive_quantity(args, "yield_quantity")
        unit = args.get("yield_unit")
        if unit not in (FoodItem.GRAMS, FoodItem.MILLILITRES):
            raise ValueError("yield_unit must be 'g' or 'ml'.")
        ingredients = list(recipe.ingredients.all())
        if not ingredients:
            raise ValueError("The selected recipe has no ingredients.")
        return {"name": _text(args, "name"), "recipe_id": recipe.pk, "recipe_name": recipe.name, "yield_quantity": str(quantity), "yield_unit": unit, "ingredients": [{"name": str(row.food_item), "quantity": str(row.quantity), "unit": row.unit} for row in ingredients]}

    if name == "log_food_consumption":
        if set(args) - {"food_item_id", "quantity", "unit", "meal_category"}:
            raise ValueError("Unexpected arguments for log_food_consumption.")
        item = _food_item(_id(args, "food_item_id"))
        quantity = _positive_quantity(args)
        unit = args.get("unit")
        if unit != item.nutrition_basis_unit:
            raise ValueError(f"Unit for {item} must be {item.nutrition_basis_unit}.")
        category = args.get("meal_category", "")
        if category not in ("", "breakfast", "lunch", "dinner", "snack"):
            raise ValueError("meal_category must be breakfast, lunch, dinner, snack or blank.")
        return {"food_item_id": item.pk, "name": str(item), "quantity": str(quantity), "unit": unit, "meal_category": category or "unspecified"}

    if name == "log_meal_prep_portion":
        if set(args) - {"batch_id", "quantity", "unit", "meal_category"}:
            raise ValueError("Unexpected arguments for log_meal_prep_portion.")
        batch_id = _id(args, "batch_id")
        try:
            batch = MealPrepBatch.objects.get(pk=batch_id)
        except MealPrepBatch.DoesNotExist as exc:
            raise ValueError("That meal-prep batch does not exist.") from exc
        quantity = _positive_quantity(args)
        unit = args.get("unit")
        already_consumed = ConsumptionEntry.objects.filter(meal_prep_batch=batch).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
        remaining = Decimal(batch.yield_quantity) - already_consumed
        if unit != batch.yield_unit or quantity > remaining:
            raise ValueError(f"The portion must use the batch unit and cannot exceed the remaining {remaining} {batch.yield_unit}.")
        category = args.get("meal_category", "")
        if category not in ("", "breakfast", "lunch", "dinner", "snack"):
            raise ValueError("meal_category must be breakfast, lunch, dinner, snack or blank.")
        return {"batch_id": batch.pk, "name": batch.name, "quantity": str(quantity), "unit": unit, "meal_category": category or "unspecified"}

    if name == "update_food_item":
        allowed = {"food_item_id", "name", "item_type", "brand", "nutrition_basis_unit", "calories_per_100", "protein_per_100", "carbohydrates_per_100", "fat_per_100", "nutrition_source"}
        if set(args) - allowed or len(args) == 1:
            raise ValueError("Provide a food_item_id and at least one supported field to update.")
        item = _food_item(_id(args, "food_item_id"))
        changes = {}
        for key in ("name", "brand", "nutrition_source"):
            if key in args:
                maximum = 200 if key == "name" else 120
                changes[key] = _text(args, key, required=(key == "name"), maximum=maximum)
        if "item_type" in args:
            if args["item_type"] not in (FoodItem.INGREDIENT, FoodItem.PRODUCT):
                raise ValueError("item_type must be 'ingredient' or 'product'.")
            changes["item_type"] = args["item_type"]
        if "nutrition_basis_unit" in args:
            unit = args["nutrition_basis_unit"]
            if unit not in (FoodItem.GRAMS, FoodItem.MILLILITRES):
                raise ValueError("nutrition_basis_unit must be 'g' or 'ml'.")
            if unit != item.nutrition_basis_unit and any((
                item.price_observations.exists(), item.recipe_ingredients.exists(), item.purchases.exists(),
                item.consumption_entries.exists(), item.batch_ingredients.exists(),
            )):
                raise ValueError("The nutrition basis cannot be changed while this item is referenced by prices, recipes, purchases, consumption history or meal-prep batches.")
            changes["nutrition_basis_unit"] = unit
        for key in ("calories_per_100", "protein_per_100", "carbohydrates_per_100", "fat_per_100"):
            if key in args:
                changes[key] = _decimal(args, key, required=False)
        if not changes:
            raise ValueError("No fields were supplied to update.")
        before = {key: (str(getattr(item, key)) if getattr(item, key) is not None else None) for key in changes}
        after = {key: (str(value) if value is not None else None) for key, value in changes.items()}
        return {"food_item_id": item.pk, "current": before, "proposed": after, "name": str(item)}

    if name == "delete_food_item":
        if set(args) != {"food_item_id"}:
            raise ValueError("delete_food_item requires only food_item_id.")
        item = _food_item(_id(args, "food_item_id"))
        references = {
            "price_observations": item.price_observations.count(),
            "recipe_ingredients": item.recipe_ingredients.count(),
            "purchases": item.purchases.count(),
            "consumption_entries": item.consumption_entries.count(),
            "meal_prep_ingredients": item.batch_ingredients.count(),
        }
        if any(references.values()):
            raise ValueError("This catalogue item is linked to existing records. Deletion is blocked to protect price history, recipes, purchases, consumption history and meal-prep snapshots. Edit or remove those references first.")
        return {"food_item_id": item.pk, "name": str(item), "references": references, "warning": "This permanently deletes the catalogue item."}

    if name == "update_recipe":
        allowed = {"recipe_id", "name", "instructions", "ingredients"}
        if set(args) - allowed or len(args) == 1:
            raise ValueError("Provide a recipe_id and at least one supported field to update.")
        recipe = _recipe(_id(args, "recipe_id"))
        changes = {}
        if "name" in args:
            changes["name"] = _text(args, "name")
        if "instructions" in args:
            changes["instructions"] = _text(args, "instructions", required=False, maximum=4000)
        preview = {"recipe_id": recipe.pk, "current_name": recipe.name, "proposed": changes}
        if "ingredients" in args:
            preview["proposed_ingredients"] = _validate_recipe_ingredients(args["ingredients"])
            preview["existing_ingredient_count"] = recipe.ingredients.count()
        return preview

    if name == "delete_recipe":
        if set(args) != {"recipe_id"}:
            raise ValueError("delete_recipe requires only recipe_id.")
        recipe = _recipe(_id(args, "recipe_id"))
        batch_count = recipe.meal_prep_batches.count()
        if batch_count:
            raise ValueError("This recipe is linked to existing meal-prep batches. Deletion is blocked to preserve their recipe history.")
        return {"recipe_id": recipe.pk, "name": recipe.name, "ingredient_count": recipe.ingredients.count(), "warning": "This permanently deletes the recipe and its ingredient rows."}

    raise ValueError("That write function is not available.")


@transaction.atomic
def execute_food_write_tool(name, args):
    """Revalidate and execute a write operation after explicit user confirmation."""
    validate_food_write_tool(name, args)
    if name == "create_food_item":
        item = FoodItem(
            name=_text(args, "name"), item_type=args["item_type"], brand=args.get("brand", "").strip(),
            nutrition_basis_unit=args["nutrition_basis_unit"],
            calories_per_100=_decimal(args, "calories_per_100", required=False),
            protein_per_100=_decimal(args, "protein_per_100", required=False),
            carbohydrates_per_100=_decimal(args, "carbohydrates_per_100", required=False),
            fat_per_100=_decimal(args, "fat_per_100", required=False),
            nutrition_source=args.get("nutrition_source", "").strip(),
        )
        item.full_clean(); item.save()
        return {"created": "food_item", "id": item.pk, "name": str(item)}

    if name == "create_recipe":
        recipe = Recipe(name=_text(args, "name"), instructions=args.get("instructions", "").strip())
        recipe.full_clean(); recipe.save()
        for row in args["ingredients"]:
            item = _food_item(row["food_item_id"])
            ingredient = RecipeIngredient(recipe=recipe, food_item=item, quantity=_positive_quantity(row), unit=row["unit"])
            ingredient.full_clean(); ingredient.save()
        return {"created": "recipe", "id": recipe.pk, "name": recipe.name, "ingredient_count": recipe.ingredients.count()}

    if name == "create_meal_prep_batch":
        recipe = Recipe.objects.prefetch_related("ingredients__food_item", "ingredients__price_observation").get(pk=args["recipe_id"])
        ingredient_inputs = [BatchIngredientInput(food_item=row.food_item, quantity=row.quantity, unit=row.unit, price_observation=row.price_observation) for row in recipe.ingredients.all()]
        batch = create_meal_prep_batch(name=_text(args, "name"), recipe=recipe, yield_quantity=_positive_quantity(args, "yield_quantity"), yield_unit=args["yield_unit"], ingredients=ingredient_inputs)
        return {"created": "meal_prep_batch", "id": batch.pk, "name": batch.name, "yield_quantity": str(batch.yield_quantity), "yield_unit": batch.yield_unit}

    if name == "log_food_consumption":
        item = _food_item(args["food_item_id"])
        entry = create_consumption_entry(food_item=item, quantity=_positive_quantity(args), unit=args["unit"], meal_category=args.get("meal_category", ""))
        return {"created": "consumption_entry", "id": entry.pk, "food": entry.source_name, "quantity": str(entry.quantity), "unit": entry.unit}

    if name == "log_meal_prep_portion":
        batch = MealPrepBatch.objects.get(pk=args["batch_id"])
        entry = create_batch_consumption_entry(batch, consumed_quantity=_positive_quantity(args), unit=args["unit"], meal_category=args.get("meal_category", ""))
        return {"created": "consumption_entry", "id": entry.pk, "food": entry.source_name, "quantity": str(entry.quantity), "unit": entry.unit}

    if name == "update_food_item":
        item = _food_item(args["food_item_id"])
        for key, value in args.items():
            if key == "food_item_id":
                continue
            setattr(item, key, _decimal(args, key, required=False) if key in ("calories_per_100", "protein_per_100", "carbohydrates_per_100", "fat_per_100") else value.strip() if key in ("name", "brand", "nutrition_source") else value)
        item.full_clean(); item.save()
        return {"updated": "food_item", "id": item.pk, "name": str(item)}

    if name == "delete_food_item":
        item = _food_item(args["food_item_id"])
        item_name = str(item)
        item.delete()
        return {"deleted": "food_item", "id": args["food_item_id"], "name": item_name}

    if name == "update_recipe":
        recipe = _recipe(args["recipe_id"])
        if "name" in args:
            recipe.name = _text(args, "name")
        if "instructions" in args:
            recipe.instructions = _text(args, "instructions", required=False, maximum=4000)
        recipe.full_clean(); recipe.save()
        if "ingredients" in args:
            recipe.ingredients.all().delete()
            for row in args["ingredients"]:
                item = _food_item(row["food_item_id"])
                ingredient = RecipeIngredient(recipe=recipe, food_item=item, quantity=_positive_quantity(row), unit=row["unit"])
                ingredient.full_clean(); ingredient.save()
        return {"updated": "recipe", "id": recipe.pk, "name": recipe.name, "ingredient_count": recipe.ingredients.count()}

    if name == "delete_recipe":
        recipe = _recipe(args["recipe_id"])
        recipe_name = recipe.name
        recipe.delete()
        return {"deleted": "recipe", "id": args["recipe_id"], "name": recipe_name}

    raise ValueError("That write function is not available.")


FOOD_WRITE_TOOL_DEFINITIONS = [
    {"type": "function", "function": {"name": "create_food_item", "description": "Create a Food catalogue ingredient or product. Only use information the user supplied or explicitly approved; unknown nutrition values must be omitted, not guessed.", "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "item_type": {"type": "string", "enum": ["ingredient", "product"]}, "brand": {"type": "string"}, "nutrition_basis_unit": {"type": "string", "enum": ["g", "ml"]}, "calories_per_100": {"type": ["number", "null"]}, "protein_per_100": {"type": ["number", "null"]}, "carbohydrates_per_100": {"type": ["number", "null"]}, "fat_per_100": {"type": ["number", "null"]}, "nutrition_source": {"type": "string"}}, "required": ["name", "item_type", "nutrition_basis_unit"]}}},
    {"type": "function", "function": {"name": "create_recipe", "description": "Create a reusable Food recipe with existing catalogue ingredients and quantities.", "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "instructions": {"type": "string"}, "ingredients": {"type": "array", "items": {"type": "object", "properties": {"food_item_id": {"type": "integer"}, "quantity": {"type": "number"}, "unit": {"type": "string", "enum": ["g", "ml"]}}, "required": ["food_item_id", "quantity", "unit"]}}}, "required": ["name", "ingredients"]}}},
    {"type": "function", "function": {"name": "create_meal_prep_batch", "description": "Create a meal-prep batch from an existing recipe. yield_quantity is the total batch yield in yield_unit.", "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "recipe_id": {"type": "integer"}, "yield_quantity": {"type": "number"}, "yield_unit": {"type": "string", "enum": ["g", "ml"]}}, "required": ["name", "recipe_id", "yield_quantity", "yield_unit"]}}},
    {"type": "function", "function": {"name": "log_food_consumption", "description": "Log consumption of one existing catalogue item for now, using its saved nutrition snapshot.", "parameters": {"type": "object", "properties": {"food_item_id": {"type": "integer"}, "quantity": {"type": "number"}, "unit": {"type": "string", "enum": ["g", "ml"]}, "meal_category": {"type": "string", "enum": ["breakfast", "lunch", "dinner", "snack", ""]}}, "required": ["food_item_id", "quantity", "unit"]}}},
    {"type": "function", "function": {"name": "log_meal_prep_portion", "description": "Log one consumed portion from an existing meal-prep batch, using the saved batch snapshots.", "parameters": {"type": "object", "properties": {"batch_id": {"type": "integer"}, "quantity": {"type": "number"}, "unit": {"type": "string", "enum": ["g", "ml"]}, "meal_category": {"type": "string", "enum": ["breakfast", "lunch", "dinner", "snack", ""]}}, "required": ["batch_id", "quantity", "unit"]}}},
    {"type": "function", "function": {"name": "update_food_item", "description": "Edit an existing catalogue item. Supply only fields to change. Keep unknown nutrition values null; never guess. Changing its basis unit is blocked when referenced.", "parameters": {"type": "object", "properties": {"food_item_id": {"type": "integer"}, "name": {"type": "string"}, "item_type": {"type": "string", "enum": ["ingredient", "product"]}, "brand": {"type": "string"}, "nutrition_basis_unit": {"type": "string", "enum": ["g", "ml"]}, "calories_per_100": {"type": ["number", "null"]}, "protein_per_100": {"type": ["number", "null"]}, "carbohydrates_per_100": {"type": ["number", "null"]}, "fat_per_100": {"type": ["number", "null"]}, "nutrition_source": {"type": "string"}}, "required": ["food_item_id"]}}},
    {"type": "function", "function": {"name": "delete_food_item", "description": "Permanently delete an unused catalogue item. Refuse deletion if it has any price, recipe, purchase, consumption or meal-prep references.", "parameters": {"type": "object", "properties": {"food_item_id": {"type": "integer"}}, "required": ["food_item_id"]}}},
    {"type": "function", "function": {"name": "update_recipe", "description": "Edit a reusable recipe. You may change name/instructions and optionally replace the complete ingredient list using existing Food item IDs and quantities.", "parameters": {"type": "object", "properties": {"recipe_id": {"type": "integer"}, "name": {"type": "string"}, "instructions": {"type": "string"}, "ingredients": {"type": "array", "items": {"type": "object", "properties": {"food_item_id": {"type": "integer"}, "quantity": {"type": "number"}, "unit": {"type": "string", "enum": ["g", "ml"]}}, "required": ["food_item_id", "quantity", "unit"]}}}, "required": ["recipe_id"]}}},
    {"type": "function", "function": {"name": "delete_recipe", "description": "Permanently delete a recipe only when no meal-prep batches are linked to it.", "parameters": {"type": "object", "properties": {"recipe_id": {"type": "integer"}}, "required": ["recipe_id"]}}},
]

FOOD_WRITE_TOOL_NAMES = {item["function"]["name"] for item in FOOD_WRITE_TOOL_DEFINITIONS}
