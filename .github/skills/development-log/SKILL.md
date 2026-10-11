---
name: development-log
description: 'Use when recording or updating the chronological development log for the Personal AI Homelab Platform. Trigger phrases: update the development log, summarise today’s development, log this development session, record what we accomplished, create a development checkpoint.'
argument-hint: 'Describe the session or milestone to record, if needed.'
user-invocable: true
disable-model-invocation: false
---

# Development Log

Maintain `docs/development-log.md` as one concise, reverse-chronological record of meaningful work across the Personal AI Homelab Platform.

## Required workflow

1. Read `docs/development-log.md` if it exists before writing anything.
2. Inspect relevant Git history, current status, and diffs. Use commit messages and changed files as evidence, but do not treat a commit message alone as proof that tests passed.
3. Read relevant project and module documentation, including `docs/project-design.md`, the applicable module specification, implementation plan, and `.github/copilot-instructions.md`.
4. Consider the current Copilot conversation and work performed during the session. Separate direct evidence from information inherited from earlier reports.
5. Identify completed features, fixes, decisions, tests, documentation changes, known limitations, blockers, unfinished work, and practical next steps.
6. Distinguish verified implementation from proposed, attempted, reported, or pending work. Never claim a test, server check, manual verification, commit, or architectural decision without evidence.
7. Use the user’s configured local date when available. If the date or event timing is uncertain, use a clearly labelled grouped history entry rather than inventing precision.
8. Add the newest entry at the top of the file. Preserve every previous entry.
9. If the current session already has a matching entry, update that entry instead of creating a duplicate. Do not rewrite older historical facts merely because designs have evolved.
10. Keep the entry concise. Link to relevant design documents or milestone plans instead of duplicating them.
11. Summarise what was recorded after updating the file.

## Entry format

Use this structure and omit sections that have no meaningful content:

```markdown
### YYYY-MM-DD — Session Title
**Area:** Food / Finance / Core / AI / Media / etc.

**Summary:**
A short description of what was achieved.

**Completed:**

- Important features, fixes, or changes.

**Technical decisions:**

- Relevant architectural or implementation decisions.

**Testing and verification:**

- Exact tests/checks executed and their actual results.
- Identify anything not independently verified.

**Known issues / deferred work:**

- Remaining limitations, bugs, blockers, and unresolved questions.

**Next steps:**

- Practical tasks for the next development session.

**Git status:**

- Relevant commit references when available.
- Important uncommitted changes when known.
```

## Historical accuracy rules

- Never invent completed work, successful tests, commits, dates, or decisions.
- Never mark a feature implemented merely because it appears in a design document.
- Preserve prior entries and avoid repeating the same session.
- When several commits cover one milestone, summarise the milestone instead of listing every changed line.
- Distinguish planning, implementation, testing, documentation, and manual verification.
- If evidence comes only from a previous Copilot completion report, identify it as reported rather than independently verified.
- If the worktree is dirty, record relevant uncommitted changes and avoid implying they are committed.
- Do not modify application code, design documents, or implementation plans as part of this skill unless a separate explicit instruction requests it.
- Do not commit or push changes.

## Relationship with project documentation

The log complements, rather than replaces:

- `docs/project-design.md`, which explains platform intent and architecture;
- module specifications such as `docs/modules/food-design.md`, which explain requirements and design decisions;
- implementation plans, which explain intended milestone steps;
- ADRs, which explain durable architectural choices.

The development log records what actually happened, what was verified, what remains incomplete, and what should happen next.

## Completion response

After updating the log, report:

- the entry date and title recorded or updated;
- the main verified accomplishments;
- tests or checks recorded;
- known limitations or evidence gaps;
- the next step recorded;
- whether the worktree was clean or had uncommitted changes.
