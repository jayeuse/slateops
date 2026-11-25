# Slate Operations data and privacy statement

> **Draft: not legal advice. Review before use.**
>
> This statement describes how the current build of Slate Operations handles data. It belongs to the [setup and support order](service-agreement.md).
>
> **Blanks to fill:** [owner legal name], [support contact].
>
> **A Philippine lawyer must check:**
>
> 1. The duties of each party under the Data Privacy Act of 2012 (Republic Act 10173): to be checked by a lawyer. This draft states no duty under that Act.
> 2. Whether the Customer is the personal information controller, and whether the Provider becomes a personal information processor during support.
> 3. Whether a data processing or outsourcing agreement is needed for remote support sessions.
> 4. Whether the Customer must tell its own staff and contacts about this processing, and how.
> 5. Whether the outside connections in section 4 need a notice.
> 6. Whether the encrypted backup download (section 5), the admin exceptions (section 7) and the setup logs kept after uninstall (section 8) need a notice.

## 1. Summary

Slate Operations is self-hosted. It runs on one Windows 11 PC in the Customer's office, as its own separate installation ([Deployment architecture](../architecture/12-deployment-architecture.md#per-client-compose-installation)). The Customer's data stays on that PC and on the Customer's backup drive. Section 4 lists the outside connections, and section 5 lists the copies that leave the PC. The software sends no business data to [owner legal name].

## 2. Where the data lives

1. The setup program installs a Linux part (WSL2) on the PC. The database, the sign-in service, the file storage, the app server and the web server run there ([windows-installer plan, section 3](../plans/windows-installer.md#3-architecture-proposed); `infra/supabase/compose.installer.yaml:6`).
2. The Customer chooses the drive and the folder for the data during setup. Setup lists only drives inside the PC, not USB or network drives (`infra/windows/installer/wizard/Copy.iss:179-188`).
3. Uploaded files are private. They pass through the application, which checks access on each upload and download ([Data architecture](../architecture/06-data-architecture.md#identity-and-files)).
4. People on the office network open the app over HTTPS with a local certificate ([plan, section 6.3](../plans/windows-installer.md#63-caddy-and-the-trust-page)).

## 3. What data the app keeps

1. **Accounts:** name, user name, email address and sign-in data of each person ([Authentication and authorization](../architecture/08-authentication-authorization.md)).
2. **Business data:** records, boards, sheets, reports, messages and files that people put in the app.
3. **Audit history:** who changed what, and when ([Audit and history](../architecture/10-audit-and-history.md)).
4. **Sign-in records:** the network address and the browser name of each session, sign-in and failed sign-in (`backend/app/systems/access/identity/models.py:69-70`; `backend/app/systems/access/users/sign_in_history.py:31-44`). They stay 365 days by default. The security settings can change this from 1 to 3650 days (`backend/app/systems/manage/workspace/models.py:126-127,222-227`; `backend/app/systems/manage/workspace/security_router.py:146-165`).
5. **Service logs:** the app's request log holds the time, the page route, the result and the internal ID of the person. It holds no network address (`backend/app/core/observability.py:58-110`; `backend/app/__main__.py:39`). The web server keeps no access log (`infra/caddy/Caddyfile.template`). How long the app's request log stays: unverified. Docker keeps at most 30 MB of log for each service (`packaging/linux-image/rootfs/etc/docker/daemon.json:5-9`). Whether the third-party services write device addresses in their logs: unverified.

The Customer decides what data people put in the app.

## 4. What leaves the PC

The PC connects to outside services only in these cases. A search of the built setup program, Linux part and service settings found no other outside connection.

| Connection | What it sends | Source |
|---|---|---|
| Email, when the Customer sets up an email account | Invitation, password reset, email change and test emails, through the Customer's own email provider. Each email holds the person's email address and a link to the app. To suggest the settings, setup asks public DNS for the mail servers of the email domain. | `infra/supabase/compose.yaml:83-94`; `infra/windows/installer/scripts/lib/Windows.ps1:1128-1140`; DEC-0041; [plan, section 9.3](../plans/windows-installer.md#93-maintenance-mode) |
| Update check, about every 6 hours | A request to GitHub for the latest stable version number. It sends no business data and no installation ID. GitHub sees the PC's internet address. | `backend/operations/backup_runner.py:68-95,365-376` |
| Internet check during setup | Short requests to GitHub Container Registry (ghcr.io) and Docker Hub. Setup also reads the time from their answers. | `infra/windows/installer/scripts/lib/Checks.ps1:643-680` |
| Setup and updates | Downloads of the database, sign-in, storage, messages and gateway software from GitHub Container Registry and Docker Hub. The setup program carries the Slate Operations parts. | `infra/supabase/compose.yaml` (image lines); `packaging/engine/prefetch.py:1-11`; [plan, section 5.2](../plans/windows-installer.md#52-release-workflow) |
| Signature check during setup and updates | The Linux part gets public signing data from the Sigstore service to check that the software is genuine. It sends no business data. | `packaging/engine/receive.py:11,47,185-201` |
| Weekly security updates of the Linux part | On Sunday between 03:00 and 06:00, downloads of Linux security updates from Debian and Docker. | `packaging/engine/packages.py:1-13,106-110`; `packaging/linux-image/rootfs/etc/apt/sources.list.d/` |
| Time check | The Linux part keeps its clock correct with three public time services (time.cloudflare.com, nts.netnod.se, ptbtime1.ptb.de). | `packaging/linux-image/rootfs/etc/chrony/chrony.conf:5-7` |
| Office network name | The PC answers devices on the office network that ask for its `.local` name. This stays on the office network. | `infra/windows/installer/scripts/lib/Mdns.ps1:1-10` |

No analytics, tracking or error-reporting service was found:

1. The app's web pages can load content only from the PC itself (`backend/app/core/static_site.py:22-26`).
2. The app server, the database, the file storage, the message service and the gateway run on internal networks with no internet route (`infra/supabase/compose.yaml:393-398`; `infra/supabase/compose.production.yaml:157-161`; `compose.installer.yaml:18-22`).
3. Only the sign-in service (to send email), the web server and the backup runner have a network with an internet route (`compose.yaml:111,399`; `compose.production.yaml:151,165`; `packaging/engine/backups.py:96-118`).
4. Whether the third-party software has built-in telemetry: unverified.

## 5. Backups

1. Slate Operations makes a backup every night at 2:00, to a drive that the Customer chooses. Setup recommends another drive, for example a USB drive. The Customer can also keep backups on the data drive, after a warning (`Copy.iss:263-271`; [plan, section 8.2](../plans/windows-installer.md#82-backup-location)).
2. Backups are encrypted. A recovery key opens them if the PC's disk is lost. Setup shows the key once. The Customer prints it or saves it to a USB drive (`Copy.iss:408-415`; [plan, section 8.3](../plans/windows-installer.md#83-recovery-key)).
3. Slate Operations does not store the recovery key on Windows. A printed key passes through the Windows print queue ([plan, section 8.3](../plans/windows-installer.md#83-recovery-key); [section 3.2](../plans/windows-installer.md#32-rules-of-the-boundary), check 7).
4. A backup holds all data and the settings of the installation. Keep the backup drive safe (`infra/supabase/RESTORE.md:7,9`).
5. An administrator can download an encrypted copy of a backup through the browser. The administrator sets its passphrase and confirms with their own password. That copy then leaves the PC ([Security architecture](../architecture/14-security-architecture.md); `infra/supabase/RESTORE.md:60`).

## 6. Support access

1. [owner legal name] accesses the PC or the data only when the Customer asks for it, through a remote session. The Customer watches the session and can end it at any time ([support policy](support-policy.md), section 4).
2. The "Save report" file holds logs and technical facts about the PC for support. It also holds the PC's own network addresses and two days of Windows events. It goes to the desktop of the person who saves it. Nothing is sent automatically; the Customer sends the file (`infra/windows/installer/scripts/lib/Report.ps1:1-15`; `Facts.ps1:103`; [plan, section 10.6](../plans/windows-installer.md#106-save-report)).
3. Setup removes passwords, keys and the recovery key from the report. It leaves out a file that it cannot clean (`packaging/engine/log_bundle.py:1-7`; `Report.ps1:18-33`). Email addresses, Windows user names and the addresses of client devices in log lines are replaced (`packaging/engine/redaction.py:13-17`; `Report.ps1:18-33`). The logs do not record message text, file content or business records ([plan, section 10.1](../plans/windows-installer.md#101-logging-contract), item 7). This is unverified for the logs of the third-party services.
4. [owner legal name] does not copy the Customer's data ([setup and support order](service-agreement.md), section 8).

## 7. Access inside the organization

1. The organization admin gives each person access by groups. A person without access does not see a module ([Authentication and authorization](../architecture/08-authentication-authorization.md#application-authorization)).
2. A guest can only read.
3. The app does not show an admin the direct or group messages that the admin is not part of ([OpenComms plan, D43](../plans/opencomms.md)). There are three recorded exceptions ([Security architecture](../architecture/14-security-architecture.md)):
   1. An admin acts on a message that a person reports, through the moderation queue.
   2. An administrator can export these messages, with a password check and a recorded reason.
   3. An administrator who sets a temporary password for a person can sign in as that person. The history records who did it.

## 8. Removal

1. Uninstall starts from Windows Settings → Apps. It offers "Keep my data (recommended)" or "Delete everything" ([plan, section 9.1](../plans/windows-installer.md#91-uninstall); `infra/windows/installer/wizard/Copy.iss:448-452`).
2. "Delete everything" removes all records, files and settings from the PC. The backups stay, unless the Customer also selects "Also delete the backups" (`Copy.iss:453-459`).
3. The setup logs in `C:\ProgramData\SlateOps\logs` stay after uninstall (`infra/windows/installer/scripts/lib/Uninstall.ps1:676-694`).

## 9. Questions

Write to [support contact].
