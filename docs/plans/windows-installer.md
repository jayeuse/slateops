# Windows installer plan

Status: **proposed**. Nothing here is built. The owner approved the scope on 2026-11-16 (company records DEC-0028 and APR-0010). This plan names three new API routes, one new table and one new bridge command (section 7.2). Each of them needs the owner's approval before its slice starts (decision H2). Company record DEC-0029 adds self-hosted editions: every installation starts as Desk, and the first public download needs the separate license work (section 5.3). Base revision: `b33ee415` on `feat/windows-installer`.

## 1. Outcome

A person who is not technical installs Slate Operations on a Windows 11 PC with a normal Windows setup wizard. The person never opens PowerShell or a command line. The wizard lets the person choose the drive and folder for the program and for the data. Updates start from the app (Manage → Updates). Uninstall starts from Windows Settings → Apps and asks "Keep your data?".

First-version choices (DEC-0028):

- Windows 11 only.
- The customer's own email account, entered in the wizard. Presets for Gmail and Microsoft 365, plus custom SMTP, with a "Send test email" check.
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

The license work is also excluded. It holds the license file format, the signature check, the limit counters and the read-only state. It also holds the "Available in Office" previews and the test license. It is a separate build with its own contract (DEC-0029 Follow-up), and it starts only when the owner says so. This plan needs it before the first stable release, so the stable tags, W13b-1, W14, W15 and the first public download wait for it (section 5.3).

### 1.3 Labels

**Current** means read in the code at the base revision. **Observed** means measured on the owner's Windows 11 Pro PC in the boot test (company request REQ-0022). **Proposed** means this plan. **Assumption** means not checked; a spike in section 10 checks it.

**Edition** means a self-hosted edition: Desk (free), Office or Headquarters (DEC-0029 item 2). Core and Scale are managed cloud plans only, and this plan does not use them. A Windows edition (Home, Pro) is always called a Windows edition. **License file** means the signed file of an edition; the Elastic License 2.0 is always named in full.

## 2. Current state

| Area | Current state | Source |
|---|---|---|
| Runtime on Windows | **Observed:** WSL2 with Docker Engine in our own imported Debian 13 serves the LAN at boot with nobody signed in. A hidden standard account runs it through Task Scheduler. It recovered after shutdown, restart, sign-out and `wsl --update`. Ready about 30 to 36 s after Windows starts. The WSL update restarted the Linux VM; the outage was about 2.5 min. | REQ-0022; `infra/windows/boot-test/README.md` |
| Proven mechanisms | Per-account `.wslconfig` (`vmIdleTimeout=-1`, `[general] instanceIdleTimeout=-1`, fixed memory, `networkingMode=mirrored`, `defaultVhdSize`); the on-demand job task `Exec` with an allow-list (`lib/svc-exec.ps1`); the boot task (At startup, `PT0S`, 1-minute repetition, IgnoreNew, keep-alive attached, `lib/start-distro.ps1`); Windows and Hyper-V firewall rules (Private, local subnet); Docker from Docker's apt repository with a key fingerprint check; folder ACL hardening and the safety check; cleanup. | `infra/windows/boot-test/` (pull request 113) |
| Installer findings | **Observed:** the server PC cannot open its own LAN address into WSL in mirrored mode. WSL updates cause a short outage. salsa.debian.org serves a bot check to PowerShell's default user agent. Drive C: can be small (26.6 GB free on the test PC). | REQ-0022 |
| Production install | About 9 manual commands and 3 env files written by hand. | `infra/supabase/README.md:29-140` |
| Secrets | `supabase_keys.py` generates the provider keys and some application keys (for example `SUPABASE_SESSION_ENCRYPTION_KEY`, the Realtime keys). It does not generate `SECURITY_EVENT_SERVER_KEY`, the `slateops_owner` and `slateops_runtime` passwords, the SMTP values or the Restic password. It writes `NAME='value'`; `docker run --env-file` needs the literal `KEY=value` format (inferred from `infra/supabase/README.md`, provisioning env). It imports `jwt`, `cryptography` and `app.*`, so it runs only with the backend environment. | `backend/operations/supabase_keys.py:109,140` |
| First administrator | `bootstrap_admin.py` needs `--confirm` outside development, `ADMIN_EMAIL`, `ADMIN_USERNAME`, a running API and working SMTP. `--name` and `--slug` set the first organization. No production step runs it. | `backend/operations/bootstrap_admin.py:54-64,196-228`; `settings.py:348-350` |
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
 │ Task \SlateOps\Maintain (SYSTEM, nightly) → one fixed action:            │
 │   install the WSL MSI pinned in version.json (SHA-256) when engine idle  │
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
| `\SlateOps\Maintain` | New. Runs nightly in the maintenance window. It takes no input from Linux except the `engine_idle` boolean of `status` (section 7.4). | SYSTEM | `Exec` (for `status`), `msiexec` for the pinned WSL MSI |
| Linux image | A Debian 13 root file system that CI builds, with Docker Engine, Restic, Python 3, the engine of the same release and systemd units. It holds no secrets and no SSH server. `wsl.conf`: systemd on, Windows interop **off**, automatic drive mounts **off** (`[automount] enabled=false`). | — | — |
| Engine | `slateops-engine`, a command in `packaging/engine/` that uses only the Python standard library, like `packaging/backup/`. It owns install, status, update, backup scheduling, restore, the email check, the CA and the uninstall support. Steps that need `app.*`, `jwt` or `cryptography` run as one-shot containers of the release server image, the same pattern as the current provisioning job (`infra/supabase/README.md`, Lifecycle). | root in the distribution (it needs the Docker socket) | Docker, the bridge in the server image, GitHub Releases, GHCR |
| Engine bundle | One file per release: the engine, the Compose files, the Caddy template, the env templates and `release-manifest.json`. The Linux image contains the bundle of its own release. An update replaces the bundle under `/opt/slateops/engine/<version>/`. | — | — |
| Compose stack | `infra/supabase/compose.yaml` plus `compose.production.yaml`, unchanged in shape. | Docker in the distribution | — |
| App | FastAPI with the static UI. It queues update runs (section 7.2) the same way as backup runs. | uid 10001 in its container | PostgreSQL |

### 3.2 Rules of the boundary

1. Windows calls Linux only through `Exec` jobs. The job name comes from a fixed allow-list. Data goes on standard input as JSON, never as command arguments. The kit already refuses to run when PowerShell module logging covers `ScheduledTasks`, and the installer keeps that check.
2. Linux never starts a Windows program: interop is off. The only Linux value that the Windows side acts on is the `engine_idle` boolean in `slateops-engine status --json`; `\SlateOps\Maintain` uses it only to wait. No value from Linux becomes a path, a URL or an argument on the Windows side. The Windows side sends two values to the engine on the standard input of `status`: the Windows-part version and the installed WSL version. Linux cannot read Windows files (automount off).
3. Secrets are made and kept on the Linux side, in `/etc/slateops/` (root, mode 0600). Two values cross the boundary, and both are named exceptions:
   - The SMTP password moves Windows → Linux once. `smtp-test` receives it, and after a passing test the engine stages the SMTP values in `/etc/slateops/new/smtp.env` (root, 0600). `install` and `set-email` read the staged file, so the password never crosses a second time. A failed test stages nothing. Cancel (section 4.1) deletes the staged file.
   - The backup recovery key moves Linux → Windows once, for display on page 11 (section 8.3). The recovery key is a second Restic key, not the engine's working password. The only Windows-side writes of it are the person's own Print and Save to a USB drive on page 11.
   - Channel (proposed): a named pipe. The wizard creates it with an access list for Administrators and `slateops-svc` only. The `Exec` job connects to it and moves the bytes between the pipe and the engine's standard input or output. Neither value is written to a Windows disk. F4 checks that Inno Setup can read and write the pipe through a hidden helper.
   - Fallback (only if F4 fails): a file in the admin-only state folder with an access list for Administrators and `slateops-svc`. The wizard deletes it right after use, and the file exists for seconds.
   
   The Security Engineer reviews both exceptions and the fallback (decision H3) with these checks:
   1. The wizard creates the pipe with a random name for each request, as the first instance (`FILE_FLAG_FIRST_PIPE_INSTANCE`), before it starts the job. The pipe refuses remote clients, and its access list holds only Administrators and `slateops-svc`.
   2. The job checks the identity of the process that created the pipe before it reads or writes.
   3. No secret is a command-line argument, an environment value, a task property, a PowerShell cmdlet parameter or a log line. If a helper must pass a secret to a cmdlet, the module-logging check (R7) covers every module that the helper uses.
   4. Inno Setup does not save the password field (`RegisterPreviousData`) and does not write it to its `/LOG` file.
   5. The engine reads standard input with a size limit, writes the SMTP values only to `/etc/slateops/new/smtp.env` (0600), and echoes nothing.
   6. The fallback (if used) never holds the password in plain text: the engine publishes a temporary public key, and the wizard encrypts the value to it. The file has the same access list, is deleted after use, and never reaches `svc-out` or a log bundle.
   7. The recovery key is shown once. Print and Save to a USB drive are the only writes; printing creates a spool file, which is a named exception (W8-5). The log bundle never holds the key.
4. Linux reaches a Windows drive only when the engine mounts the backup drive with drvfs, with the rights of `slateops-svc`. Automatic mounts are off. The installer gives `slateops-svc` access only to the data folder and the backup folder.

## 4. Wizard (proposed)

### 4.1 Page order

The owner's page list puts the restart after the email page. This plan moves the one restart forward, to the "Prepare this PC" step after the requirements check, for two reasons:

- No secret (the SMTP password) must stay on disk across a restart.
- "Send test email" must use the engine, which applies GoTrue's TLS and authentication rules. The engine exists only after WSL works.

The Linux disk needs the chosen data folder, so the distribution is imported right after the location page. The engine downloads the images in the background while the person fills in the next pages.

| # | Page | Fields | Checks | Failure message (draft; the Product Designer writes the final copy) |
|---|---|---|---|---|
| 1 | Welcome | — | An existing installation is found → maintenance mode instead (section 9.3). Kept data is found → offer reuse on page 4. | — |
| 2 | License agreement | Accept the Elastic License 2.0 (`LICENSE`). Link to the third-party notices. This page has no edition choice and no license file. | Accept is required. | — |
| 3 | Requirements | None (a list with a pass or fail mark per line) | R1 to R9 in 4.2 | Per line, in 4.2. "Next" stays off until every blocking line passes. |
| 3a | Prepare this PC (only when needed) | — | Turns on `VirtualMachinePlatform`. Installs the pinned WSL MSI, with the SHA-256 checked right before `msiexec`. | "Slate Operations must restart this PC once. Save your work, then select Restart now." After the sign-in, setup opens again (RunOnce) at page 4. |
| 4 | Location | Program folder (default `C:\Program Files\Slate Operations`). Data folder (default `<largest fixed NTFS drive>\SlateOps`). | The data drive is a fixed NTFS drive: not removable, not network, not compressed, not EFS-encrypted. Free space ≥ the S1 figure. The folder is empty, or it holds kept data. | "This drive has X GB free. Slate Operations needs Y GB. Choose another drive." / "Choose a drive inside this PC. USB and network drives cannot hold the data." |
| 4a | Getting Linux ready (progress) | — | Creates the service account, `.wslconfig`, imports the Linux image (SHA-256 checked), runs the boot task, then runs `slateops-engine prepare` (Docker ready, mirrored mode confirmed), then starts the image prefetch. | "Setup could not start the Linux part. Select Retry. If it fails again, select Save report." The report is a log bundle with no secrets. |
| 5 | Business and administrator | Business name. Administrator email. Administrator user name (default: the part of the email before `@`, cleaned to `^[a-zA-Z0-9_-]{3,100}$`). | Name 1 to 100 characters. The slug comes from the name (shown, can be edited). Email format. User name pattern (`users/schemas.py:259`). | "Use 3 to 100 letters, numbers, - or _." |
| 6 | Email account | Provider: Gmail, Microsoft 365 or Other. Email address, password or app password, and the sender name. For Other, also the host, the port and the security (SSL/TLS on 465, or STARTTLS). Button: **Send test email** (to the administrator email). | Engine `smtp-test`: connects with GoTrue's rules, refuses authentication without TLS, sends one message, and stages the values after a pass (section 3.2). "Next" stays off until a test passes. | Per error class: "The email provider refused the user name or password. For Gmail, use an app password (needs 2-Step Verification)." / "Microsoft 365 refused sign-in. SMTP AUTH is off by default; your Microsoft 365 admin can turn it on for this mailbox." / "Cannot reach smtp.example.com on port 587." / "This server does not offer a secure connection." |
| 7 | Backups | Where to keep backups: "This PC's data drive (not safe if this drive fails)" or another drive or a USB drive. | The target is writable by `slateops-svc` and has free space. On the data drive the page shows a warning and needs a check box. | "Slate Operations cannot write to E:. Plug the drive in, or choose another drive." |
| 8 | Network name | Name, default `<computer name>.local` or `<business slug>.local` (F1 in section 10 decides which). The page shows the address that phones use. The IP address is not offered: the app has one `PUBLIC_ORIGIN` and checks the exact `Origin` on changes, so a second address would break sign-in and saves. (A future passkey also cannot use an IP address.) | The network is Private (offer "Make this network private"). No other device answers to the name (mDNS probe). Ports 443 and 80 are free on Windows. | "This network is Public. Slate Operations works only on a private network. Select Make private." / "Another program uses port 443 (for example IIS). Stop it, then select Retry." |
| 9 | Ready | A summary of the choices | — | — |
| 10 | Installing (progress) | — | `slateops-engine install` steps (section 6.2) with a step list. The firewall rules, the hosts entry, the CA in LocalMachine Root and the sleep setting run on the Windows side. | For each step: "Retry" and "Save report". A failed install keeps all state so that "Retry" resumes it. |
| 11 | Recovery key | The key, shown once. Buttons: Print, Save to a USB drive. | Check box "I saved the recovery key" is required. | — |
| 12 | Finish | "Open Slate Operations" (default browser at `https://<name>.local`). A QR code for phones that opens `http://<name>.local/trust`. Text: "Open the invitation email on this PC to set your password." Text: "Your edition is Desk (free). To use Office or Headquarters, import your license file in Slate Operations: Manage → Updates & licensing." | — | — |

**Cancel after page 4a.** From page 4a on, Linux exists on the PC. Cancel then asks: "Remove what setup added?" with two answers:
- **Remove everything** (default): the uninstall steps of section 9.1 with "Delete everything", plus the staged SMTP values.
- **Keep it and continue later**: the distribution, the account and the tasks stay; the staged SMTP values are deleted. The next start of setup resumes at page 5.

While an install step runs on page 10, Cancel waits for that step to end. After a failed step, Cancel gives the same two answers.

**Edition at first run.** Every new installation runs as Desk. No wizard page asks for an edition or a license file. The maintenance mode (9.3) has no license import. Source: the owner, company record TASK-0076: "I want it inside the system itself and not on the wizard". The administrator imports a license file in the app, in Manage → Updates & licensing (DEC-0029 item 10). The license work owns that control and its states. The license work decides how a reinstall with kept data (9.2) keeps the edition.

**Handoff to the license work.** These points of this plan touch the license work, and its contract must cover them:

1. Updates (`POST /api/updates` and the engine update) and backup runs stay allowed in the read-only state after the end of a license. Source: DEC-0029 items 6 and 11.
2. A rollback by restore (7.5) and a support restore (8.4) create a new instance ID. The license must stay valid after that change.
3. When the license work gives a license path for release builds, W14 adds step W14-7. In W14-7, a licensed installation keeps its edition after the update and after the rollback.

The Product Designer must design pages 3, 4, 6, 7, 8, 11 and 12, the trust page and the uninstall page (section 9) before the build. The Inno Setup default pages (1, 2, 9) need only copy.

### 4.2 Requirements check

| ID | Check | How | Blocking | Message |
|---|---|---|---|---|
| R1 | Windows 11, build 22621 or later | Registry `CurrentBuildNumber` | Yes | "Slate Operations needs Windows 11, version 22H2 or later. Run Windows Update, then try again." |
| R2 | Windows edition Pro, Enterprise or Education | `EditionID` | Yes (decision H5; default: Home is blocked until it is tested) | "Slate Operations is not yet tested on Windows 11 Home." |
| R3 | Virtualization on | `Win32_Processor.VirtualizationFirmwareEnabled`, or `Win32_ComputerSystem.HypervisorPresent` when a hypervisor already runs (property names are an assumption; W7 checks them) | Yes | "Turn on virtualization in the PC's firmware (BIOS or UEFI) settings. Your PC supplier can help." |
| R4 | Memory | Total physical memory ≥ the S1 figure (planning value 16 GB) | Yes | "This PC has X GB of memory. Slate Operations needs Y GB." |
| R5 | Free space on the chosen data drive | Checked on page 4 | Yes | Page 4 |
| R6 | Not joined to a domain network, and the active network is not Public | `Get-NetConnectionProfile` | Domain: yes. Public: page 8 offers the fix | "Slate Operations is not tested on company domain networks." |
| R7 | PowerShell module logging does not cover `ScheduledTasks` | Policy registry (kit check) | Yes | "A security policy on this PC records commands. Ask the person who manages this PC." |
| R8 | Internet access to github.com, ghcr.io and the Docker Hub registry | HTTPS HEAD with a plain user agent (REQ-0022 finding) | Yes | "Setup cannot reach the internet. Connect this PC, then select Retry." |
| R9 | On mains power (laptops) | `Win32_Battery` | No (a warning) | "Keep this PC on mains power. A PC that sleeps or runs on battery stops serving the office." |

### 4.3 What goes where

| Part | Location | Why |
|---|---|---|
| Program | `C:\Program Files\Slate Operations\` (can be changed): the scripts, the uninstaller, `version.json`, the setup copy for maintenance mode | Protected from standard users; small (under 50 MB, assumption) |
| State and logs | `C:\ProgramData\SlateOps\` (Administrators and SYSTEM only; `slateops-svc` only where the kit allows): requests, results, logs | Same as the kit; the safety check applies |
| Data | `<data folder>\SlateOps\distro\ext4.vhdx`: the whole Linux disk, with the database, the files, the secrets and the journals | The only part that grows. The data folder can be on another drive, because drive C: can be small. `defaultVhdSize` is set from the free space (the S1 figure gives the minimum). |
| Kept data | `<data folder>\SlateOps\kept\` (after "Keep your data") | Section 9.2 |
| Backups | The folder from page 7, for example `E:\SlateOps-backups\` | A different drive protects against a drive failure |

## 5. Release artifacts (proposed)

### 5.1 Version

1. A Git tag `vX.Y.Z` on `main` is the only version source.
2. CI passes `SLATEOPS_VERSION` as a build argument. The server image keeps it as an environment value and as the OCI label `org.opencontainers.image.version`.
3. `create_app()` reads `SLATEOPS_VERSION`. The default is `0.0.0+dev` for local runs. `backend/app/main.py:186` loses the literal.
4. The release workflow refuses a tag that differs from `backend/pyproject.toml` `version` and `frontend/package.json` `version`.

`GET /api/version` keeps its response shape. The value becomes real.

### 5.2 Release workflow

A new `.github/workflows/release.yml` runs on a `v*` tag push. The workflow-level permission is `contents: read`. Each job gets only what it needs: the image job `packages: write`, `id-token: write` and `attestations: write`; the manifest-signing job `id-token: write`; the release job `contents: write`. Every Action is SHA-pinned. v1 builds `linux/amd64` only; arm64 waits for a real need.

| Step | Output |
|---|---|
| Build the server and Caddy images for `linux/amd64` with Buildx | `ghcr.io/<owner>/slateops-server:<version>` and `ghcr.io/<owner>/slateops-caddy:<version>`, public, anonymous pull (before the license work, only rc versions; section 5.3) |
| Sign the image digests with cosign keyless (GitHub OIDC). Attach build provenance. | Signatures and attestations in GHCR |
| Build the Linux image: `mmdebstrap` of Debian 13 from a fixed `snapshot.debian.org` date, plus Docker's apt repository (fingerprint check), Restic, Python 3, a pinned cosign release (SHA-256 checked; listed in the package list), the engine bundle, systemd units and `wsl.conf`. amd64 only. | `slateops-linux-<version>-amd64.tar.gz`, its package list and its source list |
| Build the engine bundle | `slateops-engine-<version>.tar.gz` |
| Write `release-manifest.json` (a new public format; owner decision H11): the version, all image references by digest (our two images plus the pinned provider digests from `infra/supabase/compose.yaml`, from the registries that H9 sets), the SHA-256 of the Linux image and of the engine bundle, the minimum Windows-part version, the known-bad WSL versions (proposed, 7.4), and migration notes. Sign it with cosign keyless. | `release-manifest.json` and its signature bundle |
| Build the installer with Inno Setup (`ISCC`) on `windows-latest`. The pinned SHA-256 of the Linux image and of the WSL MSI is compiled in. | `SlateOpsSetup-<version>.exe` (unsigned until decision H1 changes) |
| Collect the third-party notices: Python packages (from `backend/uv.lock`), npm packages in the static export (from `frontend/package-lock.json`), the Debian packages (copyright files), Docker Engine, Inno Setup, and the provider images that the installation pulls | `THIRD-PARTY-NOTICES.txt` (also inside the installer and the Linux image) |
| Write the source offer for the GPL parts of the Linux image: each Debian source package and version with its `snapshot.debian.org` URL (decision H4 decides whether the source files are also attached) | `SOURCE-OFFER.txt` |
| `SHA256SUMS` for every asset | `SHA256SUMS` |
| Create the GitHub Release as a **draft**. The owner publishes it. Before the license work, the owner publishes only as a pre-release (section 5.3). | — |
| Installer and Linux image | The installer **downloads** the Linux image from the published release by its exact URL and checks the compiled-in SHA-256, like the kit does. The installer stays small. A draft release cannot serve anonymous downloads, so every hands-on install uses a published release or pre-release. Before the license work, it is always a pre-release (section 5.3). |

A pre-release tag (`v0.2.0-rc.1`) builds the same assets. A published pre-release serves installs. The update check ignores pre-releases (`backup_runner.py:88`). `POST /api/updates` accepts only the latest observed stable release. So an update test needs two **published stable** releases (decision H8: for example `v0.2.0`, then `v0.2.1`). Both come after the license work (section 5.3). This plan adds no configurable release source; the README says none exists.

The GitHub release asset limit is 2 GiB per file (assumption from memory; W3 checks it). The Linux image does not contain the container images, so it stays far below that limit (assumption; W4 measures it).

### 5.3 Releases before the license work

DEC-0029 item 13 allows no public release without the edition limits and the license import, so that no customer loses access in a later update. The repository is public. So a published pre-release is listed publicly on the Releases page, and the GHCR packages are listed on the Packages page. This plan uses these rules until the license work merges into `main`:

1. **Tags.** The owner pushes only pre-release tags (`vX.Y.Z-rc.N`). No stable tag `vX.Y.Z` is pushed before the license work merges.
2. **Releases.** The workflow creates a draft. For a hands-on install, the owner publishes it as a pre-release, never as "Latest". Its title starts with "Test build, not for customers". The website and the README never link it. The installer is unsigned (H1), so SmartScreen warns.
3. **Images.** GHCR holds only rc versions. The packages stay public, because the install pulls anonymously (R8, 6.2 step 3). A private package would put a pull credential on the PC. An image alone has no installer and no Windows part. But a Linux operator can run the public rc images with the Compose files of the public repository, with no edition limits.
4. **Honest limit.** These test builds are not secret. Each one is listed publicly as a pre-release on the Releases page, and the GHCR packages are listed on the Packages page. Anyone can download them. They are marked as test builds and never offered as a download. Decision H13 asks the owner to accept this reading of item 13.
5. **Stable releases.** The first stable tag comes after the license work merges, so every stable release contains the edition limits and the license import. W13b-1 and W14 need two stable releases (H8), so their hands-on proof waits for the license work. The website links a stable release only after W14 passes. That release is the first public download. A fix in P9 needs a new stable tag and a new run of the failed W14 steps before the website links that release.

The license work is not a slice of this plan. It does not block P1 to P8. It blocks only the stable tags (H8), the W13b-1 hands-on proof, W14, W15 and the first public download. The W13b design checks one question: can the setup program's `update` path (7.4, 9.2 step 5) rehearse 7.3 and 7.5 on rc tags? It can only if that path needs no stable target and no `update_runs` row. If it cannot, the other W13b criteria that need an update run (W13b-2 to W13b-4, W13b-6 and W13b-7) also wait for the stable tags.

Order: P8 merges, then the license work merges, then the owner tags `v0.2.0` and `v0.2.1`, then W13b-1 and W14 run, then P9 (W15) merges. This order has three costs:

| Cost | Solution |
|---|---|
| W13b-1 merges in P8 with no hands-on proof. | P8 merges with the engine unit tests and the hands-on proofs that rc tags allow. W13b-1 runs on the stable tags before W14. A W13b-1 failure becomes a failing-first test and a fix in P9, before the website links a release. |
| W12 and the license work both change `updates-panel.tsx` and `updates-rules.ts`. | Each keeps the other's parts (7.1). P8 merges first, so the license work rebases onto W12. |
| W11 and the license work can each add an Alembic migration. | The second migration to merge rebases onto the first (its `down_revision`), and `alembic check` passes after the rebase. |


## 6. Install engine (proposed)

### 6.1 Contract

- One command does the full first install: `slateops-engine install`. It reads the wizard's answers as JSON on standard input.
- The answers schema has `business_name`, `slug`, `admin_email`, `admin_username`, `public_host`, `backup_target` and `data_vhd_max_gb`. The SMTP values are not in the answers; `install` reads the values that `smtp-test` staged (section 3.2).
- **Idempotent and resumable.** Each step writes its completion to `/var/lib/slateops/install-journal.json` before the next step starts. A rerun skips completed steps and repeats only the step that did not complete.
- A step never overwrites a secret, a CA key or a volume that exists. When existing state does not match the journal, the engine stops with a safe code and does not "repair" it.
- **No secret in logs or output.** The engine logs step names, durations and safe codes only. It runs `docker compose config` only with `--quiet`. It never echoes the answers. Its output is safe JSON, like the backup runner.
- The answers reach the engine only through the channel in section 3.2.

### 6.2 Steps of `install`

| # | Step | Where it runs |
|---|---|---|
| 1 | Validate the answers. Check the release manifest signature (cosign; the identity is the release workflow of this repository). | Host (engine) |
| 2 | Create the folders: `/etc/slateops` (0700 root), `/etc/slateops/tls` (server certificate and key; the only TLS folder that Caddy mounts), `/etc/slateops/ca` (CA material; never mounted into a container except the one-shot CA job), log root (owner 10001), backup-export root (as `infra/supabase/README.md` requires), state. | Host |
| 3 | Pull the pinned images by digest. Verify the cosign signatures of our two images. The prefetch on page 4a already started this step. | Host |
| 4 | Generate **all** secrets into `/etc/slateops/` in the literal `KEY=value` format: the keys that `supabase_keys.py` makes now, plus `SECURITY_EVENT_SERVER_KEY`, the `slateops_owner` and `slateops_runtime` passwords, the Restic password, every other secret that `Settings` requires, and `SLATEOPS_INSTANCE_ID`. The SMTP values come from the staged `smtp.env`. | One-shot container of the server image, with only `/etc/slateops/new` mounted, no network |
| 5 | Write `provider.env`, `app.env` and the provisioning env from the production templates in the engine bundle. | Host |
| 6 | Create the local CA if it is absent: a root, then an intermediate with X.509 name constraints, signed by the root. The constraint profile is in 6.3. Remove the root key after it signs the intermediate; only the root certificate stays, for the trust page and LocalMachine Root. Keep the intermediate key in `/etc/slateops/ca/`. The intermediate validity equals the root validity, because no root key remains to sign a new one. Issue the server certificate from the intermediate (validity 397 days or less; Apple's limit is 825 days, confirmed by F6) into `/etc/slateops/tls/`. Render the Caddyfile with `generate_config.py --tls-mode custom`. Write the trust files (root `.crt` and the iOS `.mobileconfig`). W6a-5 checks by hand that devices enforce the constraints in the intermediate. | One-shot server-image container for the keys and the certificates; host for the files |
| 7 | Start the provider services. Wait for health, Realtime included. | Host (Compose) |
| 8 | Run the current provisioning job: `provision_database_role.py --confirm`, `alembic upgrade head`, `alembic check`, `provision_storage.py --confirm`. | One-shot server-image container on the provider network |
| 9 | Start `api`. Wait for `/api/ready` on the internal path. | Host |
| 10 | Start `caddy`. Check `https://<public_host>/api/health` through loopback with the Host header. | Host |
| 11 | Create the first administrator: `bootstrap_admin.py --confirm --name <business_name> --slug <slug>` with `ADMIN_EMAIL` and `ADMIN_USERNAME`. It sends the invitation through the customer's SMTP. | One-shot server-image container |
| 12 | Initialize Restic at `backup_target`. Write the version-3 backup config. Add the recovery key (`restic key add`). Turn on `slateops-runner.timer`, which replaces the per-minute Windows task in `RESTORE.md`. Set the default policy (daily, at 02:00 in the organization time zone) with the new `policy_default` operation of `backup_state.py` (W5a, decision H2). | Host |
| 13 | Write `installation.json` (version, project, instance ID, `public_host`). Return the safe result: the CA certificate (public), the recovery key (exception, section 3.2) and the status. | Host |

The wizard then does the Windows-side steps:

- firewall rules for TCP 443 and 80 (Windows and Hyper-V, Private profile, local subnet);
- the hosts entry `<public_host> → 127.0.0.1`;
- the CA in LocalMachine Root;
- Sleep and Hibernate on mains power set to Never.

The `Exec` allow-list holds exactly these engine jobs: `prepare`, `prefetch`, `smtp-test`, `install`, `status`, `update` (from the new setup program, 7.4), `set-email`, `set-backup-target`, `new-recovery-key`, `export-trust`, `log-bundle`, `prepare-uninstall`, `restore`. "Repair" in the maintenance mode is Windows-side work plus `status`.

### 6.3 Caddy and the trust page

- Caddy keeps `:443` with the custom certificate. A new `:80` site serves only `/trust`, `/trust/slateops-ca.crt` and `/trust/slateops.mobileconfig`. It redirects every other path to HTTPS.
- The trust page is a static, self-contained HTML file in the Caddy image (`infra/caddy/trust/`), with steps for iOS, Android, Windows and macOS. It shows the CA fingerprint; the finish page and the maintenance mode on the server PC show the same fingerprint.
- `generate_config.py` gets a `--trust-root` option.
- **Certificate profile** (F6 facts, company record TASK-0075):
  - Chrome (Windows, macOS, Android, Linux) and Apple (iOS, iPadOS, macOS) enforce name constraints in the intermediate. A constraint in the root is ignored by Chrome on Android, so the constraint stays in the intermediate.
  - The name constraints extension is critical. It has a `dNSName` subtree for `public_host`. A DNS-only constraint does not limit IP names, so it also has an `iPAddress` subtree that excludes all addresses.
  - The constraint `<name>.local` also permits every name below it, for example `a.<name>.local`. Only the engine holds the intermediate key, so this is accepted.
  - The server certificate is minimal: the DNS name `public_host` only, with no IP address in the subject or the SAN. Windows CryptoAPI can flag a name type in the leaf that no constraint covers, so the leaf has no name type that a constraint does not cover. The subject is either empty, with a critical SAN, or covered by a `directoryName` permitted subtree equal to the leaf subject. The PowerShell check in W6a-5 decides which.
  - The server certificate lifetime is 397 days or less. Apple's limit for certificates from user-added roots is 825 days.
- **Devices.** On Android, Chrome trusts the installed CA. Other Android apps that target Android 7 or later ignore user CAs by default (an app can opt in). The trust page tells Android users to use Chrome. On iOS, the trust page shows the second step, in Settings → General → About → Certificate Trust Settings. There the person turns on full trust for the root.
- Port 80 is new public exposure. The Security Engineer reviews it (W6a).
- Renewal: `slateops-runner.timer` also checks the server certificate once a day. The engine issues a new one from the intermediate 30 days before it expires and reloads Caddy. `/etc/slateops/tls/` is the backup set's `tls_directory`; W10b adds `/etc/slateops/ca/` to the backup set (the Software Architect decides how the version-3 backup config names it). A restore and a reinstall with kept data keep the same CA, so devices stay trusted.

## 7. Update (proposed)

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

### 7.2 Contract between the app and the engine (each item needs the owner's approval before W11 starts)

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

1. Take the runner's host lock. Claim the run. Open the journal.
2. Download the new `release-manifest.json` and the engine bundle. Verify the signature and the SHA-256. Install the bundle beside the old one. Run the new engine for the next steps; keep the old one for the rollback.
3. Check the free space: the volumes need room for one restored copy (section 7.5). Not enough space → `failed`, `insufficient_space`, and nothing stops.
4. Pull the target images by digest while the services still run.
5. Stop the services. Run the offline backup (current archive function). Record the snapshot ID in the journal.
6. Write the new env files from the new templates. Add new keys only, and keep every existing secret.
7. **Rollback boundary.** Start the provider services on the target images (`db auth storage imgproxy realtime meta studio api-gw`). The journal records this step before the first container starts.
8. Wait for provider health, Realtime included (`infra/supabase/README.md`, Lifecycle: provisioning needs `realtime.messages`).
9. Run the provisioning job with the target image: roles, `alembic upgrade head`, `alembic check`, Storage.
10. Start `api` on the target image. Wait for `/api/ready` on the internal path. Check that the running `api` container reports the target `SLATEOPS_VERSION` (W1). `GET /api/version` needs a signed-in owner, so the engine does not call it.
11. Start `caddy` last. Check HTTPS through loopback with the Host header.
12. Mark the run `succeeded`. Release the lock. Remove the old images after 7 days.

**Failure before step 7** (no container runs on a target image yet): run the current `recover` path. It restarts the containers that ran before, on the old images, with `caddy` last after readiness. Then mark the run `failed`.

**Failure in or after step 7:** roll back with the restore path (7.5), then mark the run `rolled_back`.

**Gap that a rollback cannot close.** The rollback restores the snapshot from step 5. Every write after step 10 (the first start of `api`, which also starts the background workers) is lost: records, files, messages and audit rows. An external effect of that time can repeat after the rollback, for example an invitation or recovery email that the workers or Auth already sent. The Updates page states this after a rollback. The window is short, because step 11 follows at once and the check runs before ingress opens; no person can sign in before step 11.

Debian package upgrades are not part of the update outage. They run on a separate night (7.4).

### 7.4 WSL, Linux packages and the installer itself

- **Linux packages:** on a separate night from any update. The package night is once a week, on Sunday after the nightly backup, when no update run is queued or active. The engine holds the runner's host lock and upgrades the Debian packages: only the Debian security repository and the pinned Docker major version (apt preferences in the Linux image). A Docker Engine upgrade restarts the containers; the engine then checks readiness, with `caddy` last. A failure keeps the old packages where apt allows it and shows "Needs support" in the engine `status`.
- **WSL:** `\SlateOps\Maintain` (SYSTEM) runs nightly at 02:45. It reads the installed WSL version on the Windows side and compares it with the WSL version pinned in `version.json` of the installed Windows part. It acts only when the installed version is older and the engine `status` (through `Exec`) reports `engine_idle`. `engine_idle` means that no update, backup, restore or package night runs. It then installs the pinned WSL MSI from the program folder or from its pinned URL, with the SHA-256 checked right before `msiexec`. It does not run `wsl --update`, and it takes no version, path or URL from Linux. The boot task reattaches by itself; E6 observed this after a WSL update, with an outage of about 2.5 min. F10 checks the MSI install from a SYSTEM task with nobody signed in. A new pinned WSL version arrives only with a new setup program.
- **A newer WSL from Windows Update.** Windows Update can install a newer WSL at any time, outside the window (F7, closed). This is very likely: the MSI writes a Windows Update targeting key, and the WSL service writes it again at every start. Microsoft added WSL publishing to the Windows Update catalog on 2026-10-07; which rings reach normal PCs is not stated. One Insider report says the install force-stopped the running distributions after 10 seconds. The rules:
  1. The boot task reattaches by itself. E6 saw this after a WSL update, with an outage of about 2.5 min.
  2. If the stop falls in a backup or update run, the engine resumes by the rule in section 12 (Windows Update row).
  3. `\SlateOps\Maintain` never downgrades WSL. When the installed version is newer than `version.json`, it does not act, and it records the installed version in its log.
  4. The Windows side sends the installed WSL version on the standard input of `status`, like the Windows-part version (3.2 rule 2). The engine accepts a WSL version newer than `version.json`, unless a known-bad list names it. Then the engine `status` shows "Needs support". Proposed: the known-bad list is the field "known-bad WSL versions" of `release-manifest.json` (5.2, decision H11).
  5. The WSL service also checks GitHub once a day and shows a notice only; it installs nothing. The DWORD `UpdateCheckPeriodMs=0` under `HKLM\Software\Microsoft\Windows\CurrentVersion\Lxss` turns this check off. This value is not documented by Microsoft, so the plan does not depend on it.

  F10 and an unattended Windows Update install of WSL stay hands-on observations.
- **Installer and Windows part:** the owner runs the new `SlateOpsSetup-<version>.exe`. It finds the installation and shows "Update". It keeps every choice and every secret, replaces the program folder and the tasks, and then queues the engine update directly through `Exec`. The app shows this path only when the manifest needs it.

### 7.5 Rollback by restore

`RESTORE.md` restores only into a new Compose project with a new instance ID. A rollback uses that contract, with one exception:

1. Stop and remove the failed project's containers and networks with `docker compose down` without `-v`. Its volumes stay until support removes them.
2. Restore the pre-update snapshot into project `<base>-r<n>` with a new instance ID.
3. Rebind the env files.
4. Finalize (this revokes the sessions).
5. Start the services with the old images, with `caddy` last after readiness.
6. Adopt the backup policy (`recover --restore-finalized`).
7. Write `rolled_back` with `update_close_restored`.

Step 1 removes the networks for one reason. The restored project uses the same `SLATEOPS_APP_PRIVATE_SUBNET` (`infra/supabase/compose.production.yaml:70`, `:163`). Docker refuses a second network with an overlapping subnet, so step 5 fails if the old network remains. If the failed project's networks must stay, the engine runs the W5b-7 subnet check for `<base>-r<n>` instead.

**Exception to `RESTORE.md` (Rebind, line 159).** That procedure gives the target its own site, origin, issuer and gateway URLs. A rollback keeps the same `PUBLIC_ORIGIN`, `SITE_URL`, `API_EXTERNAL_URL` and host name, because phones and PCs know only that name and trust only its certificate. This is safe only because the failed project is stopped before the restored project starts, and it never starts with ingress again. The engine refuses the rollback if a container of the failed project still runs. The Software Architect and the Security Engineer review this exception in W13b.

The engine needs a non-interactive path through `restore_installation.py`. Today `--execute` refuses to run without an interactive terminal, by design (`packaging/backup/restore_installation.py:388`), so no unattended restore exists. The confirmation text binds the engine's own snapshot, project and directory. This path is limited to the engine and exists only for this case (W13a; owner decision H12). S1 cannot run a full restore for that reason. It gives the `restic restore` time for an empty installation as a lower bound (TASK-0074).

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
- F5 measures drvfs speed and Restic behavior on NTFS.

### 8.3 Recovery key

The Restic password lives inside the Linux disk. If that disk is lost, the backups cannot be read without a second key. The engine adds a second Restic key and shows it once on page 11, where the person prints it or saves it to a USB drive. Slate Operations does not store it on Windows. The maintenance mode can make a new key and remove the old one. This key is the named exception in section 3.2 (decision H3).

### 8.4 Restore in v1

Restore stays **support-run in v1**. The engine wraps the `RESTORE.md` procedure in one command, `slateops-engine restore --snapshot <id>`, which the rollback (7.5) also uses. A support person runs it through a remote session. The reasons:

- A restore replaces live data, revokes every session and needs a choice of snapshot. A wrong choice by an owner loses data.
- The procedure has many guards today, and only the release rehearsal (W14) will prove the one-command path on Windows.
- A reinstall with kept data (9.2) covers the most common case (a Windows repair or reinstall) without a restore.

An owner-started restore in the maintenance mode is a candidate for v2 after W14 (decision H7).

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

The sleep settings go back to their old values.

WSL and `VirtualMachinePlatform` stay, because other programs and accounts can use them.

| Answer | The Linux disk | Backups |
|---|---|---|
| Keep my data | `prepare-uninstall` stops the services cleanly. The disk moves to `<data folder>\SlateOps\kept\ext4.vhdx` with `kept.json` (version, instance ID, business name, `public_host`, date). Then the distribution is unregistered. F3 checks that the unregister does not delete the moved disk. | Kept |
| Delete everything | `wsl --unregister` deletes the disk. The data folder is deleted. | Kept unless the person also selects "Delete the backups on E:" |

### 9.2 Reinstall with kept data

1. Page 4 finds `kept.json` in the chosen data folder. It offers "Use the kept data (business X, version W)".
2. If W is newer than the installer, setup stops: "Use setup version W or later."
3. Setup creates a new `slateops-svc` and gives it access to the disk. It registers the disk with `wsl --import-in-place` (F3).
4. Pages 5 to 8 are skipped, because the secrets, the CA, the email account and the name are inside the disk. Page 6 can be opened to change the email account.
5. If W is older, the engine runs the update steps 3 to 11 of 7.3, with the backup first.
6. The Windows-side steps run again (firewall, hosts, CA trust).

### 9.3 Maintenance mode

The Start menu entry "Slate Operations settings" opens the setup copy in the program folder. Settings → Apps → Modify opens it too, if F4 confirms that this works. The maintenance mode offers:

- Change email account (engine `set-email`; it recreates `auth` and offers a test send). This is the path for the Microsoft 365 change at the end of December 2026 and for a revoked Gmail app password.
- Change backup location.
- Show the trust page and the QR code.
- Make a new recovery key.
- Status ("Running", "Updating", "Needs support"), with a log bundle that holds no secrets.
- Repair: rerun the tasks, the rules and the boot start.

The maintenance mode has no license import. The administrator imports a license file in the app (DEC-0029 item 10).

## 10. Spikes and the measurement slice

| ID | Question | Method | Owner | Blocks |
|---|---|---|---|---|
| F1 | Does Windows 11 answer mDNS for `<computer name>.local` to iOS and Android? Can Avahi in the distribution publish another name in mirrored mode, beside the Windows mDNS responder? | Hands-on on the owner's PC with a phone | Infrastructure Engineer prepares; owner runs | Page 8 default, W6a |
| F2 | Does Caddy on 443 and 80 in mirrored mode serve the LAN with Docker port publishing? Does the server PC reach `<name>.local` through the hosts entry? | Inside S1 | Infrastructure Engineer | W6a, W7 |
| F3 | After the VHD moves out of the registered path, does `wsl --unregister` leave it alone? Does `wsl --import-in-place` register it again under a new account? | Hands-on | Infrastructure Engineer | W9 |
| F4 | Inno Setup: does the RunOnce resume elevate after the sign-in? Do custom pages run long actions with a progress page? Do a custom uninstall page and a working "Modify" in Settings → Apps work? Can the wizard exchange a value with the `Exec` job through a named pipe and a hidden helper (section 3.2)? | Hands-on with a throwaway installer | Infrastructure Engineer | W7, W9 |
| F5 | With automount off, can the engine mount a USB drive letter with drvfs in `slateops-svc`'s distribution? How fast are Restic backup and check on NTFS through drvfs? | Hands-on | Infrastructure Engineer | W10b |
| F6 | Do iOS, Android (Chrome), Windows and macOS accept a user-trusted root with X.509 name constraints, and do they enforce them? | Web facts: closed (TASK-0075; profile in 6.3). Hands-on: step W6a-5 in P5 | Software Architect (web); owner (W6a-5) | W6a (fallback if W6a-5 fails: a root without constraints, with a Security Engineer risk decision) |
| F7 | Closed (TASK-0075). Windows Update can install a newer WSL outside the window; the rules are in 7.4. An unattended install stays a hands-on observation with F10. | — | — | — |
| F8 | Closed (TASK-0075). Docker Hub allows 100 anonymous pulls per window for each public IP address. The same pinned digests of 7 provider images are on the publishers' GHCR; the result is decision H9. | — | — | — |
| F9 | Closed. Docker and the keep-alive with interop off were observed in the boot test (the kit sets interop off). The WSL version question is gone, because `\SlateOps\Maintain` reads the WSL version on the Windows side (7.4). | — | — | — |
| F10 | Does the pinned WSL MSI install from a SYSTEM task with nobody signed in, and does the boot task reattach after it? Also observe an unattended Windows Update install of WSL (7.4). | Hands-on | Infrastructure Engineer | W13b |

**S1 (measurement, first slice).** On the owner's 16 GB Windows 11 Pro PC, run the real production stack in WSL:

- Use the boot-test kit with a new payload option. It builds the server and Caddy images inside the distribution from the checkout. It runs the current manual production steps with throwaway secrets and a placeholder SMTP host.
- Measure:
  - the WSL VM memory when idle, at startup and during a backup;
  - the time from the Windows start to `/api/ready`;
  - the image sizes and the VHD size after the install;
  - the duration of the backup;
  - the `restic restore` time for an empty installation, as a lower bound (a full restore needs a terminal, 7.5);
  - whether F2 passes.
- The output sets:
  - the `.wslconfig` `memory` value (the kit uses 6 GB; the production overlay budget is about 5 GB at worst with `shared_buffers=2GB`);
  - whether Windows needs its own PostgreSQL memory values;
  - R4 and the free-space minimum.
- S1 adds a payload option to the boot-test kit; it changes no product code, and the Software Architect reviews the kit change. The data is throwaway.

## 11. Slices

### 11.0 Pull requests

The 20 slices ship as 9 pull requests. The pull requests run **one after another**. The repository allows one writing session at a time and no worktrees, so no two pull requests are open for writing at once. Inside one pull request, the slices run in the order listed, and each slice is one task with one owner. The spikes F1 to F10 run before the pull request that they block; they change no product code. W14 (the rehearsal) changes no code; its findings go into the next commit of an open pull request or into P9.

| PR | Slices (tasks, in order) | Owners | Why a separate pull request | Depends on |
|---|---|---|---|---|
| P1 | S1 | Infrastructure Engineer | Test-kit change only; its measurements set R4, the memory value and the free-space minimum before any wizard work | — |
| P2 | W1, W3 | Backend Engineer, Infrastructure Engineer | Creates public artifacts (GHCR, rc pre-releases only, section 5.3) and the release workflow; needs its own security review and the owner's one-time GHCR setting | P1 (measurements known), H13 answered, H9 answered |
| P3 | W4 | Infrastructure Engineer | A new distributable with GPL duties (H4) and a supply-chain review | P2 |
| P4 | W2, W5a, W5b | Backend Engineer, Infrastructure Engineer | The install contract: secrets, env format, bridge entry points and the engine | P3 |
| P5 | W6b, W6a | Frontend Engineer, Infrastructure Engineer | A new public listener (H10) and the CA design; security review of exposure | P4, F1 (F6 web facts closed; its hands-on part is W6a-5) |
| P6 | W10a, W10b | Backend Engineer, Infrastructure Engineer | Changes runner behavior for every installation, Linux included | P4, P5 (W10b follows W6a in the engine), F5 |
| P7 | W7, W8, W9 | Infrastructure Engineer | The Windows installer; proved only by hands-on runs on the owner's PC | P3, P4, P5, P6, F3, F4 |
| P8 | W11, W12, W13a, W13b | Backend Engineer, Frontend Engineer, Infrastructure Engineer | The owner-approved update contract (H2, H11, H12) with a migration | P2, P6, P7, decision H2 |
| P9 | W15, and the fixes from W13b-1 and W14 | Infrastructure Engineer | W15 closes the documentation after W14, which runs on the stable tags after the license work (section 5.3). Risk: it holds the fixes that gate the first public download, and no other pull request is open then | P8, the license work, W13b-1, W14 |

Each slice still lists its own "Depends on" below; the pull request order satisfies all of them.

**License work.** It is a separate build with its own contract (DEC-0029 Follow-up), not a pull request of this plan. It must merge before the first stable tag (section 5.3). It needs the owner's start. P1 to P8 do not wait for it; it merges after P8 (order and costs in section 5.3).

| ID | Slice | Owner | Files or area | Contracts changed | Acceptance criteria | Proof | Needs from the owner | Depends on |
|---|---|---|---|---|---|---|---|---|
| S1 | Measure the real stack on Windows | Infrastructure Engineer | `infra/windows/boot-test/` (new payload option) | None (test kit only) | S1-1: memory, start time, sizes and durations recorded as in section 10. S1-2: F2 answered. | Hands-on run on the owner's PC; results in the company record | Runs the kit; about 1 hour | — |
| W1 | Single version source | Backend Engineer | `backend/app/main.py`, `infra/docker/backend.Dockerfile` (build argument), `tests/tooling/` | `GET /api/version` value (shape unchanged) | W1-1: the image built with `SLATEOPS_VERSION=1.2.3` reports `1.2.3` at `/api/version`. W1-2: without it, the value is `0.0.0+dev`. W1-3: a tooling test refuses a tag that differs from `pyproject.toml` and `package.json`. | Focused pytest; tooling test; one local image build | — | — |
| W2 | Production env templates and the complete secret set | Backend Engineer | `backend/operations/supabase_keys.py` (complete set, new `--format docker`), new `backend/operations/local_ca.py`, templates in `packaging/engine/templates/` | Env file format becomes literal `KEY=value` | W2-1: one run writes every secret in 6.2 step 4; `Settings`, `ProvisionSettings` and `AdminSettings` load from the result with no missing field. W2-2: a new `--format docker` output has no quotes. Random values come from a safe alphabet. The JSON values (`JWT_KEYS`, `JWT_JWKS`) contain no `$`, `#`, `'` or space. A test reads the file with both env readers, `docker run --env-file` and `docker compose --env-file` (which interpolates unquoted values), and compares every value byte for byte. The current default output stays, because `README.md:86`, `backend/tests/supabase_runtime.py`, `backend/tests/config_support.py` and `tests/tooling/test_environment.py` use it. W2-3: an existing output is never overwritten. W2-4: `local_ca.py` makes a root, a name-constrained intermediate signed by it (the root key is removed after this), and a server certificate of 397 days or less for one host from the intermediate; it renews 30 days before expiry. W2-5: no secret is printed. | Focused pytest under `backend/tests/operations/`, plus `tests/tooling/test_environment.py` | — | — |
| W3 | Release workflow and GHCR | Infrastructure Engineer | `.github/workflows/release.yml`, `tests/tooling/`, the provider image references in `infra/supabase/compose.yaml` (H9), `PROVIDER_IMAGES` in `backend/app/core/config/disposable_instance.py` (a Backend Engineer task in P2), the image table in `infra/supabase/README.md` | New public artifacts; provider image registries (H9) | W3-1: a `v*-rc.*` tag makes a draft release with every asset in 5.2 and `SHA256SUMS`. The release is marked as a pre-release, with the title "Test build, not for customers" (section 5.3). W3-2: both images are `linux/amd64`, public and anonymously pullable by digest, with only the rc version of their release. W3-3: cosign verify passes for the images and the manifest with the workflow identity. W3-4: per-job least-privilege permissions under a `contents: read` default; SHA-pinned Actions. W3-5: the provider image references use the registries that H9 sets, at unchanged digests. The release manifest lists them, and an anonymous pull of each digest passes. `PROVIDER_IMAGES` equals the compose references, and `backend/tests/operations/runner/test_disposable_database_guard.py` passes. The README image table shows the same names. | Tooling tests; one rc tag run; anonymous `docker pull` by digest | Sets the GHCR packages to public once; confirms that the repository stays public; answers H13 before the first rc tag; pushes the first rc tag; pushes no stable tag before the license work merges (section 5.3) | W1 |
| W4 | Our Linux image | Infrastructure Engineer | `packaging/linux-image/` (build script, units, `wsl.conf`), release job step | New artifact | W4-1: a reproducible build from a fixed snapshot date. W4-2: the Docker key fingerprint is checked. W4-3: there is no SSH server and no secret; interop and automount are off; cosign is pinned and in the package list. W4-4: the package list and the source list are produced. W4-5: `wsl --import` of the tarball starts systemd and Docker. | CI build; hands-on import on the owner's PC | — | W3 (wiring) |
| W5a | Engine bridge commands in the server image | Backend Engineer | `backend/operations/` (no new top-level command), `backend/operations/backup_state.py` (`policy_default`) | None beyond W2 | W5a-1: `bootstrap_admin.py` runs non-interactively with `--confirm --name --slug` and the env. W5a-2: one provisioning entry point that the engine calls returns safe JSON. W5a-3: the `policy_default` operation writes the default backup policy only when none exists, through `AuditSession`. | Focused pytest | Approves `policy_default` within H2 | W2 |
| W5b | Engine install, status and email check | Infrastructure Engineer | `packaging/engine/` and its tests | New engine job contract (section 6) | W5b-1: `install` from a fresh Linux with valid answers reaches HTTPS `/api/ready` and sends the invitation. W5b-2: killing it at any step and running it again completes it with no duplicate secret, CA, volume or invitation. W5b-3: `smtp-test` refuses authentication without TLS and reports the error class. W5b-4: no secret appears in any log, in the output, or in `docker compose` output. W5b-5: it uses only the standard library on the host. W5b-6: Caddy (UID 1000) can read the Caddyfile that the engine writes. The backup admission also accepts it, with no owner change around a backup. The admission needs root or the caller as owner, with no group or other access (`packaging/backup/backup_installation.py:183`). One option needs no admission change: the backup runs as UID 1000, which owns the Caddyfile. W5b-7: before the install, the engine checks the app subnet (default `172.31.248.0/28`) against the host and Docker networks. On a collision it picks another private /28 and writes it as `SLATEOPS_APP_PRIVATE_SUBNET`. | Unit tests in `packaging/engine/tests/`; one run on a Linux host with the release images | — | W2, W5a, W4 |
| W6a | TLS and the LAN name | Infrastructure Engineer | `packaging/engine/` (CA step, renewal), `infra/caddy/generate_config.py` (`--trust-root`, the `:80` site), `infra/docker/caddy.Dockerfile`, Avahi unit in `packaging/linux-image/` if F1 needs it | New public port 80 (three trust paths and a redirect) | W6a-1: port 80 serves only the three trust paths and redirects every other path. W6a-2: an iPhone, an Android phone and a second Windows PC trust the site after the trust steps (hands-on). W6a-3: the name from F1 resolves on those devices. W6a-4: the renewal replaces the certificate with no outage longer than a Caddy reload. W6a-5 (F6 hands-on): a valid `<name>.local` server certificate passes, and an `other.local` certificate from the same intermediate fails. Devices: iOS Safari, Android Chrome, Windows Chrome and Edge, Windows PowerShell, and macOS Safari. W6a-6: the CA and the server certificate follow the profile in 6.3. | Caddy generator tests; engine unit tests; hands-on | Phones for the hands-on check; runs W6a-5 | W5b, W6b, F1 |
| W6b | Trust page | Frontend Engineer | `infra/caddy/trust/` (one static HTML file, no script from another origin) | None | W6b-1: the page shows the steps for iOS, Android, Windows and macOS, and the CA fingerprint from a file that the engine writes. W6b-2: it works at 390 px and 1440 px with no network request to another host. | Hands-on in a browser at both widths | — | Product Designer design |
| W7 | Windows plumbing | Infrastructure Engineer | `infra/windows/installer/` (scripts promoted from the kit, the Inno project) | New Windows-side contract (tasks, account, rules) | W7-1: the requirements check shows R1 to R9 with the messages in 4.2. W7-2: Prepare this PC restarts once and resumes at page 4. W7-3: the distribution runs from the chosen data drive. W7-4: `Exec` refuses an unknown job and takes data only on standard input. W7-5: the folder safety check of the kit passes. W7-6: the PC serves the LAN at boot with nobody signed in (E1 and E2 again). | Inno compile in CI; hands-on on the owner's PC | Runs the unsigned build | W4, F3, F4 |
| W8 | Wizard pages and finish | Infrastructure Engineer | `infra/windows/installer/` | None | W8-1: every page in 4.1 with its checks and messages. W8-2: the SMTP password never reaches a log, and with the pipe channel never reaches a Windows disk. W8-5: the recovery key reaches page 11 through the same channel and is never written to a Windows disk or log, except by the person's own Print or Save to a USB drive. W8-3: the finish opens the app on the server PC with no certificate warning. W8-4: the recovery key page requires the check box. | Hands-on; QA Engineer pass | — | W7, W5b, W6a, W6b, W10b, design |
| W9 | Uninstall, keep data, reinstall, maintenance mode | Infrastructure Engineer | `infra/windows/installer/`, engine `prepare-uninstall` and `set-email` | None | W9-1: both answers remove the items in 9.1. W9-2: kept data is reused with the same business, sign-ins and devices trusted. W9-3: a newer kept version blocks with the message. W9-4: Change email account sends a test and recreates `auth`. | Hands-on; QA Engineer pass | — | W8, F3 |
| W10a | Backup fail-open | Backend Engineer | `backend/operations/backup_runner.py`, `backend/operations/backups/`, `infra/supabase/RESTORE.md` | Runner behavior after a failed backup (all installations); no schema or API change | W10a-1: after a forced archive failure, the runner calls `recover_claim` unchanged, the services that ran before run again, and Caddy starts only after readiness. W10a-2: an unready API keeps ingress closed and records the existing `readiness_failed`. W10a-3: at most 3 automatic tries; a refusal (exit 2) keeps the services stopped and is not counted. W10a-4: an interrupted run takes the same path on the next tick. W10a-5: exit codes are unchanged. W10a-6: no failure code, migration or API value changes. | Focused pytest of the runner | — | Software Architect confirms fail-open for the Linux path |
| W10b | Backup scheduler, location and recovery key | Infrastructure Engineer | `packaging/engine/` (`slateops-runner.timer`, drvfs mount, `set-backup-target`, `new-recovery-key`) | None, unless W10b-4 changes the admission check in `backup_installation.py`. That change applies to every installation, Linux included. | W10b-1: the timer runs one runner tick each minute while the distribution runs. W10b-2: a missing USB target gives the existing `backup_failed`, the services come back, and the engine `status` reports `backup_target_missing`. W10b-3: the recovery key opens the repository, and a new key removes the old one. W10b-4: a scheduled backup admits the Caddyfile while Caddy reads it, with no owner change around the backup (W5b-6). If the fix changes the admission in `backup_installation.py`, that part is a Backend Engineer task inside W10b. | Engine unit tests; hands-on with a USB drive | A USB drive for the hands-on check | W6a, W10a, F5 |
| W11 | Update queue API and table | Backend Engineer | `backend/app/systems/manage/backups/` (or a new `updates/` folder; the Software Architect decides), migration, `backend/operations/backup_state.py` (update operations in the existing union) | **New routes, table, column and bridge operations (7.2)** | W11-1: 201 with `Location`. W11-2: 409 `update_active`. W11-3: 409 `update_not_cancellable` after the claim. W11-4: 409 `update_target_stale`. W11-5: 409 `updater_unavailable` when the engine was not seen in 5 minutes. W11-6: 403 for a non-owner, and 404 or 403 per the current rules for others. W11-7: `update_claim` is exclusive under concurrency, under the existing advisory lock. W11-8: `update_close_restored` is admitted only by a valid restore-finalized marker. W11-9: the migration passes `alembic check`. | Focused pytest plus the PostgreSQL integration batch | **Approves the routes, the table, the column and the bridge operations (decision H2)** | Software Architect contract review |
| W12 | "Install tonight" UI | Frontend Engineer | `frontend/src/components/systems/manage/components/updates-panel.tsx`, `domain/updates-rules.ts`, `adapters/backup-api.ts` | None | W12-1: each state in 7.1 renders from the API. W12-2: Cancel works only while queued. W12-3: only the installation owner sees the button, and only while the engine was seen in the last 5 minutes. | Isolated and http Playwright specs; hands-on | — | W11, design |
| W13a | Non-interactive restore for the engine | Backend Engineer | `packaging/backup/restore_installation.py` | A new engine-only mode (owner decision H12) | W13a-1: the mode needs the engine's own snapshot, project and directory, and refuses any other value. It replaces the terminal check at `restore_installation.py:388` only for the engine. W13a-2: the interactive path is unchanged. | Focused tests in `packaging/backup/tests/` | — | — |
| W13b | Update executor and Maintain task | Infrastructure Engineer | `packaging/engine/`, `infra/windows/installer/` (Maintain) | Engine update contract (7.3, 7.4) | W13b-1: a queued run updates `v0.2.0` → `v0.2.1` (decision H8) at the window, and `/api/version` shows `v0.2.1`. W13b-2: a forced migration failure rolls back to the old version with the data intact, keeps the same origin and name, and writes `rolled_back`; the run is never claimed again. W13b-3: a failure forced before step 7 uses `recover`, not a restore. W13b-4: low space gives `insufficient_space` with no outage. W13b-5: with an older WSL installed and `engine_idle` true, Maintain installs the pinned WSL MSI after the SHA-256 check, and the service returns by itself. W13b-6: a manifest with a bad signature is refused. W13b-7: a restart during the window resumes by the rule in section 12 (Windows Update row). W13b-8: the package night runs on a night with no update and leaves the services ready. W13b-9: the rollback starts `<base>-r<n>` on the same Docker daemon with no subnet overlap. The failed project's networks are removed and its volumes kept (7.5 step 1). | Engine unit tests; hands-on on the owner's PC. W13b-1 runs on the stable tags after the license work; the design checks whether the setup program's `update` path proves W13b-2 to W13b-4 on rc tags (section 5.3). | Publishes two stable releases after the license work merges (decision H8, section 5.3) | W9, W3, W11, W13a; the license work for W13b-1 only |
| W14 | Release rehearsal on Windows | QA Engineer, with the owner | No code | None | W14-1: fresh install → invitation → sign-in on the PC and a phone. W14-2: update between the two stable releases. W14-3: forced rollback. W14-4: uninstall with Keep my data, then reinstall. W14-5: uninstall with Delete everything. W14-6: E1, E2 and E4 again. W14-7 (when the license work gives a license path for release builds): a licensed installation keeps its edition after the update and after the rollback. | Hands-on, each step recorded | Runs the rehearsal | All, and the license work |
| W15 | Documentation | Infrastructure Engineer | `README.md`, `infra/AGENTS.md`, `infra/supabase/README.md`, `RESTORE.md`, `docs/architecture/11-infrastructure.md`, `docs/architecture/12-deployment-architecture.md`, the glossary | Documented contracts only | W15-1: Windows is documented as Docker Engine in our distribution, not Docker Desktop. W15-2: new glossary rows: installer, engine, engine bundle, release manifest, maintenance mode, recovery key, trust page, edition, license file, test build. W15-3: no document calls the infrastructure production-ready. | Scope review | — | W14 (the glossary waits for the open glossary edits) |

Repository testing rules apply to every slice: focused tests and one batch per work unit, then fast checks before a push; CI runs the heavy suites. Windows behavior is proved only by a hands-on run on the owner's Windows 11 Pro PC. Linux-container evidence from macOS does not prove Windows behavior.

**Data size.** No slice or rehearsal step uses a sample pack. The sample packs are larger than the Desk limits (DEC-0029 Impact). A step with more data than the Desk limits allow needs a license from the license work. Examples are a sample pack, or more than 2 seats. The test license of the license work uses a test key that production builds refuse. So W13b and W14, which run on release builds, keep their data within the Desk limits, unless the license work gives another path.

### 11.1 Reviews and other roles per slice

The standard order (company delegation policy, section 4) adds these steps. "SA" is the Software Architect.

| Slice | Before the build | After the build |
|---|---|---|
| S1 | — | SA code review (kit payload option) |
| F-spikes | — | — |
| W1, W5a | — | SA code review |
| W2 | SA contract review (env format, secret list) | SA code review; Security Engineer |
| W3, W4, W13a | — | SA code review; Security Engineer |
| W5b | — | SA code review; Security Engineer |
| W6a | SA review of the CA design after the 6.3 profile; hands-on in W6a-5 | SA code review; Security Engineer (port 80, CA); QA Engineer (devices) |
| W6b | Product Designer | Product Designer screen review; SA code review |
| W7 | Product Designer copy for pages 3 and 4 | SA code review; Security Engineer (account, tasks, rules, ACLs, allow-list) |
| W8 | Product Designer (pages 5 to 12) | Product Designer screen review; SA code review; Security Engineer (secret channel); QA Engineer |
| W9 | Product Designer (uninstall page, maintenance mode) | Product Designer screen review; SA code review; QA Engineer |
| W10a | SA confirms fail-open for the Linux path | SA code review; Security Engineer |
| W10b | Product Designer (page 7 copy, done inside W8's design) | SA code review; Security Engineer (drvfs scope, and the backup admission check if W10b-4 changes it); QA Engineer |
| W11 | Owner approval (H2); SA contract review | SA code review; Security Engineer (authorization); QA Engineer |
| W12 | Product Designer | Product Designer screen review; SA code review; QA Engineer |
| W13b | — | SA code review; Security Engineer (signature check, Maintain task, the same-origin rollback exception); QA Engineer |
| W14 | — | Security Engineer release review |
| W15 | — | SA review |

## 12. Risks

| Risk | Mitigation |
|---|---|
| Smart App Control blocks the unsigned installer; SmartScreen warns. | Only the owner's PCs run it (DEC-0028). The code-signing certificate is bought before the first customer install (decision H1). |
| Microsoft 365 turns Basic SMTP AUTH off by default at the end of December 2026 (an admin can turn it back on); Gmail revokes app passwords on a password change. | Clear messages on page 6; "Change email account" in the maintenance mode; the company relay comes in a later version. |
| The memory of a 16 GB PC is too small for Windows plus the stack. | S1 measures it before the wizard is final; R4 blocks a smaller PC. |
| Windows Update installs a newer WSL outside our window and stops the VM (F7: very likely). | The boot task reattaches (E6, about 2.5 min). Maintain never downgrades. The engine accepts a newer WSL unless a known-bad list names it (7.4). |
| A Windows Update restart falls in the 02:00 window, during a backup or an update. | At the next boot or distribution start the engine finds the open journal and resumes by one rule: if the backup did not complete, or no container runs on a target image yet, it runs `recover` (old images); from the first container on a target image, it rolls back by restore (7.5). The backup runner's own interrupted runs use 8.1, condition 3. |
| The VHD grows and does not shrink. | `defaultVhdSize` is set from the free space; System health shows the disk use (later). |
| One PC holds the data and the backups if the person keeps the default. | Page 7 shows a warning and needs a check box; the recovery key protects the backup if the disk is lost. |
| mDNS fails across subnets or on guest Wi-Fi with client isolation. | The requirements check needs a Private network. The trust page lists the cause. A DNS name from the later installation service removes the limit. |
| The trust page on HTTP can be changed by an attacker on the LAN. | The fingerprint shows on the server PC; Security Engineer review in W6a. |
| Docker Hub limits anonymous pulls: 100 per window for each public IP address, shared by every PC behind the office address. | Default H9 a): 7 provider images come from the publishers' GHCR; only Envoy comes from Docker Hub, with no pull limit while its Sponsored Open Source status is renewed (F8, closed). |
| The default app subnet `172.31.248.0/28` collides with a host or Docker network (seen on macOS in P1, TASK-0074). | The engine checks for a collision before the install and picks another private /28 (W5b-7). `infra/supabase/README.md:132` already allows an override; the engine sets it at install time, not at startup. |
| Caddy (UID 1000) cannot read a Caddyfile that the backup admission accepts (`backup_installation.py:183`; reproduced in P1, TASK-0074). | W5b-6 and W10b-4 need a real fix. The P1 owner swap around each backup is a test workaround only. |
| The engine runs as root with the Docker socket. | It accepts only allow-listed jobs and JSON input. Interop and automount are off. The Security Engineer reviews W5b and W13b. |
| A customer installs a release without the edition limits and loses access in a later update (DEC-0029 item 13). | Before the license work, only rc pre-releases marked "Test build" exist. The website never links them. The first stable tag comes after the license work (section 5.3, H13). |
| The license work starts late, so the first public download waits. | P1 to P8 do not wait for it. Only the stable tags, W13b-1, W14 and W15 wait (section 5.3). |
| A `RESTORE.md` restore into a new project on the same Docker daemon reuses `SLATEOPS_APP_PRIVATE_SUBNET`. Docker refuses the overlapping network while the source project's networks exist. This gap exists today. | The engine rollback removes the old networks first (7.5 step 1, W13b-9). For the support restore, W15 adds the same step, or a different /28 for the target, to `RESTORE.md`. |
| A rollback revokes every session. | The Updates page says so; it happens only after a failed update. |
| The data disk is not encrypted unless BitLocker is on. | Noted on the requirements page as a recommendation (decision H5 can make it a requirement). |

## 13. Decisions for the owner

| ID | Decision | Options (default first) | Blocks |
|---|---|---|---|
| H1 | Code signing | a) Unsigned until the first customer install (DEC-0028). | Nothing now |
| H2 | The update contract in 7.2 | a) Approve exactly: the routes `POST /api/updates`, `GET /api/updates` and `POST /api/updates/{id}/cancel`; the `update_runs` table; the engine-presence column `update_statuses.updater_seen_at`; and the `backup_state.py` operations `update_claim`, `update_inspect`, `update_progress`, `update_outcome`, `updater_heartbeat`, `update_close_restored` and `policy_default`. b) Change it. | W5a (`policy_default`), W11, W12, W13b |
| H3 | The two secret exceptions in 3.2 (SMTP password in, recovery key out) | a) Accept, after the Security Engineer's review. b) No recovery key: a lost disk then means lost backups. | W8, W10b |
| H4 | GPL source offer for the Linux image | a) Attach the Debian source packages to each release (about 1 to 2 GB of release storage; assumption). b) Links to `snapshot.debian.org` only. A link alone may not meet the GPLv2 written-offer duty for commercial copies, so a legal check is advised. | W3, W4 |
| H5 | Windows 11 Home and BitLocker | a) Block Home until it is tested; recommend BitLocker. b) Allow Home with a warning. c) Require BitLocker. | W7 |
| H6 | Alert channel for a failed backup or update | a) In-app only in v1 (System health, Manage). b) Add an application mailer (a new capability). | W10a, W10b |
| H7 | Restore in v1 | a) Support-run with the one-command engine restore. b) Owner-started restore in the maintenance mode in v1. | W13a scope |
| H8 | Update rehearsal releases | a) After the license work merges, publish two stable releases (for example `v0.2.0` and `v0.2.1`) that contain it, for W13b and W14. The website links neither until W14 passes. This keeps DEC-0029 item 13. But the stable tags, W13b-1, W14 and W15 wait for the license work, which waits for the owner's start. P8 merges without it. b) Publish two stable releases before the license work, only for the rehearsal, then delete them. This removes the wait, but it breaks DEC-0029 item 13 for that time. Anyone can install a stable build without the edition limits, and the first becomes "Latest". It needs a change of DEC-0029. A configurable release source is not offered. | W13b, W14 |
| H9 | Provider image source (F8 closed, TASK-0075) | a) Pull the 6 Supabase images from `ghcr.io/supabase/*` and imgproxy from `ghcr.io/imgproxy/imgproxy`, at the same pinned digests (checked: identical). Pull Envoy from Docker Hub, which has no pull limit while its Sponsored Open Source status is renewed (yearly). We redistribute nothing, and none of the 7 counts against a Docker Hub limit. `PROVIDER_IMAGES` in `disposable_instance.py` and the image table in `infra/supabase/README.md` change with the compose references (W3). GitHub states no anonymous pull limit for GHCR. b) Docker Hub, as now. This keeps the current files, but it allows 100 pulls per window for each public IP address. Every PC behind the office address shares that count, and one install uses about 7 counted pulls. c) Mirror the images to our GHCR. This puts every image under our control, but we then redistribute them: the Apache NOTICE duties and the GPLv2 source duties, like H4. | W3 (W3 changes the image references in `infra/supabase/compose.yaml`, which development also uses) |
| H10 | A second public listener on port 80 for the trust page | a) Approve: Caddy serves only `/trust`, the root certificate and the iOS profile on port 80 and redirects every other path to HTTPS. `infra/supabase/README.md:136` names 443 as the only public listener today, so this changes a documented contract. b) No port 80: phones get the trust files another way (for example from the server PC by USB or email). | W6a |
| H11 | The `release-manifest.json` format | a) Approve the fields in 5.2, including the known-bad WSL versions (proposed, 7.4), as a public format that the engine and the installer read; a change after v1 keeps old fields readable. b) Change it. | W3, W13b |
| H12 | The non-interactive restore mode | a) Approve an engine-only mode in `restore_installation.py` that the engine's own snapshot, project and directory bind (7.5, W13a). Today `--execute` needs an interactive terminal (`restore_installation.py:388`). b) No such mode: a failed update then needs a support person for the rollback. | W13a, W13b |
| H13 | Test-build pre-releases before the license work (section 5.3) | a) Accept: rc pre-releases titled "Test build, not for customers", never "Latest", not linked by the website or the README, with public rc images. Each one is listed publicly as a pre-release on the Releases page, and the GHCR packages are listed on the Packages page. The owner counts them as not a public release under DEC-0029 item 13. b) No published release before the license work. This removes every public artifact. But every hands-on proof from P2 on waits for the license work: W3, W4-5, W6a and W7 to W10b. c) Make the repository and the packages private until the first public download. This removes public access. But the anonymous download (5.2), the anonymous image pull (R8) and the update check (`backup_runner.py`) then fail. The owner's PCs then need a stored credential, with a new design and a Security Engineer review. | W3, P2 to P7 hands-on runs |
