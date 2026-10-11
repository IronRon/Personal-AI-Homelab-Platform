# Personal AI Homelab Platform

A local-first, modular platform for personal applications, information, automation, long-running jobs, and AI-assisted workflows.

The platform is intended to remain useful without AI. AI will provide natural-language interaction, analysis, recommendations, planning, and controlled tool execution on top of ordinary deterministic application features.

> **Status:** Pre-prototype / early research
>
> The current architecture and technology choices are provisional. See [docs/project-design.md](docs/project-design.md) for the living design document and decision history.

## Vision

Create one personal software platform with shared conventions for:

- personal modules such as Food, Finance, Media, and Fitness;
- a responsive dashboard for desktop and phone access;
- local-first data and optional cloud services;
- safe, typed AI tools instead of direct database access;
- long-running jobs with progress, cancellation, and history;
- controlled use of CPU, GPU, storage, and external services;
- import/export using ordinary formats such as CSV and JSON.

## Planned capabilities

- Central dashboard, navigation, settings, and authentication
- Food, nutrition, recipe, meal preparation, and shopping workflows
- Finance imports, categorisation, budgets, and analysis
- Deterministic media processing with FFmpeg/FFprobe
- Local AI inference with optional cloud providers behind an adapter
- Approved read, write, external, and destructive tool categories
- Job tracking for imports, analysis, transcription, and video processing
- Mobile-friendly browser access over a private network
- Exportable structured data and documented backup/restore procedures

## Provisional architecture

The recommended starting point is a modular monolith with specialised workers only where they are useful:

```text
Desktop / Phone Browser
          |
          v
Django control plane ---- Relational database
          |
          +---- AI orchestrator ---- Local or optional cloud provider
          |
          +---- Job system -------- Python and video workers
          |
          +---- Controlled filesystem/media storage
```

The web application owns the dashboard, module boundaries, structured data, AI orchestration, and job metadata. Heavy or dependency-specific work should run in separate worker processes rather than inside web requests.

## Initial technology direction

These choices are recommendations, not fixed requirements:

| Area | Initial direction |
| --- | --- |
| Control plane | Django |
| UI | Django templates with targeted JavaScript or HTMX |
| Database | SQLite initially, with portable ORM usage and a likely PostgreSQL promotion later |
| AI runtime | Ollama first; evaluate llama.cpp and other runtimes as needed |
| Media processing | FFmpeg and FFprobe |
| Background work | Simple worker experiment first; evaluate Django Tasks, Celery, Redis, or another queue when justified |
| Deployment | Local Windows processes first; Docker Compose only when it reduces operational friction |
| Remote access | Private network solution such as Tailscale; no public exposure by default |

## Development path

The project is intended to grow through useful vertical slices:

1. Establish the Django control plane and shared conventions.
2. Build the first Food module with relational data, calculations, forms, and exports.
3. Add Finance imports and read-only analysis.
4. Introduce the common job model and a worker for long-running tasks.
5. Deliver a deterministic video milestone: verify local clips, concatenate or transcode them, report progress, and record the output artifact.
6. Add controlled AI tools and provider abstraction around real workflows.
7. Expand into Fitness, richer media workflows, scheduling, and other modules only when useful.

## Design principles

- Local-first, not local-only.
- AI enhances core functionality; it is not a requirement for basic operations.
- Start simple and earn complexity.
- Use deterministic tools for deterministic work.
- Keep module ownership and service boundaries clear.
- Store structured state in a relational database and large files on the filesystem.
- Treat GPU-heavy work as an explicit resource with scheduling limits.
- Require approval for sensitive writes and destructive operations.
- Keep data exportable and backups recoverable.
- Record architectural rationale, including rejected alternatives.

## Repository layout

```text
.
├── docs/
│   └── project-design.md
└── README.md
```

The layout will grow as implementation begins. The design document includes an illustrative target structure for apps, workers, adapters, templates, static files, and tests.

## Current status

No application code has been implemented yet. The repository currently contains the project design and foundational documentation. Technology decisions remain open where the design document marks them as proposed or under consideration.

## Documentation

- [Project design](docs/project-design.md): requirements, architecture, modules, technology comparisons, AI safety model, data strategy, job system, and roadmap notes.
