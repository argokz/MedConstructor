# MedConstructor

MedConstructor is a research prototype for protocol-grounded clinical
reasoning education. Learners represent diagnostic and therapeutic reasoning as
directed knowledge graphs; teachers review reference graphs and publish tasks;
the evaluation service compares submitted graphs with approved references and
returns interpretable structural, semantic, pathway, and safety indicators.

> This software is intended for education and research. It is not a medical
> device and must not be used to make patient-care decisions.

## Current status

The repository contains an actively developed platform and reproducible
benchmark tooling. Technical and scoring validity have been evaluated on
controlled graph variants and a blinded cardiology expert panel. Prospective
classroom effectiveness has not yet been established.

## Core capabilities

- clinical protocol ingestion, chunking, embedding, and retrieval;
- protocol-grounded generation of task and reference-graph drafts;
- mandatory teacher review before a reference graph can be published;
- Vue Flow clinical graph construction with typed nodes and relations;
- deterministic clinical-weighted graph evaluation with safety caps;
- student, teacher, administrator, and expert-review workspaces;
- RAG, graph-quality, and expert-agreement benchmark exports.

## Model roles and scoring

The reported research configuration uses OpenAI models. GPT-5.1 supports
schema-constrained task/reference generation and validation assistance.
`text-embedding-3-small` supports semantic retrieval and concept matching.
The final graph score is calculated by the versioned evaluation algorithm; it
is not assigned directly by a language model.

The runtime router retains optional Gemini compatibility for deployments that
configure it explicitly; the documented and evaluated configuration is
OpenAI-first.

Generated reference graphs are drafts. A competent teacher or clinical expert
must inspect, edit, approve, and publish them before student use.

## Repository structure

```text
backend/                 FastAPI API, evaluator, RAG services, migrations
backend/benchmarks/      benchmark seeds and de-identified research artifacts
backend/scripts/         data preparation and reproducibility commands
backend/tests/           evaluator, retrieval, and validation tests
frontend/                Nuxt 3 / Vue Flow user interface
docs/                    research methods and validation documentation
```

## Local setup

Requirements: Python 3.10+, Node.js 20+, PostgreSQL 15+ with pgvector.

```powershell
Copy-Item .env.example .env
Copy-Item backend/.env.example backend/.env
docker compose up -d db

cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --port 8012
```

In a second terminal:

```powershell
cd frontend
npm ci
$env:NUXT_PUBLIC_API_BASE = "http://127.0.0.1:8012"
npm run dev
```

Open `http://localhost:3008/medical/`.

OpenAI-dependent features require a valid `OPENAI_API_KEY` in
`backend/.env`. Never commit production credentials.

Demo accounts are local fixtures. Their credentials are shown only when
`NUXT_PUBLIC_SHOW_DEMO_CREDENTIALS=true`; do not seed or expose these accounts
in production.

## Verification

```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q

cd ../frontend
npm run typecheck
npm run build
```

Research design, artifact provenance, model boundaries, and benchmark
limitations are documented in [docs/research_validation.md](docs/research_validation.md).

## Data governance

The repository must not contain patient data, signed consent forms, expert
contact details, production database dumps, credentials, or private deployment
configuration. Public expert-validation exports use cohort-local identifiers
such as `E1`..`E5`; the re-identification mapping is not exported.

All published expert-validation numbers are computed directly from the platform
database (`validation_ratings`), the single source of truth.

## License

No open-source license is granted at this stage. Public source availability is
provided for research review and reproducibility; contact the maintainers about
reuse or redistribution.
