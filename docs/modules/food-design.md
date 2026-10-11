# Food Module Design

> **Document status:** Living module specification
> **Version:** 0.1.0
> **Date:** 2026-10-11
> **Design status:** Approved starting point; implementation not started
> **Implementation status:** Phases 1-3 implemented; recipes, meal preparation, targets, and AI remain deferred
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
- A batch records the cooking date, actual quantities, actual yield, total cost, calculated nutrition, and portions.
- Consumption entries may reference portions from a specific batch.
- Recipe and batch calculations should initially use additive ingredient nutrition and cost.
- Scale results using actual batch yield or portion count.
- Allow manual correction when calculated values do not represent reality.

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
| `Recipe` | Reusable preparation and expected servings. |
| `RecipeIngredient` | Quantity/unit relationship between a recipe and an ingredient or product. |
| `MealPrepBatch` | Actual cooking session, inputs, yield, cost, nutrition, and date. |
| `Portion` | Consumable portion derived from a meal-prep batch. |

Relationships should preserve module ownership and avoid direct access from future AI tools to ORM tables. Cross-module use should occur through application services or stable read models.

## 6. Business rules and calculations

### 6.1 Consumption nutrition

Calculate calories and macronutrients from the source nutrition basis and the consumed quantity. Preserve the values used at logging time so later catalog edits do not change history.

### 6.2 Recipe and batch nutrition

For the initial model:

- sum ingredient calories, protein, carbohydrates, fats, and costs;
- scale quantities using explicit units and conversions;
- divide batch totals by actual yield or portion count;
- allow manual correction when additive calculations are insufficient.

Detailed cooking-loss, water-absorption, and nutrient-retention models are deferred.

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

Recipes and meal-prep screens are the next vertical slice unless the open prioritisation question changes that order.

The UI should be mobile-friendly and should support common actions through normal forms and buttons without requiring chat.

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

- Recipes and recipe scaling.
- Meal-prep batches and portions.
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

1. Should basic meal preparation be prioritised earlier than the current daily-tracking-first MVP sequence?
2. How should grocery purchase expenditure differ from the allocated cost of consumed food?
3. How should serving sizes, food density, quantities, and unit conversions be represented and validated?
4. Should daily targets be fixed values or vary by day?
5. Should meal-prep portions be weight-based, count-based, or support both?
6. Should recipe ingredients reference generic ingredients, products, or either?
7. How should alcohol, supplements, and restaurant meals be represented?
8. Should currency conversion be supported later?
9. Which historical reports and charts are most useful beyond daily totals?

## 13. Proposed development milestones

- [x] Define the minimum Food models and calculation value objects for Phase 1.
- [x] Implement the initial FoodItem, PriceObservation, and ConsumptionEntry models with direct nutrition fields and historical snapshots.
- [x] Implement reusable nutrition scaling, allocated cost, and daily aggregation services.
- [x] Implement Phase 2 catalogue management, search, FoodItem forms, and price history.
- [x] Implement consumption entries, snapshot application services, and daily summaries.
- [x] Add quick logging, history, and estimated consumed-cost metrics. Daily targets remain deferred.
- [ ] Add recipe and meal-prep batch workflows.
- [ ] Add focused calculation and workflow tests.
- [ ] Expose validated domain services for future AI tools.
- [ ] Add AI tools only after deterministic workflows are reliable.

Milestone ordering should be revisited if the meal-preparation prioritisation question is answered differently.

## 14. Acceptance criteria

- [ ] A user can create or quick-add a food/product.
- [ ] A user can log a measured or estimated consumption.
- [ ] Daily calories, protein, carbohydrates, fats, and cost are calculated.
- [ ] Unknown values are clearly flagged.
- [ ] Historical entries remain stable after catalog edits.
- [ ] Optional targets can be compared with daily intake.
- [ ] Core cost metrics are available.
- [ ] The primary workflows work on desktop and mobile layouts.
- [ ] Domain calculations are tested independently of AI.
- [ ] Future AI tools can call shared services without direct database access.

## 15. Current implementation status

**Implemented:** Phase 1 contains `FoodItem`, `PriceObservation`, and `ConsumptionEntry` models, the initial Food migration, reusable nutrition/cost/daily aggregation services, and focused automated tests. Phase 2 adds catalogue listing/search, FoodItem create/edit forms, nutrition validation, price observation create/edit forms, price history, and integration tests. Phase 3 adds application services for consumption creation, metadata-only updates, explicit recalculation, and daily summaries, plus logging, Today, history, correction, deletion, and integration tests. The configured reporting timezone is `Europe/Dublin`.

**Planned:** Daily targets, recipes, meal-prep workflows, advanced cost analysis, and AI tool integrations remain planned. Serving/density conversions and external data sources are also deferred.

This status should be updated as milestones are completed. Planned requirements must not be described as implemented until they exist in working code and have been tested.

## 16. Revision history

| Version | Date | Change |
|---|---|---|
| 0.1.0 | 2026-10-11 | Recorded the approved starting design from the Food module discovery interview. |
| 0.2.0 | 2026-10-11 | Recorded implementation of Phase 1 models, migration, calculation services, Europe/Dublin timezone, and automated tests. |
| 0.3.0 | 2026-10-11 | Recorded Phase 2 catalogue management, search, forms, price history, and integration tests. |
| 0.4.0 | 2026-10-11 | Recorded Phase 3 consumption services, snapshot creation/recalculation, Today/history pages, deletion, timezone aggregation, and tests. |
