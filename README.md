# Personal AI Homelab Platform

A local-first, modular platform for personal applications, information, automation, long-running jobs, and AI-assisted workflows.

The platform is intended to remain useful without AI. AI will provide natural-language interaction, analysis, recommendations, planning, and controlled tool execution on top of ordinary deterministic application features.

> **Status:** Early development; Food is the currently implemented module
>
> The wider architecture and technology choices remain provisional. See [docs/project-design.md](docs/project-design.md) and [docs/modules/food-design.md](docs/modules/food-design.md) for current design and implementation status.

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
├── backend/
│   ├── manage.py
│   ├── apps/
│   │   ├── core/
│   │   └── food/
│   ├── config/
│   └── templates/
├── docs/
│   ├── development-log.md
│   ├── modules/
│   └── project-design.md
└── README.md
```

The wider design document includes a provisional target structure for future apps, workers, adapters, and integrations.

## Current status

The Django control plane currently contains a working Core home page and Food catalogue, consumption tracking, history, Recipe management, and Meal Prep Batch list/create/read-only detail and consumption workflows. Recipe estimates use current catalogue data; batch history and logged batch consumption use stored snapshots. Purchase history, quick-add meals, cumulative batch availability, and other platform modules remain future work. Architecture choices not explicitly accepted in the design documents remain provisional.

## Development setup

### Python requirements

Use Python 3.12, 3.13, or 3.14. This project was initialized with Python 3.14 and Django 6.1.2.

### Create and activate a virtual environment

```powershell
cd "C:\Users\Ronak\Documents\Coding\Personal AI Homelab Platform"
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell policy blocks activation, invoke the interpreter directly instead of activating:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Install dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Run the project

```powershell
cd backend
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

### Run tests

```powershell
cd backend
python manage.py test
```

### Project structure

```text
.
├── backend/
│   ├── apps/
│   │   ├── core/
│   │   └── food/
│   ├── config/
│   ├── templates/
│   ├── manage.py
│   └── db.sqlite3
├── docs/
│   └── project-design.md
├── .gitignore
├── README.md
├── requirements.txt
└── .venv/
```

## Documentation

- [Project design](docs/project-design.md): requirements, architecture, modules, technology comparisons, AI safety model, data strategy, job system, and roadmap notes.
- [Food module design](docs/modules/food-design.md): Food requirements, implemented data foundations, deferred workflows, and cost/nutrition rules.
