# RE:SCENE

**A second look at the story.** [Open the app](https://hermes-agent-a1.tail5317ee.ts.net:10000/)

An English-language film discovery and discussion app built with React, FastAPI, Google Gemini and official ClickHouse MCP. Explore completed scene segments at your viewing position, revisit post-ending readings, and open spoiler-blurred comments or replies individually after a warning.

Stored analysis covers *The Bat Whispers*, *The Greene Murder Case* and *The Thirteenth Chair*. The wider catalog does not imply analysis or playback for every film. Hosted browsing retrieves stored analysis; it does not generate a paid response per page view.

## Local preview

Recommended: Python 3.11 and Node.js 22. From the repository root:

```sh
python -m venv .venv
# Activate: source .venv/bin/activate (macOS/Linux)
# PowerShell: .venv\Scripts\Activate.ps1
# Copy .env.example to .env, then:
python -m pip install -e ".[dev]"
npm --prefix apps/web ci
npm --prefix apps/web run build
python -m scripts.seed_demo
python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

Open [localhost:8000](http://localhost:8000); API docs: [/docs](http://localhost:8000/docs). The preview uses SQLite, stored analysis and no paid calls. Seeding adds two demonstration readings without replacing existing ones. For UI development, run `npm --prefix apps/web run dev` alongside the API and open port 5173.

Local registration does not send email: enable `AUTH_DEV_OUTBOX_VIEWER_ENABLED=true` in `.env`, restart, and read requested codes at `/api/v1/dev/auth/outbox`. Use only on your loopback development server; disable afterward.

Docker alternative: `docker compose up --build`, then `docker compose exec app python -m scripts.seed_demo`. Includes Redis, but not ClickHouse; SQLite is disposable, and the root `.env` is not forwarded to the container. This is a preview, not production configuration.

## Verification and integrations

```sh
python -m pytest tests/unit/test_comment_explicit_reveal.py tests/unit/test_clickhouse_publication.py tests/unit/test_selected_portion_analysis.py tests/unit/test_live_service_verification.py -q
npm --prefix apps/web run build
```

These tests block paid generation. The broader suite has known failures and private-fixture dependencies. See [runtime setup and dated results](docs/runtime.md) for ClickHouse bootstrap, Google credentials, production requirements and separately budgeted execution. A [September 10 verification receipt](docs/runtime-verification-20260910.json) records real MCP retrieval and one successful local Gemini call, not continuous hosted generation.

## Data and lessons

Analysis may be AI-generated or AI-edited, not independently human-verified. Full films, credentials and production user data are not included. Spoiler boundaries follow input-segment endings; explicit comment consent is separate from AI inspection. Offline success alone does not prove external-service use.

Code: [Apache-2.0](LICENSE). Media, fonts, metadata and optional synthetic persona data have separate terms: [data and asset notices](DATA_LICENSES.md).
