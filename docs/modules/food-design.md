# Food Module Design

> **Document status:** Living module specification
> **Version:** 0.6.0
> **Date:** 2026-10-25
> **Design status:** Approved starting point with accepted recipe/batch data-foundation decisions
> **Implementation status:** Food tracking phases 1-4 and recipe/batch data foundation implemented; recipe/batch UI and consumption integration, targets, and AI remain deferred
>
> This document records the agreed starting design from the Food module discovery interview. It should be updated as implementation and real-world use expose better decisions. It does not override the wider guidance in [docs/project-design.md](../project-design.md).

## 1. Purpose and scope

The Food module will support personal food and drink tracking, calorie and macronutrient tracking, recipes, meal preparation, ingredient and product prices, and nutritional cost analysis.

The module should support both:

- individual foods and drinks consumed throughout the day;
- homemade meals prepared in batches and consumed as portions.

The core application must remain useful without AI. Future AI interaction will use validated Food domain services rather than direct database access.

## 2. Design status and decision categories

This specification uses the following categories:

- **Confirmed requirement:** Agreed behaviour or constraint for the current design.
- **Proposed technical decision:** Recommended implementation direction that may change after experimentation.
- **Future idea:** Deliberately outside the initial implementation scope.
- **Unresolved question:** A decision that should not be silently assumed during implementation.
- **Implemented:** Exists in working code and has been tested.

The design was approved as a starting point, not as an irreversible schema or product contract.

## 3. Confirmed requirements

### 3.1 Consumption tracking

- Use one unified consumption log for every food or drink consumed.
- A consumption entry may refer to an ingredient, branded product, recipe portion, meal-prep portion, or quick-added item.
- Support measured quantities and practical estimates or serving presets.
- Store an actual timestamp and derive the reporting date using the configured local timezone.
- Allow an explicit date override for corrections.
- Support optional meal context such as breakfast, lunch, dinner, or snack.
- Provide fast search, recent-item, and favourite-item logging workflows.
- Preserve historical nutrition, cost, source, and calculation-basis snapshots on consumption entries.
- Catalog edits must not silently rewrite historical totals.
- Allow explicit correction or recalculation of an individual historical entry.

### 3.2 Nutrition

- Track calories, protein, carbohydrates, and fats.
- Use per 100 g or per 100 ml as the canonical basis where applicable.
- Support serving, item, package, and other conversions where needed.
- Allow an entry with unknown nutrition values, but visibly flag incomplete totals.
- Unknown nutrition must not silently be treated as zero.
- Support optional personal daily calorie and macronutrient targets.
- Daily tracking must remain useful when no targets are configured.

### 3.3 Food catalog

- Keep generic ingredients and branded products as distinct but connectable concepts.
- An ingredient represents a reusable food type such as rice or chicken.
- A product represents a specific brand/package with label nutrition and purchase details.
- Allow a quick-add food or drink that can optionally be saved as a reusable record.
- Retain nutrition and price provenance, including manual entry, label, estimate, dataset, or later import sources.

### 3.4 Costs and prices

- Derive consumption cost from product or ingredient prices and consumed quantity when possible.
- Allow a manual estimated cost or an explicitly unknown cost when a derived value is unavailable.
- Keep actual paid price separate from normal or reference price.
- Preserve discounted price observations rather than overwriting normal prices.
- Support cost per serving, daily and weekly food expenditure, cost per 100 g of protein, and calories/protein per currency unit.
- Incomplete cost data must be visible and must not silently become zero.

### 3.5 Recipes and meal preparation

- Keep a reusable `Recipe` separate from each actual `MealPrepBatch`.
- Recipes may reference existing `FoodItem` records, which continue to represent both generic ingredients and specific products.
- Recipe estimates are dynamic and use current FoodItem nutrition and the selected current `PriceObservation` values.
- A batch records a stable name, optional source Recipe, cooking date, actual ingredient rows, and positive yield in grams or millilitres.
- RecipeIngredient rows cascade with their Recipe, protect their FoodItem, and set a deleted optional PriceObservation reference to null. A batch's optional Recipe reference and its BatchIngredient catalogue references use `SET_NULL`; deleting a batch cascades to its owned ingredient rows.
- Each batch ingredient stores its actual quantity and historical name, nutrition contribution, allocated cost, currency, and provenance. Nullable FoodItem and PriceObservation references are provenance only; deleting those catalogue records must not erase snapshots.
- Batch totals are calculated only from stored `BatchIngredient` snapshots. Later FoodItem, PriceObservation, or Recipe edits must not silently change a batch.
- Recipe and batch ingredient quantities and batch yield must be positive. Ingredient units must match the FoodItem nutrition basis, and selected prices must belong to that FoodItem. Known costs in one batch must use one currency; unlike currencies are not added.
- Missing nutrient and cost values remain unknown and make the corresponding total incomplete rather than being treated as known zero.
- Recipe or batch corrections to nutrition/cost are not arbitrary overrides in the first implementation; correct actual ingredient quantities or selected prices instead.
- `ConsumptionEntry` remains the unified consumption log, but batch-backed entries and portions are not implemented yet.
- Count-based portions and servings, unit conversion, inventory, and purchase accounting are deferred.

The current batch-creation service accepts actual ingredient inputs and an optional Recipe reference. It does not yet copy recipe rows automatically or expose a user workflow.

### 3.6 Data entry and scope

- Manual entry is the initial data-entry method.
- CSV imports, public nutrition datasets, receipt processing, and label OCR are not MVP requirements.
- The design should retain provenance so those sources can be added later.
- The initial implementation should remain a normal Django module using the existing SQLite development database.
- No separate service, queue, AI runtime, MCP server, or external database is required for the Food MVP.

## 4. User workflows

### 4.1 Daily consumption

1. Open the Food Today view.
2. Search for a recent, favourite, or catalogued food/product.
3. Enter a measured quantity or practical estimate.
4. Optionally select a meal context and adjust the date/time.
5. Save the consumption entry.
6. Review daily calories, macros, cost, targets, and any incomplete-data warnings.

### 4.2 Quick-add consumption

1. Start a consumption entry when the item is not in the catalog.
2. Enter the available name, quantity, nutrition values, and cost if known.
3. Save the entry with explicit provenance and unknown fields where necessary.
4. Optionally promote the item into a reusable ingredient or product.

### 4.3 Catalog management

1. Create or edit a generic ingredient or branded product.
2. Add nutrition values with their basis and source.
3. Add one or more price observations, including store, date, actual price, and normal/reference price where known.
4. Reuse the record in future consumption, recipes, or meal preparation.

### 4.4 Recipe and meal preparation

**Designed workflow; not yet available through the application UI.** The model and calculation foundation exists, but forms, views, templates, and batch-backed consumption are deferred.

1. Create a reusable recipe with ingredients, quantities, units, and instructions.
2. Start a meal-prep batch from the recipe or create one directly.
3. Record actual ingredients and quantities used.
4. Record actual yield or portions produced.
5. Review calculated cost and nutrition.
6. Create portions that can be referenced by consumption entries.

### 4.5 Analysis

- View today’s totals and target comparison.
- Review historical consumption.
- Review daily and weekly food spending.
- Compare products, ingredients, recipes, or prepared meals using cost and nutrition metrics.
- Identify incomplete or estimated values before relying on a report.

## 5. Candidate data model

These are candidate concepts, not an instruction to implement every model immediately.

| Concept | Purpose |
|---|---|
| `Ingredient` | Generic food concept used in recipes and tracking. |
| `Product` | Brand/package-specific food with label, pack, and purchase details. |
| `NutritionProfile` | Calories, protein, carbohydrates, fats, basis, and provenance. |
| `NutritionSource` | Source classification such as label, manual entry, estimate, dataset, or import. |
| `PriceObservation` | Actual/reference price, currency, store, date, and product/ingredient relationship. |
| `ConsumptionEntry` | What was consumed, quantity, unit, timestamp, context, and snapshots. |
| `DailyTarget` | Optional calorie and macronutrient targets. |
| `Recipe` | Implemented reusable preparation name and instructions; serving counts are deferred. |
| `RecipeIngredient` | Quantity/unit relationship between a recipe and an ingredient or product. |
| `MealPrepBatch` | Implemented cooking-event record with stable name, optional Recipe reference, cooked date, and yield. |
| `BatchIngredient` | Implemented actual batch input with historical nutrition, cost, currency, name, and provenance snapshots. |
| `Portion` | Deferred concept; batch yield is currently weight/volume based, with no count-based portion model. |

Relationships should preserve module ownership and avoid direct access from future AI tools to ORM tables. Cross-module use should occur through application services or stable read models.

## 6. Business rules and calculations

### 6.1 Consumption nutrition

Calculate calories and macronutrients from the source nutrition basis and the consumed quantity. Preserve the values used at logging time so later catalog edits do not change history.

### 6.2 Recipe and batch nutrition

Implemented calculation behavior:

- Recipe estimates sum nutrient contributions and allocated costs from current FoodItem and PriceObservation values. The estimate can therefore change when catalogue values change.
- Recipe price selection follows the existing policy: no observation leaves cost unknown, one is selected automatically, and multiple observations require an explicit selection.
- Batch creation calculates actual ingredient contributions once and stores them on `BatchIngredient`. Batch totals sum those snapshots only; they do not reread current catalogue or recipe data.
- Batch yield is stored in `g` or `ml`; division by yield for per-unit values and batch consumption are not yet implemented.
- Nutrient and cost completeness are tracked independently. Known subtotals may be returned, but an incomplete flag means the subtotal is not a complete total.
- Known batch costs must share one currency. Recipe estimates with mixed currencies do not produce a combined monetary total.
- Model validation is explicitly invoked by the batch service; Django `save()` does not call `full_clean()` automatically. Batch and ingredient snapshot writes are transactional.

Arbitrary manual total overrides, cooking-loss, water-absorption, and nutrient-retention models are deferred.

### 6.3 Cost analysis

Initial metrics:

- cost per serving;
- daily food spend;
- weekly food spend;
- cost per 100 g of protein;
- calories per currency unit;
- protein per currency unit.

The distinction between grocery purchase expenditure and the allocated cost of food consumed remains an unresolved design question and must be settled before implementing comprehensive expenditure reporting.

### 6.4 Incomplete data

Entries may be saved with unknown nutrition or cost. Reports should calculate known values, identify incomplete totals, and preserve the missing-data state. Estimates must be labelled as estimates.

## 7. UI requirements

### MVP screens

- **Today:** current-day entries, calorie/macro/cost totals, optional targets, and incomplete-data warnings.
- **Quick logger:** search, recent items, favourites, quantity/unit entry, optional meal context, and quick-add.
- **History:** consumption records, date filtering, correction, and basic trends.
- **Catalog:** ingredients, products, nutrition profiles, price observations, and provenance.

Recipe and meal-prep screens and batch-backed consumption are the next user-facing vertical slice. They are not part of the implemented data foundation.

The UI should be mobile-friendly and should support common actions through normal forms and buttons without requiring chat.

### 7.1 Phase 4 navigation and guidance decisions

- Food Today is the Food module landing page at `/food/`.
- The central dashboard opens Food Today through the named `food_today` route.
- Food-specific navigation provides Today, Log Food, Food Catalogue, and Consumption History on every Food page.
- The global navigation remains focused on the Homelab platform and Food module entry point rather than exposing every Food page.
- Food guidance distinguishes generic ingredients from specific products. Products include branded supermarket items, workplace canteen meals, restaurant meals, takeaways, and ready meals.
- Product nutrition and cost may be estimated, with unknown values preserved and labelled rather than converted to zero.
- The current grams/millilitres restriction remains intentional. Complete meals with unknown weight require an estimate; serving, count, density, and portion conversions remain future work.
- Estimated consumed-food cost is explained separately from actual grocery expenditure.

## 8. Future AI integration

AI is excluded from the initial Food release, but the domain should be designed for future read and write tools.

Future tools may include:

- `food.log_consumption`
- `food.search_history`
- `food.get_daily_summary`
- `food.compare_costs`
- `food.create_recipe`
- `food.update_recipe`
- `food.create_meal_prep_batch`
- `food.update_product_price`
- `food.generate_shopping_list`
- `food.suggest_meal_plan`

AI tools must call validated, reusable application services shared with normal UI workflows. They must not issue SQL or access the database directly.

Suggested policy:

- read operations may be automatic;
- write operations produce a preview and require confirmation;
- bulk, destructive, or historically impactful changes require stronger safeguards;
- permissions, validation, idempotency, auditability, and provenance should be handled at the tool/service boundary.

## 9. MVP scope

The first usable Food release should include:

- food/product catalog;
- quick-add food entry;
- search, recent, and favourite items;
- measured and estimated quantities;
- optional meal context;
- local-date daily tracking;
- daily calorie, macro, and cost summaries;
- consumption history;
- optional daily calorie and macro targets;
- core cost metrics;
- nutrition and price provenance;
- focused calculation and workflow tests.

The MVP does not include live AI integration, OCR, external nutrition APIs, CSV imports, advanced cooking transformations, shopping lists, or full meal planning.

## 10. Future backlog

- Recipe and batch forms, views, templates, and user workflows.
- Copying a recipe plan into editable actual batch ingredient inputs.
- Batch-backed consumption entries and yield-based nutrition/cost scaling.
- Count-based portions, servings, and unit conversions.
- Shopping lists.
- CSV imports.
- Receipt and nutrition-label OCR.
- Public nutrition dataset integrations.
- Detailed cooking transformations.
- More trends and recommendations.
- Meal planning.
- AI-assisted queries, summaries, logging, recipe changes, price updates, and batch creation.

## 11. Edge cases and validation

- Unknown calories, macros, or costs.
- Estimated restaurant meals.
- Products with changing package sizes.
- Discounted versus normal prices.
- Recipe changes after historical batches exist.
- Variable batch yields.
- Leftovers and partial portions.
- Consumption near midnight.
- Duplicate catalog entries.
- Unit conversion errors.
- Manual corrections to historical logs.
- Future AI requests that would create bulk, destructive, or historically impactful changes.

## 12. Unresolved questions

These questions must remain visible rather than being silently resolved during implementation:

1. How should grocery purchase expenditure differ from the allocated cost of consumed food?
2. How should serving sizes, food density, quantities, and unit conversions be represented and validated?
3. Should daily targets be fixed values or vary by day?
4. How should alcohol, supplements, and restaurant meals be represented differently?
5. Should currency conversion be supported later?
6. Which historical reports and charts are most useful beyond daily totals?

Resolved for the data foundation: recipes may use either FoodItem type; batch yield is `g` or `ml`; recipe estimates are dynamic; batch ingredient contributions are snapshots; and mixed known batch-cost currencies are rejected. Count-based portions remain deferred.

## 13. Proposed development milestones

- [x] Define the minimum Food models and calculation value objects for Phase 1.
- [x] Implement the initial FoodItem, PriceObservation, and ConsumptionEntry models with direct nutrition fields and historical snapshots.
- [x] Implement reusable nutrition scaling, allocated cost, and daily aggregation services.
- [x] Implement Phase 2 catalogue management, search, FoodItem forms, and price history.
- [x] Implement consumption entries, snapshot application services, and daily summaries.
- [x] Add quick logging, history, and estimated consumed-cost metrics. Daily targets remain deferred.
- [x] Add Recipe, RecipeIngredient, MealPrepBatch, and BatchIngredient data models and migration.
- [x] Add dynamic recipe estimates, snapshot-based batch totals, and transactional batch creation.
- [x] Add focused model, calculation, snapshot-stability, currency, and service tests.
- [ ] Add recipe and meal-prep forms, views, templates, and user workflows.
- [ ] Add batch-backed ConsumptionEntry logging and yield-based scaling.
- [ ] Expose validated domain services for future AI tools.
- [ ] Add AI tools only after deterministic workflows are reliable.

Milestone ordering should be revisited if the meal-preparation prioritisation question is answered differently.

## 14. Acceptance criteria

- [x] A user can create or edit a reusable FoodItem catalogue record.
- [ ] A user can quick-add an uncatalogued food directly while logging consumption.
- [x] A user can log a measured catalogue consumption and view daily nutrition/cost summaries.
- [x] Unknown consumption and estimate values are preserved and represented by completeness state.
- [x] Existing ConsumptionEntry snapshots remain stable after catalogue edits.
- [ ] Optional targets can be compared with daily intake.
- [ ] Comprehensive cost analysis and purchase accounting are available.
- [ ] All primary workflows have been manually verified on desktop and mobile layouts.
- [x] Recipe estimates use current catalogue data and expose independent completeness results.
- [x] MealPrepBatch ingredient contributions are snapshotted and batch totals do not reread catalogue or Recipe data.
- [x] Positive quantities/yield, unit matching, price ownership, deletion behavior, and single-currency batch costs are validated and tested.
- [ ] Recipe and batch workflows are available through the UI, including batch-backed consumption.
- [x] Domain calculations are tested independently of AI.
- [ ] Future AI tools can call shared services without direct database access.

## 15. Current implementation status

**Implemented:** Phases 1-4 provide `FoodItem`, `PriceObservation`, and `ConsumptionEntry`, catalogue management, consumption logging, historical snapshots, Today/History, navigation, and focused automated tests. The recipe/batch data foundation adds `Recipe`, `RecipeIngredient`, `MealPrepBatch`, and `BatchIngredient`, dynamic recipe estimates, snapshot-based batch totals, and transactional batch creation. Its migration is generated; the development database has not been migrated as part of that implementation. The configured reporting timezone is `Europe/Dublin`.

**Planned or deferred:** Recipe and batch forms/views/templates, copying recipe rows into actual batch inputs, batch-backed ConsumptionEntry logging, yield-based scaling for consumed batch quantities, daily targets, advanced cost analysis, and AI tool integrations are not implemented. Arbitrary manual nutrition/cost overrides, count-based portions and servings, conversions, inventory, purchase accounting, and external data sources remain deferred.

This status should be updated as milestones are completed. Planned requirements must not be described as implemented until they exist in working code and have been tested.

## 16. Revision history

| Version | Date | Change |
|---|---|---|
| 0.1.0 | 2026-10-11 | Recorded the approved starting design from the Food module discovery interview. |
| 0.2.0 | 2026-10-11 | Recorded implementation of Phase 1 models, migration, calculation services, Europe/Dublin timezone, and automated tests. |
| 0.3.0 | 2026-10-11 | Recorded Phase 2 catalogue management, search, forms, price history, and integration tests. |
| 0.4.0 | 2026-10-11 | Recorded Phase 3 consumption services, snapshot creation/recalculation, Today/history pages, deletion, timezone aggregation, and tests. |
| 0.5.0 | 2026-10-11 | Recorded Phase 4 navigation, user guidance, outside-meal terminology, responsive UI improvements, and verification. |
| 0.6.0 | 2026-10-25 | Recorded the recipe/meal-prep data foundation, dynamic recipe estimates, historical batch snapshots, validation, and deferred UI/consumption workflows. |
