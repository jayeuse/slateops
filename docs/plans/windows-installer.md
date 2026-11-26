# Windows installer plan

> **Status: in progress (2026-11-25), PR #115, #121, #123, #124, #126.** The first deliverable is done: the installer (PR #115), the owner's one-button restore (PR #121), editions (PR #123) and the stable releases v1.0.0 and v1.0.1 (PR #124, #126). The second deliverable (the in-app update: W11, W12, W13c, W16) is not built; its text below is kept unchanged. Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/plans/windows-installer.md`.

Company records: scope DEC-0028 and APR-0010; decisions H2 to H13 DEC-0030 and APR-0011; editions DEC-0029; end-user testing only DEC-0031; email after install DEC-0041; address name DEC-0039; wizard spec `docs/specs/windows-installer-wizard.md` (TASK-0080). Headings that say "(proposed)" keep their text because other files cite their anchors; for the first deliverable they describe built behavior.

## 1. Outcome

A person who is not technical installs Slate Operations on a Windows 11 PC with a normal setup wizard (Inno Setup) and never opens a command line. The wizard chooses the program and data folders. An update starts when the person runs a newer setup program. Uninstall starts from Windows Settings → Apps and asks "Keep your data?". Code: `infra/windows/installer/` (wizard, uninstaller, maintenance mode), `packaging/engine/` (the install engine), `packaging/linux-image/` (our Debian 13 WSL image), `.github/workflows/release.yml` and `scripts/release_*.py` (release artifacts).

First-version choices (DEC-0028): Windows 11 only; the customer's own email account (Gmail or Other SMTP), set up after the install; HTTPS with a local CA and a "Trust this device" page; unsigned builds until the first customer install. Every installation starts as Desk; the license file is imported in the app, never in the wizard (DEC-0029 item 10).

### 1.1 Preserved

- The Linux Compose path keeps working; Windows uses the same engine.
- Every control in `SECURITY.md` "Controls that reviews protect" stays.
- Application images hold no provisioning and no secrets; the engine does those steps from outside.
- One `PUBLIC_ORIGIN` per installation and one Caddy `--public-host`.

### 1.2 Excluded

The installation service, the email relay, public certificates, a code-signing certificate, the managed cloud, macOS or Linux desktop installers, Windows 10, Windows on Arm, and proxies. Windows 11 Home stays blocked (R2, H5). The license work has its own contract, `docs/specs/editions.md`.

### 1.3 Labels

Current = read in code. Observed = measured on the owner's PC (REQ-0022). Assumption = not checked; 10.3 gives the self-check. Planning value = a number that the installer report corrects (10.2). Edition = Desk, Office or Headquarters; a Windows edition is always called a Windows edition.

## 2. Current state

The boot-test kit (`infra/windows/boot-test/`, PR #113, REQ-0022) proved the runtime: WSL2 with Docker Engine in our own Debian serves the LAN at boot with nobody signed in. Facts that still govern: the server PC cannot open its own LAN address in mirrored mode (so it uses a hosts entry to 127.0.0.1); mirrored mode needs build 22621 or later; GoTrue SMTP supports only a user name and password; Microsoft 365 turns Basic SMTP AUTH off by default for existing tenants at the end of December 2026; Gmail revokes app passwords when the account password changes; `.local` does not resolve across subnets; no public certificate can name `.local` or a private IP address.

## 3. Architecture (proposed)

The setup program (elevated) writes requests to the task `\SlateOps\Exec`, which runs as the hidden standard account `slateops-svc` and calls `wsl.exe -d SlateOps -u root -- slateops-engine <job>`. The task `\SlateOps\Start` (at startup) starts the distribution and keeps the keep-alive attached. The distribution "SlateOps" lives in `<data folder>\SlateOps\distro\ext4.vhdx` and runs systemd, Docker, `slateops-runner.timer` (1 minute), the engine and the Compose stack (`db auth storage imgproxy realtime meta studio api-gw api caddy`). Secrets live in `/etc/slateops/` (root, 0600). Phones and PCs on the LAN open `https://<name>.local`.

### 3.1 Parts

- **Wizard and uninstaller:** one Inno Setup program, per machine.
- **`\SlateOps\Exec`:** accepts only allow-listed job names and a validated request ID.
- **`\SlateOps\Start`:** the boot task.
- **Linux image:** Debian 13, built in CI, with Docker Engine, Restic, Python 3, the engine of the same release and systemd units. It has no secrets and no SSH server. `wsl.conf`: systemd on, interop off, automount off.
- **Engine:** `slateops-engine` in `packaging/engine/`, standard-library Python, runs as root. Steps that need `app.*` run as one-shot containers of the release server image.
- **Engine bundle:** the engine, Compose files, templates and `release-manifest.json`.
- **Setup payload:** the engine bundle, the signed manifest and our two image archives, streamed by `receive`.

### 3.2 Rules of the boundary

1. Windows calls Linux only through allow-listed `Exec` jobs. Data goes on standard input as JSON, never as arguments. `receive` takes a size-limited tar stream, and the engine uses a part only after it matches the signed manifest. The R7 module-logging check stays.
2. Linux never starts a Windows program (interop off). The Windows side acts only on `engine_idle` from `status --json`. No Linux value becomes a Windows path, URL or argument. Windows sends `status` its own version and the WSL version.
3. Secrets are made and kept in `/etc/slateops/`. Three named exceptions cross the boundary, each through a named pipe with a random name, first-instance, no remote clients, access for Administrators and `slateops-svc` only (decision H3):
   - the first administrator's password, Windows → Linux once, on the standard input of `install`, held in memory only (DEC-0041);
   - the SMTP password, once, to `smtp-test`, which stages it in `/etc/slateops/new/smtp.env`; `set-email` reads the staged file;
   - the backup recovery key, Linux → Windows once, for page 11.
   No secret is an argument, environment value, task property, cmdlet parameter or log line. Inno Setup does not save or log the password field. The file fallback is not built (10.3, F4d). Printing the key makes a spool file, a named exception (W8-5).
4. Linux reaches a Windows drive only when the engine mounts the backup drive with drvfs. `slateops-svc` has access only to the data and backup folders.

## 4. Wizard (proposed)

### 4.1 Page order

The wizard spec `docs/specs/windows-installer-wizard.md` (TASK-0080) owns the final page order, checks and copy. Rules that stay:

- One restart, if needed, on "Prepare this PC" before any answer is collected. No secret stays on disk across it. Setup resumes at the location page (RunOnce or the desktop shortcut; F4a).
- Versions are compared by SemVer precedence; `X.Y.Z-rc.N` is older than `X.Y.Z`. A newer setup offers Update; otherwise the maintenance mode opens.
- The data drive must be a fixed NTFS drive with at least 25 GB free (planning value).
- The address is `<address name>.local`, from the organization name (DEC-0039), answered by setup's own mDNS responder. One inbound rule: UDP 5353, Private profile, local subnet, for Windows PowerShell (S97-5 option a). The IP address is not offered, because the app has one `PUBLIC_ORIGIN`.
- Setup asks for no email account; email is set up in the maintenance mode (section 9.3, DEC-0041). The administrator password: 12 characters or more, at most 72 bytes, one line.
- Cancel, close or failure removes everything that setup added (never kept data). There is no "continue later".
- No page asks for an edition or a license file.

### 4.2 Requirements check

| ID | Check | Blocking |
|---|---|---|
| R1 | Windows 11, build 22621 or later | Yes |
| R2 | Windows edition Pro, Enterprise or Education (H5) | Yes |
| R3 | Virtualization on | Yes |
| R4 | Memory at least 16 GB (planning value) | Yes |
| R5 | Free space on the data drive | Yes |
| R6 | Not domain-joined; network not Public | Domain yes; Public: "Make private" |
| R7 | PowerShell module logging does not cover `ScheduledTasks` | Yes |
| R8 | Internet access to ghcr.io and Docker Hub | Yes |
| R9 | On mains power | No (warning) |

### 4.3 What goes where

Program: `C:\Program Files\Slate Operations\`. State and logs: `C:\ProgramData\SlateOps\` (Administrators and SYSTEM). Data: `<data folder>\SlateOps\distro\ext4.vhdx` (the whole Linux disk). Kept data: `<data folder>\SlateOps\kept\`. Backups: the chosen folder, preferably another drive.

## 5. Release artifacts (proposed)

### 5.1 Version

The Git tag is the only version source: `vX.Y.Z` on `main` (stable) or `vX.Y.Z-rc.N` on a pushed branch (test build). CI passes `SLATEOPS_VERSION`; the local default is `0.0.0+dev`. The workflow refuses a tag that differs from `backend/pyproject.toml` and `frontend/package.json`.

### 5.2 Release workflow

`.github/workflows/release.yml` runs on a `v*` tag push, with `contents: read` by default and per-job permissions; every Action is SHA-pinned; `linux/amd64` only. It builds the server and Caddy images, signs the digests with cosign keyless, builds the Linux image (`mmdebstrap` from a fixed snapshot date, Docker key fingerprint check, pinned cosign), the engine bundle, `release-manifest.json` (signed), the installer `SlateOpsSetup-<version>.exe` (one file below 2 GiB, carrying the Linux image, the WSL MSI and the setup payload), `THIRD-PARTY-NOTICES.txt`, `SOURCE-OFFER.txt` with the GPL source packages (H4), and `SHA256SUMS`. It always creates a draft release.

Manifest format (H11): `schema_version` 1; readers ignore unknown keys; an added field keeps version 1; a rename, removal or change of meaning raises it; a reader refuses a higher version. It holds all image digests, the archive SHA-256s, the Linux image and engine bundle SHA-256, the minimum Windows-part version and the known-bad WSL versions. The engine checks the signature with the identity `.github/workflows/release.yml@refs/tags/v*` of this repository, then each part by SHA-256 and each loaded image by config digest. Compose never pulls our images.

### 5.3 Releases before the license work

Until the license work merged, every release was a draft test build titled "Test build, not for customers", and no stable tag was pushed (DEC-0029 item 13). The license work merged in PR #123, and the stable releases are v1.0.0 and v1.0.1. Rules that stay: an rc tag makes a draft that nobody publishes; the owner publishes a stable release only after the release checks in root `AGENTS.md`.

## 6. Install engine (proposed)

### 6.1 Contract

`slateops-engine install` does the whole first install from JSON answers on standard input (`business_name`, `slug`, `admin_email`, `admin_username`, `public_host`, `backup_target`, `data_vhd_max_gb`, `time_zone`, plus `admin_password`, never stored). It is idempotent and resumable: each step writes to `/var/lib/slateops/install-journal.json` before the next starts. A step never overwrites an existing secret, CA key or volume; a mismatch stops with a safe code. No secret reaches logs or output; `docker compose config` runs only with `--quiet`.

### 6.2 Steps of `install`

1. Validate the answers, the manifest signature and the payload. 2. Create `/etc/slateops` (0700) with `tls/` (the only TLS folder that Caddy mounts) and `ca/` (mounted only into the CA job). 3. Load our images and pull the provider images by digest. 4. Generate all secrets as literal `KEY=value` in a one-shot container with no network. 5. Write the env files from the templates. 6. Create the CA (6.3), the server certificate, the Caddyfile and the trust files. 7. Start the provider services. 8. Provision: roles, `alembic upgrade head`, `alembic check`, Storage. 9. Start `api` and wait for `/api/ready`. 10. Start `caddy` and check HTTPS. 11. Create the first administrator with `bootstrap_admin.py --password-stdin` (no email; DEC-0041). 12. Initialize Restic, take the first backup, run `restic check`, add the recovery key, start `slateops-runner.timer`, set the default policy (daily 02:00, `policy_default`). 13. Write `installation.json` and return the safe result.

The wizard then adds the Windows-side parts: firewall rules for TCP 443 and 80 (Windows and Hyper-V, Private, local subnet), the hosts entry, the CA in LocalMachine Root, sleep set to Never on mains power, and the HTTPS check from Windows. The `Exec` allow-list: `receive`, `prepare`, `prefetch`, `smtp-test`, `install`, `status`, `update`, `set-email`, `set-backup-target`, `new-recovery-key`, `export-trust`, `log-bundle`, `prepare-uninstall`, `restore`.

### 6.3 Caddy and the trust page

Caddy serves `:443` with the custom certificate. The `:80` site serves only `/trust`, `/trust/slateops-ca.crt` and `/trust/slateops.mobileconfig`, and redirects every other path to HTTPS (H10). The trust page is one static file in the Caddy image (`infra/caddy/trust/`) with steps for iOS, Android, Windows and macOS and the CA fingerprint. Certificate profile: a root, then an intermediate with critical name constraints (a `dNSName` subtree for `public_host` and an `iPAddress` subtree that excludes all addresses); the root key is removed after it signs. The leaf has only the DNS name, an empty subject, a critical SAN, and a lifetime of 397 days or less. The runner checks the certificate daily and renews it 30 days before expiry. A restore or a kept-data reinstall keeps the same CA.

## 7. Update (proposed)

Built: the setup-program update path (7.3 to 7.5). Not built: the in-app flow (7.1, 7.2), kept below unchanged.

### 7.1 Flow

1. The backup runner records a new stable release (current behavior).
2. Manage → Updates shows "Version X is ready" with the release notes link and **Install tonight**. Only the installation owner sees the button, after a fresh sign-in check, the same as for backups. The button shows only when the engine reported its presence in the last 5 minutes (`updater_seen_at`, 7.2). A Linux installation without the engine never shows it, so it never queues a run that nothing executes.
3. "Install tonight" queues an update run. The page shows "Scheduled for tonight at 02:00", with **Cancel**.
4. At the window, the engine claims the run and does the steps in 7.3. The update's backup replaces that night's scheduled backup, so the night has one outage.
5. In the morning, the page shows the result: "Updated to X", or "The update failed. Slate Operations is back on version W. Nothing was lost." Every person signs in again after a rollback, because a restore revokes the sessions.

Other states:

- "Not enough free space for a safe update (needs X GB)".
- "This update needs the new setup program", with a download link. It shows when `release-manifest.json` needs a newer Windows part than `version.json`.

The Product Designer designs these states. The Frontend Engineer builds them in `updates-panel.tsx` and `updates-rules.ts`. The same page holds the edition and the license import of the license work (DEC-0029 item 10). W12 keeps those parts and does not change them. The license work keeps the update states of W12 and does not change them. The second of the two to merge rebases onto the first (section 5.3).

### 7.2 Contract between the app and the engine (approved with decision H2, DEC-0030)

| Item | Kind | Detail |
|---|---|---|
| `POST /api/updates` | New route | Body `{ "target_version": "X.Y.Z" }`. `Idempotency-Key` header. Installation owner and fresh administrator only (`require_fresh_exact_admin`, `require_platform_operator`). 201 with `Location`. 409 `update_active` when a run is queued or active. 409 `update_target_stale` when the version is not the latest observed stable release. 409 `updater_unavailable` when `updater_seen_at` is older than 5 minutes or empty. |
| `GET /api/updates` | New route | The standard list of update runs, newest first. Installation owner only. |
| `POST /api/updates/{id}/cancel` | New route | Allowed only while the run is `queued`. 409 `update_not_cancellable` otherwise. |
| `update_runs` | New table | `id`, `requested_by`, `from_version`, `target_version`, `scheduled_for`, `state` (`queued`, `claimed`, `backing_up`, `updating`, `verifying`, `succeeded`, `failed`, `rolled_back`, `cancelled`), `failure_code`, `backup_run_id`, `claimed_at`, `finished_at`. The installation fence is the same as for `backup_runs`. Audited ORM changes. |
| Engine presence | New column `update_statuses.updater_seen_at` | The time of the engine's last heartbeat. The API reads it for the 409 `updater_unavailable` rule and for the button. |
| Bridge operations | New members of the existing operation union in `backend/operations/backup_state.py` (`Command`, lines 54-67) | `update_claim`, `update_inspect`, `update_progress`, `update_outcome`, `updater_heartbeat`, and `update_close_restored`. They use the existing admission and the existing advisory lock; there is no second bridge command. `update_close_restored` is a cross-instance close: it is admitted by the restore-finalized marker, like `AdoptCommand`, and sets `rolled_back` on the source instance's run in the restored database. `policy_default` (W5a) is also a member: it writes the default backup policy only when none exists. |
| SSE | Existing kind | An opaque installation invalidation when a run changes state (installation owner only, as now). |

The engine also keeps its own journal in `/var/lib/slateops/update/<id>.json`, outside the database. A rollback restores the database to a time before the run, so the restored `update_runs` row would say `claimed`. After a rollback the engine writes `rolled_back` into the restored database with `update_close_restored`. A run with a closed journal is never claimed again. The engine holds the backup runner's host lock for the whole update, so no runner tick, backup or export starts during it.

### 7.3 Engine steps

1. Take the runner's host lock; open the journal `/var/lib/slateops/update/<id>.json`.
2. Get and verify the target manifest and engine bundle.
3. Check free space for one restored copy; else `failed`, `insufficient_space`, and nothing stops.
4. Load or pull the target images by digest while the services run.
5. Stop the services and run the offline backup; journal the snapshot ID.
6. Write the new env files; add new keys only, keep every secret.
7. **Rollback boundary** (journaled first): start the provider services on the target images.
8. Wait for provider health. 9. Provision with the target image. 10. Start `api`; check that it reports the target `SLATEOPS_VERSION`. 11. Start `caddy` last and check HTTPS.
12. Mark `succeeded`, release the lock, remove old images after 7 days.

A failure before step 7 runs the current `recover` path on the old images. A failure in or after step 7 rolls back by restore (7.5). Writes after step 10 are lost on a rollback; the Updates page states this.

### 7.4 WSL, Linux packages and the installer itself

- **Linux packages:** a weekly package night (Sunday, after the nightly backup, with no update active) under the host lock; only the Debian security repository and the pinned Docker major version.
- **WSL:** only the setup program installs the pinned WSL MSI, with a person present, after `engine_idle` and a SHA-256 check right before `msiexec`. No unattended WSL install and no `\SlateOps\Maintain` task (F10). Nothing downgrades WSL. The engine accepts a newer WSL unless the manifest's known-bad list names it; then `status` shows "Needs support". The boot task reattaches after a WSL update (E6, about 2.5 min).
- **Setup-program update path:** a newer `SlateOpsSetup-<version>.exe` finds the installation, keeps every choice and secret, replaces the program folder and tasks, streams the payload (`receive`), installs the WSL MSI when needed, and runs `update` with progress, Retry and Save report.

### 7.5 Rollback by restore

1. Stop and remove the failed project's containers and networks (`docker compose down` without `-v`); its volumes stay.
2. Restore the pre-update snapshot into `<base>-r<n>` with a new instance ID.
3. Rebind the env files. 4. Finalize (revokes sessions). 5. Start with the old images, `caddy` last. 6. Adopt the backup policy (`recover --restore-finalized`). 7. Close the journal as `rolled_back`.

Step 1 removes the networks because the restored project reuses `SLATEOPS_APP_PRIVATE_SUBNET`. Exception to `RESTORE.md`: a rollback keeps the same `PUBLIC_ORIGIN`, `SITE_URL`, `API_EXTERNAL_URL` and host name; the engine refuses if a failed-project container still runs. The engine-only non-interactive restore mode is in `packaging/backup/restore_installation.py` (W13a, H12).

## 8. Backup and restore (proposed)

### 8.1 Fail open after a failed backup

After a failed or interrupted run, the runner calls `recover_claim` by itself, at most 3 times, 1 minute apart. It restarts only the containers that ran before, and `caddy` only after `/api/ready`. A refusal (exit 2) keeps the services stopped and does not count. Exit codes stay (3 for a failed run). When readiness still fails, ingress stays closed with `readiness_failed`. No new failure code, migration or API value. No email alert in v1 (H6). This applies to the Linux path too.

### 8.2 Backup location

The backup target is chosen in the wizard or "Change backup location" in the maintenance mode; the web app does not choose Windows drives. The engine mounts only the chosen drive with drvfs at backup time and unmounts it after. A missing USB drive gives `backup_failed`, the services come back (8.1), and `status` carries `backup_target_missing`.

### 8.3 Recovery key

The engine adds a second Restic key and shows it once on page 11, where the person prints it or saves it to a USB drive. Slate Operations does not store it on Windows. The maintenance mode can make a new key and remove the old one. It is a named exception in section 3.2 (H3).

### 8.4 Restore in v1

Owner decision 2026-11-24 (replaces H7 a), built in PR #121: the settings program (M01) has **Restore the latest backup**, with a confirmation that later changes are lost and everyone signs in again ("Go back" is the default). It runs the engine job `restore` (`packaging/engine/restore.py`): take the runner's lock, mount the backup drive, choose the newest snapshot that this installation made, and run the rollback steps of 7.5. A failure before the env files change starts the old project again; a later failure closes `needs_support`. An older snapshot stays a support restore (`RESTORE.md`).

## 9. Uninstall and maintenance (proposed)

### 9.1 Uninstall

Settings → Apps → Slate Operations → Uninstall asks **"Keep your data?"**: **Keep my data** (default) or **Delete everything** (a second dialog and a check box). Both remove the `\SlateOps\*` tasks, the `slateops-svc` account, the firewall rules, the hosts entry, our CA, the program and state folders (logs optional), and the Start menu entry, and restore the sleep settings. WSL stays. Keep my data: `prepare-uninstall` stops the services and renames the disk to `<data folder>\SlateOps\kept\ext4.vhdx` with `kept.json`; nothing is removed until the move is checked (F3). Delete everything: `wsl --unregister` and the data folder are deleted; backups stay unless the person also deletes them.

### 9.2 Reinstall with kept data

Setup finds `kept.json`, offers to reuse it, and stops if the kept version is newer. It registers the disk with `wsl --import-in-place`; `status` must report the instance ID in `kept.json`, else setup stops without changes. The answer pages are skipped and no password is sent. An older kept version runs update steps 3 to 11 of 7.3.

### 9.3 Maintenance mode

The Start menu entry "Slate Operations settings" and Settings → Apps → Modify open it (`ModifyPath`, `NoModify=0`). "Slate Operations: Save report" makes the report of 10.6. It offers: set up or change the email account (`smtp-test`, then `set-email`; the only email setup, DEC-0041), change backup location, show the trust page and QR code, make a new recovery key, Status ("Running", "Updating", "Needs support") with Save report, Repair, and Restore the latest backup (8.4). It has no license import.

## 10. Diagnostics and anticipated failures (proposed)

The owner tests only what end users see (DEC-0031). So the installer must find and explain its own failures, and one Save report file must be enough to resolve a failure.

### 10.1 Logging contract

1. Each run has one run ID `<kind>-<UTC time>-<6 random characters>`, on every log line and passed to containers as `SLATEOPS_RUN_ID`.
2. Each line has a UTC timestamp, the run ID, a step ID (for example `install.08.provision`) and a level.
3. Each command is logged with arguments, exit code and duration; its output goes to a file per step, capped at 1 MB per stream. A stream bridged to the secret pipe is never captured; only its byte count is logged. The engine redacts before it writes or sends.
4. Locations: Windows `C:\ProgramData\SlateOps\logs\` (`setup`, `uninstall`, `maintenance`, `start`, `exec`); Linux `/var/log/slateops/` (`install`, `update`, `backup`, `package-night`, `renewal`, `boot`, `receive`); Docker logs capped by the Compose log options.
5. Each folder keeps the last 20 runs and at most 50 MB; the install log and the first update log are never rotated out.
6. Never logged: a secret, the recovery key, env values, message bodies, file content or business records. Email addresses and user names are placeholders.

### 10.2 Installer report and planning values

`/var/lib/slateops/report.json` holds safe values: WSL VM memory (idle and peak), the time from each Linux start to `/api/ready`, disk use and VHD size, backup and `restic check` durations, and kernel and WSL version changes. Planning values until a real report corrects them: R4 16 GB; `.wslconfig` memory 6 GB; free space 25 GB; readiness time limit 5 minutes.

### 10.3 Former owner-run items: designs and self-checks

Each risky step has a conservative design and a self-check that stops the step with Retry and Save report.

- F1: setup's mDNS responder; page 8 checks a Private network and a free name.
- F2: Docker publishes 443 and 80; the wizard checks HTTPS from Windows with normal certificate checks.
- F3: Keep my data renames the disk first; the uninstaller checks the kept file before and after `wsl --unregister`.
- F4a resume from RunOnce or the desktop shortcut; F4b each long action is a timed `Exec` job; F4c the keep-data form opens before any removal; F4d the named pipe is the only secret channel, tested with a random value first.
- F5: the first backup and `restic check` at install prove the drvfs mount.
- F6 (W6a-5): the CA job checks the chain; a throwaway `other.local` certificate must fail.
- F7, F8, F9: closed (7.4, H9, section 2). F10 (W13b-5): no unattended WSL install.
- W4-5: `prepare` checks systemd, Docker and mirrored mode. W7-6: the tasks keep the kit's settings (REQ-0022: E1, E2, E4, E5, E6).

### 10.4 Environment facts

Each run, and Save report, records the Windows build, CPU and virtualization, memory, free space and BitLocker state (never `KeyProtector`), WSL and kernel versions, Docker image digests, app version, network and proxy settings, firewall rules, port listeners on 80 and 443, power settings, antivirus and Smart App Control state, clock sync and pending restarts.

### 10.5 Failure snapshot

On any failure, both sides save WSL and systemd state, container states and redacted log tails (200 lines), `/api/ready` and `/api/health`, the Windows events since the run started, and the `\SlateOps\*` task results.

### 10.6 Save report

1. Every failure screen, and the Start menu entry "Slate Operations: Save report", has Save report. It works when the Linux part does not answer and then writes "Linux part not reachable".
2. One zip with the logs (10.1), facts (10.4), snapshots (10.5) and the report (10.2); the engine's `log-bundle` job makes the Linux part.
3. Before it writes, the engine replaces every secret value it holds, and both sides scan for secret patterns (private keys, tokens, connection strings, `KEY=value` secret lines, BitLocker recovery passwords). A file with a hit that cannot be replaced is left out and listed.
4. No business records, message text or file content; email addresses, user names and client addresses are replaced (Republic Act 10173).
5. The file goes to the running person's own desktop as `SlateOps-report-<run ID>.zip`. Nothing is sent automatically.

### 10.7 Failure catalog

Each anticipated problem has a detection, a logged fact, a message and a recovery; the messages end with Retry and Save report. Rows: virtualization off (R3); Windows too old or Home (R1, R2); restart pending; WSL MSI or `VirtualMachinePlatform` install fails (1618 retried 3 times, 3010 restarts); resume after restart does not start; antivirus or Smart App Control blocks; distribution import fails; Docker or systemd does not start; pull errors by class (name lookup, TLS, time-out, HTTP 429 with 3 retries, proxy not supported in v1); disk full during install or later; ports 80 or 443 in use; firewall rule fails; Public network or domain; `<name>.local` does not open on a phone; certificate not trusted; SMTP errors by class (including Microsoft 365 reply 535 5.7.139); provisioning, migration or readiness fails; "The service account cannot sign in" (`0x8007052F`, `0x80070569`; Repair resets the right and password); WSL stops the idle VM; Windows Update installs a newer WSL; power cut (journal resume); clock row (the engine compares its clock with a registry `Date` header; the image runs a time sync client, W4-6); low memory; Wi-Fi not connected at start; "the network changed" (Repair updates the rule); boot-test kit leftovers (removed first); uninstall leftovers (logged, removed by the next setup); kept data that does not match.

## 11. Slices

### 11.0 Delivery: one branch, one pull request

The first deliverable shipped as one pull request (#115); the plan made its merge wait for the owner's end-user pass (W14). The second deliverable (W11, W12, W13c, then W16) is a separate pull request and is not built. Every slice meets section 10.

Slices in build order: W1 single version source (W1-1 to W1-3); W2 env templates, full secret set and `local_ca.py` (W2-1 to W2-5); W3 release workflow and test builds, TASK-0079 (W3-1 to W3-6; W3-5 moved to W5b-10); W4 our Linux image (W4-1 snapshot build, W4-2 Docker key and pinned major, W4-3 no SSH or secret and interop and automount off, W4-4 package lists, W4-5 systemd and Docker start, W4-6 time sync, W4-7 notices and GPL sources); W5a engine bridge commands (W5a-1 to W5a-3, `policy_default`); W5b engine install, status and email check (W5b-1 to W5b-10: W5b-6 Caddyfile readable under the backup admission, W5b-7 app subnet check, W5b-8 `receive` limits, W5b-10 provider images from the H9 registries); W6b trust page (W6b-1 to W6b-3); W6a TLS and the LAN name (W6a-1 to W6a-7; W6a-7 `/trust/ok` is static); W10a backup fail-open (W10a-1 to W10a-6); W10b backup timer, location and recovery key (W10b-1 to W10b-5; W10b-4 Caddyfile admission); W7 Windows plumbing (W7-1 to W7-7); W8 wizard pages and finish (W8-1 to W8-7; W8-5 recovery key, W8-7 below 2 GiB); W9 uninstall, kept data and maintenance mode (W9-1 to W9-6); W13a engine-only restore mode (W13a-1, W13a-2); W13b engine update and setup-program update (W13b-1 to W13b-10; W13b-5 WSL step, W13b-9 no subnet overlap, W13b-10 SemVer order); W14 the owner's end-user pass (W14-1 to W14-6); W15 documentation (W15-1 Docker Engine not Docker Desktop, W15-2 glossary rows, W15-3 no "production-ready" claim).

Second deliverable (not built; rows unchanged):

| ID | Slice | Owner | Files or area | Contracts changed | Acceptance criteria | Proof | Needs from the owner | Depends on |
|---|---|---|---|---|---|---|---|---|
| W11 | Update queue API and table (second deliverable) | Backend Engineer | `backend/app/systems/manage/backups/` (or a new `updates/` folder; the Software Architect decides), migration, `backend/operations/backup_state.py` (update operations in the existing union) | **New routes, table, column and bridge operations (7.2)** | W11-1: 201 with `Location`. W11-2: 409 `update_active`. W11-3: 409 `update_not_cancellable` after the claim. W11-4: 409 `update_target_stale`. W11-5: 409 `updater_unavailable` when the engine was not seen in 5 minutes. W11-6: 403 for a non-owner, and 404 or 403 per the current rules for others. W11-7: `update_claim` is exclusive under concurrency, under the existing advisory lock. W11-8: `update_close_restored` is admitted only by a valid restore-finalized marker. W11-9: the migration passes `alembic check`. Meets section 10. | Focused pytest plus the PostgreSQL integration batch | — (H2 decided, DEC-0030) | Software Architect contract review |
| W12 | "Install tonight" UI (second deliverable) | Frontend Engineer | `frontend/src/components/systems/manage/components/updates-panel.tsx`, `domain/updates-rules.ts`, `adapters/backup-api.ts` | None | W12-1: each state in 7.1 renders from the API. W12-2: Cancel works only while queued. W12-3: only the installation owner sees the button, and only while the engine was seen in the last 5 minutes. Meets section 10. | Isolated and http Playwright specs; hands-on | — | W11, design |
| W13c | App-queued update in the engine (second deliverable) | Infrastructure Engineer | `packaging/engine/`, `.github/workflows/release.yml` (the public GHCR push of stable releases) | Uses the 7.2 contract (H2) | W13c-1: a queued run updates `v0.2.0` → `v0.2.1` (decision H8) at the window, and `/api/version` shows `v0.2.1`. W13c-2: the claim, the progress, the outcome and the heartbeat use the bridge operations of 7.2. W13c-3: after a rollback, `update_close_restored` writes `rolled_back`, and the run is never claimed again. W13c-4 (when the license work gives a test path): a licensed installation keeps its edition after a rollback. Meets section 10. | Engine unit tests; Linux-host runs. W13c-1: the owner's in-app update pass (W16). | Before the first stable tag, three GitHub settings: GHCR package visibility, a `v*` tag rule and immutable releases. Then he publishes two stable releases after the license work merges (decision H8, section 5.3) | W11, W13b; the license work for W13c-1 |
| W16 | The owner's in-app update pass (second deliverable) | Human Owner as the end user; the QA Engineer | No code | None | W16-1: on `v0.2.0`, Manage → Updates shows `v0.2.1`; "Install tonight" queues it; the next morning the page shows "Updated to 0.2.1". W16-2 (when the license work gives a license path for release builds): a licensed installation keeps its edition after the update. Meets section 10. | What the owner sees, written in the company record; the Save report file | Runs the pass on the stable tags (H8) | The second deliverable, the license work, the stable tags |

### 11.1 Reviews and other roles per slice

Every slice gets a Software Architect code review. The Security Engineer also reviews each slice that touches secrets, the boundary, ports, the CA, signatures, the backup admission or authorization (W11 included). The Product Designer reviews screens (W6b, W8, W9, W12), and the QA Engineer reviews W8 to W16.

### 11.2 The owner's end-user pass (W14)

The owner installs from a draft test build, signs in on the PC and the phone through the trust page, checks the next morning's backup, updates with a newer test build, opens Modify and saves a report, uninstalls with "Keep my data", reinstalls with the kept data, and sends a report for any error (W14-1 to W14-6). Each defect becomes a failing-first test and a fix.

## 12. Risks

- Unsigned builds: buy a code-signing certificate before the first customer install (H1).
- A Windows Update restart in the 02:00 window: the engine resumes from the open journal; before the first container on a target image it runs `recover`, after it rolls back by restore (7.5).
- A `RESTORE.md` support restore on the same Docker daemon reuses the app subnet; remove the old networks first or use another /28.
- The data disk is not encrypted unless BitLocker is on (H5).

## 13. Decisions for the owner

All decided: H1 in DEC-0028, H2 to H13 option a) in DEC-0030 and APR-0011.

| ID | Decision |
|---|---|
| H1 | Unsigned builds until the first customer install. |
| H2 | Approve the update contract of 7.2 exactly, including `policy_default`. |
| H3 | Accept the secret exceptions of 3.2 after the Security Engineer's review. |
| H4 | Attach the Debian and Alpine source packages to each release (GPL source offer). |
| H5 | Block Windows 11 Home until it is tested; recommend BitLocker. |
| H6 | Alerts for a failed backup or update are in-app only in v1. |
| H7 | Support-run restore with the engine; replaced on 2026-11-24 by the owner's one-button restore (8.4). |
| H8 | Two published stable releases after the license work for the in-app update pass. |
| H9 | Provider images from `ghcr.io/supabase/*` and `ghcr.io/imgproxy/imgproxy` at the same digests; Envoy from Docker Hub. |
| H10 | A second public listener on port 80 for the trust page only. |
| H11 | The `release-manifest.json` format of 5.2 is public; old fields stay readable. |
| H12 | An engine-only non-interactive restore mode in `restore_installation.py`. |
| H13 | Test-build pre-releases are allowed; the first deliverable used drafts. |

## Open items

- The second deliverable is not built: W11, W12, W13c and W16 (sections 7.1, 7.2, 11.0). The stable tags are v1.0.0 and v1.0.1, not the `v0.2.0`/`v0.2.1` that H8 and W13c name.
- W15-2: the glossary has no rows yet for the installer terms (installer, engine, release manifest, maintenance mode, recovery key, trust page, Save report and others).
- The file fallback of the secret channel (F4d) is a reserve design only.
- Device rejection of a wrong name under the name constraints is unverified (F6).
