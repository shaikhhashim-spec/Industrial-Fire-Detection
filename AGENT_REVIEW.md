# Agent Review And Selected Design

Three implementation agents worked in disjoint file sets using the prompts in
`IMPLEMENTATION_PROMPTS.md`. Integration selected changes by observable behavior,
security boundaries and tests, not by a simulated argument or subjective winner.

| Challenge | Selected resolution |
| --- | --- |
| Interface and globe selected different overlapping observations | Compare observation timestamps; national evidence wins ties. Test same-day replacement and browser deep links. |
| Every console asset counted as a login attempt | Count failed Basic credentials; valid admin assets do not exhaust the guessing limit. |
| Worker output assumed visible to another service | No worker in the free Blueprint. Future shared snapshot publication remains explicitly unimplemented. |
| Demo accepted refresh jobs without an executor | Jobs disabled by default and forced off in demo startup; API reports unavailable. |
| Unreadable browser storage could be overwritten silently | Preserve it on read failure, show the failure, and require explicit recovery. |
| Memory-only review changes could lose navigation warnings | Keep a separate unsaved-storage state until successfully persisted. |
| Opening a TCP socket could imply readiness | Cloud probes Streamlit HTTP health plus public assets and secured database. Failed readiness returns 503. |
| Console Origin checks compared only host | Check both scheme and host for HTTP and WebSocket requests. |
| Free hosting mistaken for durable shared storage | One free service only; ephemeral server state and browser-local reviews are separately labeled. |
| Linux container omitted shared frontend imports | Include site modules in the Node build stage, not only in the Python runtime. |
| Mocked fetch hid a browser-specific receiver error | Preserve the native fetch receiver; test the actual capabilities network request and real API login/save flow. |

## Verification Boundaries

Local Python, JavaScript, type checking, lint, production build and desktop/mobile
browser checks cover the implemented behavior. Linux Docker startup at 512 MB and
dedicated PostgreSQL driver parity are configured in GitHub CI. Actual Render
deployment needs the owner's connected account and runtime admin secret; no paid
services are authorized. Authentication in a hosted console may consume more
memory than idle health checks, so a free-tier smoke test is not a production
capacity guarantee.

Public screening remains rule-based. Facility proximity, estimated plumes and
classification rules do not establish a confirmed fire, cause or observed smoke.
Unavailable exported evidence is not reconstructed or fabricated.
