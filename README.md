# RE:SCENE

**A second look at the story.**

RE:SCENE is a film discovery and discussion app that separates what you can see at your current viewing position from what becomes meaningful after the ending. It combines a React interface, a FastAPI backend, stored scene evidence, and Google Gemini integrations.

[Open the hosted app](https://hermes-agent-a1.tail5317ee.ts.net:10000/).
The hosted film-analysis endpoint reads stored observations from ClickHouse
through the official MCP integration. Browsing does not trigger paid generation.

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

The offline preview does not demonstrate live service use. See [runtime setup and verification](docs/runtime.md) for ClickHouse initialization, read-only official-MCP delivery, Google credentials, and the separate budgeted generation workflow. Do not enable paid calls just to browse the included dataset. Keep credentials server-side and out of version control.

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

## Findings and lessons learned

- A working offline preview does not prove that an external integration runs.
  We added explicit database initialization, runtime source metadata, and a
  separate verification command rather than treating installed SDKs as evidence.
- Spoiler boundaries must follow the end of the source input, not just the
  timestamp assigned to an interpretation. Retrieval checks the saved viewing
  position before returning each completed analysis segment.
- A failed database dependency must remain visible. The live retrieval profile
  returns an error instead of silently substituting a bundled file.
- Account and community records remain in PostgreSQL on the hosted service;
  ClickHouse serves narrative evidence and analysis. The local preview uses
  SQLite for account and community data.
- Generated observations need explicit provenance and review labels. Source
  attribution does not by itself grant redistribution rights to third-party media.

On September 10, 2026 (KST), an authorized local worker retrieved a real completed
segment through official ClickHouse MCP and successfully generated a complete
Google Gemini reading with source IDs, SDK usage and a settled budget record.
See [verification evidence](docs/runtime-verification-20260910.json) and
[runtime setup](docs/runtime.md). Google credentials remain on the operator's
machine; ordinary hosted browsing uses stored analysis and does not generate a
new response on every page view. This does not certify all submission or
third-party media-rights requirements.
