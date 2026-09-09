# RE:SCENE

**A second look at the story.**

RE:SCENE is a film discovery and discussion app that separates what you can see at your current viewing position from what becomes meaningful after the ending. It combines a React interface, a FastAPI backend, stored scene evidence, and Google Gemini integrations.

## Features

- **Progress-aware analysis:** only completed input segments are available before the end of a film.
- **Retrospective readings:** revisit scenes with timestamped observations and alternative interpretations after finishing.
- **Evidence-linked exploration:** connect interpretations to scene records and available reference frames.
- **Film discovery and community:** browse films, manage viewing progress, and discuss readings behind spoiler gates.
- **English and Korean interface.**

## Run locally

Requirements: Python 3.11+, Node.js 22+, and npm. Run commands from the repository root with a Python virtual environment activated.

```sh
git clone https://github.com/Koreahwan/re-scene.git
cd re-scene
python -m venv .venv
```

Activate with `source .venv/bin/activate` on macOS/Linux, or `.venv\Scripts\Activate.ps1` in Windows PowerShell. Copy `.env.example` to `.env`, then:

```sh
python -m pip install -e ".[dev]"
npm --prefix apps/web ci
npm --prefix apps/web run build
python -m scripts.seed_demo
python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

Open [localhost:8000](http://localhost:8000). API documentation is at [/docs](http://localhost:8000/docs), and the liveness endpoint is [/live](http://localhost:8000/live).

The local profile uses SQLite and stored analysis without paid model calls. The demo command registers the film catalog and two evidence-linked readings for *The Bat Whispers*. It can use an in-memory cache when Redis is unavailable. Accounts and community activity start from a fresh local database; production user data is not included.

For frontend development, run `npm --prefix apps/web run dev` alongside the API server. The development server proxies `/api` to port 8000.

### Docker preview

```sh
docker compose up --build
```

The preview binds to `127.0.0.1:8000`, includes Redis, and leaves paid generation disabled. Its database is disposable container state. To register the demonstration readings, run `python -m scripts.seed_demo` inside the application container. The container image has not been end-to-end validated for this release. It is not a production deployment configuration.

## Configuration

See [.env.example](.env.example) and [`Settings`](src/reframe/shared/config.py). Runtime model integrations use Google Gemini through the Google Gen AI SDK and Google ADK; narrative retrieval supports ClickHouse through the official `mcp-clickhouse` package.

Live generation is optional and requires separately configured Google credentials, model access, retrieval services, and the existing budget controls. Do not enable paid calls just to browse the included dataset. Keep credentials server-side and out of version control.

Production deployment additionally requires unique authentication secrets, secure cookies, real email delivery, database migrations, Redis, and the retrieval/worker services needed by the chosen features. `/ready` checks those dependencies; local liveness does not imply production readiness.

## Tests

```sh
python -m pytest tests/security tests/unit -q
npm --prefix apps/web run build
```

Ordinary Python tests use isolated databases and block model generation. Optional integration suites require their own services and fixtures. The broad suite currently has known failures, including older authentication expectations and checks requiring private database, design, or deployment fixtures omitted from this source release; a passing frontend build does not mean the complete Python suite passes.

## Data and limitations

The repository contains stored demonstration analysis and test fixtures, not complete film files, credentials, production databases, or user uploads. Full-video playback requires separately supplied, appropriately licensed media.

Included interpretations may be AI-generated or AI-edited. They are exploratory readings, not independently established facts or human-reviewed conclusions. Provenance, evidence boundaries, and review-status fields are retained in the data.

Source code is licensed under [Apache-2.0](LICENSE). Third-party media, fonts, metadata, and datasets have separate terms; see [DATA_LICENSES.md](DATA_LICENSES.md).
