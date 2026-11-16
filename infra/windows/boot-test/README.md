# WSL2 boot-test kit

This kit answers one question with evidence:

> Can WSL2, with Docker Engine in our own imported Linux distribution, serve the office network at boot with nobody signed in, and keep serving through restarts, power cuts, sign-outs, idle time and WSL updates?

The kit is a test, not the product. It runs a small test stack (PostgreSQL, a heartbeat writer and a small web service) instead of Slate Operations. Its setup steps model the steps of a future Windows installer.

Status: the scripts have never run on Windows. The first run on the test PC is the first execution. Treat every result as unverified until that run.

Tested target: Windows 11 Pro, build 22621 (22H2) or later. Not tested: Windows 11 Home, Windows 10.

## Contents

| File | Purpose |
|---|---|
| `00-precheck.ps1` | Checks the PC. Changes nothing. |
| `10-setup.ps1` | Sets up WSL, the service account, the distribution, Docker, the boot task and the firewall rules. |
| `20-status.ps1` | Shows the tasks, the firewall rules, the test service, the distribution and the event log. |
| `90-cleanup.ps1` | Removes everything that setup added. Keeps WSL unless you use `-RemoveWsl`. |
| `lib/common.ps1` | Shared settings, pinned versions, checksums and helpers. |
| `lib/svc-exec.ps1` | Runs one allow-listed job (`prepare`, `status`, `unregister`) as the service account. |
| `lib/start-distro.ps1` | The action of the boot task. Starts the distribution and keeps it attached. |
| `linux/` | Scripts that run inside the distribution, and the test stack (`payload/compose.yaml`). |

Every PowerShell script supports `-WhatIf`. With `-WhatIf`, a script shows each change and makes none. It also writes no log file. Every script stops at the first error. Logs go to `C:\ProgramData\SlateOpsBootTest\logs` (administrators only). The precheck writes its log to your `%TEMP%` folder, so it creates nothing under `C:\ProgramData`. Jobs that run as the service account write to `C:\ProgramData\SlateOpsBootTest\svc-out`.

## What the kit changes on the PC

| Change | Why | Cleanup |
|---|---|---|
| Windows feature `VirtualMachinePlatform` on | WSL2 needs it. One restart. | Stays on. `-RemoveWsl` turns it off if setup turned it on. |
| WSL 3.0.3 from the offline MSI | Pinned version, SHA-256 checked. It is one stable release behind the newest (3.0.5), so event E6 has a real update to install. | Stays. `-RemoveWsl` uninstalls it, but only if WSL was absent before setup. |
| Local account `slateops-svc` (standard user) | The distribution runs as this account, not as you. | Account, profile and rights removed. |
| User rights of `slateops-svc` | "Log on as a batch job"; deny local, Remote Desktop and network sign-in (not with `-NoDenyRights`). | Removed. |
| Sign-in screen entry hidden | The account does not show on the sign-in screen. | Removed. |
| Distribution `SlateOpsBootTest` (Debian 13) | Our own imported distribution. | Unregistered. Its virtual disk is deleted. |
| Scheduled tasks `\SlateOpsBootTest\Start` and `\SlateOpsBootTest\Exec` | Start at boot; run jobs as the account. | Deleted. |
| Firewall rule `SlateOpsBootTest-TCP-8443` | Inbound TCP 8443, Private profile, local subnet only. | Deleted. |
| Hyper-V firewall rule `SlateOpsBootTest-HyperV-TCP-8443` | Inbound TCP 8443 to the WSL VM, Private profile, LAN only. | Deleted. |
| Sleep and Hibernate on mains power set to Never | A sleeping PC cannot serve the network. | Old values restored. |
| Task Scheduler event log on | `20-status.ps1` shows when the boot task started. | Old state restored. |
| Folder `C:\ProgramData\SlateOpsBootTest` | Kit copy, downloads, distribution disk, state, logs, service account output. Only Administrators and SYSTEM have access, plus the service account where it needs it. | Deleted. Logs stay unless you use `-RemoveLogs`. |

The kit does not change your own account, your own WSL distributions, your own `.wslconfig`, your network profile type or Fast Startup.

## Before you start

You need:

- The PC on mains power for the whole test, connected to the office or home network, with internet access. On a laptop, keep the lid open and keep it on mains power.
- A phone or a second PC on the same network.
- A stopwatch (the phone clock app is sufficient).
- About 30 minutes for setup, plus about 6 days for all events.

Get the kit:

1. Download the repository ZIP from the GitHub branch `feat/windows-boot-test`.
2. Extract the ZIP.
3. Open the folder `infra\windows\boot-test` in the extracted files.

Open an administrator PowerShell window in that folder:

1. Click Start and type `powershell`.
2. Right-click "Windows PowerShell" and click "Run as administrator".
3. Type `Set-Location "<the boot-test folder>"` and press Enter.
4. Type `Get-ChildItem -Recurse | Unblock-File` and press Enter. This removes the "downloaded from the internet" mark from the kit files.

Run each script with this command form. It allows the script for this one run only. It does not change the execution policy of the PC.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\00-precheck.ps1
```

## Setup

1. Run `00-precheck.ps1`. Read each FAIL and WARN line.
2. If a line says FAIL, correct the cause and run the precheck again. Typical causes:
   - Virtualization is off: turn on Intel VT-x or AMD-V/SVM in the UEFI/BIOS settings.
   - The network is "Public": set it to "Private" in Settings > Network & internet > (your network).
   - The network is a company domain network: the kit is not tested there. Use a home or office network that Windows marks "Private".
   - PowerShell module logging covers `ScheduledTasks`: this group policy would record the service account password. Ask whoever manages the PC to turn it off for the test.
   - `C:\ProgramData\SlateOpsBootTest` fails the safety check: delete the folder (or run `90-cleanup.ps1`), then run the precheck again.
3. Quit Docker Desktop if it is installed.
4. Run `10-setup.ps1`.
5. If setup tells you to restart, save your work, restart the PC and sign in. Setup opens again in a new window and continues.
6. Wait until setup shows "Setup is complete" and the status URL, for example `http://192.168.1.23:8443/`.
7. Write the status URL in the results file.

If setup shows a WARN line that this PC cannot read `http://127.0.0.1:8443/`, setup is still complete. Open the status URL on another device. If it answers, continue. If it does not, see Troubleshooting.

Setup takes about 15 to 30 minutes. Most of the time goes to the downloads and the Docker installation inside the distribution.

To see each change before you make it, run `10-setup.ps1 -WhatIf` first.

## Check the service

You check the service in three ways:

| Check | How | What it proves |
|---|---|---|
| From another device (the real test) | Open the status URL in a phone browser, or run `curl http://<PC address>:8443/` on another PC. | The office network reaches the service. |
| From this PC | Run `20-status.ps1`. It reads `http://127.0.0.1:8443/`. | The service runs. It does not prove LAN access. If this PC cannot read the URL, the script shows WARN (exit code 2), not a failure: the check from another device decides. |
| Inside the distribution | `20-status.ps1` runs the read-only job `status` as `slateops-svc`. | WSL, systemd, Docker, the containers and mirrored networking run. The script also shows that this job did not change `attach_number` or `linux_boot_id`. |

This PC cannot reach its own LAN address through WSL mirrored networking. Always do the LAN check from another device.

The status URL returns a small JSON document. Read these fields:

| Field | Meaning |
|---|---|
| `fresh` | `true` when a heartbeat was written in the last 150 seconds, in the current Linux boot. |
| `status.heartbeat_count` | Number of heartbeat rows in PostgreSQL. One row each minute. Rows are never deleted. |
| `status.first_heartbeat` | Time of the first row. It must never change. |
| `status.last_heartbeat` | Time of the last row (UTC). |
| `status.largest_gap_seconds` | The longest time between two rows. |
| `status.gaps_over_120s` | Number of gaps longer than 120 seconds (outages). |
| `status.linux_boot_id` | Changes each time the WSL VM starts. |
| `status.windows.windows_boot_type_name` | "cold boot", "hybrid boot (Fast Startup)" or "resume from hibernation", from the Kernel-Boot event 27 value 0, 1 or 2. The kit takes this mapping from common usage; no Microsoft page confirms it, so it is a note, not a pass condition. |
| `status.windows.attach_number` | How many times the boot task attached to the distribution since Windows started. |

All times are UTC.

## Test protocol

### Pass conditions

"Ready" means: the status URL answers on another LAN device with `"fresh":true`.

Each event passes when all of these are true:

- **P1 Ready time.** The service is ready within 5 minutes after power-on (or after the event ends, for events without a restart; for E9, after the sign-in screen appears). Measure the time with the stopwatch and record it.
- **P2 Heartbeat resumes.** Read the URL two times, 2 minutes apart. `heartbeat_count` increases between the two reads.
- **P3 Data kept.** `first_heartbeat` is the same as in the baseline, and `heartbeat_count` is not smaller than the value that you read just before the event.

Some events have one more pass condition. The event says it.

Do not sign in to the PC during an event unless the event tells you to.

### Before E1: keep the PC address the same

The status URL holds the PC address. If the router gives the PC a different address after a restart, the old URL stops working, and the event looks failed. Reserve the address in the router (a "DHCP reservation") before E1.

1. In PowerShell, type `Get-NetAdapter | Where-Object Status -eq Up | Format-Table Name, MacAddress` and press Enter. Record the MAC address of the adapter that setup used (the precheck shows its name).
2. Open the router administration page in a browser. Its address is usually the default gateway: type `ipconfig` and read "Default Gateway", for example `192.168.1.1`.
3. Sign in to the router. Find the DHCP settings. Typical names: "DHCP reservation", "Address reservation", "Static lease" or "Fixed IP".
4. Add a reservation: the MAC address from step 1 and the PC address in the status URL.
5. Save the setting.

If your router has no reservation setting, record that in the notes. After each restart, check the PC address in the router client list before you decide that an event failed.

### Baseline

1. Wait 10 minutes after setup is complete.
2. Open the status URL on the phone.
3. Make sure that `fresh` is `true`.
4. Record `first_heartbeat`, `heartbeat_count` and `gaps_over_120s` in the results file as the baseline.

Before each event, open the status URL and record `heartbeat_count` and `gaps_over_120s` in the "before" columns.

### E1: Cold boot, nobody signs in

1. In the administrator PowerShell window, type `shutdown /s /t 0` and press Enter. This is a full shutdown, not a Fast Startup shutdown.
2. Wait until the PC is off. Then wait 30 more seconds.
3. Press the power button and start the stopwatch at the same time.
4. Do not sign in.
5. Refresh the status URL on the phone every 30 seconds until `fresh` is `true`.
6. Stop the stopwatch. Record the time.
7. Do the P2 and P3 checks.

Record in the notes: `status.windows.windows_boot_type_name` (expected "cold boot").

### E2: Restart (as Windows Update does), nobody signs in

1. Type `shutdown /r /t 0` and press Enter. Start the stopwatch.
2. Do not sign in.
3. Refresh the status URL every 30 seconds until `fresh` is `true`. Record the time.
4. Do the P2 and P3 checks.

Extra pass condition: `status.linux_boot_id` is different from the value before the restart.

### E3: Power cut, then power on

> **Caution:** A power cut can cause loss of data in open files. It can also damage the file systems of the PC. Before you cut the power, save your work, close all programs, and make sure that you have a backup of your own files.

1. Make sure that the status URL shows `fresh` is `true`. Record `heartbeat_count`.
2. Close all programs. Sign out.
3. Cut the power at the wall socket, or disconnect the power cable. On a laptop, hold the power button for 10 seconds instead (a laptop battery keeps it on).
4. Wait 30 seconds.
5. Connect the power. Press the power button if the PC does not start by itself. Start the stopwatch.
6. Do not sign in.
7. Refresh the status URL every 30 seconds until `fresh` is `true`. Record the time.
8. Do the P2 and P3 checks.

Extra pass condition: `status.postgres_started_at` is after the power-on time, and the URL keeps answering for 10 minutes. PostgreSQL uses data checksums, so a damaged data page stops the heartbeat, and the check fails.

### E4: You sign in and sign out

1. Sign in to the PC with your own account.
2. Wait 5 minutes. Open the status URL on the phone while you are signed in. Make sure that `fresh` is `true`.
3. Sign out (Start > your account > Sign out).
4. Wait 5 minutes. Open the status URL.
5. Do the P2 and P3 checks.

Extra pass condition: `gaps_over_120s` did not increase.

### E5: Shut down with Fast Startup, then power on

This event needs Fast Startup on. The precheck shows the setting. If Fast Startup is off, write "not applicable: Fast Startup off" in the results and go to E6. The kit does not change this setting.

1. Click Start > Power > Shut down. Do not hold Shift.
2. Wait until the PC is off. Then wait 30 more seconds.
3. Press the power button and start the stopwatch.
4. Do not sign in.
5. Refresh the status URL every 30 seconds until `fresh` is `true`. Record the time.
6. Do the P2 and P3 checks.

Record in the notes: `status.windows.windows_boot_type_name` (expected "hybrid boot (Fast Startup)"). If it shows "cold boot", Windows did a full boot.

### E6: WSL update while the service runs

Setup installs WSL 3.0.3 on purpose, one stable release behind the newest stable release (3.0.5 on 2026-11-03). So `wsl --update` has a real update to install.

1. Sign in. Open an administrator PowerShell window.
2. Type `wsl --version` and press Enter. Record the WSL version (expected 3.0.3).
3. Type `wsl --update` and press Enter. Start the stopwatch when the command ends.
4. If the command says that no update is available, record "not run: no update available" and stop this event. Do not use `--pre-release`: it can leave a pre-release version installed.
5. Refresh the status URL every 30 seconds until `fresh` is `true`. Record the time.
6. Type `wsl --version` again. Record the new version.
7. Sign out. Do the P2 and P3 checks.

Note: after this event, WSL is newer than the pinned 3.0.3. Record both versions.

### E7: Idle for 4 days, nobody signs in

The Task Scheduler stops a task after 72 hours by default. The boot task has no time limit. This event proves that it keeps running after 72 hours.

Windows Update can restart the PC during E7 and E8. That restart is a different event (E9). Pause updates for E7 and E8, and do E9 after them.

1. Click Settings > Windows Update > Pause updates, and select "Pause for 1 week". This covers E7 and E8.
2. Record `gaps_over_120s` and the date and time.
3. Do not sign in for at least 4 days (96 hours).
4. Open the status URL on the phone one time each day. Record `fresh` and `heartbeat_count` in the notes.
5. After 4 days, open the status URL. Do the P2 and P3 checks.
6. Sign in and run `20-status.ps1`. Make sure that the task `\SlateOpsBootTest\Start` shows state "Running".

Extra pass condition: `gaps_over_120s` did not increase during the 4 days. If it did, look at the event log part of `20-status.ps1`. If a restart (event 1074 or 12) explains the gap, record the gap and the restart separately in the notes: the pause did not hold.

### E8: You use the PC normally for one day

Keep Windows Update paused (see E7).

1. Sign in and use the PC for normal work for one day.
2. At the end of the day, sign out or leave the PC signed in, as you usually do.
3. Open the status URL. Do the P2 and P3 checks.
4. Click Settings > Windows Update > Resume updates.

Extra pass condition: `gaps_over_120s` did not increase during the day. Record a gap that a restart (event 1074 or 12) explains separately, as in E7.

### E9: A real Windows Update restart

Do this event after E7 and E8, when updates are resumed, and only when Windows installs an update that needs a restart. Do not force an update.

The "Working on updates" stage of a restart can take many minutes. That time belongs to Windows, not to the kit. So you measure it separately, and P1 starts when the sign-in screen appears.

1. When Windows asks for a restart, record the date and the update name (Settings > Windows Update > Update history).
2. Let Windows restart. Start the stopwatch when the screen goes off.
3. When the sign-in screen appears, read the stopwatch. Record it in the notes as "update stage" (screen off to sign-in screen). Then reset the stopwatch and start it again.
4. Do not sign in.
5. Refresh the status URL every 30 seconds until `fresh` is `true`. Stop the stopwatch. Record this time as the time to ready (P1 counts from the sign-in screen).
6. Do the P2 and P3 checks.

Limit: Windows can sign you in automatically after an update restart, to finish the update (the setting "Use my sign-in info to automatically finish setting up after an update"). Then somebody is signed in during this event. After the event, sign in and run `20-status.ps1`. A Winlogon event 7001 before your own sign-in means that Windows signed you in automatically. Record it in the notes.

If no update arrives during the test, write "not run: no update" in the results.

### After each event

1. Sign in.
2. Run `20-status.ps1`.
3. Copy its log file name (shown at the end) into the notes of the event.
4. Sign out, unless the next event needs you signed in.

## Results template

Keep the results outside the repository (for example, in a note or a spreadsheet). The repository holds no test results. Copy this table.

Status URL: `http://<PC address>:8443/`. PC: Windows 11 Pro, version `____`, build `____`. WSL version: `____`. Fast Startup: on / off.

Baseline: `first_heartbeat` = `____`, `heartbeat_count` = `____`, `gaps_over_120s` = `____`, date `____`.

| Event | Date | Time to ready (mm:ss) | `heartbeat_count` before / after | `first_heartbeat` same (yes/no) | `gaps_over_120s` before / after | Extra condition (yes/no) | Pass / Fail | Notes |
|---|---|---|---|---|---|---|---|---|
| E1 Cold boot, no sign-in | | | / | | / | | | |
| E2 Restart, no sign-in | | | / | | / | | | |
| E3 Power cut | | | / | | / | | | |
| E4 Sign in and sign out | | n/a | / | | / | | | |
| E5 Fast Startup shutdown | | | / | | / | | | |
| E6 `wsl --update` | | | / | | / | | | |
| E7 Idle 4 days | | n/a | / | | / | | | |
| E8 Normal use for a day | | n/a | / | | / | | | |
| E9 Windows Update restart | | | / | | / | | | |

## Cleanup

> **Caution:** Cleanup deletes the test distribution and its database. The test data is lost. Record your results first.

> **Caution:** `-RemoveWsl` removes WSL for every account on the PC, yours too. Use it only if you do not use WSL yourself. Cleanup removes WSL only if WSL was absent before setup; otherwise it keeps WSL and says so.

1. Open an administrator PowerShell window in the kit folder.
2. Run `90-cleanup.ps1 -WhatIf` to see what cleanup removes.
3. Run `90-cleanup.ps1`.
4. Read the list. Type `REMOVE` and press Enter.

The logs stay in `C:\ProgramData\SlateOpsBootTest\logs`. To delete them too, run `90-cleanup.ps1 -RemoveLogs`.

## Troubleshooting

| Symptom | Do this |
|---|---|
| Setup stops in the job "prepare" | Read `C:\ProgramData\SlateOpsBootTest\svc-out\svc-exec-prepare.log`. Correct the cause and run setup again. Setup continues from where it stopped. |
| Setup shows WARN: this PC cannot read `http://127.0.0.1:8443/` | Setup is complete. Open the status URL on another device. If it answers, continue with the test and record the WARN in the notes. If it does not answer, run `20-status.ps1` and read the part "Inside the distribution". |
| Setup or the precheck says the folder fails the safety check | Something in `C:\ProgramData\SlateOpsBootTest` has an unexpected owner, access entry or junction. Run `90-cleanup.ps1` (or delete the folder), then run setup again. Record the message. |
| `20-status.ps1` passes, but the phone gets no answer | 1) Make sure that the phone uses the same network (not mobile data). 2) Make sure that the network is still "Private". 3) Run setup again with `-WebNetwork host` (see the next section). Record this in the notes: it is a finding. |
| The status job says "Distribution is NOT running" | Record the event as failed. To start the service again, run `Start-ScheduledTask -TaskPath '\SlateOpsBootTest\' -TaskName 'Start'`. |
| The task shows last result `0x8007052F` or `0x80070569` | The account cannot sign in for the task. Record the code. Run setup again: it sets a new password and gives the rights again. If the code stays, run `10-setup.ps1 -NoDenyRights`: setup then gives only "Log on as a batch job" and removes the deny sign-in rights. Record this as a finding: a deny right blocks the task. |
| The status URL stopped answering after a restart, and `20-status.ps1` passes | The PC probably got a new address. Type `ipconfig` and compare the address with the status URL. Use the new address, record the change, and set a DHCP reservation (see "Before E1"). If the new address is in a different network, run setup again: the Hyper-V rule holds the old network. |
| `fresh` is `false` and `same_linux_boot` is `false` | The service answers, but the heartbeat of this boot is not written yet. Wait 2 minutes. If it stays `false`, run `20-status.ps1`. |

## Design notes

### How setup works

| Question | Answer |
|---|---|
| Why the offline MSI, not `wsl --install --no-distribution`? | The MSI is pinned and checked with its SHA-256 (the GitHub release asset digest), and setup checks the hash again right before `msiexec`. `wsl --install` installs the latest version, which changes between runs. An installer can ship the same MSI. |
| Why WSL 3.0.3, not the newest? | 3.0.3 (stable, 2026-10-09) is one stable release behind the newest stable release, 3.0.5 (2026-11-03). Event E6 needs an update to install. 3.0.3 is above 2.5.4, which `instanceIdleTimeout` needs. |
| How is the kit folder protected? | `C:\ProgramData` lets every user create folders. Setup creates `C:\ProgramData\SlateOpsBootTest` in one call with an access list for Administrators and SYSTEM only. If the folder exists, setup stops unless the folder and everything in it pass a safety check: owners, access entries, and no junctions or links. The service account can write only to `svc-out` and `distro`; the administrator side only reads `svc-out`. Cleanup deletes without following junctions, and it ignores `state.json` if the folder fails the check. |
| How does the password stay out of logs? | Setup builds the password as a SecureString one character at a time. Only `Register-ScheduledTask` receives it as plain text. PowerShell module logging records command parameters, so setup and the precheck stop when module logging covers the `ScheduledTasks` module. Script block logging and transcription do not record it. |
| Which Windows feature? | `VirtualMachinePlatform` only. WSL2 does not need the WSL 1 feature (`wsl --install` adds it only with `--enable-wsl1`). |
| Where does Debian come from? | The Debian 13 (trixie) WSL image v1.26.0.0, built by the Debian WSL team on salsa.debian.org. Its URL and SHA-256 come from Microsoft's WSL distribution manifest (`distributions/DistributionInfo.json` in github.com/microsoft/WSL). Setup and the job "prepare" both check the SHA-256. |
| How does setup run commands as `slateops-svc`? | Setup writes the job name and a random request ID to `state\request.txt` (only administrators can write there). It starts the on-demand task `\SlateOpsBootTest\Exec`, which runs `lib\svc-exec.ps1` as the account. The job writes its log and a result file with the request ID. Setup polls for that result, shows the job log, and stops on a non-zero exit code. |
| Why does the account need its own `.wslconfig`? | WSL distributions and `.wslconfig` are per user. The distribution is registered in the account's registry hive, and its settings are in `C:\Users\slateops-svc\.wslconfig`. |
| How is the Docker key checked? | `setup-docker.sh` downloads the key and stops unless it holds one primary key with the fingerprint `9DC8 5822 9FC7 DD38 854A E2D8 8D81 803C 0EBF CD88`. Docker's convenience script is not used. |

### The service account

| Setting | Why |
|---|---|
| Standard user, member of Users only | It needs no administrator rights. |
| Random 32-character password | Generated in memory and given only to Task Scheduler. It is never written to a file, a log or the screen. A new setup run sets a new password. |
| "Log on as a batch job" (`SeBatchLogonRight`) | Task Scheduler needs it to run a task "whether the user is logged on or not". A standard account does not have it by default. Setup gives it through the Local Security Authority API. |
| Deny local, Remote Desktop and network sign-in | Nobody can sign in with the account. A batch logon (Task Scheduler) is a different logon type, so the tasks should still run. If the first run shows a logon error, run setup again with `-NoDenyRights` and record it: this choice is then wrong. |
| Hidden from the sign-in screen | The account is not offered at sign-in. |

### `.wslconfig` of the account

| Setting | Why |
|---|---|
| `vmIdleTimeout=-1` | The WSL VM does not stop when idle (Windows 11 only). |
| `[general] instanceIdleTimeout=-1` | The distribution does not stop when idle (WSL 2.5.4 or later). Both settings are needed. |
| `memory=6GB` | A fixed limit. The default is 50% of the PC memory. Change it with `-WslMemoryGB`. |
| `networkingMode=mirrored` | The LAN reaches the WSL VM on the PC address. NAT mode changes the VM address at each restart. The jobs "prepare" and "status" check the mode inside the distribution (`wslinfo --networking-mode`); "prepare" stops unless it is `mirrored`. |
| `defaultVhdSize=64GB` | A limit for the distribution disk (the default is 1 TB). The job "prepare" shows the real size (`df -h /`). |

### The boot task `\SlateOpsBootTest\Start`

| Setting | Why |
|---|---|
| Trigger "At startup" | Starts before anyone signs in. |
| Repetition every 1 minute | Starts the task again within a minute if it stopped. "Do not start a new instance" makes the repetition do nothing while the task runs. |
| Run whether user is logged on or not (password logon) | Runs in session 0, with no interactive user. WSL works from session 0 since WSL 2.0.0. |
| `ExecutionTimeLimit` `PT0S` | No time limit. The default stops a task after 72 hours. |
| Restart on failure: every 1 minute, 999 times | Task Scheduler tries again if the start fails. |
| Battery settings off | A laptop on battery does not block or stop the task. |
| Start when available | A missed start runs as soon as possible. |
| Priority 4 | Normal priority. The default (7) is below normal. |
| Action: `lib\start-distro.ps1` | Starts the distribution and keeps `keepalive.sh` attached, so WSL does not stop it. systemd services alone do not keep WSL running. If `wsl.exe` ends, the script attaches again after 30 seconds. Its log is `svc-out\start-distro.log`. |

### Network

Only TCP 8443 opens, and only for the Private network profile. The kit refuses Public networks and company domain networks (DomainAuthenticated): it is not tested on domain networks, and its rules do not cover the Domain profile.

- Windows Defender Firewall rule: inbound TCP 8443, Private profile, remote address `LocalSubnet`.
- Hyper-V firewall rule for the WSL VM creator ID `{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}`: inbound TCP 8443, Private profile (set when the rule is created), remote address the LAN network of the PC (for example `192.168.1.0/24`). The documentation does not say if Hyper-V rules accept `LocalSubnet`, so setup uses the network address. If the PC moves to a different network, run setup again.
- The Hyper-V firewall blocks other inbound traffic to the WSL VM by default. `20-status.ps1` shows that default.

The web service uses plain HTTP. It carries test data only. TLS is out of scope for this test.

WSL documents a known issue: Docker containers with published ports can fail in mirrored mode. The documented workaround is the host network. By default the kit publishes the port (`-WebNetwork bridge`), because the product will publish its ports. If the LAN check fails, run setup again with `-WebNetwork host`, and record it as a finding.

### The test stack (`linux/payload/compose.yaml`)

| Service | What it does |
|---|---|
| `db` | PostgreSQL 17.12 (official image, pinned by digest). Data checksums on. Internal network only, no published port. Random password, created inside the distribution. |
| `heartbeat` | Writes one row each minute and writes `status.json`. If it fails, Docker restarts it. |
| `web` | BusyBox httpd on port 8443. Returns `status.json` and its age. No database access. |

All services run as non-root users, with all Linux capabilities dropped, `no-new-privileges` and a read-only root file system. All have `restart: unless-stopped`, so Docker starts them again at each boot.

### Input for the installer design (Proposed)

The setup steps, in order, as candidate steps for the installer:

1. Check the build (22621 or later), virtualization, memory, disk, network category and the PowerShell module logging policy.
2. Create the program data folder with an administrators-only access list in the same call, and refuse a folder that exists with other owners or junctions.
3. Turn on `VirtualMachinePlatform`, install the pinned WSL MSI (hash checked again right before the install), restart once, and continue at the next sign-in.
4. Create a standard service account with a random password, the batch logon right and the deny sign-in rights.
5. As that account: write `.wslconfig` with `vmIdleTimeout=-1`, `[general] instanceIdleTimeout=-1` (both are needed) and `networkingMode=mirrored`; import the distribution; turn on systemd; install Docker Engine; start the stack; check that the networking mode is mirrored.
6. Register the boot task with no time limit, restart settings and a 1-minute repetition. Its action keeps one process attached to the distribution, because systemd services alone do not keep WSL running.
7. Add the Windows and Hyper-V firewall rules for the product ports, Private profile only.
8. Set Sleep and Hibernate on mains power to Never.

The test results decide which of these steps the installer keeps.
