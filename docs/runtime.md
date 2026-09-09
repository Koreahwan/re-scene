# Runtime setup and verification

The default preview reads the bundled analysis and makes no paid calls. That
preview is not evidence of a live Google or ClickHouse invocation. Use the
explicit profiles below to exercise the integrations with your own services.

## ClickHouse: existing server or optional local server

ClickHouse Cloud is optional. An existing self-hosted server also works. Runtime
queries use the official `mcp-clickhouse` server through `fastmcp.Client`; the
bootstrap command uses an administrative connection only to initialize data.

Requirements: the Python environment from the README, access to a ClickHouse
server, a bootstrap account with schema/insert privileges, and a distinct runtime
account restricted to SELECT on `reframe.*`. Never use the bootstrap account in
the web application. Do not expose database ports publicly.

For a local server, set `CLICKHOUSE_BOOTSTRAP_USER` and
`CLICKHOUSE_BOOTSTRAP_PASSWORD` to your chosen administrator identity in your
shell, then start the optional service:

```sh
docker compose -f compose.clickhouse.yaml up -d
```

This stores data in a named volume and exposes HTTP only on
`127.0.0.1:18123`. Do not remove the volume if you need to keep the data.

Configure the application's `.env`:

```dotenv
CLICKHOUSE_HOST=127.0.0.1
CLICKHOUSE_PORT=18123
CLICKHOUSE_DATABASE=reframe
CLICKHOUSE_USER=reframe_runtime
CLICKHOUSE_PASSWORD=REPLACE_WITH_YOUR_RUNTIME_PASSWORD
CLICKHOUSE_SECURE=false
CLICKHOUSE_VERIFY=true
CLICKHOUSE_ALLOW_WRITE_ACCESS=false
NARRATIVE_MEMORY_BACKEND=OFFLINE_FILE
CLICKHOUSE_PUBLICATION_ID=
```

For ClickHouse Cloud, use the endpoint and TLS port supplied by that service and
set `CLICKHOUSE_SECURE=true` and `CLICKHOUSE_VERIFY=true`. Do not copy the local
non-TLS values to a Cloud deployment. Containerized apps must use a reachable
database hostname, not their own loopback address.

Keep `CLICKHOUSE_BOOTSTRAP_USER` and `CLICKHOUSE_BOOTSTRAP_PASSWORD` in the shell
environment of the initialization command only. They are intentionally not
application Settings fields and must not be committed or baked into an image.

First inspect the offline plan, then explicitly apply it:

```sh
python -m scripts.initialize_clickhouse
python -m scripts.initialize_clickhouse --apply
```

The command creates missing tables and inserts the repository's source-attributed
analysis. It refuses conflicting existing rows, never deletes records, and
verifies the inserted values. Repeating a completed initialization inserts zero
additional records. If interrupted, inspect the result and rerun the same approved
input; do not use the older destructive dataset-refresh loader as a substitute.

Expected input counts for the included publication:

| Table | Records |
|---|---:|
| films | 1 |
| scenes | 43 |
| events | 187 |
| facts | 94 |
| reveals | 4 |
| knowledge_states | 10 |
| analysis_segments | 58 |
| analysis_publications | 3 |

The canonical narrative rows describe The Bat Whispers. Independent analysis
segments cover the three included editions. Inferred knowledge remains labeled
as inferred; bootstrap does not turn generated content into human-reviewed facts.

Before enabling the app, use your server's administrative interface to create
the separate runtime identity with a unique password and minimum permissions:

```sql
CREATE USER reframe_runtime IDENTIFIED WITH sha256_password BY 'REPLACE_WITH_YOUR_RUNTIME_PASSWORD'
SETTINGS readonly = 1;
GRANT SELECT ON reframe.* TO reframe_runtime;
```

For an existing runtime identity, inspect its grants instead of recreating or
resetting it. The loader deliberately does not execute the old schema file's
passwordless user-creation block. Configure the runtime password above to match
the account you actually created, then remove bootstrap credentials from the
web application's environment.

Set `NARRATIVE_MEMORY_BACKEND=CLICKHOUSE_MCP` and copy the exact `publication_id`
printed by initialization to `CLICKHOUSE_PUBLICATION_ID`. Restart the API.
Keep the Google paid-call switches disabled while validating retrieval.

## Verify the deployed retrieval path

Open a supported film, save a viewing position, and request its
`/api/v1/films/{movie_id}/selected-portion-analysis?edition_id={edition_id}`
endpoint in the same browser session. The response's `meta` must report
`source: CLICKHOUSE_MCP`, `tool: run_query`, two MCP queries and the pinned
publication ID. At the beginning, an empty segment list is expected; after a
complete input segment has been watched, it must contain the matching observations.

The backend fetches only completed segments and checks payload hashes and
per-edition timing boundaries. A missing publication, missing expected records,
checksum mismatch or unavailable MCP server returns 503. It must not silently
substitute the local file. Test dependency failures in an isolated test instance,
not by stopping a shared production database.

Run the focused zero-cost regression tests:

```sh
python -m pytest tests/unit/test_clickhouse_publication.py tests/unit/test_selected_portion_analysis.py -q
```

These unit tests use controlled test doubles. They verify behavior but do not,
by themselves, certify a real database or Google call. Preserve a separate
runtime receipt from the actual deployed system.

## Google Cloud authentication and paid execution

Use your own Google Cloud project, with the relevant API and billing enabled,
appropriate model access, and an identity permitted to invoke that model. Follow
[Google's ADC setup instructions](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/start/gcp-auth).
For local development, the supported ADC login is:

```sh
gcloud auth application-default login
```

This is an interactive authentication step, not a repository-provided credential.
On servers, provision an approved workload identity or securely mounted
credential configuration for that workload. Do not copy a personal login token
into a public repository or an image. The application/worker also needs outbound
HTTPS access to Google; an egress-free database network alone is insufficient.

Configure project and a location supported by the selected model. The guarded
generation path explicitly uses a Vertex client. Client construction or finding
a project name is not proof of an authenticated model call.

For Gemini 3.6 Flash, use `global`, `us`, or `eu` per Google's
[deployment support table](https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/locations).
`us-central1` is not a supported generation endpoint for this model, even when
model-metadata lookup succeeds. The default is `global`; override any old `.env`
or deployment setting explicitly. The guard rejects unsupported locations before
claiming or sending a generation request. Global token rates differ from
multi-region rates and are selected using the configured location.

Only for an authorized, budgeted generation worker:

```dotenv
GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
GOOGLE_CLOUD_LOCATION=global
GOOGLE_GENAI_USE_VERTEXAI=true
EXECUTION_MODE=LIVE_GOOGLE
PAID_CALLS_ENABLED=true
SPEND_KILL_SWITCH_ACTIVE=false
LIVE_AGENT_ENABLED=true
MAX_MODEL_CALLS_PER_ANALYSIS_RUN=1
```

Do not apply these switches to unrestricted public browsing. The existing
administrative analysis-run endpoint requires authentication, CSRF protection,
an idempotency key, a persisted run/owner, an active budget reservation and a
worker. Google execution additionally requires verified MCP evidence. Any live
test must preserve those controls and use current, verified model pricing.

The raw-media intake command is a separate offline operator workflow. It requires
appropriately licensed local media chunks, frame files and matching manifests;
those full media files are not bundled. Its project is configurable:

```sh
python -m scripts.analyze_sound_films --inputs PATH_TO_PREPARED_MEDIA --output outputs/intake --project YOUR_PROJECT_ID --location global
```

Without `--execute-paid`, this plans only. Do not add that option without an
explicit budget and checking the prepared inputs; this is not the small text-only
integration smoke test. Existing historical generation receipts are not a fresh
hosted-runtime test.

Use the separate runtime verification entrypoint, not the old `tests/paid_live`
suite (which inherits the ordinary test suite's zero-cost safeguards):

```sh
python -m scripts.verify_live_services --project YOUR_PROJECT_ID --location global --output outputs/runtime-preflight
```

This performs real official-MCP retrieval and checks Google authentication. It
does not generate text. `PREFLIGHT_COMPLETE_GENERATION_NOT_TESTED` is explicitly
not proof of a paid invocation. Missing credentials produce a nonzero exit and
`BLOCKED_GOOGLE_AUTH`.

Only after approving a paid test and checking the budget, use a **new** output
directory and an explicit cap (the example reserves at most USD 0.50):

```sh
python -m scripts.verify_live_services --project YOUR_PROJECT_ID --location global --execute-paid --budget-usd 0.50 --output outputs/runtime-paid-check
```

The command reads an actual completed observation segment through MCP and uses
the guarded Google integration to create a short reading grounded in that input.
For this short verification role, it explicitly selects `MINIMAL` thinking and
allows up to 8,192 output tokens, with conservative cost reservation before the
call. Other analysis roles retain their normal thinking behavior. A 2,048-token
shared thinking/output cap previously truncated the JSON and failed validation;
the output was not repaired or falsely accepted as a complete response.
It permits one model call, does not automatically retry, and creates its journal
under the output directory instead of changing the application's user database.
It refuses to reuse an existing output directory or silently return a cached
success. Only `LIVE_SERVICES_VERIFIED` confirms both service calls in this
operator workflow. This does not claim that a new paid call happened on every
public page view or that a generated reading was automatically published.

The receipt includes source evidence identifiers, timestamps, output hash, actual
SDK token usage, and settled budget/claim state. Provider response IDs are retained
when returned; missing IDs are never invented. Estimated token cost is not a
provider invoice. A missing usage record fails validation rather than substituting
an estimated token count. After uncertain failures, retain the journal and inspect
the claim before authorizing another attempt.

## Submission evidence

Record the actual deployed source/image version, initialization receipt,
nonempty official-MCP retrieval, and the separately authorized Google execution
receipt. Show the app using the resulting data. Distinguish cached generation
from current database retrieval and from a newly executed paid invocation.
Neither a README mention nor a successful `SELECT 1` alone demonstrates the
complete feature.

### Observed deployment checks — September 10, 2026 (KST)

- The deployed analysis route completed 18 real retrieval scenarios across three
  films. A separate real narrative search returned five candidates.
- A nonempty preflight retrieved `chunk-001` through two official MCP queries.
  The publication was
  `d60a829a4ddbb59d2e91a639002401b62dcf0205a3d8a501015431a3a006f6fb`.
- The isolated dependency-failure check returned an error without an offline
  fallback. Existing hosted account and community records were unchanged.
- The public-source candidate passed 74 focused unit and cost-guard tests and its frontend
  production build. These are not a claim that the entire test suite passes.
- Hosted Google preflight returned `BLOCKED_GOOGLE_AUTH`; no paid generation
  occurred during these checks. A valid local login is not a server credential
  deployment and does not prove access to the chosen model.
- A subsequent authorized local worker passed real MCP retrieval and Google
  authentication. Its one generation attempt returned `ClientError`; the claim
  remains `NEEDS_RECONCILIATION`, with no successful usage ledger entry. This
  does not establish zero provider charges. There was no automatic retry and
  the Google credential was not copied to the server. Vertex API enablement
  and model metadata were checked independently, but do not prove generation.
- A separately approved attempt captured `404 NOT_FOUND` for generation at
  `us-central1`. Correcting the endpoint to `global` resolved that error.
  The first global response exhausted its shared output budget; a further
  separately authorized check used the corrected verification settings and
  completed successfully. No attempts were automatically retried.
- The successful check returned `LIVE_SERVICES_VERIFIED`, cited `chunk-001`,
  used 467 input tokens, 148 output tokens and zero thinking tokens, and settled
  its budget with a successful claim. Its estimated token cost was USD 0.000905;
  this is not a provider invoice or a statement about charges for earlier
  unsuccessful attempts. See [the sanitized receipt](runtime-verification-20260910.json).
- Direct operator execution exposed an internal import-path problem hidden by
  pytest's path configuration. The verification command now resolves that path
  explicitly, with a subprocess regression test independent of pytest's path.

These observations are dated evidence, not a permanent availability guarantee.
The public source intentionally omits the operator's default Google project;
configure your own project explicitly before running the verification command.
