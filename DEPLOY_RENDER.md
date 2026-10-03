# Free Render Demonstration

The default `render.yaml` defines exactly one **free web service**. It creates no
PostgreSQL database, worker, cron job, or persistent disk. Service creation is a
manual owner action in Render; nothing in this repository provisions resources.
Automatic deploys and previews are disabled. Local `python start_all.py` retains
its existing port, refresh, browser, and build defaults.

SQLite reviews, users, sessions, audit records, jobs, and runtime files are
**ephemeral**. They reset on redeploy or instance replacement. A free service
sleeps after inactivity and may take time to wake. Treat all demo state as
disposable; do not promise persistence across sleep/wake. Committed public feed
snapshots remain image assets and are only updated by rebuilding the image.
There is no automatic refresh, worker, scheduler, browser opening, or Node build
at startup. Refresh requests have no executor in this demo and should remain
disabled; the launcher forces `JOBS_ENABLED=false` and disables the scheduler in
demo mode. Keep `THERMAL_REFRESH_PROVIDER` unset.

Render documents these limitations in [Free Services](https://render.com/docs/free).
The 512 MB free instance may struggle with the geospatial Streamlit app; memory
and cold-start behavior require a real hosted demonstration to assess.
The public UI and API run without executing the Streamlit application script.
An authenticated console session imports geospatial/numerical libraries and may
use much more memory; pipeline runs are explicit console actions, not startup
actions. The container caps OpenMP/OpenBLAS/MKL/NumExpr at one thread to limit
oversubscription, which is not proof of fitting into 512 MB. The gated console is
retained to meet the combined-service requirement. The smallest alternative is
a public static UI/API service with console disabled, if the owner later chooses
that scope; it requires integration changes and is not implemented here.

## Build And Run

The image pins Node `24.11.0-bookworm-slim` and Python
`3.13.7-slim-bookworm`. Node 24 matches the existing Pages workflow and the globe's
Vite 8/TanStack build. `npm ci` uses the checked-in lockfile. The Node stage builds
once with `BASE_PATH=/globe/`; Python assembles `site/` and the globe into `_site/`.
There is no Node runtime in the final image. Python wheels and the PostgreSQL
driver come from backend-owned `requirements-server.txt`, which includes the
unchanged `requirements.txt`. `pip check` is part of the image build; the Linux
runtime includes `libgomp1` for numerical dependencies. Exact base tags are
deliberate pins, not a claim that they are the newest security releases.

```sh
docker build --tag thermal-demo .
docker run --rm --publish 10000:10000 --env THERMAL_DEMO_MODE=true \
  --env THERMAL_ADMIN_PASSWORD thermal-demo
```

For `docker run`, export a unique `THERMAL_ADMIN_PASSWORD` in the calling shell
first; `--env NAME` forwards it without putting its value in this command.
Use at least 12 characters. Do not put secrets in build arguments or image layers.
The image runs as UID 10001. `.dockerignore` excludes environment files, Streamlit
secrets, local databases, output, cached/private data, environments, and generated
builds. `models/classifier.pkl` is the one permitted pickle asset; repository
reference data and public globe JSON exports are deliberately included.

Manually connect the repository as a Blueprint in Render, review the plan as
**Free**, supply the admin password at creation, and apply only this one service.
The snapshot demo needs no FIRMS key; `FIRMS_API_KEY` is deliberately absent from
the default Blueprint. Add it manually in Render only for an explicitly enabled
live refresh workflow. The admin password uses `sync: false` and never appears
in the YAML. For an existing service, add new secrets manually in
the dashboard because `sync: false` only prompts at initial creation.
See [Blueprint Reference](https://render.com/docs/blueprint-spec).
This task does not commit, push, deploy, or create services.

## Cloud Contract

| Variable | Contract |
| --- | --- |
| `CLOUD_MODE` | Launcher forces `true`; gateway/config/app must honor it. |
| `THERMAL_DEMO_MODE` | Blueprint sets `true`, allowing SQLite with no `DATABASE_URL`. |
| `JOBS_ENABLED` | Forced `false` in demo mode; opt in only for future worker deployments. |
| `PORT` | Render public port, default 10000; gateway binds `0.0.0.0`. |
| `GLOBE_URL` | Launcher forces public relative `/globe`. |
| `GATEWAY_DASH_PORT` | Launcher-selected private loopback port shared by both children. |
| `GATEWAY_SITE_DIR` | Default `/app/_site` in the image. |
| `GATEWAY_GLOBE_DIR` | Default `/app/_site/globe`. |
| `GATEWAY_GLOBE_DATA_DIR` | Default `/app/_site/globe/data`, immutable public seed data. |
| `THERMAL_DATA_DIR` | Default `/var/lib/thermal/data`; config must honor it. |
| `THERMAL_OUTPUT_DIR` | Default `/var/lib/thermal/output`; config must honor it. |
| `THERMAL_SERVER_DB` | Default `${THERMAL_DATA_DIR}/server.db`, SQLite demo state. |
| `DATABASE_URL` | Omit for demo. PostgreSQL required when demo flag is false. |
| `THERMAL_ADMIN_USERNAME` | Defaults to `admin`; creates/uses a backend admin user. |
| `THERMAL_ADMIN_PASSWORD` | Required, 12-1024 characters, supplied as a runtime secret. |
| `ALERT_AUTO_DISPATCH_CRITICAL` | Launcher forces `false`. |
| `ALERT_AUTO_ESCALATE_CALL` | Launcher forces `false`. |

Streamlit binds **only** `127.0.0.1`, with `--server.baseUrlPath console` and
headless mode. The gateway owns all public HTTP and WebSocket access. `/` serves
the public static workspace; `/globe/` serves the built globe. Every `/console`
HTTP/WebSocket route must require Basic credentials backed by an active backend
user with **admin** role, including assets and Streamlit internal endpoints.
Never forward the Authorization header upstream or expose database/private files.

The gateway uses Render's automatically supplied `RENDER_EXTERNAL_URL` for console
Origin checks and external redirects, even when the private hop uses HTTP.
For a custom domain, explicitly set `PUBLIC_ORIGIN=https://your-domain` to its
registered origin. Do not set `FORWARDED_ALLOW_IPS=*` on a directly exposed server.
See [Render's declared public URL](https://render.com/docs/environment-variables).

The gateway must implement `Config.cloud_mode`; the launcher refuses the old
local-only gateway. This compatibility guard is not an auth audit. Gateway health
must request `http://127.0.0.1:<private-port>/console/_stcore/health`, verify the
static site/globe and usable backend, and return `200` with `{"ready": true}` only
when ready, otherwise `503`. Merely opening a TCP socket is insufficient.
The launcher exits nonzero on readiness timeout or either child dying. SIGTERM
and SIGINT stop both children, then kill/reap unresponsive processes.

`app.py` trusts the configured `GLOBE_URL` and renders `/globe` directly in its
iframe branch; this branch does not call `_holo_app_reachable`, so no relative
reachability-probe fix is needed. Bootstrap credentials do not rotate an
existing database user's password; use the backend's explicit password update
method for paid deployments. Recreated demo storage reboots the admin account.

## Optional Paid Architecture

This is a future, separately authorized choice. It is **not** in the default
Blueprint and must not be provisioned automatically. Review current plans and
costs before manually changing the architecture. Use a paid web service,
PostgreSQL, a background worker, and an enqueue-only cron job in the same region.
Set `THERMAL_DEMO_MODE=false` and inject the same PostgreSQL `DATABASE_URL` into
all three processes. Do not use SQLite for production or assume disks are shared
between Render services. Local data/output paths remain scratch space unless
explicitly configured otherwise; database state is the durable shared contract.

| Service | Command / Setting |
| --- | --- |
| Web | `python cloud_launcher.py` |
| Worker | `python -m src.server.worker` |
| Cron | `python -m src.server.scheduler --scope national --scope global --period 21600 --once` |
| Cron schedule | `17 */6 * * *` (UTC, every six hours) |

Worker/cron require `JOBS_ENABLED=true`, `THERMAL_REFRESH_PROVIDER=firms`, the admin bootstrap username
and password, and the shared database. Cron additionally requires
`THERMAL_SCHEDULER_ENABLED=1`; it only enqueues deduplicated jobs and exits. The
current worker requires `FIRMS_API_KEY` even for global jobs; the key is optional
in the free web demo. Each paid service needs its own runtime secret injection.
Disable automatic deploys/previews until explicitly selected by the owner.

**Shared snapshot publication is not implemented by the current backend.** The
worker invokes scripts that write pickle/SQLite history and globe JSON into its
own filesystem. Database jobs alone do not make those exports visible to web.
Before enabling separate paid workers, backend/integration must store national
and global public snapshot payloads in PostgreSQL (or explicitly selected shared
storage), publish atomically with generation/fencing checks, and expose them
through web API/globe data routes. Snapshot failure must preserve the previous
valid publication and report its timestamp/staleness. No service file sharing.
National accumulated detection history also needs a durable shared contract.

## Verification And Cross-Review

Run `python -m pytest tests/test_cloud_launcher.py -q` for mocked process/signal,
port, readiness timeout, demo/production database policy, startup failure and
cleanup regression checks. Tests neither contact services nor run refresh/build.
Verify the image on Linux with `docker build` and the run command above, then
check health before and after stopping Streamlit, unauthenticated HTTP/WebSocket
console rejection, analyst rejection, valid admin console assets, relative globe
links, and demo reset after replacement. A persistent PostgreSQL restart/worker
test applies only after the paid shared-snapshot contract is implemented.

Cross-review initially found gateway/backend state and authentication method
mismatches. The backend now exposes both `state.backend`/`state.server` and the
`authorize_admin_basic` alias; integration installs API routes ahead of catch-all,
handles auth rejection and closes the backend in lifespan. Authentication checks
the persisted active admin role, and successful console assets do not consume
the failed-login limit. Initial gateway/backend regression suites passed, but
concurrent integration edits require the main agent's final test run.
Cloud gateway health now requests the private `/console/_stcore/health` endpoint
with a two-second timeout and requires HTTP 200 with body `ok`; local TCP
compatibility remains unchanged. Public site, globe and database failures yield
503 readiness. Code integration is complete for this demo contract; deployment
and container verification remain pending. Shared public snapshot publication
remains unsupported; see the paid architecture prerequisite.

The integration-owned `.github/workflows/ci.yml` now builds the Docker image on
Linux and runs the demo with a 512 MB memory limit. Its smoke test checks ready
health, public investigations/feed routes, anonymous console rejection, secret
file rejection and anonymous review-write rejection. This workflow has not run
as part of this local task. It does not open an authenticated console session or
execute a pipeline; passing it will establish public startup within that limit,
not the console's peak memory use. Assemble uses only standard-library modules
and imports neither `config` nor pipeline modules. The runtime copies cover
gateway/backend, Streamlit app/config, both launchers, refresh/assemble scripts,
reference data, the permitted classifier asset and assembled public assets.

The Python 3.13 Linux x86_64 binary-wheel dependency resolution dry run passed
for `requirements-server.txt` using manylinux 2.28/2014 targets. This resolves
available wheels without installing or importing them in a Linux container.
Docker CLI/Desktop and an installed WSL Linux distribution are unavailable on
the authoring machine; an actual Linux Docker build, hosted Render smoke test,
and PostgreSQL verification have not been completed here. Python regression tests
run in the existing Python 3.13 environment. Do not treat these checks as proof
that every pinned requirement has an installable Linux wheel or that the free
instance has sufficient memory.
