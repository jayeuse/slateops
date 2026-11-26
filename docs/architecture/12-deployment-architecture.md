# Deployment Architecture

> **Scope:** Per-client self-hosted Compose deployment, its current implementation state, and release-operation boundaries.
> **Related documents:** [Infrastructure](11-infrastructure.md), [Configuration](17-configuration.md), [Runtime Flows](13-runtime-flows.md), [Architecture index](README.md)

## State classifications

- **Implemented** means the repository contains the service definition, code path, or command.
- **Partially implemented** means some required artifacts exist but full host or customer-operation acceptance is missing.
- **Pending** means an explicit runtime acceptance check has not been performed.
- **Absent** means no supported release artifact or workflow is checked in.
- **Future** means a distinct target that still requires a product and operations decision.

## Deployment state map

| Area | State | Repository boundary |
| --- | --- | --- |
| Development provider stack | Implemented | Pinned Supabase Compose base and development overlay; `scripts/dev.py` and `scripts/environment.py` guard the project, environment, image, and owned database resources. FastAPI and Next development server remain host-run. |
| Production Compose definition | Implemented artifacts | Provider base plus production overlay define PostgreSQL, Auth, Storage, Studio, metadata/API gateway, the unified FastAPI/static UI image, and Caddy. Per-client paths, secrets, images, and TLS must be supplied by the operator. |
| Application data and identity | Implemented paths | SQLAlchemy/Alembic own Slate Operations schema. Supabase Auth authenticates; FastAPI resolves the explicitly bound application profile and authorizes requests. Private Storage uses the `slateops-ready` bucket through the server-side API. |
| Linux server operation | Partially implemented | The Compose path is checked in. A production Compose rehearsal using Linux containers on macOS Docker Desktop exercised TLS, bounded readiness, five-volume restore, target session finalization, authorization, file access, and service restart. Native Linux host installation, boot/reboot, retention, and general customer acceptance remain separate requirements. |
| Windows server operation | Partially implemented | The shipped path is the setup program `SlateOpsSetup-<version>.exe` (`.github/workflows/release.yml`, job `installer`; `infra/windows/installer/`) on Windows 11 Pro, Enterprise or Education, version 22H2 or later (`infra/windows/installer/scripts/lib/Checks.ps1`). It imports its own WSL2 Debian image with Docker Engine (`packaging/linux-image/`) and starts the stack with `infra/supabase/compose.installer.yaml`. It does not use Docker Desktop. The engine (`packaging/engine/`) sets up HTTPS with a local CA (`backend/operations/local_ca.py`, `trust.py`), daily encrypted backups at 02:00 (`backend/app/systems/manage/backups/policy_default.py`, `backups.py`), restore of the latest backup (`restore.py`), Stop and Start (`power.py`), and update by a newer setup program with a backup first and rollback by restore (`update.py`). A boot task starts the stack with Windows (`infra/windows/installer/scripts/start.ps1`). Windows 10, Windows 11 Home and Windows on Arm are refused. What acceptance exists is in Health and release acceptance below. |
| macOS server | Not a target | macOS remains available for development. It is not a supported customer server target. |
| Hosted application or managed Supabase deployment | Future, separate target | No registry, hosted service, customer provisioning, DNS/TLS control plane, managed database, or deployment workflow is implemented. A self-hosted installation can hold several organizations, isolated by membership checks and row-level security. It is not a hosted service; the Supabase Cloud target is Phase 3 work. |
| Native installer or service manager | Partially implemented | The Windows setup program exists and registers the Windows boot task (see the Windows row). It is not code-signed (`scripts/release_artifacts.py` release notes). No Linux or macOS installer, OS service package, or bundled database runtime exists; a Linux host runs the Compose files directly. |
| CI deployment | Partially implemented | `.github/workflows/backend.yml` builds the unified server image with `push: false`. On a `v*` tag, `.github/workflows/release.yml` (:12-15) pushes the server and Caddy images to GHCR (job `images`, :91-126), signs them with cosign and attests their provenance (:176-197), builds the engine bundle, the Linux image and the setup file, and creates a draft GitHub release with `SHA256SUMS` (job `release`, :808-820). A person publishes the draft. No workflow deploys to a client host. |

## Per-client Compose installation

Each client receives an isolated Compose project with its own `SLATEOPS_INSTANCE_ID`, provider and application credentials, named volumes, internal networks, host paths, and public origin. `infra/supabase/compose.yaml` pins the provider services. `compose.dev.yaml` adds loopback development ports and Mailpit. `compose.production.yaml` adds the Slate Operations application and Caddy.

Development uses the root owner-only `.env` and the wrapper `./scripts/dev.py db`. The wrapper selects the pinned development Compose files, project name, and minimal process environment. FastAPI connects directly to the admitted database runtime role; Alembic uses its owner connection. The host-run Next development server proxies `/api` to FastAPI. Supabase Studio is reached through the loopback gateway and operator authentication; pgweb and the inspector role are no longer part of the topology.

Production uses separate owner-only provider and application environment files. Follow the staged provider, schema, Storage, and application startup sequence in [`infra/supabase/README.md`](../../infra/supabase/README.md). The application image contains FastAPI and the static Next export; Node is a build dependency only. Caddy carries public HTTPS traffic to the single API service. PostgreSQL, the provider gateway, Auth, Storage, and application ports are not public listeners.

The production path keeps three distinct credentials and schema responsibilities:

- `DATABASE_BOOTSTRAP_URL` uses `supabase_admin` for guarded role provisioning.
- `MIGRATION_DATABASE_URL` uses `slateops_owner` for application Alembic migrations.
- `DATABASE_URL` uses `slateops_runtime` for normal application queries, including in-process workers.

A fresh installation explicitly provisions roles, applies the current Alembic head, checks for drift, and creates the private Storage bucket before bootstrapping the first administrator by email invitation. Compose container health alone does not prove these application contracts. `README.md` documents the production app environment, image tags, logs, and Caddy/TLS inputs; [`Configuration`](17-configuration.md) describes their ownership.

## Listener, TLS, and service boundary

The production overlay publishes HTTPS only through Caddy. The operator selects an interface and a Caddy TLS mode, and aligns `PUBLIC_ORIGIN`, the Auth issuer, gateway URL, generated Caddyfile, certificate files, and Compose port. Internal TLS and supplied custom certificates are supported by the checked-in Caddy generator. The development database and gateway bindings are loopback-only. Provider networks are isolated, and the application does not expose PostgREST tables or Storage directly to browser clients.

Persistent volumes and restart policies alone do not establish safe reboot recovery. The release does not establish native Windows-container support.

## Identity and authorization at deployment

Supabase Auth sends invitation and recovery email through the configured provider SMTP service. Slate Operations retains application profiles, session listing and revocation, invitation eligibility, roles, groups, and resource authorization in its own database. A provider account or provider metadata alone does not grant application access. The production API environment receives only the application runtime values they need; provider bootstrap, Auth private signing material, Studio credentials, and SMTP credentials stay in the provider environment.

This is a per-installation identity and access model. There is no account import, local-password compatibility mode, or seamless session migration in the fresh-start scope. Existing data volumes are not automatically deleted by startup commands.

## Health and release acceptance

`/api/health` is an API-process liveness response. `/api/ready` reports Database, Auth, Storage, and SMTP configuration states, all required. SMTP status verifies configuration presence only. Exercise readiness with each provider present and absent before accepting a deployment. Schema compatibility, mail delivery, backup currency, and restore integrity require their own operator checks.

The Compose files and adapters are implementation artifacts, not a declaration that every client-host operating procedure has passed. Before customer operation, acceptance must establish at least:

1. A fresh isolated provider project, roles, Alembic schema, private bucket, and email invitation.
2. API and frontend access through the intended Caddy origin, with PostgreSQL and internal provider services unreachable from the client network.
3. Login, current Slate Operations role/group authorization, session revocation, invitation, recovery, and provider-outage behavior.
4. File-type validation, private ready object, authorized download, and safe behavior on Storage failure.
5. Reboot recovery with the documented Linux or Windows host/container mode.
6. Encrypted backup and restore to a new project and instance ID, with application sessions invalidated and the target admitted before ingress opens.

Windows acceptance is limited. These checks exist:

- `.github/workflows/release.yml`, job `install-proof`, runs `packaging/linux-image/install-proof.sh` on `ubuntu-latest`. The release image boots systemd in a privileged container, and the engine installs from the build's own artifacts with HTTPS readiness, sign-in, an install rerun, and a set-email check. The job does not run on Windows or WSL, and the release job waits for it.
- `.github/workflows/release.yml`, job `installer`, compiles the setup file on `windows-latest` and checks that it is below 2 GiB. It does not run the setup file.
- `.github/workflows/windows-installer.yml` compiles the setup project and runs the Windows-side script tests on `windows-latest`. Its header states that those runners have no nested virtualization, so nothing there starts WSL.
- The owner ran end-user tests of release candidates of the setup program on a Windows 11 PC (plan slice W14, `docs/plans/windows-installer.md` section 11.2). No written acceptance record is checked in.

No item in the list above has a checked-in Windows record, and none covers a run of the published release or a second PC. A Linux container run on macOS or another desktop OS does not satisfy Windows acceptance. A guarded isolated physical restore has been exercised through the production Compose path; see the [restore runbook](../../infra/supabase/RESTORE.md). That rehearsal does not establish native Linux host boot/reboot.

## Backup, restore, and persistent data

The version 3 backup command creates an offline encrypted Restic snapshot of a stopped installation. It packages the physical PostgreSQL and Supabase volumes, pinned image and volume manifest, Compose source files, provider environment, and—on production—application environment, Caddy configuration, TLS files, and Caddy data volume. Development backups contain the four provider volumes; production also includes `caddy-data`. Restic verification and restored-manifest integrity are required before a completion marker is published.

Restore requires the full snapshot ID, a new Compose project, a new `SLATEOPS_INSTANCE_ID`, a fresh target directory, and exact interactive confirmation. It refuses existing target resources and validates the source manifest, files, tar archives, image IDs, and matching release Compose files before volume import. Keep ingress closed while the target configuration is rebound. Start only the isolated target database for finalization; the finalizer checks its actual target volumes, internal-only network, pinned image, `cluster_name`, and session postcondition before writing the finalized marker. Slate Operations application sessions are invalidated so users must establish fresh application sessions. Start the remaining provider services, API, and Caddy only through the staged sequence in [`infra/supabase/RESTORE.md`](../../infra/supabase/RESTORE.md).

Do not run restore against an existing client project or use `docker compose down -v` as cleanup. Retention and off-host Restic repository policy remain operator responsibilities. The Windows installer schedules the backup runner with a systemd timer (`packaging/engine/units/slateops-runner.timer`); a Linux host without the installer has no scheduled backup service checked in (`infra/supabase/RESTORE.md`, Schedule the runner). The guarded five-volume restore has been exercised with a separate target using Linux containers on macOS Docker Desktop. Native Linux host boot/reboot acceptance remains pending. The restore of the latest backup on Windows (`packaging/engine/restore.py`) has no checked-in acceptance record.

## Hosted deployment remains separate

A future hosted Slate Operations service could run a version of this application, but it needs its own hosting, tenancy, operational ownership, backup, identity, secret delivery, and release decisions. None of those controls follows from deploying a self-hosted Supabase Compose stack. One installation already holds several organizations, but self-serve signup, plans, and the Cloud target are Phase 3 work. No managed Supabase project, hosted deployment trigger, or image publisher is represented as implemented here.
