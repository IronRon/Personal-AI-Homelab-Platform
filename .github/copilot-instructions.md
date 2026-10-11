# Copilot Instructions

This project is a local-first, modular, AI-enhanced personal homelab platform. The current implementation uses Django for the backend, but the larger architecture remains intentionally flexible as the platform grows.

- Keep functional modules clearly separated and avoid mixing unrelated responsibilities into a single app.
- Prefer reusable domain services that can be called from both UI views and future AI tools.
- AI should remain optional for core platform functionality; do not make the project dependent on a model or provider for basic operations.
- Prefer simple, maintainable solutions over premature abstraction or framework churn.
- Read the relevant design documentation before implementing significant features and treat provisional architecture notes as guidance, not mandatory rules.
- When a feature is ambiguous, clarify the goal, user workflow, constraints, and edge cases before proposing a solution.
- Do not silently add infrastructure such as Redis, Celery, MCP, new databases, or extra frameworks without a clear need.
- Write focused tests and verify the actual behavior of the code you change.
- Avoid unrelated edits and keep implementation, comments, and documentation aligned.
- Do not automatically commit or push changes.
- Preserve the local-first, modular, and incremental nature of the project.
