---
name: implement-milestone
description: 'Use when implementing one explicitly approved development milestone from the project design or a module specification. Follow a controlled, incremental, test-driven workflow: inspect documentation and code, confirm scope, resolve material questions, implement, test, review, and update status.'
argument-hint: 'Name the approved milestone and link or identify its design document.'
user-invocable: true
disable-model-invocation: false
---

# Implement Milestone

Use this skill to implement one approved development milestone for the Personal AI Homelab Platform. The skill is reusable across Food, Finance, Media, Fitness, core platform work, and future modules.

## Purpose

Turn an approved milestone into a small, verified change while preserving the project’s modular, local-first architecture. Treat design documents as the source of product requirements and keep implementation decisions visible.

## Required workflow

1. **Read the design context.** Read the relevant module specification, `docs/project-design.md`, `README.md`, and any linked design or decision documents before changing code.
2. **Inspect the current implementation.** Locate the owning Django app, existing views, templates, models, services, tests, settings, and nearby patterns. Identify reusable functionality before adding new code.
3. **Confirm the milestone.** State the exact milestone, its intended outcome, and the files or boundaries likely to be affected. Confirm that the request covers one milestone only.
4. **Make a small plan.** Describe the implementation steps, test strategy, documentation changes, and any expected migration or compatibility impact.
5. **Check unresolved decisions.** Identify open questions in the design documents that materially affect this milestone. Ask for clarification or approval before implementing when an unresolved decision changes scope, data meaning, user workflow, or compatibility.
6. **Implement only the agreed scope.** Do not implement later milestones, speculative features, or unrelated cleanup. Preserve existing behaviour where practical.
7. **Separate domain logic from delivery code.** Keep business rules and calculations in reusable application or domain services where future UI views and AI tools can call the same behaviour. Keep views focused on request handling and presentation.
8. **Add focused tests.** Add or update unit tests for domain rules and integration tests for important Django workflows, routes, forms, persistence, or user-visible behaviour. Prefer real behaviour over mocks that only verify calls.
9. **Run verification.** Execute the narrowest relevant tests first, then the relevant Django system checks and broader tests when appropriate. Run migrations or migration checks when models change. Never claim success without fresh command output.
10. **Review the change.** Check for unnecessary complexity, security problems, data-validation gaps, regressions, accidental scope expansion, and inconsistencies with the approved design.
11. **Update documentation.** Update the relevant module or project document’s implementation status and revision history. Record meaningful deviations, newly resolved decisions, or remaining limitations without rewriting unrelated documentation.
12. **Report completion.** Provide a concise report covering the implementation, changed files, migrations, tests and results, limitations, documentation updates, and the suggested next milestone.

## Scope and safety rules

- Implement only one explicitly approved milestone at a time.
- Do not silently change approved business rules or requirements.
- Do not invent a product decision where the design document marks a question as unresolved.
- Do not add Redis, Celery, MCP, AI agents, model integrations, Docker, new databases, or other infrastructure unless the milestone explicitly approves it and the project owner requests it.
- Do not introduce unnecessary frameworks, dependencies, generic abstractions, or premature optimisation.
- Do not put all domain calculations in views or models without considering reusable services.
- Keep module boundaries clear and avoid unrelated cross-module coupling.
- Do not expose arbitrary database or shell access to future AI capabilities.
- Preserve backwards compatibility with existing functionality where practical.
- Do not modify unrelated files or application areas.
- Do not automatically begin the next milestone.
- Do not automatically commit or push changes.

## Handling blockers and failures

- If an important requirement is ambiguous, pause implementation and ask a focused question with a recommended option and its trade-off.
- If a test or check fails, investigate the failure, report the actual result, and fix only issues within the agreed milestone scope.
- If the failure reveals a design problem or a new requirement, stop and request a decision rather than silently expanding scope.
- If a command or dependency is unavailable, report the limitation and identify the closest meaningful verification that was performed.

## Completion report

Use this structure after the milestone is complete:

### Implemented

Summarise the user-visible and technical behaviour delivered.

### Files changed

List added, modified, or deleted files and why they changed.

### Database changes

List migrations created or applied. State explicitly when no database changes were needed.

### Verification

List the exact tests, Django checks, migration checks, or other relevant commands executed, with their actual results.

### Limitations and unresolved issues

Record known gaps, deferred design questions, and anything that could affect the next milestone.

### Documentation

Identify updated design documents, implementation-status changes, and revision-history entries.

### Suggested next milestone

Suggest one next milestone only. Do not start it automatically.
