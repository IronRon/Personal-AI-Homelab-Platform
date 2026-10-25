# Development Log

This is the chronological record of meaningful development work on the Personal AI Homelab Platform. Entries are newest first. Design documents describe intended requirements and rationale; this log records work actually performed and verification evidence.

### 2026-10-25 — Recipe Management UI
**Area:** Food / Recipe UI

**Summary:**
Added server-rendered Recipe management and planned ingredient workflows on top of the existing Food data foundation.

**Completed:**

- Added Recipe list, metadata create/edit, detail, and planned ingredient create/edit/POST-only removal routes and pages, plus a Recipes link in Food navigation.
- Recipe detail calls the existing estimate service. Estimates use current FoodItem and PriceObservation values, show completeness independently for calories, protein, carbohydrates, fat, and cost, and do not present incomplete subtotals as complete totals.
- Added server-rendered price choices using the existing zero/one/multiple observation policy, Recipe-parent scoping for ingredient updates/removal, and friendly handling when catalogue edits make a stored ingredient selection invalid.
- Added focused Recipe UI tests for list/detail, create/edit, ingredient CRUD and validation, price policy, live estimate updates, missing data, mixed currencies, stale catalogue data, and absence of batch/consumption side effects.

**Technical decisions:**

- Recipe estimates remain dynamic; editing Recipe metadata or planned ingredients does not create batch snapshots.
- Views delegate nutrition and cost calculations to `calculate_recipe_estimate()`.
- RecipeIngredient removal is POST-only and lookup is constrained to its parent Recipe.
- No schema changes or migration were needed.

**Testing and verification:**

- Reported for the Recipe UI implementation: `python manage.py check` passed; `python manage.py makemigrations --check --dry-run` reported no changes; `python manage.py test apps.food` passed with 72 tests; the full Django suite passed with 74 tests; and `git diff --check` passed.
- These implementation checks were not rerun during this documentation-sync pass.

**Known issues / deferred work:**

- Meal Prep Batch forms, views, templates, browser-based batch creation, and batch-backed `ConsumptionEntry` remain future work.
- Count-based portions, servings, unit conversion, inventory, purchase accounting, arbitrary nutrition/cost overrides, AI, and APIs remain deferred.

### 2026-10-25 — Recipe and Meal-Prep Data Foundation
**Area:** Food / Data Layer

**Summary:**
Added the first Recipe and meal-prep batch data foundation to the existing Food Django app. Recipe estimates remain dynamic; cooked batch ingredient values are historical snapshots.

**Completed:**

- Added `Recipe` and `RecipeIngredient` for reusable plans using existing `FoodItem` records.
- Added `MealPrepBatch` and `BatchIngredient` for actual cooking events, positive gram/millilitre yield, actual ingredient inputs, and copied nutrition/cost/currency/name/provenance snapshots.
- Added dynamic recipe estimates, batch total aggregation from snapshots only, shared price-selection behavior, independent nutrient/cost completeness, and rejection of mixed known-cost currencies.
- Added transactional batch creation with explicit model validation. Recipe deletion preserves batches; deleting FoodItems or price observations nulls batch references while preserving snapshots; recipe ingredient FoodItem references are protected.
- Changed `backend/apps/food/models.py` and `backend/apps/food/services/calculations.py`; added `backend/apps/food/services/meal_prep.py`; extended `backend/apps/food/tests.py`.
- Added additive migration `backend/apps/food/migrations/0002_recipe_mealprepbatch_recipeingredient_and_more.py` and focused model, calculation, and service coverage in `backend/apps/food/tests.py`.
- Added short code docstrings/comments at the estimate, snapshot, completeness, currency, and transactional-validation boundaries.

**Technical decisions:**

- `FoodItem` remains the shared ingredient/product catalogue; Recipe estimates use current catalogue values.
- BatchIngredient snapshots, not current catalogue or Recipe records, are the source for historical batch totals.
- Missing values remain nullable and mark their corresponding totals incomplete. Known subtotals do not imply complete totals.
- Batch creation validates with `full_clean()` because model `save()` does not call it, and the transaction prevents partial batches.
- The batch service accepts actual input rows and an optional Recipe association; it does not yet copy RecipeIngredient rows automatically.

**Testing and verification:**

- `python manage.py check` passed.
- `python manage.py makemigrations --check --dry-run` reported no changes.
- `python manage.py test apps.food` passed: 57 tests.
- `python manage.py test` passed: 59 tests.
- `git diff --check` passed.
- The migration was not applied to the development database.

**Known issues / deferred work:**

- No recipe/batch forms, views, URLs, templates, or user-facing workflows were added.
- `ConsumptionEntry` does not yet reference batches; yield-based batch consumption remains future work.
- Count-based portions, conversions, inventory, purchase accounting, arbitrary nutrition/cost overrides, AI, and infrastructure remain deferred.

**Git status:**

- Implementation paths were already staged when documentation synchronization began. No staging, commit, or push was performed during this work; documentation and comment updates remain unstaged.

### 2026-10-11 — Phase 4 Food Verification and User Experience
**Area:** Food / Core UI

**Summary:**
Completed the Food module verification and usability pass before recipes and meal preparation.

**Completed:**

- Made Food Today the main Food landing page at `/food/`.
- Added named-route navigation between Today, Log Food, Food Catalogue, and Consumption History.
- Moved the catalogue to `/food/catalogue/` and changed the central dashboard Food link to use the named Today route.
- Added shared Food navigation, contextual actions, empty-state guidance, responsive styling, and explanatory help text.
- Clarified Ingredient versus Product terminology, including supermarket, workplace canteen, restaurant, takeaway, and ready-meal products.
- Documented outside-meal support and the current grams/millilitres limitation.
- Updated [food-design.md](modules/food-design.md) and [food-mvp-plan-1.md](modules/food-mvp-plan-1.md).

**Technical decisions:**

- No schema change was needed for outside meals: they can currently be represented as `Product` records with optional brand/source, estimated nutrition, and price observations.
- Serving, count, density, and portion conversions remain deferred.
- Global navigation remains focused on the Homelab and Food entry point; Food-specific navigation is local to Food pages.

**Testing and verification:**

- Django system check passed.
- Migration consistency check reported no changes.
- Focused Food tests passed: 36 tests.
- Full Django test suite passed: 38 tests.
- Live HTTP smoke checks returned `200` for `/`, `/food/`, `/food/catalogue/`, `/food/today/`, `/food/log/`, and `/food/history/`.
- Static diagnostics and `git diff --check` passed.
- Screenshot-based visual inspection was not independently performed; manual desktop/mobile review remains pending.

**Known issues / deferred work:**

- Recipes, meal preparation, daily targets, AI/MCP, imports, OCR, advanced analytics, and serving/density conversions remain deferred.

**Next steps:**

- Review the UI manually at desktop and narrow/mobile widths.
- Design the recipe foundation before implementing meal-prep batches.

**Git status:**

- Commit `18e7b9b` (`master`, `origin/master`): Phase 4 navigation, contextual help, and responsive design improvements.
- Worktree was clean at the time of inspection.

### 2026-10-11 — Phase 3 Food Consumption Logging
**Area:** Food

**Summary:**
Implemented service-backed consumption logging, historical correction rules, Today summaries, and consumption history.

**Completed:**

- Added application services for consumption creation, metadata-only updates, explicit recalculation, date filtering, and daily summaries.
- Wired snapshot creation through the existing `calculate_consumption` service.
- Added logging, Today, history, edit, and POST-only deletion workflows.
- Applied the multiple-price policy: one observation is auto-selected, multiple require explicit selection, and no observation leaves cost unknown.
- Preserved historical snapshots when catalogue data changes.

**Technical decisions:**

- Date and meal-category edits do not recalculate snapshots.
- Food, quantity, unit, or price changes require deliberate recalculation confirmation.
- Per-nutrient completeness flags prevent unknown values from being displayed as zero totals.
- Reporting uses the configured `Europe/Dublin` timezone.

**Testing and verification:**

- Focused Food tests passed: 34 tests.
- Full Django test suite passed: 36 tests.
- Django check and migration consistency checks passed.
- Live HTTP smoke checks returned `200` for the homepage, Food catalogue, Today, logging, and history pages.

**Known issues / deferred work:**

- Daily targets, recipes, meal preparation, serving conversions, AI/MCP, imports, OCR, and advanced analytics remain deferred.

**Next steps:**

- Verify the workflow manually in desktop and mobile browsers.
- Improve navigation and user guidance before designing recipes.

**Git status:**

- Commit `0847465`: consumption logging and daily summary features.

### 2026-10-11 — Phase 2 Food Catalogue Management
**Area:** Food

**Summary:**
Implemented the server-rendered Food catalogue and price management workflow.

**Completed:**

- Added FoodItem and PriceObservation ModelForms.
- Added catalogue listing, name/brand search, create/edit pages, FoodItem detail, and price-history pages.
- Added nutrition and package-unit validation, optional unknown nutrition, success messages, and responsive shared styling.
- Updated the database-backed route test to use `TestCase`.

**Testing and verification:**

- Focused Food tests passed: 22 tests.
- Full Django test suite passed: 24 tests.
- Django check and migration consistency checks passed.
- Live smoke checks returned `200` for `/`, `/food/`, and `/food/new/`.

**Known issues / deferred work:**

- Consumption logging and automatic snapshot creation were not yet implemented at this point.
- Recipes, meal preparation, AI, imports, OCR, and infrastructure remained deferred.

**Next steps:**

- Implement service-backed consumption logging and Today summaries.

**Git status:**

- Commit `cebf400`: Food catalogue management with item creation, editing, and price observations.

### 2026-10-11 — Phase 1 Food Models and Calculations
**Area:** Food / Data Layer

**Summary:**
Implemented the initial Food persistence and reusable calculation foundation.

**Completed:**

- Added `FoodItem`, `PriceObservation`, and `ConsumptionEntry` models.
- Added the initial Food migration.
- Added Decimal nutrition scaling, proportional allocated-cost calculation, and timezone-aware daily aggregation services.
- Added explicit nutrition/cost snapshot fields and validation for unknown values, incompatible units, and invalid quantities.
- Set the reporting timezone to `Europe/Dublin`.

**Technical decisions:**

- Use a unified FoodItem with ingredient/product type for the first slice.
- Store current nutrition directly on FoodItem and historical values on ConsumptionEntry.
- Support grams and millilitres only; defer density, count, and serving conversions.
- Treat allocated consumed cost separately from grocery expenditure.

**Testing and verification:**

- Focused Food tests passed: 12 tests after migration creation.
- Full Django test suite passed: 16 tests.
- Django checks, migration checks, and diagnostics passed.

**Known issues / deferred work:**

- The calculation helper initially did not persist snapshots automatically; that was intentionally completed in Phase 3 through application services.
- Catalogue UI, consumption UI, recipes, meal preparation, and AI remained deferred.

**Next steps:**

- Build the Food catalogue workflow.

**Git status:**

- Commit `29c8ca0`: Food models and calculation services.

### 2026-10-11 — Food Design and Implementation Planning
**Area:** Food / Product Planning

**Summary:**
Completed the Food discovery process and documented the approved starting design and Basic Food Tracking implementation plan.

**Completed:**

- Defined unified consumption logging, nutrition/cost snapshots, ingredient/product concepts, recipes, meal preparation, provenance, and future AI tool boundaries.
- Recorded unresolved questions around grocery expenditure, serving/density conversions, meal preparation priority, and future reporting.
- Created the phased plan for models/calculations, catalogue management, consumption logging, and verification.

**Technical decisions:**

- AI should call validated application services rather than issue SQL.
- Core functionality remains deterministic and useful without AI.
- SQLite and the existing Django modular-monolith approach remain the initial platform direction.

**Known issues / deferred work:**

- This entry records planning and documentation, not implementation of the planned features.

**Next steps:**

- Implement Phase 1 only, with tests and migration verification.

**Git status:**

- Commits `03d295e` and `059aa43`: Food design documentation and initial milestone plan.

### 2026-10-11 — Django Foundation and Copilot Workflow
**Area:** Core / Developer Workflow

**Summary:**
Established the Django project foundation and reusable Copilot planning workflow.

**Completed:**

- Created the Django project under `backend/` with `config` settings and SQLite.
- Added `core` and `food` Django apps, dashboard placeholder, Food placeholder, templates, and initial route tests.
- Added project README and `.gitignore` documentation.
- Added project-wide Copilot instructions, the Product Discovery agent, `grill-me`, and `implement-milestone` skills.
- Defined the platform as local-first, modular, AI-enhanced, and incremental.

**Testing and verification:**

- Django foundation checks, migrations, and initial route tests were executed successfully according to the project setup record.
- Later milestone work independently verified the existing Core and Food routes.

**Known issues / deferred work:**

- The development server is a local development server only.
- Food functionality initially consisted of placeholders and was expanded by later entries.

**Next steps:**

- Continue milestone-based development with approved plans and explicit verification.

**Git status:**

- Commits `d505d70`, `5f9175f`, and `7d2dbba` cover the Django foundation, Copilot workflow setup, and initial project design.
