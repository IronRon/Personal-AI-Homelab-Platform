## Plan: Basic Food Tracking Milestone

Create the smallest useful end-to-end Food feature on the existing Django/SQLite foundation: a catalogue of generic ingredients or branded products, reusable nutrition data, optional package price observations, consumption logging, stable historical snapshots, and a Today view with daily totals. Keep the implementation server-rendered, modular, testable, and ready for future recipes, meal preparation, and validated AI tools without implementing those later features now.

**Decisions from discovery**
- Use one `FoodItem` catalogue model with a type distinguishing `ingredient` and `product`; optional brand/package fields preserve the distinction without duplicating the first CRUD flow.
- Store the current nutrition basis directly on `FoodItem` for this milestone, with provenance and basis unit. Defer a separate versioned `NutritionProfile` until multiple profiles/sources justify it.
- Support decimal grams and millilitres only in the first slice. Require the logged unit to match the FoodItem nutrition basis. Defer density, count, household measures, and serving conversions.
- Use a separate `PriceObservation` model with package quantity, package unit, paid price, currency, and observed date. It represents an input to estimated consumed cost, not a grocery purchase ledger.
- Use `ConsumptionEntry` for actual intake, with explicit nutrition and cost snapshots plus source-identifying fields. Catalogue edits affect future entries only.
- Store an aware `consumed_at` timestamp and derive Today using the configured local Django timezone. Confirm the exact IANA timezone before implementation; do not silently retain UTC or invent a location.
- Allow unknown nutrition/cost values as nullable and visibly incomplete; never treat unknowns as zero.
- Use confirmed hard delete for mistaken consumption entries in this single-user MVP, with UI confirmation and totals recalculated afterward.
- No recipes, meal-prep batches, portions, imports, OCR, AI, queues, or new infrastructure in this milestone.

**Steps**

### Phase 1: Model and calculation foundation
1. Confirm the exact IANA value for the user’s local timezone before changing Django settings. *Blocks the date/reporting implementation.*
2. Add the minimum Food models in `backend/apps/food/models.py`: `FoodItem`, `PriceObservation`, and `ConsumptionEntry`. Keep fields explicit and relational rather than using JSON for core nutrition/cost data.
3. Use `DecimalField` for calories, macros, quantities, prices, and calculated costs with documented precision/rounding. Use nullable nutrition and cost snapshot fields plus provenance/source labels. Add validation for positive quantities/package sizes, supported units (`g`/`ml`), non-negative nutrition/prices, and coherent package data.
4. Create and apply a Food migration. Avoid adding `NutritionProfile`, `NutritionSource`, `DailyTarget`, recipe, batch, or portion tables until a later milestone.
5. Add calculation services under `backend/apps/food/services/` or the smallest local service module that matches repository conventions. Keep functions for scaling nutrition from per-100 basis values, deriving allocated cost from package price/quantity, and aggregating daily totals. Services should be callable by views now and future AI tools later.
6. Add unit tests for scaling, Decimal rounding, g/ml mismatch, nullable nutrition/cost, cost allocation, and daily aggregation before wiring the UI.

**Phase 1 status: Implemented.** The minimum models, initial migration, reusable calculation services, `Europe/Dublin` reporting timezone, and focused model/service tests are complete. No forms, views, templates, recipes, meal preparation, AI, or infrastructure were added.

### Phase 2: Catalogue workflow
7. Add `backend/apps/food/forms.py` for FoodItem and optional PriceObservation create/edit flows. Do not create generic form abstractions.
8. Extend `backend/apps/food/views.py` and `backend/apps/food/urls.py` with catalogue list, create, edit, and detail or price-entry routes. Use application services for normalization/validation where business rules are involved.
9. Add `backend/templates/food/catalogue.html`, `food/food_item_form.html`, and any narrowly needed partials. Reuse `backend/templates/base.html` styling and navigation. Keep the pages responsive and functional rather than adding a frontend framework.
10. Add catalogue integration tests covering create/edit, invalid nutrition/price values, optional prices, ingredient/product type, unit basis, and browser-visible list/form behavior.

**Phase 2 status: Implemented.** Catalogue listing/search, FoodItem create/edit forms, nutrition validation, price observation create/edit forms, price history, success messages, responsive templates, and integration tests are complete. Consumption logging and snapshot-creation services remain deferred to Phase 3.

### Phase 3: Consumption workflow and Today dashboard
11. Add a consumption form supporting FoodItem search/selection, quantity in the matching g/ml basis, optional meal category, and date/time with a local-time default.
12. Add routes/views for logging, today’s entries, history, edit, and confirmed delete. Use POST plus CSRF protection for mutations and redirect after successful writes.
13. On creation, call the calculation service and persist source name, quantity/unit, nutrition snapshots, estimated allocated cost, currency, provenance, and aware timestamp. Do not recalculate old entries from current catalogue values.
14. Add `backend/templates/food/today.html`, `food/consumption_form.html`, and `food/history.html` or similarly focused templates. Show incomplete-data warnings and distinguish estimated consumed cost from grocery expenditure.
15. Add integration tests for logging, snapshot stability after catalogue edits, edit/delete behavior, invalid units/quantities, missing nutrition/price handling, local timezone/date assignment, and Today totals for calories/protein/carbohydrates/fat/cost.

**Phase 3 status: Implemented.** Consumption application services now create snapshots through `calculate_consumption`, preserve metadata-only edits, require explicit confirmation for catalogue-based recalculation, apply the approved multiple-price selection rule, and provide timezone-aware daily summaries. Logging, Today, history, correction, and POST-only deletion pages are implemented and tested. Daily targets, recipes, meal preparation, and AI remain deferred.

### Phase 4: Verification and documentation
16. Run the focused Food tests, `python manage.py check`, migrations/migration checks, and the full Django test suite. Start the local server and manually verify catalogue creation, logging, Today, history correction, and deletion in a desktop and narrow/mobile viewport.
17. Review the diff for scope expansion, security issues, direct view calculations, accidental grocery-spend claims, and regressions to `/` and `/food/`.
18. Update `docs/modules/food-design.md` implementation status, milestone checklist, acceptance checklist, and revision history only for behavior actually implemented. Do not mark recipes, meal prep, AI, or deferred features implemented.
19. Report changed files, migration status, exact verification commands/results, limitations, unresolved questions, and one suggested next milestone. Do not begin the next milestone.

**Phase 4 implementation: Complete; manual visual review remains outstanding.** Verification, Food landing-page navigation, shared Food navigation, contextual help, empty states, outside-meal guidance, responsive styling improvements, route regressions, and documentation updates are complete. No recipes, meal preparation, serving conversions, AI, or new infrastructure were added. Rendered visual inspection was not automated in this environment; manual desktop/mobile browser review remains part of the checklist below.

### Follow-on: Recipe and meal-prep data foundation

**Status: Data foundation, Recipe UI, and Meal Prep Batch list/create/read-only detail implemented.** This is follow-on work beyond the original basic tracking milestone above.

- Added `Recipe` and `RecipeIngredient` for reusable plans using existing `FoodItem` records. Recipe estimates use current nutrition and price data and follow the existing zero/one/multiple price-selection policy.
- Added `MealPrepBatch` and `BatchIngredient` for actual cooking events and actual ingredient inputs. Ingredient names, nutrient contributions, allocated costs, currency, and provenance are snapshotted when the batch is created; batch totals read snapshots only.
- Added positive quantity/yield and unit/price ownership validation, single-currency validation for known batch costs, and transactional batch creation. Missing nutrient or cost values remain incomplete.
- Added one additive migration and focused model, calculation, snapshot-stability, currency, and service tests. The migration was not applied to the development database.

### Follow-on: Recipe UI

**Status: Implemented on 2026-10-25.** This UI work follows the data foundation and does not change the original basic tracking milestone above.

- Added Recipe list, metadata create/edit, detail, planned ingredient create/edit/POST-only delete, and a Recipes link in Food navigation.
- Recipe detail calls the existing estimate service and presents nutrition/cost completeness independently. Estimates update from current FoodItem and PriceObservation values.
- Added focused tests for list/detail, create/edit, ingredient management and validation, parent scoping, price selection, completeness, mixed currencies, live catalogue refresh, and stale data handling.
- Reported verification: `python manage.py check` passed; `python manage.py makemigrations --check --dry-run` reported no changes; `python manage.py test apps.food` passed with 72 tests; the full suite passed with 74 tests; `git diff --check` passed.
- No Meal Prep Batch forms/views/templates, batch creation through the browser, batch-backed consumption, AI, APIs, or new infrastructure were added. No model or migration changes were needed for the Recipe UI.

### Follow-on: Meal Prep Batch UI and consumption

**Status: Implemented on 2026-10-25.** The batch UI added no schema changes to the Recipe/batch data foundation. Batch-backed consumption is a separate follow-on slice that adds migration 0003.

- Added the batch list, direct creation, Recipe-detail “Create batch” entry point, Recipe selection, and explicit loading of planned Recipe ingredients into editable actual rows.
- Ingredient add/remove and Recipe-load actions are server-rendered POST round-trips without JavaScript; these interim submissions do not persist a batch. Existing PriceObservation selection rules apply.
- Final creation delegates validation and snapshot creation to transactional `create_meal_prep_batch()`. Read-only detail totals come from stored snapshots through `calculate_batch_totals()`.
- Batch detail provides “Log as eaten”. The service validates a positive amount no greater than batch yield and matching yield unit, then scales stored batch snapshots into `ConsumptionEntry`; it does not recalculate from current catalogue values.
- Migration 0003 adds a nullable `SET_NULL` batch relation and constraints against dual sources or a batch price observation. Deleting a batch preserves the entry's source name and nutrition/cost snapshots. Database constraints prevent both source FKs being set but do not independently require one; creation validation requires exactly one.
- Each consumption row may be no greater than the yield, but cumulative consumption is not limited and remaining availability is not tracked.
- User-reported implementation-run verification: `python manage.py check` passed; `python manage.py makemigrations --check --dry-run` reported no changes; Food tests passed (105); Core + Food tests passed (107); `git diff --check` passed; the migration compatibility test passed; and 300 g from a 1,200 g / 2,400 kcal batch produced 600 kcal.
- User reported migrations 0001-0003 all unapplied in the development database; none were applied. These implementation checks were not rerun during this documentation sync.

Basic purchase history, quick-add meals/foods, cumulative batch availability/inventory, batch editing/recalculation, portions/count units/conversions, and AI/API integration remain deferred. Final MVP polish and full desktop/mobile review also remain outstanding.

### Follow-on: Food Purchase and Cost History

**Status: Implemented on 2026-10-25.** This follow-on adds a minimal actual-spend record and read-only cost timeline without introducing inventory or accounting behavior.

- Added `FoodPurchase` for a description, purchase timestamp, amount paid, currency, and optional FoodItem, quantity/unit, and shop/source. It is separate from `PriceObservation`, `ConsumptionEntry`, and MealPrepBatch snapshots.
- Added a purchase form, single-local-date Cost History page, and Food navigation link. The timeline labels actual purchases, estimated Meal Prep cost, ordinary consumption cost, and batch consumption separately.
- Today shows actual purchases separately from estimated consumed-food cost; both use currency-specific totals and never combine unlike currencies. Saving a purchase does not create consumption, and consumption/Meal Prep does not create purchases.
- Verification: `python manage.py check` passed; `python manage.py makemigrations --check --dry-run` reported no changes; `python manage.py test apps.food` passed with 116 tests; `python manage.py test apps.core apps.food` passed with 118 tests; `git diff --check` passed.
- Migration 0004 adds `FoodPurchase`. Current `showmigrations food` reports 0001–0003 applied and 0004 unapplied; no migration was applied during this implementation.

Receipt grouping/imports, bank/Finance accounting, budgets, purchase-to-inventory linkage, cumulative batch availability, and full desktop/mobile review remain deferred.

- `README.md` — existing setup and project structure; update only if the implemented workflow makes the development instructions materially stale.
- `backend/apps/food/models.py` — minimum persistent Food models and validation.
- `backend/apps/food/services/` — reusable nutrition, cost, and daily aggregation logic; create only the smallest service files needed.
- `backend/apps/food/forms.py` — catalogue and consumption validation/forms.
- `backend/apps/food/views.py` and `backend/apps/food/urls.py` — Food request routing and presentation orchestration.
- `backend/apps/food/tests.py` or focused test modules — unit and integration behavior tests.
- `backend/templates/food/` — Today, catalogue, form, and history pages using the existing base template.
- `backend/config/settings.py` — confirm/set the exact local `TIME_ZONE` only after user value is known; preserve SQLite and existing middleware.
- `backend/config/urls.py` — likely no change because `/food/` is already included; only change if named route structure requires it.
- `backend/templates/base.html` — only a minimal navigation/style adjustment if the Food pages need it.

**Verification**
1. Run focused Food unit/service tests for Decimal nutrition scaling, cost allocation, missing values, unit validation, snapshots, and daily aggregation.
2. Run Food Django integration tests for model/form/view/database behavior, including edit and hard delete.
3. Run `python manage.py check` from `backend/`.
4. Run `python manage.py makemigrations --check --dry-run` after migration creation and apply migrations with `python manage.py migrate`.
5. Run `python manage.py test` for the full suite.
6. Start `python manage.py runserver 127.0.0.1:8000` and manually verify `/food/`, catalogue create/edit, consumption logging, Today totals, history correction, and delete confirmation.
7. Verify the existing homepage `/` still returns successfully and that no unrelated application behavior changed.
8. Review mobile/narrow layout and visible incomplete-data/estimated-cost labels.

**Open questions / pre-implementation checks**
- The reporting timezone is resolved as `Europe/Dublin` for this milestone.
- Price selection is resolved: one observation is auto-selected, multiple observations require explicit selection, and no observations leave estimated cost unknown.
- Whether basic meal preparation should be moved earlier remains deferred and does not affect this slice unless the user changes milestone order.
- Grocery purchase expenditure versus allocated consumed cost remains explicitly outside this milestone; only estimated consumed cost is calculated.
- Density, serving-size conversions, count units, and household measures remain deferred; g/ml basis matching is the first-slice rule.
- Daily targets, recipes, meal-prep portions, alcohol/supplements/restaurant modeling, currency conversion, and richer charts remain deferred.

**Acceptance criteria**
- A user can create and edit a generic ingredient or branded product in the local catalogue.
- A FoodItem stores calories, protein, carbohydrates, and fat per 100 g or 100 ml, with provenance and optional package data.
- A user can add an optional package price observation without implying a grocery-purchase ledger.
- A user can search/select a saved FoodItem and log a positive decimal g/ml quantity.
- A consumption entry records date/time, optional meal category, source details, nutrition snapshot, and estimated consumed cost where derivable.
- Today shows consumed foods and totals for calories, protein, carbohydrates, fat, and estimated consumed cost.
- Missing nutrition or price is allowed, clearly flagged, and excluded from calculations without becoming zero.
- Catalogue edits do not rewrite historical consumption snapshots.
- A user can correct and hard-delete a mistaken consumption entry after confirmation.
- Tests cover calculation, validation, snapshots, timezone/date behavior, forms, views, persistence, edit, delete, and daily totals.
- Existing dashboard and Food placeholder routing remain functional.
- No recipe, meal-prep, AI, OCR, import, queue, or infrastructure feature is implemented in this milestone.
