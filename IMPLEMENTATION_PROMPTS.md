# Investigations And Render Implementation Prompts

## Shared Objective

Implement the approved public investigations workspace and a deployable Render
backend without breaking GitHub Pages or the local application. Preserve existing
uncommitted dataset refreshes. No agent may commit, push, create billable services,
invent evidence, or expose credentials. Use existing module conventions and tests.

## Interface Agent

Own investigations HTML, JS, domain/review helpers, focused tests and investigation
CSS. Build regional case search/filter/sort/pagination, four dossier tabs, truthful
history/evidence, shared Arena, plume context, review notes/bookmarks and timestamps,
validated local review import/export, CSV/JSON/print reports, responsive list-detail
navigation and region/event deep links. Independent feed failures must not hide a
working feed. Use existing shared location, branding and evidence helpers. Storage
failure must be visible, not silently claimed successful. Browser-local reviews are
not shared or ground truth. Never render data as unsafe HTML.

## Backend Agent

Own new persistence/auth/API/job modules and their tests. Implement SQLite locally
and PostgreSQL through DATABASE_URL with explicit migrations, persisted reviews,
audit records, users/sessions, analyst/admin permissions, protected refresh jobs,
bounded request bodies, optimistic concurrency, rate limits and exclusive job
claims. No operational dispatch without configured provider and explicit admin
action. Credentials stay server-side; anonymous writes are rejected. Share route
and configuration contracts with the integration agent early.

## Deployment Agent

Own Dockerfile, dockerignore, render blueprint, cloud launcher adaptations and
deployment documentation/tests. Build Node assets once in a multi-stage image,
run the gateway on 0.0.0.0:$PORT, keep Streamlit private, use /console in cloud
mode and /globe for built assets, avoid refresh/build/browser opening on startup,
support worker/scheduler commands and graceful shutdown. Keep local defaults.
Paid service creation remains a user-controlled step. Do not edit gateway/app.py
or backend modules; the integration agent owns gateway routing/security wiring.

Hosting decision: the owner selected a FREE demonstration. The default Blueprint
must contain only a free web service, without paid database, worker, cron or disk.
Server-side state is temporary; personal browser reviews can survive server resets.
Refresh execution must report unavailable without an explicitly configured worker.

## Integration And Adversarial Review

Integrate static public routes, secure console, readiness and bidirectional globe
deep links. The interface agent challenges data/storage behavior; the backend agent
challenges public exposure, imports and authentication; the deployment agent
challenges persistence, health, startup and worker assumptions. Record concrete
findings and fixes. Favor tested, least-complex solutions over unsupported claims.

## Acceptance

Public investigations work without localhost, desktop/mobile remain usable, failed
feeds and unavailable evidence are explicit, reviews and reports round-trip, globe
links select the correct case, anonymous mutations fail, analyst cannot perform
admin actions, restart preserves backend state, worker claims are exclusive, cloud
health reflects readiness, all applicable tests/builds pass. Report any unverified
Docker/PostgreSQL/Render behavior plainly.
