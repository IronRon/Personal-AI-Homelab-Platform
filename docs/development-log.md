# Development Log

This is the chronological record of meaningful development work on the Personal AI Homelab Platform. Entries are newest first. Design documents describe intended requirements and rationale; this log records work actually performed and verification evidence.

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
