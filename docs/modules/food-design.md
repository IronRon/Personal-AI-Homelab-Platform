# Food Module Design

> **Document status:** Living module specification
> **Version:** 1.0.0
> **Date:** 2026-10-25
> **Design status:** Approved starting point with accepted recipe/batch data-foundation decisions
> **Implementation status:** Food tracking phases 1-4, recipe/batch data foundation and UI, batch-backed consumption, and simple Food Purchase/Cost History implemented; accounting, inventory, quick-add, targets, and AI remain deferred
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

- `PriceObservation` is catalogue price data for estimating allocated consumption cost; it does not prove that a purchase occurred.
- `FoodPurchase` records actual money spent with a description, timestamp, amount, currency, and optional FoodItem, quantity/unit, and shop/source.
- Purchase spending is separate from estimated consumption cost. Recording a purchase does not create a `ConsumptionEntry`, and consumption does not create a purchase.
- A MealPrepBatch shows an estimated cost from stored ingredient snapshots; creating or consuming a batch does not add a FoodPurchase.
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
- `ConsumptionEntry` is the unified log for FoodItem and MealPrepBatch sources. New entries require exactly one source through model/service validation; database constraints reject both sources being set but do not independently reject neither source. A batch-backed entry cannot reference a PriceObservation.
- Batch consumption records an amount no greater than the batch yield and scales saved batch ingredient snapshots by amount/yield. Missing nutrient and cost snapshots remain unknown; a known cost retains its currency, and unlike currencies are never combined.
- The nullable batch foreign key uses `SET_NULL`. Deleting a batch preserves the entry's source name and nutrition/cost snapshots. Such entries remain recognized as batch-backed and cannot be recalculated from catalogue values.
- Count-based portions and servings, unit conversion, inventory, and purchase accounting are deferred.

The Meal Prep Batch UI is implemented: users can start from Recipe detail or create directly, select a Recipe, explicitly load its planned ingredients, and edit actual ingredient rows before saving. Loading, adding, and removing rows are server-rendered POST round-trips and do not persist a batch. Existing PriceObservation selection rules apply. Final creation delegates snapshot creation to the transactional `create_meal_prep_batch()` service; read-only detail calculates totals from stored snapshots. Batch detail also links to a consumption form; successful creation redirects to the local-date Food Today view. Each logged amount is checked against the full yield, but cumulative consumption is not capped and remaining availability is not tracked. Batch editing/recalculation, receipt grouping/imports, accounting/budgets, quick-add meals, inventory/availability, portions/conversions, AI/API integration, and final MVP polish remain deferred.

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

**Recipe, Meal Prep, and batch-consumption workflows are implemented.** Recipe list/create/edit/detail and planned ingredient management are available. Meal Prep provides a batch list, direct creation or creation from the Recipe detail action, explicit Recipe ingredient loading, editable actual ingredient rows, and read-only historical detail. Intermediate add/remove/load actions do not save a batch; final creation uses the transactional service. From batch detail, a user can log an amount consumed with time and optional meal category; the unified Food log stores scaled snapshots from the batch.

1. Open Recipes and create a reusable plan with a name and optional instructions.
2. Add or edit planned FoodItems and quantities, then review the current completeness-aware nutrition and cost estimate.

The Meal Prep workflow is available:

1. Start from a Recipe or create a batch directly.
2. Load planned ingredients when useful, then adjust actual FoodItems, quantities, units, and existing price observations.
3. Add/remove rows through server-rendered POST actions, select existing PriceObservations, and record cooked date/time and final yield.
4. Create the batch through `create_meal_prep_batch()`, then review stored ingredient snapshots and totals calculated from those snapshots on read-only detail.

Batch editing/deletion/recalculation, basic purchase history, quick-add meals/foods, cumulative batch availability/inventory, portions/count units/conversions, and AI/API integration remain deferred. Full MVP polish and desktop/mobile review are still outstanding.

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
| `FoodPurchase` | Implemented simple record of actual Food spending, separate from price observations and consumption snapshots. |
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
- Batch yield is stored in `g` or `ml`; batch consumption scales historical batch totals by consumed quantity divided by yield. Per-unit batch totals and portion/count conversions are not implemented.
- Nutrient and cost completeness are tracked independently. Known subtotals may be returned, but an incomplete flag means the subtotal is not a complete total.
- Known batch costs must share one currency. Recipe estimates with mixed currencies do not produce a combined monetary total.
- Incomplete batch snapshots remain unknown when scaled into a consumption entry. Daily cost aggregation groups by currency rather than combining unlike currencies.
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

Food purchase spending and estimated consumption cost are separate measures. Today displays both independently by currency; Cost History labels purchases, Meal Prep estimates, ordinary consumption, and batch consumption separately. This is Food-specific context, not accounting: purchases are not grouped into receipts, reconciled, or tied to inventory.

### 6.4 Incomplete data

Entries may be saved with unknown nutrition or cost. Reports should calculate known values, identify incomplete totals, and preserve the missing-data state. Estimates must be labelled as estimates.

## 7. UI requirements

### MVP screens

- **Today:** current-day entries, calorie/macro/cost totals, optional targets, and incomplete-data warnings.
- **Quick logger:** search, recent items, favourites, quantity/unit entry, optional meal context, and quick-add.
- **History:** consumption records, date filtering, correction, and basic trends.
- **Catalog:** ingredients, products, nutrition profiles, price observations, and provenance.
- **Cost History:** actual purchases alongside separately labelled Meal Prep estimates and consumption-cost events for a selected local date.

Recipe list/create/edit/detail and ingredient management screens are implemented. Meal Prep Batch list/create/read-only detail and batch-backed consumption screens are implemented. Full desktop/mobile review and remaining MVP polish are outstanding.

The UI should be mobile-friendly and should support common actions through normal forms and buttons without requiring chat.

### 7.1 Phase 4 navigation and guidance decisions

- Food Today is the Food module landing page at `/food/`.
- The central dashboard opens Food Today through the named `food_today` route.
- Food-specific navigation provides Today, Log Food, Food Catalogue, and Consumption History on every Food page.
- Food navigation also provides Cost History. Today shows actual purchased spend separately from estimated consumed cost, grouped by currency.
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

- Receipt grouping/imports, accounting/budgets, and purchase-to-inventory tracking.
- Quick-add meals/foods and portions/count-unit conversions.
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

1. How should serving sizes, food density, quantities, and unit conversions be represented and validated?
2. Should daily targets be fixed values or vary by day?
3. How should alcohol, supplements, and restaurant meals be represented differently?
4. Should currency conversion be supported later?
5. Which historical reports and charts are most useful beyond daily totals?

Resolved: actual FoodPurchase spending is separate from PriceObservation catalogue prices and estimated ConsumptionEntry costs. Meal Prep cost and later batch consumption are estimated events, never purchases; daily totals remain separate by currency with no conversion or receipt accounting. Recipes may use either FoodItem type; batch yield is `g` or `ml`; recipe estimates are dynamic; batch ingredient contributions are snapshots; and mixed known batch-cost currencies are rejected. Count-based portions remain deferred.

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
- [x] Add Recipe list/create/edit/detail UI and planned ingredient create/edit/remove workflows.
- [x] Show current Recipe estimates with independent nutrition/cost completeness and safe invalid-data feedback.
- [x] Add Meal Prep Batch list, create, and read-only detail workflows, including editable Recipe-prefilled actual ingredient inputs.
- [x] Add batch-backed ConsumptionEntry logging and yield-based scaling from stored snapshots.
- [x] Add simple actual FoodPurchase records, Cost History, and separate per-currency Today purchase totals.
- [ ] Expose validated domain services for future AI tools.
- [ ] Add AI tools only after deterministic workflows are reliable.

The next Food work is MVP polish and prioritized follow-ons such as quick-add meals, cumulative batch availability, and full desktop/mobile review. Batch editing, deletion, and recalculation remain out of scope.

## 14. Acceptance criteria

- [x] A user can create or edit a reusable FoodItem catalogue record.
- [ ] A user can quick-add an uncatalogued food directly while logging consumption.
- [x] A user can log a measured catalogue consumption and view daily nutrition/cost summaries.
- [x] Unknown consumption and estimate values are preserved and represented by completeness state.
- [x] Existing ConsumptionEntry snapshots remain stable after catalogue edits.
- [x] Recipe UI supports listing, create/edit/detail, planned ingredient management, and completeness-aware estimates.
- [ ] Optional targets can be compared with daily intake.
- [ ] Comprehensive cost analysis and purchase accounting are available.
- [ ] All primary workflows have been manually verified on desktop and mobile layouts.
- [x] Recipe estimates use current catalogue data and expose independent completeness results.
- [x] MealPrepBatch ingredient contributions are snapshotted and batch totals do not reread catalogue or Recipe data.
- [x] Positive quantities/yield, unit matching, price ownership, deletion behavior, and single-currency batch costs are validated and tested.
- [x] Meal Prep Batch list, direct/Recipe-prefilled creation, actual ingredient editing, and read-only historical detail are available through the UI.
- [x] ConsumptionEntry can log an amount from a MealPrepBatch and preserve scaled historical snapshots.
- [x] A user can record actual Food purchases and review them separately from estimated Meal Prep and consumption costs.
- [x] Domain calculations are tested independently of AI.
- [ ] Future AI tools can call shared services without direct database access.

## 15. Current implementation status

**Implemented:** Phases 1-4 provide `FoodItem`, `PriceObservation`, and `ConsumptionEntry`, catalogue management, consumption logging, historical snapshots, Today/History, navigation, and focused automated tests. The recipe/batch data foundation adds `Recipe`, `RecipeIngredient`, `MealPrepBatch`, and `BatchIngredient`, dynamic recipe estimates, snapshot-based batch totals, and transactional batch creation. The Recipe UI supports list, metadata create/edit, detail, planned ingredient create/edit/POST-only delete, and completeness-aware estimates. Meal Prep supports list, direct or Recipe-prefilled batch creation with editable actual rows and POST-based add/remove controls, plus read-only detail from historical snapshots. Batch detail can log an amount as eaten; the unified entry stores nutrition/cost snapshots scaled from batch snapshots and appears in Food Today by local reporting date. `FoodPurchase` records actual spend separately from these estimates; Cost History labels purchase, Meal Prep, and consumption events distinctly, and Today displays purchase totals separately by currency. Migration 0003 adds batch consumption and 0004 adds FoodPurchase. The configured reporting timezone is `Europe/Dublin`.

**Planned or deferred:** Receipt grouping/imports, accounting/budgets, purchase-to-inventory tracking, quick-add meals/foods, cumulative batch availability/inventory, batch editing/recalculation, daily targets, advanced cost analysis, and AI/API integrations are not implemented. Arbitrary manual nutrition/cost overrides, count-based portions and servings, conversions, and external data sources remain deferred. Final MVP polish and full desktop/mobile review are outstanding.

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
| 0.7.0 | 2026-10-25 | Recorded Recipe list/detail/edit and planned ingredient UI, completeness-aware live estimates, and the still-deferred Meal Prep Batch UI. |
| 0.8.0 | 2026-10-25 | Recorded Meal Prep Batch list, direct and Recipe-prefilled creation, and snapshot-based read-only detail; batch-backed consumption remains deferred. |
| 0.9.0 | 2026-10-25 | Recorded batch-backed consumption with yield-scaled historical snapshots, migration 0003, source/deletion semantics, verification evidence, and remaining follow-on scope. |
| 1.0.0 | 2026-10-25 | Recorded simple FoodPurchase events, Cost History, and separate actual-purchase versus estimated-consumption totals. |
