# Windows installer plan

Status: **proposed**. Nothing here is built. The owner approved the scope on 2026-11-16 (company records DEC-0028 and APR-0010). This plan names three new API routes, one new table and one new bridge command (section 7.2). The owner approved them with decision H2 (company records DEC-0030 and APR-0011). Company record DEC-0029 adds self-hosted editions: every installation starts as Desk, and the first public download needs the separate license work (section 5.3). Company record DEC-0031: the owner tests only what end users see, and no virtual machine runs on the development machine. Section 10 replaces the owner's spikes with conservative designs and self-checks. The work ships as one pull request with one first deliverable (section 11.0). Base revision: `b33ee415` on `feat/windows-installer`.

## 1. Outcome

A person who is not technical installs Slate Operations on a Windows 11 PC with a normal Windows setup wizard. The person never opens PowerShell or a command line. The wizard lets the person choose the drive and folder for the program and for the data. In the first deliverable, an update starts when the person runs a newer setup program. Updates from the app (Manage → Updates) come in the second deliverable (section 11.0). Uninstall starts from Windows Settings → Apps and asks "Keep your data?".

First-version choices (DEC-0028):

- Windows 11 only.
- The customer's own email account, set up after the install in the "Slate Operations settings" program on the server PC (DEC-0041). Presets: Gmail and Other (custom SMTP; DEC-0040), with a "Send test email" check. Setup itself asks for no email account.
- HTTPS with a local certificate authority (CA). The installer trusts it on the server PC. Phones and other PCs use a "Trust this device" page.
- Unsigned builds until the first customer install. Only the owner's PCs run them.
- No company installation service, no email relay, no public certificates.
- Every installation starts as the Desk edition (free). The administrator imports a license file inside the app, in Manage → Updates & licensing (DEC-0029 item 10). It is never in the wizard (the owner, company record TASK-0076: "I want it inside the system itself and not on the wizard").
- The first public download includes the edition limits and the license import (DEC-0029 item 13). Until the license work merges, every release is a test build (section 5.3).

### 1.1 Preserved

- The self-hosted Compose stack and the Linux server path keep working. Windows is an added path through the same engine (section 6).
- Every production security control in `SECURITY.md` ("Controls that reviews protect"): HttpOnly cookies, CSRF with the exact `Origin`, allowed hosts, rate limits, audit, the provider secrets kept out of the API environment, SHA-pinned Actions.
- Application images stay free of provisioning and secrets (`infra/AGENTS.md`). They do not start provider services, run migrations, provision roles or buckets, or bootstrap users. The engine does these steps from outside the images.
- One `PUBLIC_ORIGIN` per installation (`backend/app/core/config/settings.py:121`) and one Caddy `--public-host` (`infra/caddy/generate_config.py:175`).

### 1.2 Excluded

The company installation service, the email relay, public certificates, the purchase of a code-signing certificate, the managed cloud, installers for macOS or Linux desktops, Windows 10, Windows on Arm, and everything else that DEC-0028 defers. Windows 11 Home stays untested (section 4.2, requirement R2).

The license work is also excluded. It holds the license file format, the signature check, the limit counters and the read-only state. It also holds the "Available in Office" previews and the test license. It is a separate build with its own contract (DEC-0029 Follow-up), and it starts only when the owner says so. This plan needs it before the first stable release. So the stable tags, the second deliverable's end-user pass (W16) and the first public download wait for it (section 5.3). The first deliverable does not wait for it.

### 1.3 Labels

**Current** means read in the code at the base revision. **Observed** means measured on the owner's Windows 11 Pro PC in the boot test (company request REQ-0022). **Proposed** means this plan. **Assumption** means not checked; section 10.3 gives the conservative design and the self-check that cover it. **Planning value** means a number that this plan uses until the installer report of the owner's first real install corrects it (section 10.2).

**Edition** means a self-hosted edition: Desk (free), Office or Headquarters (DEC-0029 item 2). Core and Scale are managed cloud plans only, and this plan does not use them. A Windows edition (Home, Pro) is always called a Windows edition. **License file** means the signed file of an edition; the Elastic License 2.0 is always named in full.

## 2. Current state

| Area | Current state | Source |
|---|---|---|
| Runtime on Windows | **Observed:** WSL2 with Docker Engine in our own imported Debian 13 serves the LAN at boot with nobody signed in. A hidden standard account runs it through Task Scheduler. It recovered after shutdown, restart, sign-out and `wsl --update`. Ready about 30 to 36 s after Windows starts. The WSL update restarted the Linux VM; the outage was about 2.5 min. | REQ-0022; `infra/windows/boot-test/README.md` |
| Proven mechanisms | Per-account `.wslconfig` (`vmIdleTimeout=-1`, `[general] instanceIdleTimeout=-1`, fixed memory, `networkingMode=mirrored`, `defaultVhdSize`); the on-demand job task `Exec` with an allow-list (`lib/svc-exec.ps1`); the boot task (At startup, `PT0S`, 1-minute repetition, IgnoreNew, keep-alive attached, `lib/start-distro.ps1`); Windows and Hyper-V firewall rules (Private, local subnet); Docker from Docker's apt repository with a key fingerprint check; folder ACL hardening and the safety check; cleanup. | `infra/windows/boot-test/` (pull request 113) |
| Installer findings | **Observed:** the server PC cannot open its own LAN address into WSL in mirrored mode. WSL updates cause a short outage. salsa.debian.org serves a bot check to PowerShell's default user agent. Drive C: can be small (26.6 GB free on the test PC). | REQ-0022 |
| Production install | About 9 manual commands and 3 env files written by hand. | `infra/supabase/README.md:29-140` |
| Secrets | `supabase_keys.py` generates the provider keys and some application keys (for example `SUPABASE_SESSION_ENCRYPTION_KEY`, the Realtime keys). It does not generate `SECURITY_EVENT_SERVER_KEY`, the `slateops_owner` and `slateops_runtime` passwords, the SMTP values or the Restic password. It writes `NAME='value'`; `docker run --env-file` needs the literal `KEY=value` format (inferred from `infra/supabase/README.md`, provisioning env). It imports `jwt`, `cryptography` and `app.*`, so it runs only with the backend environment. | `backend/operations/supabase_keys.py:109,140` |
| First administrator | `bootstrap_admin.py` needs `--confirm` outside development, `ADMIN_EMAIL`, `ADMIN_USERNAME`, a running API and working SMTP. `--name` and `--slug` set the first organization. No production step runs it. (DEC-0041 adds `--password-stdin`: install step 11 creates a confirmed account with a password and needs no SMTP.) | `backend/operations/bootstrap_admin.py:54-64,196-228`; `settings.py:348-350` |
| Images | CI builds the server image for amd64 only, with `push: false`. CI does not build the Caddy image. | `.github/workflows/backend.yml:288-310` |
| Version | Hard-coded `0.1.0`. | `backend/app/main.py:186`; `backend/pyproject.toml:3` |
| Update check | The backup runner reads GitHub `releases/latest`, ignores drafts and pre-releases, and records `update_statuses`. `GET /api/version` shows the running version. No update is applied; updates are prose only. | `backend/operations/backup_runner.py:67-95`; `backend/app/systems/manage/backups/router.py:245`; `infra/supabase/README.md:92-98` |
| Backup | An offline physical Restic backup. It stops the services. The app queues runs (`POST /api/backups`); a host runner claims them once a minute through a bridge in the release image. The host runner uses only the Python standard library. After a failed backup the services stay stopped until an operator runs `recover`. | `infra/supabase/RESTORE.md:48-104`; `backend/operations/backups/` |
| Restore | Support-run, about 15 steps. A restore always goes into a **new** Compose project with a **new** `SLATEOPS_INSTANCE_ID`. Finalization revokes all application sessions. | `infra/supabase/RESTORE.md:132-200` |
| Alerts | There is no application mailer. System health shows backup freshness and failed jobs. | `backend/app/systems/manage/health/organization.py`, `installation.py` |
| Editions | No code checks a license or a limit (DEC-0029, Context). Manage → Updates & licensing shows "No license required · Self-hosted". | `frontend/src/components/systems/manage/domain/updates-rules.ts:9` |
| Setup page | `/setup` says "the installer creates the first administrator". | `frontend/src/app/setup/page.tsx:50,60` |
| Documentation | `infra/AGENTS.md` and `infra/supabase/PLAN.md` describe Windows as Docker Desktop with WSL2. This plan uses Docker Engine in our own distribution instead. | `infra/AGENTS.md` |

Windows and email facts used in this plan come from the Software Architect's facts runs of 2026-11-16 (summarized in company record TASK-0073):

- Inno Setup has no mandatory fee. Its `PrepareToInstall` can return `NeedsRestart`, and a resume after a restart needs a sign-in (RunOnce).
- WiX v7 needs a paid sponsorship above $10,000 revenue.
- MSIX cannot turn on Windows features, import a distribution, add tasks or add firewall rules.
- WSL has an offline MSI. `VirtualMachinePlatform` needs one restart, and virtualization must be on.
- Mirrored networking needs Windows 11 22H2 (build 22621) or later.
- SmartScreen warns on unsigned and new-publisher builds. Smart App Control blocks unsigned code.
- GoTrue SMTP supports a user name and password only (PLAIN, LOGIN, CRAM-MD5; no OAuth). It uses implicit TLS on port 465 and opportunistic STARTTLS on other ports.
- Microsoft 365 turns Basic SMTP AUTH off by default for existing tenants at the end of December 2026. A tenant administrator can turn it back on.
- Gmail app passwords need 2-Step Verification and are revoked when the account password changes.
- `.local` (mDNS) resolves on Windows 10 1703 and later, on Apple devices, and on Android since about 2021. It does not resolve across subnets.
- No public certificate can name `.local` or a private IP address.
- iOS needs a profile plus "Certificate Trust Settings". Chrome on Android trusts user-added CAs.
- Passkeys need a domain-format RP ID. An IP address cannot be an RP ID. The app has no passkeys today, so this is a reason for the future only.

**Plan location.** `infra/supabase/PLAN.md` is the Supabase migration contract (deployment topology, authentication, files, Realtime). It does not cover packaging, release, a Windows installer or updates, so this plan is a new file, as `docs/AGENTS.md` allows.

## 3. Architecture (proposed)

```text
 Windows 11 PC
 ┌──────────────────────────────────────────────────────────────────────────┐
 │ SlateOpsSetup-<version>.exe (Inno Setup, elevated)                       │
 │   wizard ─ maintenance mode (Start menu "Slate Operations settings")     │
 │   uninstaller (Settings → Apps)                                          │
 │        │ request file; answers and secrets through a named pipe          │
 │        ▼                                                                  │
 │ Task \SlateOps\Exec  (runs as hidden account slateops-svc)               │
 │   allow-listed jobs → wsl.exe -d SlateOps -u root --                     │
 │                        slateops-engine <job>  (answers on stdin)         │
 │ Task \SlateOps\Start (At startup, as slateops-svc) → keep-alive attached │
 │ Firewall: TCP 443 and 80, Private profile, local subnet (+ Hyper-V)      │
 │ hosts: <name>.local → 127.0.0.1     LocalMachine Root: our CA            │
 └───────────────┬──────────────────────────────────────────────────────────┘
                 │ WSL2, mirrored networking
 ┌───────────────▼──────────────────────────────────────────────────────────┐
 │ Distribution "SlateOps" (our Linux image, Debian 13 based)               │
 │   disk: <data folder>\SlateOps\distro\ext4.vhdx  (all business data)     │
 │   systemd: docker.service, slateops-runner.timer (1 min)                 │
 │   /usr/local/bin/slateops-engine → /opt/slateops/engine/<version>/       │
 │   /etc/slateops/ (root 0600): provider.env, app.env, Restic password,    │
 │     Caddyfile, tls/ (Caddy)   ca/ (CA keys; Caddy does not mount it)     │
 │   /var/lib/slateops/: journals     wsl.conf: interop off, automount off  │
 │                                                                          │
 │   Engine (root, standard-library Python) ──docker──► Compose project     │
 │     one-shot jobs in the release server image:                           │
 │       keys, provisioning, migrations, CA, first administrator, bridge    │
 │                                                                          │
 │   Compose: db auth storage imgproxy realtime meta studio api-gw          │
 │            api (FastAPI + static UI)   caddy (:443 TLS, :80 trust page)  │
 └──────────────────────────────────────────────────────────────────────────┘
 Phones and PCs on the LAN → https://<name>.local
```

### 3.1 Parts

| Part | What it is | Runs as | Talks to |
|---|---|---|---|
| Wizard and uninstaller | One Inno Setup program, per machine, elevated. It holds the Windows-side scripts, which come from the boot-test kit. | The signed-in administrator | `Exec` task (writes a request file, then reads the result file), Windows APIs |
| `\SlateOps\Exec` | The kit's on-demand job task, renamed. It accepts only allow-listed job names and validates the request ID. | `slateops-svc` (standard user, batch logon right, deny local, RDP and network sign-in, hidden) | `wsl.exe` into the distribution as root |
| `\SlateOps\Start` | The kit's boot task, renamed. | `slateops-svc` | Starts the distribution and keeps `keepalive.sh` attached |
| Linux image | A Debian 13 root file system that CI builds, with Docker Engine, Restic, Python 3, the engine of the same release and systemd units. It holds no secrets and no SSH server. `wsl.conf`: systemd on, Windows interop **off**, automatic drive mounts **off** (`[automount] enabled=false`). | — | — |
| Engine | `slateops-engine`, a command in `packaging/engine/` that uses only the Python standard library, like `packaging/backup/`. It owns install, the setup payload (`receive`, 5.2), status, update, backup scheduling, restore, the email check, the CA and the uninstall support. Steps that need `app.*`, `jwt` or `cryptography` run as one-shot containers of the release server image, the same pattern as the current provisioning job (`infra/supabase/README.md`, Lifecycle). | root in the distribution (it needs the Docker socket) | Docker, the bridge in the server image, the provider registries (H9); GitHub Releases and GHCR only in the second deliverable |
| Engine bundle | One file per release: the engine, the Compose files, the Caddy template, the env templates and `release-manifest.json`. The Linux image contains the bundle of its own release. An update replaces the bundle under `/opt/slateops/engine/<version>/`. | — | — |
| Setup payload | Proposed. The parts that the setup program carries for the engine (5.2). They are the engine bundle, the signed manifest and our two container images as image archives. | — | `receive` job |
| Compose stack | `infra/supabase/compose.yaml` plus `compose.production.yaml`, unchanged in shape. | Docker in the distribution | — |
| App | FastAPI with the static UI. It queues update runs (section 7.2) the same way as backup runs. | uid 10001 in its container | PostgreSQL |

### 3.2 Rules of the boundary

1. Windows calls Linux only through `Exec` jobs. The job name comes from a fixed allow-list. Data goes on standard input as JSON, never as command arguments. The one exception is `receive`: it takes the setup payload as a tar stream on standard input, with a size limit. The engine uses a part only after it matches the signed manifest (5.2). The kit already refuses to run when PowerShell module logging covers `ScheduledTasks`, and the installer keeps that check.
2. Linux never starts a Windows program: interop is off. The only Linux value that the Windows side acts on is the `engine_idle` boolean in `slateops-engine status --json`. The setup program uses it only to wait before it installs the pinned WSL MSI (7.4). It shows other safe status codes to the person and acts on none of them. No value from Linux becomes a path, a URL or an argument on the Windows side. The Windows side sends two values to the engine on the standard input of `status`: the Windows-part version and the installed WSL version. Linux cannot read Windows files (automount off).
3. Secrets are made and kept on the Linux side, in `/etc/slateops/` (root, mode 0600). Three values cross the boundary, and each is a named exception:
   - The first administrator's password moves Windows → Linux once, as `admin_password` on the standard input of `install` (DEC-0041). The engine holds it in memory only, masks it in every log line, and gives it to step 11 on the container's standard input. It is never written to a file, an argument or an environment value. A kept-data reinstall sends no password.
   - The SMTP password moves Windows → Linux once, after the install, from the "Slate Operations settings" program (DEC-0041). `smtp-test` receives it, and after a passing test the engine stages the SMTP values in `/etc/slateops/new/smtp.env` (root, 0600). `set-email` reads the staged file, so the password never crosses a second time. A failed test stages nothing.
   - The backup recovery key moves Linux → Windows once, for display on page 11 (section 8.3). The recovery key is a second Restic key, not the engine's working password. The only Windows-side writes of it are the person's own Print and Save to a USB drive on page 11.
   - Channel (proposed): a named pipe. The wizard creates it with an access list for Administrators and `slateops-svc` only. The `Exec` job connects to it and moves the bytes between the pipe and the engine's standard input or output. Neither value is written to a Windows disk. Before the first secret, a channel self-test sends a random value through the pipe (10.3, F4d).
   - Fallback (not built in v1; a reserve design for a fix build, 10.3 F4d): a file in the admin-only state folder with an access list for Administrators and `slateops-svc`. The wizard deletes it right after use, and the file exists for seconds.
   
   The Security Engineer reviews both exceptions and the fallback (decision H3) with these checks:
   1. The wizard creates the pipe with a random name for each request, as the first instance (`FILE_FLAG_FIRST_PIPE_INSTANCE`), before it starts the job. The pipe refuses remote clients, and its access list holds only Administrators and `slateops-svc`.
   2. The job checks the identity of the process that created the pipe before it reads or writes.
   3. No secret is a command-line argument, an environment value, a task property, a PowerShell cmdlet parameter or a log line. If a helper must pass a secret to a cmdlet, the module-logging check (R7) covers every module that the helper uses.
   4. Inno Setup does not save the password field (`RegisterPreviousData`) and does not write it to its `/LOG` file.
   5. The engine reads standard input with a size limit, writes the SMTP values only to `/etc/slateops/new/smtp.env` (0600), holds the administrator password only in memory, and echoes nothing.
   6. The fallback (if used) never holds the password in plain text: the engine publishes a temporary public key, and the wizard encrypts the value to it. The file has the same access list, is deleted after use, and never reaches `svc-out` or a log bundle.
   7. The recovery key is shown once. Print and Save to a USB drive are the only writes; printing creates a spool file, which is a named exception (W8-5). The log bundle never holds the key.
4. Linux reaches a Windows drive only when the engine mounts the backup drive with drvfs, with the rights of `slateops-svc`. Automatic mounts are off. The installer gives `slateops-svc` access only to the data folder and the backup folder.

## 4. Wizard (proposed)

### 4.1 Page order

The owner's page list puts the restart after the email page. This plan moves the one restart forward, to the "Prepare this PC" step after the requirements check, for two reasons:

- No secret (the administrator password) must stay on disk across a restart.
- All server work starts after Install, so the restart must come before the pages that collect the answers (DEC-0041).

The Linux disk needs the chosen data folder, so the distribution is imported right after the location page. The engine downloads the images in the background while the person fills in the next pages.

| # | Page | Fields | Checks | Failure message (draft; the Product Designer writes the final copy) |
|---|---|---|---|---|
| 1 | Welcome | — | An existing installation is found: when this setup is newer, it offers Update (7.4); otherwise the maintenance mode opens (section 9.3). Versions are compared by SemVer precedence, so `X.Y.Z-rc.N` is older than `X.Y.Z-rc.N+1`, and both are older than `X.Y.Z`. Kept data is found → offer reuse on page 4. | — |
| 2 | License agreement | Accept the Elastic License 2.0 (`LICENSE`). Link to the third-party notices. This page has no edition choice and no license file. | Accept is required. | — |
| 3 | Requirements | None (a list with a pass or fail mark per line) | R1 to R9 in 4.2 | Per line, in 4.2. "Next" stays off until every blocking line passes. |
| 3a | Prepare this PC (only when needed) | — | Turns on `VirtualMachinePlatform`. Installs the pinned WSL MSI, with the SHA-256 checked right before `msiexec`. | "Slate Operations must restart this PC once. Save your work, then select Restart now. After you sign in, setup opens again. If it does not, select Continue Slate Operations setup on the desktop." Setup opens again at page 4 (RunOnce, or the desktop shortcut; 10.3, F4a). |
| 4 | Location | Program folder (default `C:\Program Files\Slate Operations`). Data folder (default `<largest fixed NTFS drive>\SlateOps`). | The data drive is a fixed NTFS drive: not removable, not network, not compressed, not EFS-encrypted. Free space ≥ 25 GB (planning value, 10.2). The folder is empty, or it holds kept data. | "This drive has X GB free. Slate Operations needs Y GB. Choose another drive." / "Choose a drive inside this PC. USB and network drives cannot hold the data." |
| 4a | Getting Linux ready (progress) | — | Creates the service account, `.wslconfig`, imports the Linux image (SHA-256 checked), runs the boot task. Then it streams the setup payload into the engine (`receive`, 5.2). Then it runs `slateops-engine prepare`: systemd and Docker ready, mirrored mode confirmed (10.3, W4-5). Then it starts the pull of the provider images. | "Setup could not start the Linux part. Select Retry. If it fails again, select Save report." Save report is defined in 10.6. |
| 5 | Business and administrator | Business name. Administrator email. Administrator user name (default: the part of the email before `@`, cleaned to `^[a-zA-Z0-9_-]{3,100}$`). Administrator password and its confirmation (DEC-0041). | Name 1 to 100 characters. The slug comes from the name (shown, can be edited). Email format (any address; no email is sent to it). User name pattern (`users/schemas.py:259`). Password: 12 characters or more, at most 72 bytes, one line (the engine and `bootstrap_admin.py` check the same rule). | "Use 3 to 100 letters, numbers, - or _." |
| 6 | (Removed by DEC-0041) | Setup has no email page. The email account is set up after the install in the "Slate Operations settings" program (section 9.3): `smtp-test` sends the test email to the administrator's stored address, then `set-email` applies the values. Until then, invitations, password resets and email-address changes end with `email_not_configured`. | — | — |
| 7 | Backups | Where to keep backups: "This PC's data drive (not safe if this drive fails)" or another drive or a USB drive. | The target is writable by `slateops-svc` and has free space. On the data drive the page shows a warning and needs a check box. | "Slate Operations cannot write to E:. Plug the drive in, or choose another drive." |
| 8 | Network name | The address is `<address name>.local`. The address name comes from the organization name on page 5 (DEC-0039); the person can change it under More options. Setup's own mDNS responder answers the name (10.3, F1). v1 offers no other name. The page shows the address that phones use. The IP address is not offered: the app has one `PUBLIC_ORIGIN` and checks the exact `Origin` on changes, so a second address would break sign-in and saves. (A future passkey also cannot use an IP address.) | The network is Private (offer "Make this network private"). No other device answers to the name (one mDNS probe). Ports 443 and 80 are free on Windows. The install adds one inbound firewall rule for the responder: UDP to local port 5353, Private profile, local subnet only, for Windows PowerShell (the responder's host process; Windows cannot name one PowerShell process, so the rule covers every PowerShell program on the PC; Human Owner accepted this as S97-5 option a, DEC-0039); the removal and the uninstall remove it (DEC-0039). | "This network is Public. Slate Operations works only on a private network. Select Make private." / "Another program uses port 443 (for example IIS). Stop it, then select Retry." / "Another device on this network already uses <name>.local. Choose another address name." |
| 9 | Ready | A summary of the choices | — | — |
| 10 | Installing (progress) | — | `slateops-engine install` steps (section 6.2) with a step list. The firewall rules, the hosts entry, the CA in LocalMachine Root and the sleep setting run on the Windows side. Then the wizard opens `https://<name>.local/api/health` from Windows with normal certificate checks (10.3, F2 and F6). | For each step: "Retry" and "Save report". A failed install keeps all state so that "Retry" resumes it. Check failure: "This PC cannot open Slate Operations at https://<name>.local." |
| 11 | Recovery key | The key, shown once. Buttons: Print, Save to a USB drive. | Check box "I saved the recovery key" is required. | — |
| 12 | Finish | "Open Slate Operations" (default browser at `https://<name>.local`). A QR code for phones that opens `http://<name>.local/trust`. Text: "Sign in with the administrator email and the password from page 5." (DEC-0041) Text: "If your phone cannot open the page, connect it to the same Wi-Fi as this PC and turn off its VPN." Text: "Your edition is Desk (free). To use Office or Headquarters, import your license file in Slate Operations: Manage → Updates & licensing." | — | — |

**Cancel, close and failure (DEC-0041).** The result is a complete installation or nothing. Cancel, closing the window, a failed install and a run that did not finish remove everything that setup added (never data that an uninstall kept). There is no "continue later". While an install step runs on page 10, Cancel waits for that step to end, then removes everything.

**Edition at first run.** Every new installation runs as Desk. No wizard page asks for an edition or a license file. The maintenance mode (9.3) has no license import. Source: the owner, company record TASK-0076: "I want it inside the system itself and not on the wizard". The administrator imports a license file in the app, in Manage → Updates & licensing (DEC-0029 item 10). The license work owns that control and its states. The license work decides how a reinstall with kept data (9.2) keeps the edition.

**Handoff to the license work.** These points of this plan touch the license work, and its contract must cover them:

1. Updates (`POST /api/updates` and the engine update) and backup runs stay allowed in the read-only state after the end of a license. Source: DEC-0029 items 6 and 11.
2. A rollback by restore (7.5) and a support restore (8.4) create a new instance ID. The license must stay valid after that change.
3. When the license work gives a license path for release builds, W16 checks that a licensed installation keeps its edition after the in-app update. A Linux-host run of W13c checks the same after a rollback.

The Product Designer must design pages 3, 4, 6, 7, 8, 11 and 12, the trust page and the uninstall page (section 9) before the build. The Inno Setup default pages (1, 2, 9) need only copy.

The wizard spec `docs/specs/windows-installer-wizard.md` (TASK-0080) gives the final page order, checks and copy. It puts the PC check before the license and folds page 8 into the PC check. Where the spec differs from 4.1, 4.2 or the 6.2 allow-list, the spec wins once the Software Architect, and for the allow-list also the Security Engineer, accepts it.

### 4.2 Requirements check

| ID | Check | How | Blocking | Message |
|---|---|---|---|---|
| R1 | Windows 11, build 22621 or later | Registry `CurrentBuildNumber` | Yes | "Slate Operations needs Windows 11, version 22H2 or later. Run Windows Update, then try again." |
| R2 | Windows edition Pro, Enterprise or Education | `EditionID` | Yes (decision H5; default: Home is blocked until it is tested) | "Slate Operations is not yet tested on Windows 11 Home." |
| R3 | Virtualization on | `Win32_Processor.VirtualizationFirmwareEnabled`, or `Win32_ComputerSystem.HypervisorPresent` when a hypervisor already runs (property names are an assumption; W7 checks them in Microsoft's documentation). When neither value can be read, R3 shows a warning, and the `prepare` self-check on page 4a catches a real failure. | Yes | "Turn on virtualization in the PC's firmware (BIOS or UEFI) settings. Your PC supplier can help." |
| R4 | Memory | Total physical memory ≥ 16 GB (planning value, 10.2) | Yes | "This PC has X GB of memory. Slate Operations needs Y GB." |
| R5 | Free space on the chosen data drive | Checked on page 4 | Yes | Page 4 |
| R6 | Not joined to a domain network, and the active network is not Public | `Get-NetConnectionProfile` | Domain: yes. Public: page 8 offers the fix | "Slate Operations is not tested on company domain networks." |
| R7 | PowerShell module logging does not cover `ScheduledTasks` | Policy registry (kit check) | Yes | "A security policy on this PC records commands. Ask the person who manages this PC." |
| R8 | Internet access to ghcr.io and the Docker Hub registry (github.com only in the second deliverable) | HTTPS HEAD with a plain user agent (REQ-0022 finding) | Yes | "Setup cannot reach the internet. Connect this PC, then select Retry." |
| R9 | On mains power (laptops) | `Win32_Battery` | No (a warning) | "Keep this PC on mains power. A PC that sleeps or runs on battery stops serving the office." |

### 4.3 What goes where

| Part | Location | Why |
|---|---|---|
| Program | `C:\Program Files\Slate Operations\` (can be changed): the scripts, the uninstaller, `version.json`, the setup copy for maintenance mode | Protected from standard users; small (under 50 MB, assumption) |
| State and logs | `C:\ProgramData\SlateOps\` (Administrators and SYSTEM only; `slateops-svc` only where the kit allows): requests, results, logs | Same as the kit; the safety check applies |
| Data | `<data folder>\SlateOps\distro\ext4.vhdx`: the whole Linux disk, with the database, the files, the secrets and the journals | The only part that grows. The data folder can be on another drive, because drive C: can be small. `defaultVhdSize` is set from the free space (the planning value in 10.2 gives the minimum). |
| Kept data | `<data folder>\SlateOps\kept\` (after "Keep your data") | Section 9.2 |
| Backups | The folder from page 7, for example `E:\SlateOps-backups\` | A different drive protects against a drive failure |

## 5. Release artifacts (proposed)

### 5.1 Version

1. A Git tag is the only version source: `vX.Y.Z` on `main` for a stable release, and `vX.Y.Z-rc.N` on a commit of a pushed branch (in practice `feat/windows-installer`) for a test build (5.3). The release workflow refuses an rc tag whose commit is on no pushed branch.
2. CI passes `SLATEOPS_VERSION` as a build argument. The server image keeps it as an environment value and as the OCI label `org.opencontainers.image.version`.
3. `create_app()` reads `SLATEOPS_VERSION`. The default is `0.0.0+dev` for local runs. `backend/app/main.py:186` loses the literal.
4. The release workflow refuses a tag whose `X.Y.Z` differs from `backend/pyproject.toml` `version` and `frontend/package.json` `version`.

`GET /api/version` keeps its response shape. The value becomes real.

### 5.2 Release workflow

A new `.github/workflows/release.yml` runs on a `v*` tag push. The tag is a stable tag on `main` (second deliverable) or a test-build tag on the branch (5.3). A tag push runs the workflow file of the tagged commit, so it works before the file reaches `main`. A `workflow_dispatch` trigger does not: GitHub needs that workflow file on the default branch (GitHub documentation; the Infrastructure Engineer confirms it in W3). The workflow-level permission is `contents: read`. Each job gets only what it needs: the image job `packages: write`, `id-token: write` and `attestations: write`; the manifest-signing job `id-token: write`; the release job `contents: write`. Every Action is SHA-pinned. v1 builds `linux/amd64` only; arm64 waits for a real need.

| Step | Output |
|---|---|
| Build the server and Caddy images for `linux/amd64` with Buildx | Test builds: both images as image archives for the setup payload, each made from the pushed digest. The workflow also pushes them to GHCR as private packages; no install reads GHCR. Stable releases (second deliverable): `ghcr.io/<owner>/slateops-server:<version>` and `ghcr.io/<owner>/slateops-caddy:<version>`, public, anonymous pull |
| Sign the image digests with cosign keyless (GitHub OIDC). Attach build provenance. | Test builds: the digests are in the signed manifest. Stable releases: signatures and attestations in GHCR |
| Build the Linux image: `mmdebstrap` of Debian 13 from a fixed `snapshot.debian.org` date, plus Docker's apt repository (fingerprint check), Restic, Python 3, a pinned cosign release (SHA-256 checked; listed in the package list), the engine bundle, systemd units and `wsl.conf`. amd64 only. | `slateops-linux-<version>-amd64.tar.gz`, its package list and its source list |
| Build the engine bundle | `slateops-engine-<version>.tar.gz` |
| Write `release-manifest.json` (a new public format; owner decision H11): `schema_version` (1), the version, all image references by digest (our two images plus the pinned provider digests from `infra/supabase/compose.yaml`, as the compose file names them; W5b-10 moves them to the registries that H9 sets), for each of our two images an object with the reference, the archive file name, the archive SHA-256, the size and the image config digest, the SHA-256 of the Linux image and of the engine bundle, the minimum Windows-part version, the known-bad WSL versions (proposed, 7.4), and migration notes. Sign it with cosign keyless. Format rules (parent decision within H11): readers ignore unknown keys; a missing optional field means "not provided"; an added field keeps `schema_version` 1; a rename, a removal or a change of type or meaning raises it; a reader refuses a higher `schema_version`. | `release-manifest.json` and its signature bundle |
| Build the installer with Inno Setup (`ISCC`) on `windows-latest`. It carries the Linux image, the WSL MSI and the setup payload (the engine bundle, the signed manifest and our two image archives). The SHA-256 of the Linux image and of the WSL MSI is compiled in. | `SlateOpsSetup-<version>.exe`, one file (unsigned until decision H1 changes) |
| Collect the third-party notices: Python packages (from `backend/uv.lock`), npm packages in the static export (from `frontend/package-lock.json`), the Debian packages of the Linux image and of the server image (copyright files), the Alpine packages of the Caddy image, the Python runtime, Caddy, Docker Engine, Inno Setup, the WSL MSI (W8 checks its redistribution terms before any public build), and the provider images that the installation pulls | `THIRD-PARTY-NOTICES.txt` (also inside the installer and the Linux image) |
| Write the source offer for the GPL parts of the Linux image and of our two images: each Debian and Alpine source package and version with its source URL (decision H4: the source packages are also attached, DEC-0030) | `SOURCE-OFFER.txt` and the source packages |
| `SHA256SUMS` for every asset | `SHA256SUMS` |
| Create the GitHub Release as a **draft**. A test build stays a draft (5.3). The owner publishes only a stable release (second deliverable). | — |
| Installer and Linux image | The installer **carries** the Linux image and checks the compiled-in SHA-256 before `wsl --import`. It needs no download from a release, so a draft release serves the owner's test. The setup program streams the setup payload into the engine (`receive`). The engine checks the manifest signature with the identity `.github/workflows/release.yml@refs/tags/v*` of this repository, so a test-build tag on the branch passes. Then it checks each part: the engine bundle by its SHA-256, each image archive by its SHA-256 before `docker load`, and each loaded image by its config digest after it. The Linux image sets Docker's image store explicitly (W4). The Compose files name the loaded local images, so Compose never pulls our images (W5b). W3 records which digest survives `docker load` in each image store. |

**Which slice adds which step.** W3 builds only what exists when it runs:

- the server and Caddy images;
- the manifest, with the fields that exist then;
- the notices for those parts;
- `SHA256SUMS` and the draft release.

Later slices add their steps to the same workflow. W4 adds the Linux image, its package and source lists, the source offer, the source packages, and the notices and GPL source packages of our two images (W4-7). W5b adds the engine bundle. W7 and W8 add the installer. The manifest keeps the H11 format from W3 on. Some fields stay empty until their slice fills them: the Linux image SHA-256, the engine bundle SHA-256 and the minimum Windows-part version. In W3, the Infrastructure Engineer builds the workflow (TASK-0079). The switch of the provider image references to the H9 registries is W5b-10: it needs image admission by pinned digest, because the development stack's instance check stores the current image name.

The update check ignores drafts and pre-releases (`backup_runner.py:88`). `POST /api/updates` accepts only the latest observed stable release. So the in-app update pass (W16, second deliverable) needs two **published stable** releases (decision H8: for example `v0.2.0`, then `v0.2.1`). Both come after the license work (section 5.3). The first deliverable's update uses the setup-program path with two test builds (7.4), so it needs no published release. This plan adds no configurable release source; the README says none exists.

The GitHub release asset limit is 2 GiB per file (assumption from memory; W3 checks it). The installer holds the Linux image, the WSL MSI and our two image archives, but not the provider images. It stays below that limit (assumption; W8 checks the size in CI).

### 5.3 Releases before the license work

DEC-0029 item 13 allows no public release without the edition limits and the license import, so that no customer loses access in a later update. The repository is public. This plan uses these rules until the license work merges into `main`:

1. **Test builds are drafts.** The team pushes a test-build tag `vX.Y.Z-rc.N` on a commit of `feat/windows-installer`. The workflow makes a draft release with the title "Test build, not for customers". Nobody publishes it. Only people with write access to the repository can see a draft, so a test build is not a public release. The tag itself is visible, but it carries no release.
2. **One file.** The test-build installer carries the Linux image, the WSL MSI and the setup payload (5.2). It needs no public GHCR package, no published release and no anonymous download from GitHub. The provider images come from their public registries (H9).
3. **The only owner step before his test.** The owner downloads the setup file from the draft release while he is signed in to GitHub. The team does every other step: test-build tags, workflow runs and release notes. The first deliverable needs no GHCR visibility setting and no repository setting from the owner.
4. **Stable releases.** No stable tag `vX.Y.Z` is pushed before the license work merges. So every stable release contains the edition limits and the license import. The GHCR visibility setting, the stable tags and any owner setting that guards them belong to the second deliverable (11.0). The website links a stable release only after W16 passes. That release is the first public download.
5. **H13.** Decision H13 (DEC-0030) accepts published rc pre-releases. The first deliverable does not use them: a draft exposes less. A published pre-release stays allowed under H13 if a later need arises.

The license work is not a slice of this plan. The first deliverable does not wait for it. It blocks only the stable tags (H8), W16, the merge of the second deliverable's fixes and the first public download.

Order: the first deliverable merges after the owner's end-user pass (W14). Then the license work and the second deliverable merge, in either order. Then the owner publishes `v0.2.0` and `v0.2.1`, and he runs W16. This order has three costs:

| Cost | Solution |
|---|---|
| The second deliverable (W11, W12, W13c) merges before its end-user pass, because the stable tags must contain it. | It merges with the engine unit tests and the Linux-host runs. A W16 failure becomes a failing-first test and a fix with a new stable tag, before the website links a release. |
| W12 and the license work both change `updates-panel.tsx` and `updates-rules.ts`. | Each keeps the other's parts (7.1). The second to merge rebases onto the first. |
| W11 and the license work can each add an Alembic migration. | The second migration to merge rebases onto the first (its `down_revision`), and `alembic check` passes after the rebase. |

## 6. Install engine (proposed)

### 6.1 Contract

- One command does the full first install: `slateops-engine install`. It reads the wizard's answers as JSON on standard input.
- The answers schema has `business_name`, `slug`, `admin_email`, `admin_username`, `public_host`, `backup_target`, `data_vhd_max_gb` and `time_zone`. The install input also holds `admin_password` beside `answers` (never stored; required until step 11 is done; section 3.2). The install needs no SMTP values (DEC-0041).
- **Idempotent and resumable.** Each step writes its completion to `/var/lib/slateops/install-journal.json` before the next step starts. A rerun skips completed steps and repeats only the step that did not complete.
- A step never overwrites a secret, a CA key or a volume that exists. When existing state does not match the journal, the engine stops with a safe code and does not "repair" it.
- **No secret in logs or output.** The engine logs step names, durations and safe codes only. It runs `docker compose config` only with `--quiet`. It never echoes the answers. Its output is safe JSON, like the backup runner.
- The answers reach the engine only through the channel in section 3.2.

### 6.2 Steps of `install`

| # | Step | Where it runs |
|---|---|---|
| 1 | Validate the answers. Check the release manifest signature (cosign; the identity is the release workflow of this repository). Check the setup payload against it (5.2). | Host (engine) |
| 2 | Create the folders: `/etc/slateops` (0700 root), `/etc/slateops/tls` (server certificate and key; the only TLS folder that Caddy mounts), `/etc/slateops/ca` (CA material; never mounted into a container except the one-shot CA job), log root (owner 10001), backup-export root (as `infra/supabase/README.md` requires), state. | Host |
| 3 | Load our two images from the setup payload and check their digests. Pull the provider images by digest. The pull on page 4a already started this step. A pull error is classified and retried (10.7). | Host |
| 4 | Generate **all** secrets into `/etc/slateops/` in the literal `KEY=value` format: the keys that `supabase_keys.py` makes now, plus `SECURITY_EVENT_SERVER_KEY`, the `slateops_owner` and `slateops_runtime` passwords, the Restic password, every other secret that `Settings` requires, and `SLATEOPS_INSTANCE_ID`. The SMTP values come from the staged `smtp.env`. | One-shot container of the server image, with only `/etc/slateops/new` mounted, no network |
| 5 | Write `provider.env`, `app.env` and the provisioning env from the production templates in the engine bundle. | Host |
| 6 | Create the local CA if it is absent: a root, then an intermediate with X.509 name constraints, signed by the root. The constraint profile is in 6.3. Remove the root key after it signs the intermediate; only the root certificate stays, for the trust page and LocalMachine Root. Keep the intermediate key in `/etc/slateops/ca/`. The intermediate validity equals the root validity, because no root key remains to sign a new one. Issue the server certificate from the intermediate (validity 397 days or less; Apple's limit is 825 days, confirmed by F6) into `/etc/slateops/tls/`. Render the Caddyfile with `generate_config.py --tls-mode custom`. Write the trust files (root `.crt` and the iOS `.mobileconfig`). Before it writes any file, the CA job checks the chain (10.3, F6). | One-shot server-image container for the keys and the certificates; host for the files |
| 7 | Start the provider services. Wait for health, Realtime included. | Host (Compose) |
| 8 | Run the current provisioning job: `provision_database_role.py --confirm`, `alembic upgrade head`, `alembic check`, `provision_storage.py --confirm`. | One-shot server-image container on the provider network |
| 9 | Start `api`. Wait for `/api/ready` on the internal path. | Host |
| 10 | Start `caddy`. Check `https://<public_host>/api/health` through loopback with the Host header. | Host |
| 11 | Create the first administrator: `bootstrap_admin.py --confirm --json --password-stdin --name=<business_name> --slug=<slug> --time-zone=<time_zone>` with `ADMIN_EMAIL` and `ADMIN_USERNAME`, and the password on standard input. It creates a confirmed Auth account with that password, the profile, the organization and the administrator membership. No invitation and no email (DEC-0041). | One-shot server-image container |
| 12 | Initialize Restic at `backup_target`. Take the first backup and run `restic check` (10.3, F5). Write the version-3 backup config. Add the recovery key (`restic key add`). Turn on `slateops-runner.timer`, which replaces the per-minute Windows task in `RESTORE.md`. Set the default policy (daily, at 02:00 in the organization time zone) with the new `policy_default` operation of `backup_state.py` (W5a, decision H2). | Host |
| 13 | Write `installation.json` (version, project, instance ID, `public_host`). Return the safe result: the CA certificate (public), the recovery key (exception, section 3.2) and the status. | Host |

The wizard then does the Windows-side steps:

- firewall rules for TCP 443 and 80 (Windows and Hyper-V, Private profile, local subnet);
- the hosts entry `<public_host> → 127.0.0.1`;
- the CA in LocalMachine Root;
- Sleep and Hibernate on mains power set to Never;
- the HTTPS check from Windows (10.3, F2).

The `Exec` allow-list holds exactly these engine jobs: `receive`, `prepare`, `prefetch`, `smtp-test`, `install`, `status`, `update` (from the new setup program, 7.4), `set-email`, `set-backup-target`, `new-recovery-key`, `export-trust`, `log-bundle`, `prepare-uninstall`, `restore`. "Repair" in the maintenance mode is Windows-side work plus `status`.

### 6.3 Caddy and the trust page

- Caddy keeps `:443` with the custom certificate. A new `:80` site serves only `/trust`, `/trust/slateops-ca.crt` and `/trust/slateops.mobileconfig`. It redirects every other path to HTTPS.
- The trust page is a static, self-contained HTML file in the Caddy image (`infra/caddy/trust/`), with steps for iOS, Android, Windows and macOS. It shows the CA fingerprint; the finish page and the maintenance mode on the server PC show the same fingerprint.
- `generate_config.py` gets a `--trust-root` option.
- **Certificate profile** (F6 facts, company record TASK-0075):
  - Chrome (Windows, macOS, Android, Linux) and Apple (iOS, iPadOS, macOS) enforce name constraints in the intermediate. A constraint in the root is ignored by Chrome on Android, so the constraint stays in the intermediate.
  - The name constraints extension is critical. It has a `dNSName` subtree for `public_host`. A DNS-only constraint does not limit IP names, so it also has an `iPAddress` subtree that excludes all addresses.
  - The constraint `<name>.local` also permits every name below it, for example `a.<name>.local`. Only the engine holds the intermediate key, so this is accepted.
  - The server certificate is minimal: the DNS name `public_host` only, with no IP address in the subject or the SAN. Windows CryptoAPI can flag a name type in the leaf that no constraint covers, so the leaf has no name type that a constraint does not cover. The subject is empty, with a critical SAN (decided: Software Architect, TASK-0077 review; RFC 5280 4.1.2.6). Device acceptance stays unverified until the owner's run (DEC-0031).
  - The server certificate lifetime is 397 days or less. Apple's limit for certificates from user-added roots is 825 days.
- **Devices.** On Android, Chrome trusts the installed CA. Other Android apps that target Android 7 or later ignore user CAs by default (an app can opt in). The trust page tells Android users to use Chrome. On iOS, the trust page shows the second step, in Settings → General → About → Certificate Trust Settings. There the person turns on full trust for the root.
- Port 80 is new public exposure. The Security Engineer reviews it (W6a).
- Renewal: `slateops-runner.timer` also checks the server certificate once a day. The engine issues a new one from the intermediate 30 days before it expires and reloads Caddy. `/etc/slateops/tls/` is the backup set's `tls_directory`; W10b adds `/etc/slateops/ca/` to the backup set (the Software Architect decides how the version-3 backup config names it). A restore and a reinstall with kept data keep the same CA, so devices stay trusted.

## 7. Update (proposed)

The first deliverable has one update path: the person runs a newer setup program (7.4, last item). It runs the engine steps in 7.3 and the rollback in 7.5, with no `update_runs` row and no stable release. The in-app flow (7.1, 7.2) and the app-queued run come in the second deliverable (11.0).

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

1. Take the runner's host lock. For an app-queued run (second deliverable), claim the run. Open the journal.
2. Get the new `release-manifest.json` and the engine bundle: from the setup payload (setup-program path) or from the published release (app-queued path). Verify the signature and the SHA-256. Install the bundle beside the old one. Run the new engine for the next steps; keep the old one for the rollback.
3. Check the free space: the volumes need room for one restored copy (section 7.5). Not enough space → `failed`, `insufficient_space`, and nothing stops.
4. Load or pull the target images by digest while the services still run. In the setup-program path, our two images come from the setup payload.
5. Stop the services. Run the offline backup (current archive function). Record the snapshot ID in the journal.
6. Write the new env files from the new templates. Add new keys only, and keep every existing secret.
7. **Rollback boundary.** Start the provider services on the target images (`db auth storage imgproxy realtime meta studio api-gw`). The journal records this step before the first container starts.
8. Wait for provider health, Realtime included (`infra/supabase/README.md`, Lifecycle: provisioning needs `realtime.messages`).
9. Run the provisioning job with the target image: roles, `alembic upgrade head`, `alembic check`, Storage.
10. Start `api` on the target image. Wait for `/api/ready` on the internal path. Check that the running `api` container reports the target `SLATEOPS_VERSION` (W1). `GET /api/version` needs a signed-in owner, so the engine does not call it.
11. Start `caddy` last. Check HTTPS through loopback with the Host header.
12. Mark the run `succeeded` (the journal; and the `update_runs` row for an app-queued run). Release the lock. Remove the old images after 7 days.

**Failure before step 7** (no container runs on a target image yet): run the current `recover` path. It restarts the containers that ran before, on the old images, with `caddy` last after readiness. Then mark the run `failed`.

**Failure in or after step 7:** roll back with the restore path (7.5), then mark the run `rolled_back`.

**Gap that a rollback cannot close.** The rollback restores the snapshot from step 5. Every write after step 10 (the first start of `api`, which also starts the background workers) is lost: records, files, messages and audit rows. An external effect of that time can repeat after the rollback, for example an invitation or recovery email that the workers or Auth already sent. The Updates page states this after a rollback. The window is short, because step 11 follows at once and the check runs before ingress opens; no person can sign in before step 11.

Debian package upgrades are not part of the update outage. They run on a separate night (7.4).

### 7.4 WSL, Linux packages and the installer itself

- **Linux packages:** on a separate night from any update. The package night is once a week, on Sunday after the nightly backup, when no update run is queued or active. The engine holds the runner's host lock and upgrades the Debian packages: only the Debian security repository and the pinned Docker major version (apt preferences in the Linux image). A Docker Engine upgrade restarts the containers; the engine then checks readiness, with `caddy` last. A failure keeps the old packages where apt allows it and shows "Needs support" in the engine `status`.
- **WSL:** v1 has no unattended WSL install and no `\SlateOps\Maintain` task (10.3, F10). Only the setup program installs the pinned WSL MSI, with a person present. It does this on page 3a, and in its update path when the installed WSL is older than `version.json` says. Before the install, it waits until the engine `status` reports `engine_idle`. `engine_idle` means that no update, backup, restore or package night runs. It checks the SHA-256 right before `msiexec`, and it does not run `wsl --update`. It takes no version, path or URL from Linux. The boot task reattaches by itself; E6 observed this after a WSL update, with an outage of about 2.5 min. A new pinned WSL version arrives only with a new setup program.
- **A newer WSL from Windows Update.** Windows Update can install a newer WSL at any time, outside the window (F7, closed). This is very likely: the MSI writes a Windows Update targeting key, and the WSL service writes it again at every start. Microsoft added WSL publishing to the Windows Update catalog on 2026-10-07; which rings reach normal PCs is not stated. One Insider report says the install force-stopped the running distributions after 10 seconds. The rules:
  1. The boot task reattaches by itself. E6 saw this after a WSL update, with an outage of about 2.5 min.
  2. If the stop falls in a backup or update run, the engine resumes by the rule in section 12 (Windows Update row).
  3. Nothing in Slate Operations downgrades WSL. When the installed version is newer than `version.json`, the setup program does not act, and it records the installed version in its log.
  4. The setup program, the maintenance mode and the boot task at each Linux start send the installed WSL version to `status` on standard input (3.2 rule 2). The engine also records the Linux kernel version at each start, which changes with a WSL update (10.2). The engine accepts a WSL version newer than `version.json`, unless a known-bad list names it. Then the engine `status` shows "Needs support". Proposed: the known-bad list is the field "known-bad WSL versions" of `release-manifest.json` (5.2, decision H11).
  5. The WSL service also checks GitHub once a day and shows a notice only; it installs nothing. The DWORD `UpdateCheckPeriodMs=0` under `HKLM\Software\Microsoft\Windows\CurrentVersion\Lxss` turns this check off. This value is not documented by Microsoft, so the plan does not depend on it.

  The first WSL install by Windows Update on a real PC shows in the engine's log and report (10.1, 10.2). It shows as a new kernel version and a Linux restart.
- **Setup-program update path (the first deliverable's update):** the person runs a newer `SlateOpsSetup-<version>.exe`. It finds the installation and shows "Update". It keeps every choice and every secret, and replaces the program folder and the tasks. It streams the new setup payload into the engine (`receive`), installs the pinned WSL MSI when needed, and runs the engine `update` through `Exec`. It shows each step of 7.3 with a progress page, and the result with Retry and Save report. This path needs no `update_runs` row and no stable release. In the second deliverable, the app shows this path only when the manifest needs a newer Windows part.

### 7.5 Rollback by restore

`RESTORE.md` restores only into a new Compose project with a new instance ID. A rollback uses that contract, with one exception:

1. Stop and remove the failed project's containers and networks with `docker compose down` without `-v`. Its volumes stay until support removes them.
2. Restore the pre-update snapshot into project `<base>-r<n>` with a new instance ID.
3. Rebind the env files.
4. Finalize (this revokes the sessions).
5. Start the services with the old images, with `caddy` last after readiness.
6. Adopt the backup policy (`recover --restore-finalized`).
7. Close the engine journal as `rolled_back`. For an app-queued run (second deliverable), also write `rolled_back` with `update_close_restored`.

Step 1 removes the networks for one reason. The restored project uses the same `SLATEOPS_APP_PRIVATE_SUBNET` (`infra/supabase/compose.production.yaml:70`, `:163`). Docker refuses a second network with an overlapping subnet, so step 5 fails if the old network remains. If the failed project's networks must stay, the engine runs the W5b-7 subnet check for `<base>-r<n>` instead.

**Exception to `RESTORE.md` (Rebind, line 159).** That procedure gives the target its own site, origin, issuer and gateway URLs. A rollback keeps the same `PUBLIC_ORIGIN`, `SITE_URL`, `API_EXTERNAL_URL` and host name, because phones and PCs know only that name and trust only its certificate. This is safe only because the failed project is stopped before the restored project starts, and it never starts with ingress again. The engine refuses the rollback if a container of the failed project still runs. The Software Architect and the Security Engineer review this exception in W13b.

The engine needs a non-interactive path through `restore_installation.py`. Today `--execute` refuses to run without an interactive terminal, by design (`packaging/backup/restore_installation.py:388`), so no unattended restore exists. The confirmation text binds the engine's own snapshot, project and directory. This path is limited to the engine and exists only for this case (W13a; owner decision H12). The local Linux run of the withdrawn P1 kit found this gap (TASK-0074).

## 8. Backup and restore (proposed)

### 8.1 Fail open after a failed backup

The current behavior keeps the services stopped after a failed backup (`RESTORE.md:97`). The new behavior has four conditions:

1. **Same function.** After a failed run, the runner calls `recover_claim` (`backup_runner.py:232`) by itself, unchanged: the same code that `recover` runs today. It tries at most 3 times, 1 minute apart. It restarts only the containers that ran before the backup, in the current order, and starts `caddy` only after `/api/ready` passes.
2. **Refusals stay closed.** When `recover_claim` refuses (exit 2, for example `journal_invalid`, `child_unresolved` or `result_unconfirmed`), the services stay stopped, and the refusal does not count as a try. These states need a person, as today.
3. **Interrupted runs.** A tick that ends in the middle of a backup (a crash, a power cut, a restart) leaves an active journal. The next tick finds it and takes the same automatic path.
4. **Exit codes stay.** A failed or interrupted run still exits 3, so current monitoring keeps working.

When readiness still fails after the last try, ingress stays closed and the run records the existing code `readiness_failed`. The engine `status` shows "Needs support", and the maintenance mode on the server PC shows it too. The failed backup stays visible in System health and in Manage → Backups (current UI).

This change adds no failure code, no migration and no change to an API value. It uses the existing codes in `ck_backup_runs_failure_code` (`backend/app/systems/manage/backups/models.py:114-117`) and `FailureCode` (`schemas.py:26-30`).

There is no email alert in v1, because the app has no mailer (decision H6).

This change applies to the Linux path too, because there is one runner. The Software Architect confirms it before W10a, and `RESTORE.md` changes with it.

### 8.2 Backup location

- Page 7 of the wizard, or "Change backup location" in the maintenance mode. The web app does not choose Windows drives.
- The Linux image turns automatic mounts off (`[automount] enabled=false`). The engine mounts only the chosen backup drive with drvfs (`mount -t drvfs E: /mnt/slateops-backup`) at backup time and unmounts it after. `slateops-svc` has rights only on the backup folder.
- A missing USB drive gives a failed backup with the existing code `backup_failed`; the services come back under 8.1. The engine `status` carries the reason (`backup_target_missing`), and the maintenance mode shows "Plug in the backup drive". The database and the API get no new value.
- The first backup at install proves the mount and Restic on the chosen target (6.2 step 12; 10.3, F5). The installer report records each backup duration (10.2).

### 8.3 Recovery key

The Restic password lives inside the Linux disk. If that disk is lost, the backups cannot be read without a second key. The engine adds a second Restic key and shows it once on page 11, where the person prints it or saves it to a USB drive. Slate Operations does not store it on Windows. The maintenance mode can make a new key and remove the old one. This key is the named exception in section 3.2 (decision H3).

### 8.4 Restore in v1

Restore stays **support-run in v1**. The engine wraps the `RESTORE.md` procedure in one command, `slateops-engine restore --snapshot <id>`, which the rollback (7.5) also uses. A support person runs it through a remote session. The reasons:

- A restore replaces live data, revokes every session and needs a choice of snapshot. A wrong choice by an owner loses data.
- The procedure has many guards today. Linux-host runs prove the one-command path (W13a, W13b-2). The owner's end-user pass runs no restore, so a support restore on Windows is its first Windows run.
- A reinstall with kept data (9.2) covers the most common case (a Windows repair or reinstall) without a restore.

An owner-started restore in the maintenance mode is a candidate for v2 (decision H7).

## 9. Uninstall and maintenance (proposed)

### 9.1 Uninstall

From Windows Settings → Apps → Slate Operations → Uninstall. A custom page asks **"Keep your data?"**:

- **Keep my data** (default).
- **Delete everything.** A second dialog says "This deletes all business data on this PC. It cannot be undone." and needs a check box.

Both answers remove:

- the tasks `\SlateOps\*`;
- the `slateops-svc` account, its profile and its rights;
- the Windows and Hyper-V firewall rules;
- the hosts entry;
- our CA from LocalMachine Root;
- the program folder and the state folder (the logs stay unless the person chooses to remove them);
- the Start menu entry.

The sleep settings go back to their old values. The uninstaller then checks that each item is gone and logs the leftovers (10.7).

WSL and `VirtualMachinePlatform` stay, because other programs and accounts can use them.

| Answer | The Linux disk | Backups |
|---|---|---|
| Keep my data | `prepare-uninstall` stops the services cleanly. The disk moves to `<data folder>\SlateOps\kept\ext4.vhdx` with `kept.json` (version, instance ID, business name, `public_host`, date). The move is a rename on the same drive, so it copies no data. Setup removes nothing until the move is checked; then the distribution is unregistered (10.3, F3). | Kept |
| Delete everything | `wsl --unregister` deletes the disk. The data folder is deleted. | Kept unless the person also selects "Delete the backups on E:" |

### 9.2 Reinstall with kept data

1. Page 4 finds `kept.json` in the chosen data folder. It offers "Use the kept data (business X, version W)".
2. If W is newer than the installer, setup stops: "Use setup version W or later."
3. Setup creates a new `slateops-svc` and gives it access to the disk. It registers the disk with `wsl --import-in-place`. The engine `status` must report the instance ID in `kept.json`; if not, setup stops and does not change the kept disk (10.3, F3).
4. Pages 5 to 8 are skipped, because the secrets, the CA, the accounts, the email settings (when set up) and the address are inside the disk. The install sends no administrator password, and the existing accounts stay. Email is changed in the "Slate Operations settings" program.
5. If W is older, the engine runs the update steps 3 to 11 of 7.3, with the backup first, from the setup payload.
6. The Windows-side steps run again (firewall, hosts, CA trust).

### 9.3 Maintenance mode

The Start menu entry "Slate Operations settings" opens the setup copy in the program folder. Settings → Apps → Modify opens it too: setup writes `ModifyPath` and `NoModify=0` in its uninstall registry key (10.3, F4c). The Start menu entry "Slate Operations: Save report" makes the report of 10.6. The maintenance mode offers:

- Set up or change the email account (engine `smtp-test` to the administrator's stored address, then `set-email`, which recreates `auth` and then `api`). This is the only place where email is set up (DEC-0041), and the path for a revoked Gmail app password.
- Change backup location.
- Show the trust page and the QR code.
- Make a new recovery key.
- Status ("Running", "Updating", "Needs support"), with the main values of the installer report in plain words (10.2) and Save report (10.6).
- Repair: rerun the tasks, the rules and the boot start.

The maintenance mode has no license import. The administrator imports a license file in the app (DEC-0029 item 10).

## 10. Diagnostics and anticipated failures (proposed)

Every slice meets this section for the parts that it builds. Each slice row in section 11 says "Meets section 10".

The owner tests only what end users see, no virtual machine runs on the development machine, and nobody else can run Windows here (DEC-0031). So no Windows-only behavior is proved before the owner's end-user pass (W14). The installer must therefore find and explain its own failures. Each run must log enough to resolve a failure from the Save report file alone, with no second install to reproduce it. Source of this rule: the owner, 2026-11-16 (TASK-0077).

The S1 measurement slice, the owner's spikes and the P1 kit are withdrawn (DEC-0031). The findings of the kit's local Linux run stay in this plan (TASK-0074):

- the Caddyfile owner (W5b-6, W10b-4);
- the unattended restore (7.5, W13a);
- the app subnet (W5b-7);
- the rollback networks (7.5 step 1, W13b-9).

### 10.1 Logging contract

1. **Run ID.** Each install, update, uninstall, maintenance-mode action and Save report gets one run ID: `<kind>-<UTC time>-<6 random characters>`. The Windows side makes it and sends it in the JSON request of each `Exec` job. The engine writes it on every log line and passes it to each one-shot container as `SLATEOPS_RUN_ID`. The container log tails of a run are cut to the run's time window. Background runs get their own run ID from the engine or the task: the boot start, each backup, the package night and the certificate renewal.
2. **Line format.** Each line has a UTC timestamp, the run ID, a step ID (for example `install.08.provision`) and a level.
3. **Commands.** Each command that the Windows side or the engine starts is logged with its arguments, its exit code and its duration. Its standard output and standard error go to a file per step, capped at 1 MB per stream (planning value). Secret values never are arguments (3.2, check 3). A stream bridged to the secret pipe is never captured or logged on either side: the input of `smtp-test` and `set-email`, and the recovery key from `install` and `new-recovery-key`. The step log records only its byte count, and the result file holds `recovery_key_shown: true`, never the key. The engine redacts each line and each step output before it writes it or sends it to Windows; Save report redacts again (10.6).
4. **Locations.**
   - Windows: `C:\ProgramData\SlateOps\logs\` (Administrators and SYSTEM), with one folder per kind: `setup`, `uninstall`, `maintenance`, `start` (the boot task), `exec` (each `Exec` job). `slateops-svc` can write only to `start` and `exec`, as the kit's `svc-out` folder allows.
   - Before page 4 creates that folder, the wizard writes its Inno Setup log to `%TEMP%` and copies it in later. Save report also reads it from `%TEMP%`. The password field is never logged (3.2, check 4).
   - Linux: `/var/log/slateops/`, with one folder per kind: `install`, `update`, `backup`, `package-night`, `renewal`, `boot`, `receive`.
   - Docker keeps the container logs, capped by the Compose log options (W5b sets `max-size` and `max-file`).
5. **Caps and rotation.** Each folder keeps the last 20 runs and at most 50 MB (planning values). The install log and the first update log are never rotated out.
6. **After the install.** The boot task, every backup, every update, the package night and every renewal write logs by the same contract. v1 has no `\SlateOps\Maintain` task (10.3, F10). If a later version adds one, its log follows this contract.
7. **What is never logged.** A secret value, the recovery key, an env file's values, a message body, a file's content or a business record. An email address or a user name is written only as a placeholder, except in the engine's answers file, which stays in Linux.

### 10.2 Installer report and planning values

The engine keeps a report file (proposed): `/var/lib/slateops/report.json`. It holds safe values only:

- the memory that the WSL VM uses: when idle (the median of the runner's one-minute samples), and the peak during each backup and update;
- the time from each Linux start to `/api/ready`, with the reason of the start when it is known (Windows start, WSL update);
- the disk use inside Linux, and the VHD file size (the Windows side adds it at Save report);
- the duration of each backup and of each `restic check`;
- each change of the Linux kernel version and of the WSL version that `status` receives.

The maintenance mode Status shows the main values in plain words, for example "Memory used: 4.1 GB, highest 5.3 GB". Save report holds the whole file. System health in the app shows what it shows today: the database size, the file storage (`backend/app/systems/manage/health/installation.py`) and the backup freshness (`organization.py`). This plan adds nothing to the health page, so it adds no API value. The image sizes come from the release workflow summary in CI, not from the owner.

Planning values. Each one stands until the report of the owner's first real install corrects it. Engineering reads that report and changes the value in a fix commit on the branch.

| Value | Planning value | Why | Corrected from |
|---|---|---|---|
| R4, the memory minimum | 16 GB | The production overlay needs about 5 GB at worst with `shared_buffers=2GB`. With the 6 GB WSL limit, Windows keeps 10 GB. | The idle and peak memory in the report |
| `.wslconfig` `memory` | 6 GB | The boot-test kit used 6 GB, and it ran stable (REQ-0022). The overlay's 5 GB at worst, plus about 1 GB for Docker, systemd and the engine (assumption). | The peak memory in the report |
| PostgreSQL memory values on Windows | The production overlay values, unchanged | No evidence asks for other values. | The peak memory and any out-of-memory event in the report |
| The free-space minimum (page 4, R5) | 25 GB | Images: 2 × 7.5 GB (the running set, and the target set during an update, 7.3 step 4). Linux system: 2 GB (assumption). Data: 2 × 1 GB (the data, and room for one restored copy, 7.3 step 3). Logs and journals: 3 GB. Sum: 22 GB, rounded up. The 7.5 GB is the sum of the stack's local images on the development machine (arm64, 2026-11-16); W3 records the amd64 sizes. | The image sizes from CI, and the VHD size in the report |
| Ready time after a Windows start | About 30 to 36 s (observed in REQ-0022 with a light payload) | Used only for the time limit of the readiness checks: 5 minutes (planning value). | The ready times in the report |

The update's own space check (7.3 step 3) still measures the real need at each update.

### 10.3 Former owner-run items: designs and self-checks

For each item that needed a hands-on proof, this plan uses the design that needs no prior proof and adds a self-check. A self-check runs inside the installer or the engine. When it fails, it stops the step, shows a clear message, and offers Retry and Save report (10.6). A step changes nothing that it cannot undo before its check passes. The messages are drafts; the Product Designer writes the final copy.

| ID | Former question | Conservative design (v1) | Self-check | End-user step that proves it |
|---|---|---|---|---|
| F1 | Does Windows 11 answer mDNS for `<computer name>.local` to iOS and Android? Can another name be announced beside it? | Changed by DEC-0039: the address is `<address name>.local`, from the organization name, answered by setup's own mDNS responder (it binds UDP 5353 beside Windows' responder). Windows' `DnsServiceRegister` did not announce a non-computer name in the CI spike, so it is not used. One inbound rule allows the responder: UDP to local port 5353, Private profile, local subnet only, for Windows PowerShell, the responder's host process (S97-5, DEC-0039). | Page 8 checks that the network is Private and that no other device answers to the name (one mDNS probe). The CI spike proved that the responder answers a query on the same PC. | The phone opens the app at the address (W14-2). A second device on the owner's network still has to prove the responder; the server PC cannot check this itself (REQ-0022). |
| F2 | Does Caddy on 443 and 80 serve the LAN in mirrored mode with Docker port publishing? Does the server PC reach `<name>.local` through the hosts entry? | Docker publishes 443 and 80 with bridge networking, as the boot test did: a phone on the LAN reached its published port (REQ-0022). The server PC uses the hosts entry to 127.0.0.1, because it cannot open its own LAN address (REQ-0022). | Install step 10 checks HTTPS inside Linux. Then the wizard opens `https://<name>.local/api/health` from Windows with normal certificate checks. The wizard also checks that the product's Windows and Hyper-V firewall rules exist for the Private profile. | The app opens on the PC from the finish page (W14-1) and on the phone (W14-2). |
| F3 | Does `wsl --unregister` leave a moved VHD alone? Does `wsl --import-in-place` register it again under a new account? | "Keep my data" moves the disk with a rename on the same drive, before any removal. Reinstall registers the kept disk in place and changes the file in no other way. | Before `wsl --unregister`, the uninstaller checks that `kept\ext4.vhdx` exists with the old size and that `distro\` holds no `.vhdx`. If not, it stops: "Setup could not keep your data safely. Nothing was removed." After the unregister it checks the kept file again. At reinstall, the engine `status` must report the instance ID in `kept.json`. If not, setup stops: "Setup could not open the kept data. The kept data is not changed." | Uninstall with "Keep my data", then reinstall with the kept data (W14-4, W14-5). |
| F4a | Does the RunOnce resume elevate after the sign-in? | Setup saves its progress (no secret) before the restart. It resumes at page 4 from any start: the RunOnce entry, or the desktop shortcut "Continue Slate Operations setup". Windows shows the normal administrator prompt. | The restart message names the shortcut. Setup removes the shortcut when page 4 opens. | Install on a PC that needs the restart. The owner's PC probably has `VirtualMachinePlatform` and WSL from the boot test, so page 3a may not show there. Then this path stays unverified until a PC without them runs setup. |
| F4b | Can custom pages run long actions with a progress page? | Each long action is an `Exec` job. The wizard starts the job, then reads its result file on a timer while Inno Setup's output progress page (`CreateOutputProgressPage`) shows the step. The wizard never waits in one blocking call. | Each job has a time limit. At the limit the page shows "This step takes longer than expected" with Wait, Retry and Save report. | Install (W14-1). |
| F4c | Do a custom uninstall page and Modify in Settings → Apps work? | The "Keep your data?" question is a custom form that the uninstaller shows at its start (`InitializeUninstall`), before it removes anything. Closing the form cancels the uninstall. For Modify, setup writes `ModifyPath` (the setup copy with the maintenance switch) and `NoModify=0` in its uninstall registry key. The Start menu entry opens the same maintenance mode. | If the form cannot open, the uninstaller stops: "Uninstall stopped. Nothing was removed." | Modify, then uninstall with "Keep my data" (W14-4). |
| F4d | Can the wizard exchange a value with the `Exec` job through a named pipe and a hidden helper? | The named pipe with the checks in 3.2 is the only secret channel in v1. The file fallback is not built: it is a second secret path that nobody can test before the owner's run. It stays a reserve design for a fix build, after the Security Engineer's review (H3). | Before the first secret, the wizard sends a random test value through the pipe, and the engine returns its SHA-256. A wrong value or a time-out stops the page: "Setup cannot pass the password safely to the Linux part. Nothing was sent." | "Send test email" passes on page 6, and the recovery key shows on page 11 (W14-1). |
| F5 | With automount off, can the engine mount a USB drive letter with drvfs? How fast are Restic backup and check on NTFS through drvfs? | The engine mounts the backup target with drvfs only for each backup (8.2). The default schedule stays daily at 02:00, so the backup duration is not on a person's path. | Install step 12 takes the first backup and runs `restic check`. A failure stops the install: "Slate Operations cannot save backups to E:." with Retry, Choose another location and Save report. Later failures show in System health and Manage → Backups (current UI) and in the maintenance mode Status. | The next morning, Manage → Backups shows the night's backup (W14-3). |
| F6 (W6a-5) | Do devices accept the name-constrained CA and enforce the constraints? | The profile in 6.3 (web facts, TASK-0075), with an empty leaf subject and a critical SAN. If a device rejects it in the owner's run, the reserve design is a root without constraints, with a Security Engineer risk decision. | Before it writes any file, the CA job checks the chain with OpenSSL. The real server certificate must pass. A throwaway `other.local` certificate from the same intermediate must fail. On the server PC, the F2 check runs through Windows' own certificate checks. | The app opens on the PC and the phone with no certificate warning (W14-1, W14-2). This proves only that the valid certificate is accepted. Whether devices reject a wrong name stays unverified; the web facts are its only source. |
| F10 (W13b-5) | Does the pinned WSL MSI install from a SYSTEM task with nobody signed in? | No unattended WSL install in v1, and no `\SlateOps\Maintain` task. Only the setup program installs the pinned WSL MSI, with a person present (7.4). What this removes: a PC where Windows Update brings no new WSL keeps its WSL until the person runs a newer setup program. It also removes a SYSTEM task that acts on a Linux value, and its nightly WSL-version report; instead the boot task sends the WSL version to `status` at each Linux start, so a known-bad WSL shows in the Status. | After the MSI install, the setup program waits up to 10 minutes for the engine `status`. If it does not answer: "The Linux part did not start again after the WSL update." | Page 3a on a PC without WSL. The owner's update in W14-3 installs the MSI only if his WSL is older than the pinned version; otherwise this path stays unverified. |
| W4-5 | Does `wsl --import` of our image start systemd and Docker? | The image uses the boot test's method: our own Debian 13 with systemd on and Docker from Docker's apt repository (REQ-0022). | Page 4a: `slateops-engine prepare` checks that systemd runs, Docker answers and the networking mode is mirrored. A failure shows "Setup could not start the Linux part." | Install (W14-1). |
| W7-6 | Does the PC serve the LAN at boot with nobody signed in? | The tasks keep the kit's settings unchanged: the boot task, the hidden account, `.wslconfig` and the firewall rules. REQ-0022 observed E1, E2, E4, E5 and E6 with them. | The engine records each start and its ready time (10.2). The maintenance mode Status shows "Running", or "Not ready since <time>" with Save report. | Normal use after any restart during the pass. A restart is not a required step (DEC-0031). |
| W13b-2 to W13b-4, W13b-6 to W13b-9 | Forced failures, a restart in the window, low space | 7.3 and 7.5 as written. | The update states and messages of 7.4. | None: forced failures are not end-user steps. Linux-host runs with two test builds prove them. |

F7, F8 and F9 are closed (TASK-0075, REQ-0022). Their results are in 7.4 (F7), decision H9 (F8) and section 2 (F9, REQ-0022).

### 10.4 Environment facts

Each install, update, uninstall and maintenance run records these facts at its start. Save report records them again. The commands and registry names are proposed; W7 checks each one in Microsoft's documentation. Commands that read the distribution run as `slateops-svc` through `Exec`, because the distribution is registered for that account only.

| Fact | Source (proposed) |
|---|---|
| Windows edition, version, build and UBR | Registry `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion`: `EditionID`, `DisplayVersion`, `CurrentBuildNumber`, `UBR` |
| CPU, virtualization and SLAT | `Win32_Processor` (name, `VirtualizationFirmwareEnabled`, `SecondLevelAddressTranslationExtensions`); `Win32_ComputerSystem.HypervisorPresent` |
| Memory | `Win32_ComputerSystem.TotalPhysicalMemory`; `Win32_OperatingSystem.FreePhysicalMemory` |
| Free space on C: and on the data drive; file system; BitLocker state | `Get-Volume`; `Get-BitLockerVolume`, reading only `VolumeStatus`, `ProtectionStatus` and `EncryptionMethod`, never `KeyProtector` |
| WSL version, kernel, distribution state, `.wslconfig` | `wsl --version`, `wsl --status`, `wsl --list --verbose` (as `slateops-svc`); `uname -r`; the `.wslconfig` of `slateops-svc` (it holds no secret) |
| Docker and the image digests | `docker version`; `docker image ls --digests` |
| App version and manifest | `installation.json`; the manifest version and digests |
| Network profile, adapters, IPv4 addresses, DNS servers | `Get-NetConnectionProfile`; `Get-NetAdapter`; `Get-NetIPAddress -AddressFamily IPv4`; `Get-DnsClientServerAddress` |
| Proxy settings | `netsh winhttp show proxy`; the signed-in user's proxy settings |
| mDNS firewall rules and the multicast policy | `Get-NetFirewallRule` for the mDNS rules; the DNS Client policy key |
| The product's firewall and Hyper-V rules | `Get-NetFirewallRule` and `Get-NetFirewallHyperVRule` for the product's rules |
| Port listeners on 80 and 443, with the process name | `Get-NetTCPConnection -State Listen -LocalPort 80,443`; `Get-Process` |
| Power plan, Fast Startup, sleep and hibernate | `powercfg /getactivescheme`; `powercfg /a`; `HiberbootEnabled`; the sleep and hibernate timeouts on mains power |
| Antivirus product and Smart App Control state | `root\SecurityCenter2` `AntiVirusProduct`; the Smart App Control state value (registry name is an assumption) |
| Time zone and clock sync | `Get-TimeZone`; `w32tm /query /status`; `timedatectl` in Linux |
| Pending restart | The `RebootPending`, `RebootRequired` and `PendingFileRenameOperations` registry values |
| Installer and Windows-part version | The setup program's own version; `version.json` |

### 10.5 Failure snapshot

On any failure, the Windows side and the engine save a snapshot in the run's log folder before they show the message:

1. `wsl --list --verbose` and `wsl --status` (as `slateops-svc`).
2. The distribution's systemd state: `systemctl --failed` and the state of `docker.service` and `slateops-runner.timer`.
3. `docker ps -a` and `docker compose ps` (names and states only).
4. The last 200 lines of each container's log (planning value), after the redaction of 10.6.
5. The output of `/api/ready` and `/api/health` on the internal path.
6. The Windows event logs since the run started. They are Task Scheduler, Hyper-V-Compute, the WSL events, and the System restart and power events (Kernel-Power 41, EventLog 6008, User32 1074). The Application errors of the installer and of Windows Installer are included too. The Task Scheduler operational log is off by default (assumption); setup turns it on and the uninstaller restores the old state.
7. The state, the last run time and the last result of each `\SlateOps\*` task.

### 10.6 Save report

1. **Where.** Every failure screen of the wizard, the uninstaller and the maintenance mode has a Save report button. The Start menu entry "Slate Operations: Save report" does the same. It works when the Linux part does not answer: the Windows side saves what it has and writes "Linux part not reachable" in the report.
2. **What.** One zip file with the logs of 10.1, the environment facts of 10.4, the snapshots of 10.5 and the installer report of 10.2. The engine's `log-bundle` job makes the Linux part.
3. **Secret scan and redaction before it writes** (SEC-R3). The engine replaces every exact secret value that it holds in `/etc/slateops/`. The wizard replaces the SMTP password while it holds it. Both then scan for secret patterns: private keys, tokens, connection strings with a password, `KEY=value` lines of secret names, and the BitLocker recovery-password format (eight groups of six digits). When a hit cannot be replaced, the file is left out and the report lists it. The bundle never holds a password, a key, a token, the SMTP password or the recovery key.
4. **No customer data** (Republic Act 10173). The report holds no business records, message text or file content. Email addresses, user names and the client addresses in the Caddy access logs are replaced with placeholders.
5. **Result.** The file goes to the running person's own desktop (never the Public desktop) as `SlateOps-report-<run ID>.zip`, and the page shows its full path. Nothing is sent automatically. The test-build release notes and the `README.txt` in the program folder tell the owner to send that file to Engineering.
6. **Tests.** The engine and installer tests put known secret values and personal data into the logs. Then they check that none of them reach the zip (W5b, W8).

### 10.7 Failure catalog

Each row is an anticipated problem. "Logged" means the log of 10.1, beyond the facts of 10.4 and the snapshot of 10.5. Every message ends with Retry and Save report unless the row says otherwise. The messages are drafts; the Product Designer writes the final copy.

| Problem | Detection | Logged | Message (draft) | Recovery |
|---|---|---|---|---|
| Virtualization off | R3 | The processor and hypervisor values | R3 message (4.2) | The person turns it on in the firmware settings, then selects Retry. |
| Windows too old, or Windows 11 Home | R1, R2 | Edition, build and UBR | R1 or R2 message (4.2) | Windows Update for R1. Home: none in v1 (H5). |
| Restart pending | Registry values before page 3a and before page 10 | Which value is set | "Windows must restart before setup can continue. Restart this PC, then run setup again." | The person restarts. Setup resumes from its saved progress. |
| WSL MSI or `VirtualMachinePlatform` install fails | The `msiexec` exit code (verbose MSI log `/l*v`); the feature cmdlet result | Exit code, MSI log, feature state | "Setup could not install a Windows part (WSL)." | Exit code 1618 (another install runs): wait and try again, 3 times, automatically. Exit code 3010: the restart page. Other codes: Retry. |
| The resume after the restart does not start | Saved progress says "restart done" but page 4 did not open | The RunOnce entry and the saved progress | The restart message already names the desktop shortcut (F4a). | The person selects "Continue Slate Operations setup". |
| Antivirus or Smart App Control blocks the installer or a script | A helper exits with "access denied", or an extracted file is missing; the Smart App Control state and the antivirus product in the facts | The blocked file and the error code | "A security program on this PC blocked part of Slate Operations setup (<file name>)." | Smart App Control on: unsigned builds cannot run (H1). In the owner's pass he reports the block (11.2 step 2) and changes no setting. Antivirus: allow the program folder. If Windows blocks the setup file itself, no log exists; `README.txt` and the release notes describe this case. |
| Distribution import fails | `wsl --import` exit code and error text | Command, exit code, error text | "Setup could not start the Linux part." | Retry. When the cause is space: choose another drive. |
| Docker or systemd does not start in Linux | `prepare` (10.3, W4-5) | `journalctl -u docker` tail | "Setup could not start the Linux part." | Retry restarts the services once. Then Save report. |
| No internet, proxy, DNS failure, registry rate limit or TLS failure during a pull | R8, and the engine's class of each pull error: name lookup, TLS certificate, time-out, HTTP 429, proxy in use | Class, registry host, image, try count | Per class: "Setup cannot reach the internet." / "The image server limits downloads now. Setup tries again at <time>." / "This PC uses a proxy server. Slate Operations v1 cannot use a proxy." / "A secure connection to <host> failed. Check the PC's date and time." | Time-outs and HTTP 429: 3 automatic tries with growing waits. Proxy: not supported in v1. Others: Retry. |
| Disk full during the install | Free-space check before each step that writes; a "no space" error | Free space on both sides, the step | "The data drive is full. Free X GB, then select Retry." | The install journal keeps the state; Retry resumes. |
| Disk full later | The runner's daily check of the free space inside Linux and on the data drive | The values | Maintenance mode Status: "Disk almost full". A backup fails with the current `backup_failed`. | The person frees space. When the VHD reaches its maximum size, support grows it. |
| Ports 80 or 443 in use | Page 8, with the owning process name | Port, process | "Another program uses port 443 (<process name>). Stop it, then select Retry." | The person stops the program. |
| Firewall or Hyper-V rule fails | The cmdlet result | The error text | "Setup could not add the firewall rules." | Retry. Repair in the maintenance mode adds them again. |
| Network is Public, or the PC is in a domain | R6, page 8 | Profile, domain state | R6 and page 8 messages | Make private: one select. Domain: blocking in v1. |
| `<name>.local` does not open on a phone | Not visible on the server PC (REQ-0022). Page 8 checks the responder and the rules. | mDNS facts | Finish page text, and the trust page's list of causes: other Wi-Fi, guest Wi-Fi that isolates devices, a VPN on the phone, another subnet | The person connects the phone to the same Wi-Fi and turns off its VPN. |
| Certificate not trusted | Server PC: the F2 check, with the chain status. Phone: the trust page checks `https://<name>.local/trust/ok` and shows "This device trusts Slate Operations" or "Not yet" (route: W6a; page: W6b). | Chain status | "This PC does not trust the Slate Operations certificate." / trust page state | Server PC: Retry adds the CA again. Phone: the trust steps, with the iOS second step. |
| SMTP errors | `smtp-test` classes: password refused, Microsoft 365 SMTP AUTH off (reply 535 5.7.139), cannot connect, no TLS, TLS certificate failure, sender refused, recipient refused | Class, reply code, host, port, TLS mode (never the password) | Page 6 messages (4.1), one per class | The person fixes the value, then sends a test again. After the install, a daily sign-in check without a message (proposed) shows "Email sign-in fails" in the maintenance mode; "Change email account" fixes it. |
| Provisioning, migration or readiness fails | Exit code of step 8; `alembic` exit code; `/api/ready` not ready in 5 minutes | Container log tails, safe codes | "Setup could not prepare the database." / "Slate Operations did not start." | Install: Retry repeats only the failed step. Update: rollback by restore (7.3, 7.5). |
| The service account cannot sign in (`0x8007052F`, `0x80070569`) | The last result of the `Exec` or `Start` task | Task result, the account's rights and password policy | "Windows did not let the Slate Operations service account start. A security policy can cause this." | Repair in the maintenance mode sets the batch logon right and a new password again. If a policy removes it again, the person who manages the PC must allow it. Setup sets the password to never expire. |
| WSL stops the idle VM | The engine records each Linux start with its reason | Linux boot ID, `.wslconfig` values | None (automatic) | `vmIdleTimeout=-1`, `instanceIdleTimeout=-1` and the attached keep-alive prevent it; the boot task's one-minute repetition starts it again. A repeat shows in the Status. |
| Windows Update installs a newer WSL | A new kernel version and a Linux restart; the new WSL version at the next `status` | Versions, outage | None, unless the known-bad list names the version: "Needs support" | The boot task reattaches (E6). |
| Power cut during the install, an update or a backup | The open journal at the next start; System events 41 and 6008 | Journal state | Install: setup offers Resume at its next start. | Install: resume (6.1). Update: the journal rule in section 12 (Windows Update row). Backup: 8.1 condition 3. |
| Clock wrong | The engine compares its clock with the `Date` header of a registry response at install and each day | Offset | "This PC's clock is wrong by N minutes. Turn on Set time automatically in Windows Settings." | The person fixes the clock. The Linux image runs a time sync client (W4-6): nothing listens, and it uses NTS where it reaches the internet. |
| Low memory | R4 at the install; the engine's memory samples; an out-of-memory kill (container exit code 137, kernel log) | Samples, the killed process | Maintenance mode Status: "Slate Operations is short of memory." | The person closes programs or adds memory. Support raises the `.wslconfig` value. |
| Wi-Fi not connected at the start | The engine sees no LAN address after a start | The adapter state at each start | Maintenance mode Status: "This PC was not on the network after it started." | The person sets the Wi-Fi to connect automatically, or uses a cable. REQ-0022 saw Wi-Fi connect before the sign-in on the owner's PC. |
| The IP address changes | The Windows side compares the current subnet with the subnet in the Hyper-V rule at each Status and Repair | Old and new addresses | Maintenance mode Status: "The network changed. Select Repair." | The `.local` name follows the new address. Repair updates the rule. `README.txt` recommends a fixed address in the router. |
| Parts of the boot-test kit are on the PC (the owner's PC ran it, REQ-0022) | Page 3 looks for the account `slateops-svc`, the distribution `SlateOpsBootTest`, the tasks `\SlateOpsBootTest\*`, the rules `SlateOpsBootTest-*` and the folder `C:\ProgramData\SlateOpsBootTest` | Each part found | "This PC has parts of an earlier Slate Operations test. Setup removes them before it continues." with Continue and Cancel | Setup removes them as the kit's cleanup does: the old disk is deleted, the logs stay. The account name is the same, so setup creates its own `slateops-svc` only after the removal. |
| Uninstall leaves items behind | The uninstaller checks each item of 9.1 after removal | The list of leftovers | "Uninstall finished. Some items could not be removed." | The next setup run removes leftovers before it installs. |
| Reinstall with kept data that does not match | `kept.json` is newer, missing or damaged; the instance ID differs after the import | The `kept.json` values (no secret) | 9.2 messages; "Setup could not open the kept data. The kept data is not changed." | The person uses a matching setup version. Otherwise, support restores from a backup with the recovery key. |

## 11. Slices

### 11.0 Delivery: one branch, one pull request

The owner expects one completed output to test, not separate partial results (the owner, 2026-11-16, TASK-0077). So:

1. All work of the first deliverable is on `feat/windows-installer` and ships as one pull request (pull request 115). It merges when the installer is complete: the owner's end-user pass (W14) passes, its fixes are in, and CI is green.
2. The slices are internal work units. They run one after another in the order below, and each finishes its reviews (11.1) before the next starts. The repository allows one writing session at a time and no worktrees. Each slice is one task with one owner. The exception is W5b: the Backend Engineer does W5b-10 inside it.
3. The owner sees nothing until one installer file, `SlateOpsSetup-<version>.exe` from a test-build draft release, does the whole job. Then he runs the end-user pass (11.2).
4. The owner has one step before his test (5.3). He signs in to GitHub and downloads the test-build setup files from the draft releases. The team does every other step.
5. The former pull-request grouping P1 to P9 is withdrawn. P1 (S1 and the owner's spikes) was withdrawn by DEC-0031.
6. Every slice meets section 10 (diagnostics and anticipated failures).

| Deliverable | Slices (work units, in order) | What the owner gets | Merges when |
|---|---|---|---|
| First (this pull request) | W1, W3, W4, W2, W5a, W5b, W6b, W6a, W10a, W10b, W7, W8, W9, W13a, W13b, W14, W15 | One setup file. It installs with the wizard and runs the app on a PC and a phone. A newer test-build setup updates it. It uninstalls with kept data and reinstalls. | W14 passes, its fixes are in, and CI is green. Repository testing rules apply to every slice. |
| Second (a separate pull request, after the first merges) | W11, W12, W13c, then W16 on the stable tags | The in-app update ("Install tonight") and, from the license work, the license import | CI is green. It merges before W16, because the stable tags must contain it (5.3). Reason for a second pull request: it waits for the license work and for two published stable releases (H8). |

Each slice still lists its own "Depends on" below; this order satisfies all of them.

**License work.** It is a separate build with its own contract (DEC-0029 Follow-up), not a slice of this plan. It must merge before the first stable tag (section 5.3). It needs the owner's start. The first deliverable does not wait for it (order and costs in section 5.3).

| ID | Slice | Owner | Files or area | Contracts changed | Acceptance criteria | Proof | Needs from the owner | Depends on |
|---|---|---|---|---|---|---|---|---|
| W1 | Single version source | Backend Engineer | `backend/app/main.py`, `infra/docker/backend.Dockerfile` (build argument), `tests/tooling/` | `GET /api/version` value (shape unchanged) | W1-1: the image built with `SLATEOPS_VERSION=1.2.3` reports `1.2.3` at `/api/version`. W1-2: without it, the value is `0.0.0+dev`. W1-3: a tooling test refuses a tag that differs from `pyproject.toml` and `package.json`. Meets section 10. | Focused pytest; tooling test; one local image build | — | — |
| W2 | Production env templates and the complete secret set | Backend Engineer | `backend/operations/supabase_keys.py` (complete set, new `--format docker`), new `backend/operations/local_ca.py`, templates in `packaging/engine/templates/` | Env file format becomes literal `KEY=value` | W2-1: one run writes every secret in 6.2 step 4; `Settings`, `ProvisionSettings` and `AdminSettings` load from the result with no missing field. W2-2: a new `--format docker` output has no quotes. Random values come from a safe alphabet. The JSON values (`JWT_KEYS`, `JWT_JWKS`) contain no `$`, `#`, `'` or space. A test reads the file with both env readers, `docker run --env-file` and `docker compose --env-file` (which interpolates unquoted values), and compares every value byte for byte. The current default output stays, because `README.md:86`, `backend/tests/supabase_runtime.py`, `backend/tests/config_support.py` and `tests/tooling/test_environment.py` use it. W2-3: an existing output is never overwritten. W2-4: `local_ca.py` makes a root, a name-constrained intermediate signed by it (the root key is removed after this), and a server certificate of 397 days or less for one host from the intermediate; it renews 30 days before expiry. W2-5: no secret is printed. Meets section 10. | Focused pytest under `backend/tests/operations/`, plus `tests/tooling/test_environment.py` | — | — |
| W3 | Release workflow and test builds | Infrastructure Engineer (TASK-0079) | `.github/workflows/release.yml`, `scripts/release_artifacts.py`, `tests/tooling/` | New public artifacts | W3-1: a test-build tag `vX.Y.Z-rc.N` on the branch makes a draft release with the title "Test build, not for customers". It holds the assets that exist when W3 runs (5.2) and `SHA256SUMS`. It needs no public GHCR package and no owner setting (5.3). W3-2: both images are `linux/amd64` image archives for the setup payload, and their digests are in the manifest. The GHCR push for stable releases comes with the second deliverable. W3-3: cosign verify passes for the manifest with the workflow identity. W3-4: per-job least-privilege permissions under a `contents: read` default; SHA-pinned Actions. W3-5: moved to W5b-10. W3-6: the workflow summary records the size of each image (10.2). Meets section 10. | Tooling tests; one test-build workflow run | — (5.3: no GHCR setting and no repository setting in the first deliverable) | W1 |
| W4 | Our Linux image | Infrastructure Engineer | `packaging/linux-image/` (build script, units, `wsl.conf`), release job step | New artifact | W4-1: a reproducible build from a fixed snapshot date. W4-2: the Docker key fingerprint is checked. W4-3: there is no SSH server and no secret; interop and automount are off; cosign is pinned and in the package list. W4-4: the package list and the source list are produced. W4-5: `wsl --import` of the tarball starts systemd and Docker (self-check in 10.3). W4-6: the image runs a time sync client (nothing listens; NTS where it reaches the internet), and its offset is logged (10.7, clock row). W4-7: the release attaches the notices and the GPL source packages of our two images (the Alpine packages of the Caddy image, the Python runtime, Caddy) and the Debian source packages (H4). Meets section 10. | CI build; the `prepare` self-check (10.3, W4-5); first Windows run: the owner's install (W14-1) | — | W3 (wiring) |
| W5a | Engine bridge commands in the server image | Backend Engineer | `backend/operations/` (no new top-level command), `backend/operations/backup_state.py` (`policy_default`) | None beyond W2 | W5a-1: `bootstrap_admin.py` runs non-interactively with `--confirm --name --slug` and the env. W5a-2: one provisioning entry point that the engine calls returns safe JSON. W5a-3: the `policy_default` operation writes the default backup policy only when none exists, through `AuditSession`. Meets section 10. | Focused pytest | — (H2 decided, DEC-0030) | W2 |
| W5b | Engine install, status and email check | Infrastructure Engineer | `packaging/engine/` and its tests | New engine job contract (section 6) | W5b-1: `install` from a fresh Linux with valid answers reaches HTTPS `/api/ready` and creates the first administrator (DEC-0041: with its password; no invitation). W5b-2: killing it at any step and running it again completes it with no duplicate secret, CA, volume or administrator account. W5b-3: `smtp-test` refuses authentication without TLS and reports the error class. W5b-4: no secret appears in any log, in the output, or in `docker compose` output. W5b-5: it uses only the standard library on the host. W5b-6: Caddy (UID 1000) can read the Caddyfile that the engine writes. The backup admission also accepts it, with no owner change around a backup. The admission needs root or the caller as owner, with no group or other access (`packaging/backup/backup_installation.py:183`). One option needs no admission change: the backup runs as UID 1000, which owns the Caddyfile. W5b-7: before the install, the engine checks the app subnet (default `172.31.248.0/28`) against the host and Docker networks. On a collision it picks another private /28 and writes it as `SLATEOPS_APP_PRIVATE_SUBNET`. W5b-8: `receive` accepts only a tar stream up to its size limit. It reads only the expected file names, as regular files, into a root-only staging folder (0700) on the Linux disk, with a limit per part and in total and a free-space check first. The manifest version must equal the setup program's version. The engine uses a part only after it matches the signed manifest (5.2), and it deletes the staged archives after the load. W5b-9: the engine's logs, snapshots, report and `log-bundle` follow section 10; a test seeds known secrets and personal data and finds none in the bundle. W5b-10 (from W3-5; Backend Engineer task inside W5b): the provider image references use the registries that H9 sets, at unchanged digests, in `infra/supabase/compose.yaml`, `PROVIDER_IMAGES` (`backend/app/core/config/disposable_instance.py`) and the `infra/supabase/README.md` table; `backend/tests/operations/runner/test_disposable_database_guard.py` passes; only the `dev.py` preflight in `scripts/environment.py` accepts the old or the new name, and only when the pinned digest is equal (equality only); `up` then writes a new instance attestation, so the owner's development stack keeps working; the API checks (`backend/app/core/config/instance.py`, `provider_instance.py`) stay exact on the new name; an anonymous pull of each digest passes. Meets section 10. | Unit tests in `packaging/engine/tests/`; one run on a Linux host with the test-build images; the W5b-10 failing-first tests | — | W2, W5a, W4 |
| W6a | TLS and the LAN name | Infrastructure Engineer | `packaging/engine/` (CA step, renewal), `infra/caddy/generate_config.py` (`--trust-root`, the `:80` site), `infra/docker/caddy.Dockerfile` | New public port 80 (three trust paths and a redirect) | W6a-1: port 80 serves only the three trust paths and redirects every other path. W6a-2: the server PC and a phone trust the site after the trust steps. W6a-3: `<address name>.local` (DEC-0039) resolves on the phone. W6a-4: the renewal replaces the certificate with no outage longer than a Caddy reload. W6a-5: the CA self-check of 10.3 (F6) runs before the CA job writes any file. The real certificate passes, and a throwaway `other.local` certificate fails. W6a-6: the CA and the server certificate follow the profile in 6.3. W6a-7: `/trust/ok` is a static response on the `:443` site, outside `/api`; it reads no cookie, sends no credentialed CORS header and adds no allowed origin. Meets section 10. | Caddy generator tests; engine unit tests; the CA self-check. W6a-2 and W6a-3: the owner's end-user pass (W14-1, W14-2). Other device kinds stay unverified until someone uses them. | — | W5b, W6b |
| W6b | Trust page | Frontend Engineer | `infra/caddy/trust/` (one static HTML file, no script from another origin) | None | W6b-1: the page shows the steps for iOS, Android, Windows and macOS, and the CA fingerprint from a file that the engine writes. W6b-2: it works at 390 px and 1440 px with no network request to another host. W6b-3: it shows "This device trusts Slate Operations" or "Not yet" from a check of `https://<name>.local/trust/ok` (10.7). Meets section 10. | Hands-on in a browser at both widths | — | Product Designer design |
| W7 | Windows plumbing | Infrastructure Engineer | `infra/windows/installer/` (scripts promoted from the kit, the Inno project) | New Windows-side contract (tasks, account, rules) | W7-1: the requirements check shows R1 to R9 with the messages in 4.2. W7-2: Prepare this PC restarts once and resumes at page 4. W7-3: the distribution runs from the chosen data drive. W7-4: `Exec` refuses an unknown job and takes data only on standard input. W7-5: the folder safety check of the kit passes. W7-6: the tasks keep the kit's settings unchanged (REQ-0022: E1, E2, E4, E5, E6). The engine records each start and its ready time (10.2). W7-7: each run records the environment facts (10.4) and logs by 10.1, the boot task included. Meets section 10. | Inno compile in CI; static review of the task settings against the kit; first Windows run: the owner's install (W14) | — (he installs as an end user in W14) | W4 |
| W8 | Wizard pages and finish | Infrastructure Engineer | `infra/windows/installer/` | None | W8-1: every page in 4.1 with its checks and messages. W8-2: the SMTP password never reaches a log, and with the pipe channel never reaches a Windows disk. W8-5: the recovery key reaches page 11 through the same channel and is never written to a Windows disk or log, except by the person's own Print or Save to a USB drive. W8-3: the finish opens the app on the server PC with no certificate warning; the HTTPS check from Windows runs first (10.3, F2). W8-4: the recovery key page requires the check box. W8-6: every failure screen has Save report, and the installer tests find no seeded secret or personal data in its zip (10.6). W8-7: the installer is one file below 2 GiB (5.2). Meets section 10. | Static review; QA Engineer review of the pages and messages against 4.1 and 10.7; the self-checks of 10.3; first Windows run: the owner's install (W14-1, W14-2) | — | W7, W5b, W6a, W6b, W10b, design |
| W9 | Uninstall, keep data, reinstall, maintenance mode | Infrastructure Engineer | `infra/windows/installer/`, engine `prepare-uninstall` and `set-email` | None | W9-1: both answers remove the items in 9.1. W9-2: kept data is reused with the same business, sign-ins and devices trusted. W9-3: a newer kept version blocks with the message. W9-4: Change email account sends a test and recreates `auth`. W9-5: Modify in Settings → Apps opens the maintenance mode (10.3, F4c). W9-6: the uninstaller logs each leftover item (10.7). Meets section 10. | Static review; QA Engineer review; the self-checks of 10.3 (F3, F4c); first Windows run: W14-4 and W14-5. "Delete everything" is not in the end-user pass, so it stays unverified on Windows. | — | W8 |
| W10a | Backup fail-open | Backend Engineer | `backend/operations/backup_runner.py`, `backend/operations/backups/`, `infra/supabase/RESTORE.md` | Runner behavior after a failed backup (all installations); no schema or API change | W10a-1: after a forced archive failure, the runner calls `recover_claim` unchanged, the services that ran before run again, and Caddy starts only after readiness. W10a-2: an unready API keeps ingress closed and records the existing `readiness_failed`. W10a-3: at most 3 automatic tries; a refusal (exit 2) keeps the services stopped and is not counted. W10a-4: an interrupted run takes the same path on the next tick. W10a-5: exit codes are unchanged. W10a-6: no failure code, migration or API value changes. Meets section 10. | Focused pytest of the runner | — | Software Architect confirms fail-open for the Linux path |
| W10b | Backup scheduler, location and recovery key | Infrastructure Engineer | `packaging/engine/` (`slateops-runner.timer`, drvfs mount, `set-backup-target`, `new-recovery-key`) | None, unless W10b-4 changes the admission check in `backup_installation.py`. That change applies to every installation, Linux included. | W10b-1: the timer runs one runner tick each minute while the distribution runs. W10b-2: a missing USB target gives the existing `backup_failed`, the services come back, and the engine `status` reports `backup_target_missing`. W10b-3: the recovery key opens the repository, and a new key removes the old one. W10b-4: a scheduled backup admits the Caddyfile while Caddy reads it, with no owner change around the backup (W5b-6). If the fix changes the admission in `backup_installation.py`, that part is a Backend Engineer task inside W10b. W10b-5: install step 12 takes the first backup and runs `restic check`; a failure stops the install with its message (10.3, F5). Meets section 10. | Engine unit tests; a Linux-host run with a present and a missing target folder; first Windows run: the owner's install and the next morning's backup (W14-3) | — | W6a, W10a |
| W11 | Update queue API and table (second deliverable) | Backend Engineer | `backend/app/systems/manage/backups/` (or a new `updates/` folder; the Software Architect decides), migration, `backend/operations/backup_state.py` (update operations in the existing union) | **New routes, table, column and bridge operations (7.2)** | W11-1: 201 with `Location`. W11-2: 409 `update_active`. W11-3: 409 `update_not_cancellable` after the claim. W11-4: 409 `update_target_stale`. W11-5: 409 `updater_unavailable` when the engine was not seen in 5 minutes. W11-6: 403 for a non-owner, and 404 or 403 per the current rules for others. W11-7: `update_claim` is exclusive under concurrency, under the existing advisory lock. W11-8: `update_close_restored` is admitted only by a valid restore-finalized marker. W11-9: the migration passes `alembic check`. Meets section 10. | Focused pytest plus the PostgreSQL integration batch | — (H2 decided, DEC-0030) | Software Architect contract review |
| W12 | "Install tonight" UI (second deliverable) | Frontend Engineer | `frontend/src/components/systems/manage/components/updates-panel.tsx`, `domain/updates-rules.ts`, `adapters/backup-api.ts` | None | W12-1: each state in 7.1 renders from the API. W12-2: Cancel works only while queued. W12-3: only the installation owner sees the button, and only while the engine was seen in the last 5 minutes. Meets section 10. | Isolated and http Playwright specs; hands-on | — | W11, design |
| W13a | Non-interactive restore for the engine | Backend Engineer | `packaging/backup/restore_installation.py` | A new engine-only mode (owner decision H12) | W13a-1: the mode needs the engine's own snapshot, project and directory, and refuses any other value. It replaces the terminal check at `restore_installation.py:388` only for the engine. W13a-2: the interactive path is unchanged. Meets section 10. | Focused tests in `packaging/backup/tests/` | — | — |
| W13b | Engine update executor and the setup-program update path | Infrastructure Engineer | `packaging/engine/`, `infra/windows/installer/` (the setup program's update path and its WSL step) | Engine update contract (7.3, 7.4, 7.5) | W13b-1: running a newer test-build setup updates the installation from `X.Y.Z-rc.N` to `X.Y.Z-rc.N+1`; the running `api` container reports the new version, and the data stays. W13b-2: a forced migration failure rolls back to the old version with the data intact, and keeps the same origin and name. The journal closes as `rolled_back`, and the update never resumes again. W13b-3: a failure forced before step 7 uses `recover`, not a restore. W13b-4: low space gives `insufficient_space` with no outage. W13b-5: with an older WSL installed, the setup program waits for `engine_idle` and installs the pinned WSL MSI after the SHA-256 check. The engine answers `status` again within 10 minutes; if not, setup shows its message (10.3, F10). W13b-6: a manifest with a bad signature is refused. W13b-7: a restart during an update resumes by the rule in section 12 (Windows Update row). W13b-8: the package night runs on a night with no update and leaves the services ready. W13b-9: the rollback starts `<base>-r<n>` on the same Docker daemon with no subnet overlap. The failed project's networks are removed and its volumes kept (7.5 step 1). W13b-10: the setup program and the engine order versions by SemVer precedence, `-rc.N` included (page 1, 9.2 step 2). Meets section 10. | Engine unit tests; Linux-host runs with two test builds for W13b-2 to W13b-4 and W13b-6 to W13b-9; static review and the self-check for W13b-5. W13b-1 on Windows: the owner's update step (W14-3). | — | W9, W3, W13a |
| W13c | App-queued update in the engine (second deliverable) | Infrastructure Engineer | `packaging/engine/`, `.github/workflows/release.yml` (the public GHCR push of stable releases) | Uses the 7.2 contract (H2) | W13c-1: a queued run updates `v0.2.0` → `v0.2.1` (decision H8) at the window, and `/api/version` shows `v0.2.1`. W13c-2: the claim, the progress, the outcome and the heartbeat use the bridge operations of 7.2. W13c-3: after a rollback, `update_close_restored` writes `rolled_back`, and the run is never claimed again. W13c-4 (when the license work gives a test path): a licensed installation keeps its edition after a rollback. Meets section 10. | Engine unit tests; Linux-host runs. W13c-1: the owner's in-app update pass (W16). | Before the first stable tag, three GitHub settings: GHCR package visibility, a `v*` tag rule and immutable releases. Then he publishes two stable releases after the license work merges (decision H8, section 5.3) | W11, W13b; the license work for W13c-1 |
| W14 | The owner's end-user pass (first deliverable) | Human Owner as the end user; the QA Engineer writes the script and reads the reports | No code | None | The steps in 11.2. W14-1: install with the wizard; sign in on the PC. W14-2: open and sign in on the phone. W14-3: the next morning, the night's backup shows; update by running the newer test-build setup. W14-4: Modify opens the settings; Save report; uninstall with "Keep my data". W14-5: reinstall with the kept data; the business, the sign-ins and the phone's trust stay. W14-6: each failure has a message and a Save report file. Meets section 10. | What the owner sees at each step, written in the company record; the Save report files (10.2, 10.6) | Downloads two test-build setup files from the draft releases while signed in (5.3), then runs the pass | All other first-deliverable slices except W15 |
| W15 | Documentation | Infrastructure Engineer | `README.md`, `infra/AGENTS.md`, `infra/supabase/README.md`, `RESTORE.md`, `docs/architecture/11-infrastructure.md`, `docs/architecture/12-deployment-architecture.md`, the glossary | Documented contracts only | W15-1: Windows is documented as Docker Engine in our distribution, not Docker Desktop. W15-2: new glossary rows: installer, engine, engine bundle, release manifest, maintenance mode, recovery key, trust page, edition, license file, test build, end-user pass, installer report, Save report, setup payload. W15-3: no document calls the infrastructure production-ready. Meets section 10. | Scope review | — | W14 (the glossary waits for the open glossary edits) |
| W16 | The owner's in-app update pass (second deliverable) | Human Owner as the end user; the QA Engineer | No code | None | W16-1: on `v0.2.0`, Manage → Updates shows `v0.2.1`; "Install tonight" queues it; the next morning the page shows "Updated to 0.2.1". W16-2 (when the license work gives a license path for release builds): a licensed installation keeps its edition after the update. Meets section 10. | What the owner sees, written in the company record; the Save report file | Runs the pass on the stable tags (H8) | The second deliverable, the license work, the stable tags |

Repository testing rules apply to every slice: focused tests and one batch per work unit, then fast checks before a push; CI runs the heavy suites. The Linux-host runs run in a CI job on `ubuntu-latest` (amd64), because the development machine is arm64 and v1 builds amd64 images only. Linux-container evidence from macOS does not prove Windows behavior. No Windows behavior is proved before the owner's end-user pass (DEC-0031). Each Windows-only step has a self-check (10.3), and the end-user pass is the first Windows evidence.

**Data size.** No slice or end-user pass uses a sample pack. The sample packs are larger than the Desk limits (DEC-0029 Impact). A step with more data than the Desk limits allow needs a license from the license work. Examples are a sample pack, or more than 2 seats. The test license of the license work uses a test key that production builds refuse. W13b, W13c, W14 and W16 run on test builds and release builds. So they keep their data within the Desk limits, unless the license work gives another path.

### 11.1 Reviews and other roles per slice

The standard order (company delegation policy, section 4) adds these steps. "SA" is the Software Architect.

| Slice | Before the build | After the build |
|---|---|---|
| W1, W5a | — | SA code review |
| W2 | SA contract review (env format, secret list) | SA code review; Security Engineer |
| W3, W13a | — | SA code review; Security Engineer |
| W4 | — | SA code review; Security Engineer (time client: nothing listens, NTS) |
| W5b | — | SA code review; Security Engineer: `receive` staging and limits; the manifest signature identity (this repository's release workflow on `refs/tags/v…`, issuer exactly GitHub's) with no option that skips it; the `log-bundle` test with seeded values in real provider logs, in raw, base64, URL-encoded and JSON-escaped forms, plus a token in a URL query string; no `docker inspect` or unquiet `docker compose config` in a snapshot; no SMTP protocol trace, and CR, LF and NUL refused in SMTP values; a strict run ID pattern. SA and Security Engineer review of the W5b-10 image admission (SEC-R6): equality only, digest required, other ownership fields unchanged, the API stays exact on the new name |
| W6a | SA review of the CA design after the 6.3 profile | SA code review; Security Engineer (port 80, CA, `/trust/ok`); QA Engineer (devices) |
| W6b | Product Designer | Product Designer screen review; SA code review |
| W7 | Product Designer copy for pages 3 and 4 | SA code review (the `receive` stream goes to the process's raw input stream, not through the PowerShell pipeline); Security Engineer (account, tasks, rules, ACLs, allow-list, the `receive` job; the BitLocker read of 10.4; protected log and payload folders before the first write; masked secret parameters; fixed fact commands that no request field names) |
| W8 | Product Designer (pages 5 to 12, the failure messages of 10.7) | Product Designer screen review; SA code review; Security Engineer (secret channel: one pipe instance and one transfer, the pipe owner and access list checked through its handle instead of 3.2 check 2, R7 again before each password use, the `slateops-svc` bridge moves secret bytes only through .NET stream calls (never the PowerShell pipeline, script text or output), no page 5 or 6 value in `SetPreviousData`; Save report: no link followed, the person's own desktop, Task Scheduler events of `\SlateOps\*` only with account names replaced); QA Engineer |
| W9 | Product Designer (uninstall page, maintenance mode) | Product Designer screen review; SA code review; Security Engineer (fresh R7 before each new password: Repair, reinstall with kept data, `set-email`; `set-email` through the secret channel); QA Engineer |
| W10a | SA confirms fail-open for the Linux path | SA code review; Security Engineer |
| W10b | Product Designer (page 7 copy, done inside W8's design) | SA code review; Security Engineer (drvfs scope, and the backup admission check if W10b-4 changes it); QA Engineer |
| W11 | Owner approval: decided (H2, DEC-0030); SA contract review | SA code review; Security Engineer (authorization); QA Engineer |
| W12 | Product Designer | Product Designer screen review; SA code review; QA Engineer |
| W13b | — | SA code review; Security Engineer (signature check, the setup program's WSL step, the same-origin rollback exception); QA Engineer |
| W13c | — | SA code review; Security Engineer; QA Engineer |
| W14 | QA Engineer writes the script (11.2) in the company record; Security Engineer release review of the test build | QA Engineer reads the owner's notes and the Save report files |
| W15 | — | SA review |
| W16 | QA Engineer writes the script | QA Engineer reads the notes and the report; Security Engineer release review |

### 11.2 The owner's end-user pass (W14)

Before the pass, the team pushes two test-build tags on the branch, for example `v0.2.0-rc.1` and `v0.2.0-rc.2`. Each makes a draft release (5.3). The QA Engineer gives the owner this script. The owner writes down what he sees at each step, in his own words. He needs no stopwatch and reads no technical file.

1. On the Windows 11 Pro PC, sign in to GitHub and download the first setup file from its draft release.
2. Run it. Windows SmartScreen warns, because the build is unsigned (H1). Select More info, then Run anyway. If Windows says that Smart App Control blocked the file, stop and send a photo of the message to Engineering. Change no setting.
3. Complete the wizard. Type the administrator password on the organization page. Print or save the recovery key.
4. On the last page, select Open Slate Operations. Sign in with the administrator email and the password from setup. Then set up email in the "Slate Operations settings" program and send the test email.
5. Scan the QR code on the last page with your phone. Follow the steps on the trust page. Open Slate Operations on the phone and sign in.
6. Use the app on both for a while: post a message, add a record, upload a file. Use at most 2 people (Desk limit).
7. The next morning, open Manage → Backups. Check that the night's backup is there.
8. Download the second setup file and run it. Select Update and wait until it finishes. Open the app on the PC and the phone. Check that your data is there.
9. Open Windows Settings → Apps → Slate Operations → Modify. Slate Operations settings opens. Select Status, then Save report. Keep the file.
10. In Windows Settings → Apps → Slate Operations, select Uninstall. Choose Keep my data.
11. Run the second setup file again. Choose Use the kept data. When it finishes, open the app on the PC and the phone. Check that your data is there and that the phone has no certificate warning.
12. If any step shows an error, select Save report on that screen. Send every report file and your notes to Engineering.

The pass passes when each step does what it says. Each defect becomes a failing-first test and a fix on the branch. The owner then runs again only the failed steps, with a new test build.

## 12. Risks

| Risk | Mitigation |
|---|---|
| Smart App Control blocks the unsigned installer; SmartScreen warns. | Only the owner's PCs run it (DEC-0028). The code-signing certificate is bought before the first customer install (decision H1). |
| Microsoft 365 turns Basic SMTP AUTH off by default at the end of December 2026 (an admin can turn it back on); Gmail revokes app passwords on a password change. | Clear messages in the "Slate Operations settings" program, which is also where the email account is changed (DEC-0041); the company relay comes in a later version. |
| The memory of a 16 GB PC is too small for Windows plus the stack. | R4 blocks a PC under 16 GB (planning value, 10.2). The installer report of the owner's first install gives the real figure, and R4 and the WSL memory value change from it. |
| Windows Update installs a newer WSL outside our window and stops the VM (F7: very likely). | The boot task reattaches (E6, about 2.5 min). Nothing in Slate Operations downgrades WSL. The engine accepts a newer WSL unless a known-bad list names it (7.4). |
| A Windows Update restart falls in the 02:00 window, during a backup or an update. | At the next boot or distribution start the engine finds the open journal and resumes by one rule: if the backup did not complete, or no container runs on a target image yet, it runs `recover` (old images); from the first container on a target image, it rolls back by restore (7.5). The backup runner's own interrupted runs use 8.1, condition 3. |
| The VHD grows and does not shrink. | `defaultVhdSize` is set from the free space; System health shows the disk use (later). |
| One PC holds the data and the backups if the person keeps the default. | Page 7 shows a warning and needs a check box; the recovery key protects the backup if the disk is lost. |
| mDNS fails across subnets or on guest Wi-Fi with client isolation. | The requirements check needs a Private network. The trust page lists the cause. A DNS name from the later installation service removes the limit. |
| The trust page on HTTP can be changed by an attacker on the LAN. | The fingerprint shows on the server PC; Security Engineer review in W6a. |
| Docker Hub limits anonymous pulls: 100 per window for each public IP address, shared by every PC behind the office address. | Default H9 a): 7 provider images come from the publishers' GHCR; only Envoy comes from Docker Hub, with no pull limit while its Sponsored Open Source status is renewed (F8, closed). |
| The default app subnet `172.31.248.0/28` collides with a host or Docker network. The local Linux run of the withdrawn P1 kit saw this on macOS (TASK-0074). | The engine checks for a collision before the install and picks another private /28 (W5b-7). `infra/supabase/README.md:132` already allows an override; the engine sets it at install time, not at startup. |
| Caddy (UID 1000) cannot read a Caddyfile that the backup admission accepts (`backup_installation.py:183`; reproduced in the local Linux run of the withdrawn P1 kit, TASK-0074). | W5b-6 and W10b-4 need a real fix. That run's owner swap around each backup was a test workaround only. |
| The engine runs as root with the Docker socket. | It accepts only allow-listed jobs and JSON input. Interop and automount are off. The Security Engineer reviews W5b and W13b. |
| A customer installs a release without the edition limits and loses access in a later update (DEC-0029 item 13). | Before the license work, only draft test builds exist, and nobody publishes them. The first stable tag comes after the license work (section 5.3). |
| The license work starts late, so the first public download waits. | The first deliverable does not wait for it. Only the stable tags, W13c-1, W16 and the first public download wait (section 5.3). |
| A `RESTORE.md` restore into a new project on the same Docker daemon reuses `SLATEOPS_APP_PRIVATE_SUBNET`. Docker refuses the overlapping network while the source project's networks exist. This gap exists today. | The engine rollback removes the old networks first (7.5 step 1, W13b-9). For the support restore, W15 adds the same step, or a different /28 for the target, to `RESTORE.md`. |
| A rollback revokes every session. | The Updates page says so; it happens only after a failed update. |
| The data disk is not encrypted unless BitLocker is on. | Noted on the requirements page as a recommendation (decision H5). |
| A Windows-specific defect is first seen in the owner's end-user run, and each fix costs a full install cycle (DEC-0031). | Each former spike has a conservative default, and each risky step has a self-check (10.3). Save report holds the logs, facts and snapshots of section 10, so one report can resolve a defect with no second run. The boot test already proved the runtime (REQ-0022). The owner reruns only the failed steps. |
| No unattended WSL install: a PC where Windows Update brings no new WSL keeps an old WSL (10.3, F10). | The engine accepts any WSL that is not on the known-bad list. A newer setup program installs the pinned WSL with a person present. |
| The owner sees nothing until the whole first deliverable works, so a design error in an early slice is found late. | Each slice finishes its reviews before the next starts (11.0, 11.1). Linux-host runs prove the engine early. Section 10 makes each late defect cheap to diagnose. |
| The setup payload makes the installer large. | Only our two images travel in it; the provider images come from their registries. W8-7 checks the 2 GiB limit in CI. |

## 13. Decisions for the owner

All thirteen are decided. H1 is decided in DEC-0028. H2 to H13 take option a), as written at commit `65e6b1ef` (DEC-0030, APR-0011). The option text below stays as it was decided. Later changes to the plan, for example the draft test builds and the second deliverable, appear in the sections above. In H8, "W13b and W14" now means W13c and W16, and "W13b-1" means W13c-1 (11.0). In H13, the first deliverable uses drafts, not published pre-releases (5.3). In H2's Blocks cell, "W13b" now means W13c. In H8, "W15" and "P8" refer to the withdrawn numbering and grouping; read them as the second deliverable. In H9, "W3" now means W5b (W5b-10). "P2 to P7" in the Blocks cells refers to the withdrawn pull-request grouping; read it as the first deliverable.

| ID | Decision | Options (default first) | Blocks |
|---|---|---|---|
| H1 | **Decided: a) (DEC-0028).** Code signing | a) Unsigned until the first customer install (DEC-0028). | Nothing now |
| H2 | **Decided: a) (DEC-0030, APR-0011).** The update contract in 7.2 | a) Approve exactly: the routes `POST /api/updates`, `GET /api/updates` and `POST /api/updates/{id}/cancel`; the `update_runs` table; the engine-presence column `update_statuses.updater_seen_at`; and the `backup_state.py` operations `update_claim`, `update_inspect`, `update_progress`, `update_outcome`, `updater_heartbeat`, `update_close_restored` and `policy_default`. b) Change it. | W5a (`policy_default`), W11, W12, W13b |
| H3 | **Decided: a) (DEC-0030, APR-0011).** The two secret exceptions in 3.2 (SMTP password in, recovery key out) | a) Accept, after the Security Engineer's review. b) No recovery key: a lost disk then means lost backups. | W8, W10b |
| H4 | **Decided: a) (DEC-0030, APR-0011).** GPL source offer for the Linux image | a) Attach the Debian source packages to each release (about 1 to 2 GB of release storage; assumption). b) Links to `snapshot.debian.org` only. A link alone may not meet the GPLv2 written-offer duty for commercial copies, so a legal check is advised. | W3, W4 |
| H5 | **Decided: a) (DEC-0030, APR-0011).** Windows 11 Home and BitLocker | a) Block Home until it is tested; recommend BitLocker. b) Allow Home with a warning. c) Require BitLocker. | W7 |
| H6 | **Decided: a) (DEC-0030, APR-0011).** Alert channel for a failed backup or update | a) In-app only in v1 (System health, Manage). b) Add an application mailer (a new capability). | W10a, W10b |
| H7 | **Decided: a) (DEC-0030, APR-0011).** Restore in v1 | a) Support-run with the one-command engine restore. b) Owner-started restore in the maintenance mode in v1. | W13a scope |
| H8 | **Decided: a) (DEC-0030, APR-0011).** Update rehearsal releases | a) After the license work merges, publish two stable releases (for example `v0.2.0` and `v0.2.1`) that contain it, for W13b and W14. The website links neither until W14 passes. This keeps DEC-0029 item 13. But the stable tags, W13b-1, W14 and W15 wait for the license work, which waits for the owner's start. P8 merges without it. b) Publish two stable releases before the license work, only for the rehearsal, then delete them. This removes the wait, but it breaks DEC-0029 item 13 for that time. Anyone can install a stable build without the edition limits, and the first becomes "Latest". It needs a change of DEC-0029. A configurable release source is not offered. | W13b, W14 |
| H9 | **Decided: a) (DEC-0030, APR-0011).** Provider image source (F8 closed, TASK-0075) | a) Pull the 6 Supabase images from `ghcr.io/supabase/*` and imgproxy from `ghcr.io/imgproxy/imgproxy`, at the same pinned digests (checked: identical). Pull Envoy from Docker Hub, which has no pull limit while its Sponsored Open Source status is renewed (yearly). We redistribute nothing, and none of the 7 counts against a Docker Hub limit. `PROVIDER_IMAGES` in `disposable_instance.py` and the image table in `infra/supabase/README.md` change with the compose references (W3). GitHub states no anonymous pull limit for GHCR. b) Docker Hub, as now. This keeps the current files, but it allows 100 pulls per window for each public IP address. Every PC behind the office address shares that count, and one install uses about 7 counted pulls. c) Mirror the images to our GHCR. This puts every image under our control, but we then redistribute them: the Apache NOTICE duties and the GPLv2 source duties, like H4. | W3 (W3 changes the image references in `infra/supabase/compose.yaml`, which development also uses) |
| H10 | **Decided: a) (DEC-0030, APR-0011).** A second public listener on port 80 for the trust page | a) Approve: Caddy serves only `/trust`, the root certificate and the iOS profile on port 80 and redirects every other path to HTTPS. `infra/supabase/README.md:136` names 443 as the only public listener today, so this changes a documented contract. b) No port 80: phones get the trust files another way (for example from the server PC by USB or email). | W6a |
| H11 | **Decided: a) (DEC-0030, APR-0011).** The `release-manifest.json` format | a) Approve the fields in 5.2, including the known-bad WSL versions (proposed, 7.4), as a public format that the engine and the installer read; a change after v1 keeps old fields readable. b) Change it. | W3, W13b |
| H12 | **Decided: a) (DEC-0030, APR-0011).** The non-interactive restore mode | a) Approve an engine-only mode in `restore_installation.py` that the engine's own snapshot, project and directory bind (7.5, W13a). Today `--execute` needs an interactive terminal (`restore_installation.py:388`). b) No such mode: a failed update then needs a support person for the rollback. | W13a, W13b |
| H13 | **Decided: a) (DEC-0030, APR-0011).** Test-build pre-releases before the license work (section 5.3) | a) Accept: rc pre-releases titled "Test build, not for customers", never "Latest", not linked by the website or the README, with public rc images. Each one is listed publicly as a pre-release on the Releases page, and the GHCR packages are listed on the Packages page. The owner counts them as not a public release under DEC-0029 item 13. b) No published release before the license work. This removes every public artifact. But every hands-on proof from P2 on waits for the license work: W3, W4-5, W6a and W7 to W10b. c) Make the repository and the packages private until the first public download. This removes public access. But the anonymous download (5.2), the anonymous image pull (R8) and the update check (`backup_runner.py`) then fail. The owner's PCs then need a stored credential, with a new design and a Security Engineer review. | W3, P2 to P7 hands-on runs |
