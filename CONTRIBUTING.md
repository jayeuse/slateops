# Contributing to Slate Operations

This guide is for developers who build and change Slate Operations. It tells you how the stack fits together, how to set up a development checkout, and what a pull request needs.

- Documentation index: [docs/README.md](docs/README.md)
- Architecture: [docs/architecture/README.md](docs/architecture/README.md)
- AI agents: read [AGENTS.md](AGENTS.md) first. It holds the rules for agent work in this repository.

You need Python `>=3.12,<3.15` and Node `>=24`. The file `.node-version` pins the Node version for development and CI.

## Stack and boundaries

Slate Operations runs on Supabase services and its own API. FastAPI is the authority for application data access, identity binding, authorization, file access, SSE delivery, and private Comms publication. Do not write application data through provider APIs, Studio, or direct SQL.

- **Database:** Supabase's pinned PostgreSQL distribution. FastAPI reads and writes application tables through synchronous SQLAlchemy connections. Alembic owns only the Slate Operations schema. There is no pgweb service and no standalone PostgreSQL development stack.
- **Authentication:** Supabase Auth handles email and password verification, invitations, and recovery email. FastAPI verifies the provider identity and binds a provider subject to a Slate Operations profile. FastAPI keeps revocable application sessions and decides access from Slate Operations roles, groups, and permissions. Provider claims and metadata do not grant application permissions.
- **Files:** Supabase Storage holds file bytes in one private bucket. FastAPI checks the file type, decides upload and download authorization, and serves each download as an attachment. A file is ready when its upload request ends.
- **Events:** Most application pages use authenticated SSE with opaque PostgreSQL `LISTEN`/`NOTIFY` invalidations. OpenComms uses private Supabase Realtime topics for opaque events and for short-lived presence and typing signals. Authorized content reads and commands stay with FastAPI. These transports are implemented. They are not proof of complete browser or capacity acceptance.
- **Administration:** Supabase Studio replaces pgweb. Studio is a privileged operator surface. Keep its gateway loopback-only in development and protected in production.
- **Audit:** Normal application ORM mutations record minimal, redacted diffs in the same transaction as the business change. Alembic, direct SQL, provider operations, and file-byte operations are outside that audit boundary.

## Configuration

The ignored root `.env` is the canonical local development configuration. Start from `.env.example`. Keep `.env` owner-only. Never pass it to Next.js and never commit it.

```bash
cp .env.example .env
chmod 600 .env
```

The checked-in example has blank secrets and blank database role URLs. Fill them as follows:

1. Choose a fresh `SLATEOPS_INSTANCE_ID` and a private `SLATEOPS_INSTANCE_ROOT` for a new Supabase development installation.
2. Install the backend dependencies and generate the provider keys. Use a new private output path whose parent directory already exists:

   ```bash
   # backend/
   uv sync --locked
   uv run python operations/supabase_keys.py --output /absolute/private/path/provider-keys.env
   ```

   The key generator writes a new owner-only key file and never prints its contents. It does not make a complete installation environment.
3. Copy the generated entries into the matching blank fields in `.env`.
4. Set `DATABASE_BOOTSTRAP_URL` to the provider's `supabase_admin` connection, with `POSTGRES_PASSWORD`.
5. Set `MIGRATION_DATABASE_URL` to the application owner login `slateops_owner`. Set `DATABASE_URL` to the constrained runtime login `slateops_runtime`. Give each application role its own password. The role provisioning command (see [Local development](#local-development)) creates and checks these roles.
6. Set the remaining installation values in `.env`.
7. Check the configuration from the repository root:

   ```bash
   uv run --directory backend python ../scripts/environment.py check
   ```

Never put the bootstrap URL or `SUPABASE_SECRET_KEY` in frontend configuration or in a browser bundle.

A new Supabase development installation starts with fresh application data. It does not import old accounts, records, or files. Keep existing PostgreSQL volumes and configuration until you review what to do with them. Do not point the new Compose project at them.

Production uses separate owner-only provider and application environment files. See the [Supabase operator guide](infra/supabase/README.md).

## Local development

Run the commands from the repository root, unless a code block names a directory.

1. Start the owned Supabase development stack. Its default Compose project name comes from `SLATEOPS_INSTANCE_ID`.

   ```bash
   ./scripts/dev.py db
   ```

   The wrapper validates `.env`, resolves the pinned base and development Compose files, and checks instance ownership before it changes containers. It starts the provider services, the loopback gateway, and the development Mailpit.

2. Provision the application roles, apply the fresh-install schema, check for schema drift, and create the private Storage bucket:

   ```bash
   # backend/
   uv run python operations/provision_database_role.py
   uv run alembic upgrade head
   uv run alembic check
   uv run python operations/provision_storage.py
   ```

3. Start FastAPI and Next.js in separate terminals:

   ```bash
   # backend/
   uv run python -m app --reload

   # frontend/
   npm ci
   npm run dev
   ```

4. Bootstrap the first administrator after FastAPI runs. `ADMIN_EMAIL` and `ADMIN_USERNAME` must be set in `.env`. Supabase sends an invitation. Open it in the development Mailpit inbox, and set the password through Slate Operations.

   ```bash
   # backend/
   uv run python operations/bootstrap_admin.py
   ```

   Usernames are profile labels; users sign in with their email. In production, the command needs its `--confirm` option. Provider invitation and recovery email use the configured SMTP service. Development uses Mailpit.

### Ports and services

- PostgreSQL and the gateway bind to loopback. Host-run SQLAlchemy and Alembic use the database port.
- The gateway serves the operator Studio surface on `SUPABASE_API_PORT` (default `58000`). Sign in to Studio with the operator credentials in `.env`. Studio has broader privileges than the removed read-only pgweb inspector.
- Mailpit's inbox is on `SUPABASE_MAIL_PORT` (default `58025`).
- Next.js is the daily browser origin. It proxies `/api` to the loopback FastAPI server in development only. In production, FastAPI serves the static frontend export, and no Node.js frontend process runs.

### Development stack commands

`./scripts/dev.py` accepts these actions: `db`, `studio`, `caddy`, `containers`, `status`, and `stop`. There is no `pgweb` action.

- `./scripts/dev.py studio` starts the Studio gateway explicitly.
- `./scripts/dev.py stop` stops the owned development containers and keeps their named data volumes.

Caution: do not use `docker compose down -v` on an installation whose data you want to keep. The volumes hold the database, Auth state, and Storage bytes.

### Health and readiness

- `/api/health` is an API-process response.
- `/api/ready` returns a bounded, no-store snapshot of four required components: the application database, Supabase Auth health, Supabase Storage health, and SMTP configuration. It returns 200 only when every component is ready, and 503 otherwise.
- SMTP reports that the configuration is present, not that email is delivered.
- A guarded production Compose rehearsal exercised the all-component readiness check, and bounded Auth and Storage failure and recovery responses.
- `/api/ready` is a component signal. It is not a whole-installation check or a release check.

### Update a development checkout from before the scanner removal

New installations have permanent delete enabled in `.env.example`. `LIFECYCLE_PURGE_ENABLED` is still required. An upgrade keeps the value in your existing private `.env`; a change to the example does not enable it there.

Installations from commits before `3343730f` (2026-10-05) had antivirus file scanning. If your `.env` and local stack come from such a commit, do these steps once after you update the checkout:

1. Stop FastAPI.
2. Remove these seven lines from your private `.env`: `FILES_CLAMAV_PORT`, `FILES_CLAMAV_HOST`, `FILES_CLAMAV_MANIFEST_PATH`, `SCANNER_DEFINITIONS`, `CLAMAV_MEMORY_LIMIT`, `CLAMAV_CPUS`, `CLAMAV_PIDS_LIMIT`. Do not change other lines. They hold your installation identity and credentials.
3. In `backend/`, run `uv run python ../scripts/environment.py check`. It must print "Environment configuration is valid." While a retired name stays in `.env`, every wrapper stops with "Unknown configuration names".
4. In `backend/`, run `uv run alembic upgrade head`.
5. In `backend/`, run `uv run python operations/retire_legacy_upload_bucket.py`. This dry run reports the old upload bucket and its object count.
6. Caution: the next step permanently deletes the old bucket and its bytes. Those uploads never became available, so no user can open them. In `backend/`, run `uv run python operations/retire_legacy_upload_bucket.py --execute`.

## Production Compose

Production is one isolated stack per client. It is not shared multi-tenant SaaS.

- The production overlay adds the unified FastAPI and static-frontend image, and Caddy.
- Provider services stay on private Compose networks. The Studio gateway binds to loopback for operator access. Only the configured Caddy listener is public.
- Production needs separate provider and application environment files, real SMTP, TLS materials, and release-specific image tags.

Follow [infra/supabase/README.md](infra/supabase/README.md) for the exact Compose inputs and the startup sequence. Apply the database roles, the Alembic schema, and the private Storage bucket explicitly before you start the API or Caddy. Container health and `/api/ready` are operational signals. They do not replace installation checks or release acceptance.

Caution: do not run unrestricted `up` on a fresh production installation. Do not remove named volumes as a reset shortcut.

The server deployment paths are Linux Docker Compose and the Windows setup program. The Windows setup program runs Docker Engine in its own WSL2 image, not Docker Desktop (`infra/windows/installer/`, `packaging/linux-image/`). Windows acceptance is limited; see [Deployment architecture](docs/architecture/12-deployment-architecture.md#health-and-release-acceptance). The production path on a Linux host is not accepted for general client use. macOS is a development workstation only, not a server target. The open acceptance items are in the [implementation plan](infra/supabase/PLAN.md).

## Application data reset

The guarded reset is only for local development or disposable test instances. It is not a database-volume reset, a backup, a rollback, or a customer recovery tool.

1. Stop FastAPI.
2. Run the dry plan. Review the preserved administrator and the impact.
3. Run `--execute` in a TTY and type the exact impact digest that it shows.

```bash
# backend/
uv run python operations/reset_application_data.py
uv run python operations/reset_application_data.py --execute
```

The reset removes selected Slate Operations application records, the associated Supabase Auth accounts, and private Storage objects. It keeps the configured administrator and that account's installation operator row. It removes every organization and creates none. After the reset, run `operations/create_organization.py`. With `--email`, the `--username` option is optional; it defaults to the local part of the email. The reset reports partial cleanup failures for operator recovery.

For the support-operated restore procedure and its open acceptance gaps, see [RESTORE.md](infra/supabase/RESTORE.md).

## Application contracts

- User and role administration and audit reads need administrator authority.
- The backend applies the feature read and write capabilities, group and workspace rules, Board grants and audiences, Report eligibility, guest expiry, and lifecycle constraints.
- Session revocation and current application eligibility are checked separately from Supabase's authentication result.
- File metadata lives in the application schema. Object bytes live in the private Supabase Storage bucket. An upload passes the file-type check before FastAPI stores it, and the file is ready when the upload request ends.
- Keep upload, reconciliation, download, and deletion behind the existing FastAPI file contracts.

## OpenComms status and entrypoints

Comms conversations and messages, scoped files and settings, administrator tools, moderation, and durable jobs have implemented FastAPI contracts. The `/comms` page reads and changes them only through those APIs. It receives private Realtime notifications, and no part of it runs on browser-local example data. Private Realtime events do not grant content access. Complete integrated browser, provider-load, and release acceptance is still separate work.

- Ingress, publication, and startup boundaries: [Supabase operator guide](infra/supabase/README.md#opencomms-ingress-and-private-publication).
- Current reads, commands, and privileged purposes: [Comms API contract](docs/architecture/07-api-architecture.md#opencomms-http-boundary).
- Comms adds no other service and no operator bootstrap entrypoint.

The [sample seeder](backend/operations/seed_sample_data.py) has planners and [API executors](backend/operations/sample/controls/comms.py) for the implemented core Comms controls, including primary and partner organization paths. Its plan does not claim that every future UI tool is wired, or that a full pack passed. Full Harbor and School pack execution is deferred to S34. Keep the other unsupported feature exclusions in the [operator plan](backend/operations/sample/plan_summary.py).

## Repository architecture

- `backend/app/core/`: configuration, database wiring, provider integrations, JWT verification, and middleware.
- `backend/app/common/`: shared dependencies, exceptions, and utilities.
- `backend/app/systems/`: capabilities grouped under `sandbox`, `access`, `manage`, `openview`, `boards`, `platform`, and `comms`.
- `backend/migrations/`: the Alembic path for the Slate Operations application schema. Supabase-owned Auth and Storage schemas stay provider-managed.
- `frontend/src/app/`: App Router routes. Reusable primitives are in `frontend/src/components/ui/`.
- `infra/supabase/`: the pinned self-hosted provider stack and the development and production overlays.
- `infra/docker/`: the unified Slate Operations server image.
- `infra/caddy/`: gateway artifacts.

Run Python, uv, and Alembic in `backend/`. Run npm and Playwright in `frontend/`.

## Verification

Use focused checks while you develop. CI on the pull request is the full gate. It selects the applicable backend, frontend, and server-image checks from the changed paths. Backend verification keeps the 90% overall and changed-line coverage thresholds.

CI does not run the release check. At a major update, run it from `backend/`, one command at a time:

```bash
uv run python -m tests.smoke_runner
uv run python -m tests.fullstack_runner --acceptance-only
```

Integration tests must use the runner-owned disposable Supabase instance and its ownership manifest. Never point tests at a developer's personal installation or a customer installation. For test boundaries and the release check, see [Testing Architecture](docs/architecture/16-testing-architecture.md).

## Before you open a pull request

1. Run the fast checks for the side you changed:
   - Frontend, in `frontend/`: `npm run check`
   - Backend, in `backend/`: `uv run ruff check . ../scripts ../tests/tooling ../packaging/backup` and `uv run mypy app operations`
   - When you changed tests, from the repository root: `python3 scripts/assertion_guard.py --base <base-ref>`
2. Run the focused tests for the changed files and their direct callers (`scripts/run_tests.py ... --match`, or the frontend specs that the change touches). Do not run the full suites locally; CI runs them.
3. Write the pull request description with these three headings, in this order:
   - `## What changed`: what a user, an operator, or a developer now sees or gets.
   - `## How`: the main files or modules, the approach, and any migration or configuration change.
   - `## Problem solved`: the issue, bug, or need, with a link to the issue when one exists. Write "None" when no problem is behind the change.
4. Add one line under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md), in the section that fits. Describe the result in plain words, then add the pull request number, for example `(#131)`.
5. Push, then read the CI result. The work is done only when CI is green.

The full rules are in [AGENTS.md](AGENTS.md), sections "Testing rules" and "Pull requests and the changelog".

## Reporting security issues

Report a vulnerability as [SECURITY.md](SECURITY.md) tells you. Never open a public issue for it.

## License

Contributions are under the repository's Elastic License 2.0. See [LICENSE](LICENSE).
