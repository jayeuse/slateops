# Infrastructure Artifacts

- `supabase/` contains the pinned self-hosted Supabase Compose stack and its development and production overlays. Local development uses that stack through `./scripts/dev.py`; FastAPI and the local Next.js HMR server run on the host. Supabase Database supplies PostgreSQL; there is no standalone root PostgreSQL or pgweb service. See `supabase/README.md` for the verified service and operator contract.
- Build `docker/backend.Dockerfile` with repository root as context; its `COPY` paths are root-relative. Do not change the context. It builds the static frontend and packages it with the FastAPI runtime; the final image contains no Node.js runtime.
- Application images must not start provider services, apply Alembic migrations, provision database roles or Storage buckets, bootstrap users, or define hosted deployment; CI/operators own those steps outside the images.
- Never bake `BACKEND_URL`, frontend runtime configuration, or private/backend secrets into the image.
- `caddy/` contains production gateway artifacts. Caddy is not part of ordinary local development.
- Target: one full Compose stack per client (micro–medium SMB, on-premise first). The shipped server is Windows 11: the Windows installer (`windows/installer/`) imports its own WSL2 Linux image with Docker Engine (`../packaging/linux-image/`); it does not use Docker Desktop. The release workflow runs the Windows install acceptance. macOS is for development only. Do not introduce fleet/orchestrated deployment into these artifacts.
- `/api/health` reports API-process liveness; `/api/ready` reports the required database, Auth, and Storage components and the optional SMTP-configuration component: email is set up after install (DEC-0041; `../docs/architecture/11-infrastructure.md`).
- A native Linux server host (without the Windows installer) has no install acceptance; do not describe it as supported.

## Skills

- Compose files and Dockerfiles: the `project-tooling` skill. Use it for each change under `supabase/`, `docker/`, or `caddy/`.
- Compose exposure: the `webapp-security-review` skill. Use it when a change touches exposed ports, gateway rules, or where secrets reach an image or a container.
