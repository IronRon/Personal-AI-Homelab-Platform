---
name: grill-me
description: 'Use when you need to pressure-test a feature idea, interview the user about requirements, challenge assumptions, and turn an idea into a clear product spec before implementation. Trigger phrases: grill me, interview me, pressure-test this feature, design review.'
argument-hint: 'Describe the idea, problem, or feature you want to explore.'
user-invocable: true
disable-model-invocation: false
---

# Grill Me

Use this skill when a feature idea is vague, a requirement is uncertain, or a plan needs to be challenged before implementation begins.

## Purpose

Turn an incomplete idea into a clear and defensible feature specification. This is a product-design and architecture interview, not a coding task.

## Interview behaviour

1. Read the relevant project documentation and current code before asking questions so the interview builds on existing context instead of repeating what is already known.
2. When `vscode/askQuestions` is available, use it for the interview. Ask one meaningful question at a time and wait for the user’s response before continuing. Do not present a large questionnaire or batch unrelated questions.
3. For each interactive question, provide a small number of meaningful options where appropriate. Identify one recommended option and briefly explain the reasoning, while allowing the user to provide a custom answer rather than forcing a predefined choice.
4. After receiving each response, analyse its implications before asking the next question. Treat requirements as a decision tree: a response may reveal dependencies, invalidate an earlier assumption, or require a more specific follow-up.
5. Challenge assumptions constructively when a response overlooks a realistic use case, creates a contradiction, introduces avoidable complexity, or misses an MVP boundary.
6. Periodically summarise confirmed decisions and important unresolved questions. Continue until the main workflows, business rules, requirements, and MVP boundaries are sufficiently clear, or the user explicitly chooses to stop. Do not conclude merely because one question has been answered.
7. If `vscode/askQuestions` is unavailable in the selected agent environment, fall back to asking one question at a time through normal chat messages instead of failing.
8. Keep implementation separate. After the interview, present the proposed design for review and approval. Do not create specifications, edit the application, or implement the feature without a separate explicit instruction.
9. Keep the skill reusable across the Personal AI Homelab Platform. Do not assume a feature is specific to the Food module unless the user says so.

## Working approach

- Explore the actual problem being solved before proposing a solution.
- Build on prior answers rather than restarting from a generic template.
- Distinguish essential MVP behaviour from future enhancements and future AI capabilities.
- Explain the practical trade-offs of alternatives in plain language.
- Record open questions when a decision requires experimentation, additional research, or a later commitment.

## Hard rules

- Do not write implementation code during the interview.
- Do not create database models, migrations, or schema changes.
- Do not silently modify the application.
- Do not assume the design document contains final decisions.
- Do not make major decisions on the user’s behalf without explaining the trade-off.
- Do not repeat questions that were already answered.
- Do not focus only on implementation details; understand the user experience and real-world workflow.

## Final output after the interview

Once the interview is complete, produce a proposed feature specification containing:

- Feature overview and objectives.
- User workflows and examples.
- Functional requirements.
- Data that needs to be stored.
- Potential data models and relationships.
- Business logic and calculations.
- UI requirements.
- Possible integrations with other modules.
- Possible future AI tools.
- Edge cases and validation.
- Architectural alternatives where relevant.
- MVP scope.
- Future feature backlog.
- Open questions.
- Suggested implementation milestones.
- Acceptance criteria.

Present this design for review and approval. Only after explicit approval should a separate, explicit instruction be used to write the agreed specification into a Markdown document such as `docs/modules/food-design.md`.
