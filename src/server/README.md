# Backend foundation

Free demonstration storage is ephemeral SQLite (`data/server.db`) by default.
Reviews, users, sessions, audit and jobs survive process restarts only while that
file survives. Free-host redeployment can erase it. No separate worker is needed
or automatically started. PostgreSQL is optional future infrastructure, not a
claim of free persistent hosting.

Install `requirements-server.txt`, which includes the unchanged base requirements
and psycopg 3. Set `DATABASE_URL` to a PostgreSQL URL or `sqlite:///path/to/db`;
alternatively set `THERMAL_SERVER_DB`. The default uses `THERMAL_DATA_DIR/server.db`
when `THERMAL_DATA_DIR` is set. SQLite uses the standard library. Numbered
migrations run transactionally on construction; newer schemas are rejected.

## Gateway contract

```python
from src.server import Backend, install_backend
backend = Backend.from_env()
install_backend(app, backend)  # before startup, ahead of gateway catch-all
# app.state.backend and app.state.server both refer to backend
actor = await backend.authorize_admin_basic(header, client_key=client_ip)
# or await backend.authenticate(request_or_websocket): Bearer or Basic
backend.require_role(actor, "admin")
backend.ready()  # DB probe; False if credentials absent, DB errors propagate
backend.close()  # gateway's existing lifespan finally block
```

`create_server(backend=None)` builds a standalone Starlette app with its own
closing lifespan. `backend.get_routes(prefix="/api")` builds directly usable
routes. Body bounds, rate checks and authorization are inside the endpoints;
gateway middleware is not required for those routes. Gateway console HTTP/WS
must handle HTTPException and reject before proxying or accepting a socket.
Use TLS externally. Do not forward Authorization to Streamlit or publish DB files.

Both `THERMAL_ADMIN_USERNAME` and `THERMAL_ADMIN_PASSWORD` (12-1024 characters)
are required on every startup. Missing either disables all secured routes (503),
even if users already exist. Bootstrap inserts only when absent; changing the env
password does not reset existing users. `backend.create_user(username,password,
role)` is an explicit local administration method, also for password rotation;
it revokes that user's sessions. There is no public registration endpoint.

## API

- `POST /api/auth/login`: JSON `{username,password}` returns `{token,actor,role,
  expires_at}`. Actor contains username, role and expiry.
  Send `Authorization: Bearer TOKEN`.
- `GET /api/auth/me`: `{actor}`. `POST /api/auth/logout`: JSON `{}`, revokes token.
- `GET /api/reviews/{event_id}?scope=india|global`: authenticated; missing review
  has version 0. `PUT` accepts `{version,review:{notes,bookmarked,status,...}}`.
  Review fields are optional; status is unreviewed/investigating/reviewed.
  Optional evidence fields are `assessment` (unresolved/industrial_heat/
  suspected_fire/agricultural_burning/false_positive), `supportingSources`
  (up to 8 safe HTTP(S) URLs or text strings, 2048 characters each), `uncertainty`
  (1000 characters), and `assessedAt` (calendar-valid, timezone-qualified ISO time,
  seconds required, optional 1-3 fractional digits, or null). Non-unresolved
  assessments require sources, nonblank uncertainty and assessedAt. These fields
  persist in the review payload and audit without changing the DB schema.
  Reviewed is workflow status only; assessments do not become training truth.
  Analyst/admin may write; stale version returns 409. Scope defaults to india.
  Each write and audit row commit together. Reviews are analyst annotations,
  not verified evidence. Event existence is not checked against changing feeds.
- `POST /api/jobs`: admin Bearer only, JSON `{scope:"national"|"global"}` and
  `Idempotency-Key` header (1-128 characters). Set `THERMAL_REFRESH_PROVIDER=firms`
  and `JOBS_ENABLED=true` only when an explicit local worker is configured to
  enable queue requests. Default jobs API returns 503 (execution unavailable).
  Reusing a key returns the original job; conflicting
  actor or scope returns 400. `GET /api/jobs/{id}`: admin only.

All API mutations except login require Bearer credentials; Basic is for the
console and authenticated reads. Default streamed body cap is 65536 bytes
(`THERMAL_BODY_LIMIT`), API rate 120/minute/IP (`THERMAL_RATE_LIMIT`), login and
Basic rate 10/minute/IP (`THERMAL_LOGIN_RATE_LIMIT`), session TTL 28800 seconds
(`THERMAL_SESSION_SECONDS`). Limits are persisted fixed-window counters; trusted
proxy headers are not used. Clients behind one proxy may share limits. Basic
failures count toward the guessing limit; successful console asset and WebSocket
authentication does not consume it. No CORS or
browser cookies are enabled. Secrets/tokens are never returned from job status.

## Explicit local execution

`python -m src.server.worker --once` processes at most one queued job. Without
`--once` it polls until SIGINT/SIGTERM. It requires configured admin bootstrap,
`JOBS_ENABLED=true`, `THERMAL_REFRESH_PROVIDER=firms` and `FIRMS_API_KEY`, and can execute only the two
existing refresh scripts. It does not invoke alert dispatch. Scripts run with a
30-minute timeout; output is discarded to avoid leaking provider credentials.
Queue depth is limited to 100 pending jobs; expired leases retry up to 3 claims.
Claims serialize all refreshes with a 120-second lease and renewable heartbeat.
Stale tokens cannot update job status. Providers must tolerate replay after a
crash: enqueue is idempotent, but external refresh effects are at-least-once.
A killed host can leave a child alive until its OS reaps it; DB fencing alone
cannot fence provider filesystem writes. Use a supervisor that kills process
trees before recovery. Never run workers on different machines against local
output directories and assume the web sees their exports. A future separate
worker requires shared snapshot storage/publication and provider-side fencing.
That storage and publication are not implemented here; PostgreSQL alone does
not make worker-generated files available to the web process.

`THERMAL_SCHEDULER_ENABLED=1 python -m src.server.scheduler --scope national
--period 3600` explicitly enables enqueue only, deduplicated per period. Minimum
period is 300 seconds. Add `--once` for one tick. This is an administrator-enabled
local mechanism, not a default Free-host service. No arbitrary commands,
provider URLs, dispatch jobs, worker services or paid resources are provisioned.

Short DB transactions are serialized using SQLite write locks or a PostgreSQL
advisory transaction lock. This intentionally favors correctness at modest demo
load over high throughput. Retention/backup tooling and shared export storage
are outside this foundation; audit and completed-job history need operational
retention planning for a long-lived deployment.
