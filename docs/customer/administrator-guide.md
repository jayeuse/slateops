# Slate Operations administrator guide

> **Draft.** This guide describes the current build of Slate Operations.
>
> **Blanks to fill:** [support contact], [backup drive], [recovery key location], [where to get the setup file].

## About this guide

This guide is for the administrator of your organization in Slate Operations. Slate Operations runs on one Windows 11 PC in your office. This guide calls that PC the **server PC**.

Each statement has a source in parentheses. A source is a screen text in the product files, a runbook section, or a plan section. Slate Operations support uses the sources to check the guide. You can ignore them.

Text in square brackets, for example [support contact], is a blank. Fill each blank before you use this guide.

### Words in this guide

| Word | Meaning |
|---|---|
| Administrator | A person with the role "Administrator" in your organization ([people.ts:42](../../frontend/src/components/systems/access/helpers/people.ts#L42)). |
| Installation owner | The administrator that setup created. This account also manages backups, updates and the license file ([08-authentication-authorization.md](../architecture/08-authentication-authorization.md), "Only the organization owner"; [workspace-navigation.ts:208](../../frontend/src/components/workspace-navigation.ts#L208)). |
| Edition | What your installation can do: Desk (free), Office or Headquarters. A license file unlocks Office or Headquarters (chapter 5). |
| Server PC | The Windows 11 PC that runs Slate Operations for your office ([Copy.iss:38](../../infra/windows/installer/wizard/Copy.iss#L38)). |
| Slate Operations settings | The program on the server PC for email, backups, restore, stop and start, repair and reports ([SlateOpsSetup.iss:121](../../infra/windows/installer/SlateOpsSetup.iss#L121)). |
| Slate Operations support | The people who maintain Slate Operations. Help is free. Contact: [support contact]. See [getting help](getting-help.md). |

### Where to find things

| Task | Where |
|---|---|
| Invite people, make groups, give access | Slate Operations → **Access** ([workspace-navigation.ts:62-73](../../frontend/src/components/workspace-navigation.ts#L62)) |
| Check backups and updates | Slate Operations → **Manage** → **Backup**, **Updates & licensing** ([workspace-navigation.ts:88-104](../../frontend/src/components/workspace-navigation.ts#L88)) |
| See the edition, import a license file | Slate Operations → **Manage** → **Updates & licensing** ([workspace-navigation.ts:103](../../frontend/src/components/workspace-navigation.ts#L103)) |
| Check whether Slate Operations works | Slate Operations → **Manage** → **System health** ([workspace-navigation.ts:97](../../frontend/src/components/workspace-navigation.ts#L97)) |
| Set up email, change the backup drive, restore the latest backup, stop or start, repair | Server PC → Start menu → **Slate Operations settings** ([SlateOpsSetup.iss:121](../../infra/windows/installer/SlateOpsSetup.iss#L121)) |
| Make a file for support | Server PC → Start menu → **Slate Operations - Save report** ([SlateOpsSetup.iss:122](../../infra/windows/installer/SlateOpsSetup.iss#L122)) |
| Uninstall | Windows **Settings** → **Apps** ([Copy.iss:445](../../infra/windows/installer/wizard/Copy.iss#L445)) |

Two related guides exist: the [quick start](quick-start.md) and the [user guide](user-guide.md).

## 1. People and access

Access controls who can see and change your organization's information. The **Access** page has four sections: **Overview**, **People**, **Groups** and **Security** ([workspace-navigation.ts:68-73](../../frontend/src/components/workspace-navigation.ts#L68)).

### 1.1 Roles

Each person has one role in your organization ([08-authentication-authorization.md](../architecture/08-authentication-authorization.md), "One installation holds").

| Role | What the role does |
|---|---|
| Administrator | "Has full access everywhere and can change people and groups." ([invite-person-dialog.tsx:142](../../frontend/src/components/systems/access/components/invite-person-dialog.tsx#L142)) |
| Member | Gets access only from the groups that the person is in ([invite-person-dialog.tsx:531](../../frontend/src/components/systems/access/components/invite-person-dialog.tsx#L531)). |
| Guest | "Can only read, for a limited time, with a sponsor." ([invite-person-dialog.tsx:141](../../frontend/src/components/systems/access/components/invite-person-dialog.tsx#L141)) |

An administrator of your organization has no authority in another organization ([08-authentication-authorization.md](../architecture/08-authentication-authorization.md), "Application authorization").

### 1.2 Access levels

Groups give access to departments. Each group has one of three levels for a department ([page-guides.ts:43](../../frontend/src/components/help/page-guides.ts#L43)):

| Level | What a person can do |
|---|---|
| Read | "Read opens and views" |
| Write | "Write adds and changes records" |
| Manage | "Manage also changes settings and who has access" |

These rules apply ([08-authentication-authorization.md](../architecture/08-authentication-authorization.md), "effective_levels"):

1. A person with no group access to a department has no access to it.
2. When a person is in two groups, the higher level applies.
3. A guest gets **Read** only, also in a group that gives **Write** or **Manage**.
4. An administrator has **Manage** everywhere. You do not add an administrator to groups ([invite-person-dialog.tsx:520-521](../../frontend/src/components/systems/access/components/invite-person-dialog.tsx#L520)).

Departments come from the Sandbox. If no department exists, create departments in the Sandbox first ([group-access-editor.tsx:314](../../frontend/src/components/systems/access/components/group-access-editor.tsx#L314)).

### 1.3 Create a group

Make the groups before you invite people. Then you can add each person to groups in the invitation ([invite-person-dialog.tsx:525-526](../../frontend/src/components/systems/access/components/invite-person-dialog.tsx#L525)).

1. Open **Access** → **Groups**.
2. Select **Create group** ([groups-view.tsx:387](../../frontend/src/components/systems/access/components/groups-view.tsx#L387)).
3. Type the **Name** and, if you want, a **Description** ([create-group-dialog.tsx:232-233](../../frontend/src/components/systems/access/components/create-group-dialog.tsx#L232)).
4. Add the first members, if you know them.
5. Select **Create group** ([create-group-dialog.tsx:297](../../frontend/src/components/systems/access/components/create-group-dialog.tsx#L297)).
6. Open the group, then open its **Access** tab ([group-editor.tsx:796](../../frontend/src/components/systems/access/components/group-editor.tsx#L796)).
7. For each department, select **Read**, **Write** or **Manage** ([group-access-editor.tsx:236-241](../../frontend/src/components/systems/access/components/group-access-editor.tsx#L236)).
8. Select **Save access** ([group-editor.tsx:1095](../../frontend/src/components/systems/access/components/group-editor.tsx#L1095)).

To change the members later, open the group's **Members** tab, then select **Save members** ([group-editor.tsx:795](../../frontend/src/components/systems/access/components/group-editor.tsx#L795), [1057](../../frontend/src/components/systems/access/components/group-editor.tsx#L1057)).

**Department managers.** A person with **Manage** on a department can change the members of that department's groups. Only an administrator renames a group or changes its access ([page-guides.ts:43](../../frontend/src/components/help/page-guides.ts#L43); [08-authentication-authorization.md](../architecture/08-authentication-authorization.md), "Groups are administrator-managed").

### 1.4 Invite a person

Slate Operations can send the invitation by email only after you set up email (chapter 6). Without email, you copy a link and send it yourself ([invite-person-dialog.tsx:638-639](../../frontend/src/components/systems/access/components/invite-person-dialog.tsx#L638)).

1. Open **Access** → **People**.
2. Select **Invite person** ([people-view.tsx:441](../../frontend/src/components/systems/access/components/people-view.tsx#L441)).
3. Type the **Email**, **Username**, **Name** and **Job title** ([invite-person-dialog.tsx:430-457](../../frontend/src/components/systems/access/components/invite-person-dialog.tsx#L430)).
4. Select the **Role**: Member, Guest or Administrator ([invite-person-dialog.tsx:467](../../frontend/src/components/systems/access/components/invite-person-dialog.tsx#L467)).
5. Under **Groups**, select the groups for this person ([invite-person-dialog.tsx:517](../../frontend/src/components/systems/access/components/invite-person-dialog.tsx#L517)).
6. Under **How to send**, select one choice ([invite-person-dialog.tsx:95-101](../../frontend/src/components/systems/access/components/invite-person-dialog.tsx#L95)):
   - **Send from Slate Operations**: "An invitation email goes to their address."
   - **Copy a link to send yourself**: "Send it by any channel. It works once, for 24 hours."
7. Select **Send invitation** or **Create invitation link** ([invite-person-dialog.tsx:714-715](../../frontend/src/components/systems/access/components/invite-person-dialog.tsx#L714)).
8. If you made a link, copy it and send it to the person.

The person opens the link, sets a password and signs in ([08-authentication-authorization.md](../architecture/08-authentication-authorization.md), "Invitations and recovery").

**Edition limit.** Desk allows 2 people (administrators and members), and you are one of them ([editions.py:51](../../backend/app/systems/manage/licensing/editions.py#L51)). An invitation above the limit fails with a message (section 5.5).

### 1.5 Invite a guest

A guest reads only, for a limited time. Each guest has a sponsor in your organization ([invite-person-dialog.tsx:141](../../frontend/src/components/systems/access/components/invite-person-dialog.tsx#L141)).

Desk allows no guests. Office and Headquarters allow 2 guests for each person in the license file ([editions.py:51](../../backend/app/systems/manage/licensing/editions.py#L51), [67-74](../../backend/app/systems/manage/licensing/editions.py#L67)).

1. Do steps 1 to 3 of section 1.4.
2. Select the **Role** "Guest".
3. Select the sponsor ([invite-person-dialog.tsx:283](../../frontend/src/components/systems/access/components/invite-person-dialog.tsx#L283)).
4. Type the **Access length in days**, from 1 to 365 ([invite-person-dialog.tsx:496](../../frontend/src/components/systems/access/components/invite-person-dialog.tsx#L496); [people.ts:504-505](../../frontend/src/components/systems/access/helpers/people.ts#L504)).
5. Do steps 5 to 8 of section 1.4.

When the time ends, the guest cannot sign in. To let the guest sign in again, set a later end date ([person-account.tsx:408](../../frontend/src/components/systems/access/components/person-account.tsx#L408)).

### 1.6 Change or stop a person's access

Open **Access** → **People**, then open the person. You can change the person's details, groups and security there ([page-guides.ts:42](../../frontend/src/components/help/page-guides.ts#L42)).

| Action | What it does |
|---|---|
| **Resend invitation** | Sends the invitation email again ([person-account.tsx:82-87](../../frontend/src/components/systems/access/components/person-account.tsx#L82)). |
| **Copy a new link** | Makes a new invitation link. "The earlier link or invitation email no longer works." ([person-account.tsx:92](../../frontend/src/components/systems/access/components/person-account.tsx#L92), [504](../../frontend/src/components/systems/access/components/person-account.tsx#L504)) |
| **Revoke invitation** | "This invitation can no longer be accepted, in the app or by email link." ([person-account.tsx:102-105](../../frontend/src/components/systems/access/components/person-account.tsx#L102)) |
| **Disable** | "They are signed out everywhere and cannot sign in until you enable them again." ([person-account.tsx:113-116](../../frontend/src/components/systems/access/components/person-account.tsx#L113)) |
| **Enable** | "They can sign in again with the access they had before." ([person-account.tsx:124-126](../../frontend/src/components/systems/access/components/person-account.tsx#L124)) |
| **Delete** | "They are signed out everywhere and leave the directory. You can restore them later." ([person-account.tsx:134-137](../../frontend/src/components/systems/access/components/person-account.tsx#L134)) |
| **Restore** | "They come back to the directory and can sign in again." ([person-account.tsx:145-147](../../frontend/src/components/systems/access/components/person-account.tsx#L145)) |
| **Set a temporary password** | "For when they cannot use email." The person chooses a new password at the next sign-in ([person-temporary-password.tsx:141-158](../../frontend/src/components/systems/access/components/person-temporary-password.tsx#L141)). |

When a person leaves your organization, use **Disable** or **Delete** on the same day.

### 1.7 Private messages

Administrators do not read direct messages or group messages that they are not part of. These conversations do not show in an administrator's list, search or history ([opencomms.md, D43](../plans/opencomms.md)).

Slate Operations has no private channels. Each channel is for the whole organization or for one department ([opencomms.md, D44](../plans/opencomms.md)). Administrators manage every channel.

An administrator can export direct and group messages. The export asks for the administrator's password again and for a reason. The audit records each export ([opencomms.md, D31](../plans/opencomms.md)).

### 1.8 Security policy

**Access** → **Security** shows the account policy and the active sessions. Administrators change the policy in **Edit policy** ([page-guides.ts:44](../../frontend/src/components/help/page-guides.ts#L44); [security-view.tsx:979](../../frontend/src/components/systems/access/components/security-view.tsx#L979)). Only the organization owner or the installation owner can save a change ([08-authentication-authorization.md](../architecture/08-authentication-authorization.md), "Only the organization owner").

### 1.9 If you forget the administrator password

If email works, select **Forgot password?** on the sign-in page ([login/page.tsx:153](../../frontend/src/app/login/page.tsx#L153)). If email does not work, reset the password on the server PC:

1. On the server PC, open the Start menu.
2. Open **Slate Operations settings**.
3. Select **Reset the admin password** ([Copy.iss:341](../../infra/windows/installer/wizard/Copy.iss#L341)).
4. Type the **New password**, then type it again in **Type it again** ([Copy.iss:343-344](../../infra/windows/installer/wizard/Copy.iss#L343)).
5. Select **Change password** ([Copy.iss:345](../../infra/windows/installer/wizard/Copy.iss#L345)).
6. Sign in with the new password ([Copy.iss:348](../../infra/windows/installer/wizard/Copy.iss#L348)).

The password must have 12 to 72 characters ([Copy.iss:349](../../infra/windows/installer/wizard/Copy.iss#L349)). This action resets only the administrator that setup created ([Copy.iss:351](../../infra/windows/installer/wizard/Copy.iss#L351)).

## 2. Backups and restore

**Who can do this.** Only the installation owner opens **Manage** → **Backup**. Another administrator sees "Backup is managed by the installation owner." ([manage-unavailable.tsx:19-20](../../frontend/src/components/systems/manage/components/manage-unavailable.tsx#L19))

### 2.1 What setup made

1. Slate Operations makes a backup every night at 2:00 ([Copy.iss:264](../../infra/windows/installer/wizard/Copy.iss#L264)).
2. It keeps each backup for 30 days ([policy_default.py:14-15](../../backend/app/systems/manage/backups/policy_default.py#L14)).
3. The backups go to [backup drive].
4. The backups are locked. A recovery key opens them if the server PC breaks or is lost ([Copy.iss:410](../../infra/windows/installer/wizard/Copy.iss#L410)).
5. Setup showed the recovery key one time, to print or to save ([Copy.iss:411](../../infra/windows/installer/wizard/Copy.iss#L411)). The key is at [recovery key location].

Keep the recovery key away from the server PC and away from the backup drive ([Copy.iss:411](../../infra/windows/installer/wizard/Copy.iss#L411)).

If the backups go to a USB drive, keep it plugged in. "A backup fails while the drive is out." ([Copy.iss:271](../../infra/windows/installer/wizard/Copy.iss#L271))

**Outage.** Slate Operations stops for about a minute while a backup runs. Changes that people make in that minute may not save. It starts again by itself ([backup-panel.tsx:428-430](../../frontend/src/components/systems/manage/components/backup-panel.tsx#L428)). The nightly backup at 2:00 is outside normal office hours.

### 2.2 Check the backups

Open **Manage** → **Backup**. The **Status** shows four rows ([backup-status-panel.tsx:92-101](../../frontend/src/components/systems/manage/components/backup-status-panel.tsx#L92)):

| Row | What it shows |
|---|---|
| Schedule | For example, On · Daily at 02:00 · Kept 30 days ([backup-rules.ts:60-63](../../frontend/src/components/systems/manage/domain/backup-rules.ts#L60)) |
| Last good backup | The time, then "Verified" or "Not verified yet" ([backup-rules.ts:94-96](../../frontend/src/components/systems/manage/domain/backup-rules.ts#L94)) |
| Service | "Available", or a problem word such as "Not checked in recently" ([backup-rules.ts:27-33](../../frontend/src/components/systems/manage/domain/backup-rules.ts#L27)) |
| Queue | The backups that wait or run ([backup-rules.ts:64-67](../../frontend/src/components/systems/manage/domain/backup-rules.ts#L64)) |

**History** lists every backup. Each one has a status: Queued, Running, Completed, Verified, Failed, Interrupted or Expired ([backup-rules.ts:146-159](../../frontend/src/components/systems/manage/domain/backup-rules.ts#L146)).

Check the **Last good backup** row regularly. If it is older than two days, tell Slate Operations support.

### 2.3 Change the schedule

1. Open **Manage** → **Backup**.
2. Select **Edit schedule** ([backup-status-panel.tsx:66](../../frontend/src/components/systems/manage/components/backup-status-panel.tsx#L66)).
3. In **Schedule**, select "Disabled", "Daily at 02:00" or "Weekly on Sunday at 02:00" ([backup-api.ts:356-360](../../frontend/src/components/systems/manage/adapters/backup-api.ts#L356)).
4. In **Keep backups for**, select 7, 30 or 90 days ([backup-schedule-dialog.tsx:31-35](../../frontend/src/components/systems/manage/components/backup-schedule-dialog.tsx#L31)).
5. Select **Save schedule** ([backup-schedule-dialog.tsx:269](../../frontend/src/components/systems/manage/components/backup-schedule-dialog.tsx#L269)).

"Old backups are removed only after a newer backup is checked." ([backup-schedule-dialog.tsx:92](../../frontend/src/components/systems/manage/components/backup-schedule-dialog.tsx#L92))

**Caution:** do not select "Disabled". Without backups, a broken disk loses your data.

### 2.4 Make a backup now

Make a backup before a large change, for example before an update.

**Caution:** Slate Operations stops for about a minute while this backup runs, and changes made in that minute may not save. Tell your people before you start ([backup-panel.tsx:428-430](../../frontend/src/components/systems/manage/components/backup-panel.tsx#L428)).

1. Open **Manage** → **Backup**.
2. Select **Back up now** ([backup-status-panel.tsx:83](../../frontend/src/components/systems/manage/components/backup-status-panel.tsx#L83)).
3. Type a **Backup name** ([backup-panel.tsx:445](../../frontend/src/components/systems/manage/components/backup-panel.tsx#L445)).
4. Select **Back up now** ([backup-panel.tsx:489](../../frontend/src/components/systems/manage/components/backup-panel.tsx#L489)).

The backup goes into the queue. The backup service starts it within about one minute ([infra/supabase/RESTORE.md, "Run the installation backup policy"](../../infra/supabase/RESTORE.md#run-the-installation-backup-policy); [plan section 2](../plans/windows-installer.md#2-current-state), Backup row).

### 2.5 Make an encrypted copy

You can download one backup as an encrypted file, for example to keep a copy in another place.

1. Open **Manage** → **Backup**.
2. In **History**, select a backup with the status "Verified".
3. Select **Prepare encrypted backup** ([backup-detail.tsx:159](../../frontend/src/components/systems/manage/components/backup-detail.tsx#L159)).
4. Type a **Passphrase** with 16 to 128 printable characters ([backup-export.tsx:364](../../frontend/src/components/systems/manage/components/backup-export.tsx#L364)).
5. Type it again in **Confirm passphrase** ([backup-export.tsx:372](../../frontend/src/components/systems/manage/components/backup-export.tsx#L372)).
6. Select **Prepare encrypted backup** ([backup-export.tsx:427](../../frontend/src/components/systems/manage/components/backup-export.tsx#L427)).
7. When the copy is ready, select **Download encrypted backup** ([backup-export.tsx:212](../../frontend/src/components/systems/manage/components/backup-export.tsx#L212)).
8. Type your current password, then confirm ([backup-export.tsx:480](../../frontend/src/components/systems/manage/components/backup-export.tsx#L480)).

**Caution:** keep the passphrase in a safe place. The file is encrypted with it, and the copy cannot be opened without it ([infra/supabase/RESTORE.md, "Run the installation backup policy"](../../infra/supabase/RESTORE.md#run-the-installation-backup-policy)).

The download stops when the copy expires. The copy expires 24 hours after it is ready ([backup-export.tsx:189](../../frontend/src/components/systems/manage/components/backup-export.tsx#L189); [infra/supabase/RESTORE.md, "Run the installation backup policy"](../../infra/supabase/RESTORE.md#run-the-installation-backup-policy)).

### 2.6 Change the backup drive

**Caution:** a new backup drive has its own lock. The old recovery key does not open it. Have a printer or a USB drive ready to save the new key ([Copy.iss:516](../../infra/windows/installer/wizard/Copy.iss#L516)).

1. On the server PC, connect the new drive.
2. Open the Start menu, then open **Slate Operations settings**.
3. Select **Change backup drive** ([Copy.iss:498](../../infra/windows/installer/wizard/Copy.iss#L498)).
4. Select the new drive.
5. Save the new recovery key when setup shows it.

Backups go to the new drive from the next night at 2:00 ([Copy.iss:517](../../infra/windows/installer/wizard/Copy.iss#L517)).

### 2.7 Make a new recovery key

Make a new key when the old key is lost, or when a person who left knows it.

**Caution:** "Your current recovery key stops working." Have a printer or a USB drive ready ([Copy.iss:547](../../infra/windows/installer/wizard/Copy.iss#L547)).

1. On the server PC, open **Slate Operations settings**.
2. Select **Make a new recovery key** ([Copy.iss:500](../../infra/windows/installer/wizard/Copy.iss#L500)).
3. Confirm the change.
4. Print or save the new key.
5. Destroy the old key.

### 2.8 When a backup fails

After a failed backup, Slate Operations tries to start again by itself, up to 3 times ([fail_open.py:18](../../backend/operations/backups/fail_open.py#L18), [43](../../backend/operations/backups/fail_open.py#L43)).

These messages need action:

| Where | Message | What to do |
|---|---|---|
| **Slate Operations settings** | "Needs attention: plug in the backup drive (%1)." ([Copy.iss:485](../../infra/windows/installer/wizard/Copy.iss#L485)) | Plug in the backup drive. If the message stays, select **Repair**. |
| **Slate Operations settings** | "Needs support." ([Copy.iss:486](../../infra/windows/installer/wizard/Copy.iss#L486)) | Make a report (chapter 4). Send it to [support contact]. |
| **Manage** → **Backup** | "The person who runs your server must run backup recovery." ([backup-rules.ts:43-44](../../frontend/src/components/systems/manage/domain/backup-rules.ts#L43)) | Tell Slate Operations support. |

In this table, "%1" is the letter of your backup drive.

### 2.9 Restore the latest backup

You restore the newest backup on the server PC with one button ([plan section 8.4](../plans/windows-installer.md#84-restore-in-v1)). The app shows the same advice in **Manage** → **Backup** ([backup-rules.ts](../../frontend/src/components/systems/manage/domain/backup-rules.ts); [backup-detail.tsx:106](../../frontend/src/components/systems/manage/components/backup-detail.tsx#L106)).

**Caution:** "All changes made after the last backup are lost, and everyone must sign in again." Slate Operations is not available while the restore runs ([Copy.iss:384](../../infra/windows/installer/wizard/Copy.iss#L384)). Tell your people before you start.

1. Make sure that the backup drive is connected ([Copy.iss:403](../../infra/windows/installer/wizard/Copy.iss#L403)).
2. On the server PC, open the Start menu, then open **Slate Operations settings**.
3. Select **Restore the latest backup** ([Copy.iss:354](../../infra/windows/installer/wizard/Copy.iss#L354)).
4. In "Restore the latest backup?", select **Restore** ([Copy.iss:383](../../infra/windows/installer/wizard/Copy.iss#L383); [Copy.iss:385](../../infra/windows/installer/wizard/Copy.iss#L385)). To stop, select **Go back** ([Copy.iss:25](../../infra/windows/installer/wizard/Copy.iss#L25)).
5. Wait. The steps go from "Find the latest backup" to "Finish the restore" ([Copy.iss:402](../../infra/windows/installer/wizard/Copy.iss#L402)).
6. Read the result. "The latest backup is restored." shows the date of the restored data ([Copy.iss:394](../../infra/windows/installer/wizard/Copy.iss#L394); [Copy.iss:395](../../infra/windows/installer/wizard/Copy.iss#L395)).
7. Tell your people to sign in again, on PCs and on phones ([Copy.iss:396](../../infra/windows/installer/wizard/Copy.iss#L396)).
8. Select **Back to settings** ([Copy.iss:397](../../infra/windows/installer/wizard/Copy.iss#L397)).

| Message | What it means | What to do |
|---|---|---|
| "Setup cannot find the backup drive, so nothing changed." ([Copy.iss:403](../../infra/windows/installer/wizard/Copy.iss#L403)) | The backup drive is not connected. | Connect the drive, then try again. |
| "There is no backup to restore yet, so nothing changed." ([Copy.iss:404](../../infra/windows/installer/wizard/Copy.iss#L404)) | No backup exists yet. | Make a backup first (section 2.4). |
| "Slate Operations was busy with another task for 5 minutes, so nothing changed." ([Copy.iss:399](../../infra/windows/installer/wizard/Copy.iss#L399)) | A backup or an update was running. | Try again later. |
| "Nothing changed: Slate Operations runs again on the data it had before." ([Copy.iss:400](../../infra/windows/installer/wizard/Copy.iss#L400)) | The restore stopped early and put the old data back. | Save a report (chapter 4). Send it to [support contact]. |
| "Slate Operations is stopped." ([Copy.iss:401](../../infra/windows/installer/wizard/Copy.iss#L401)) | The restore stopped after it changed the installation. | Save a report (chapter 4). Send it to [support contact]. |

**An older backup.** The button restores only the newest backup. To go back to an older backup, write to [support contact]. Slate Operations support does it through a remote session ([infra/supabase/RESTORE.md](../../infra/supabase/RESTORE.md)).

### 2.10 Stop and start Slate Operations

Stop Slate Operations only when Slate Operations support asks, or before work on the server PC.

**Caution:** "Nobody can use Slate Operations, and backups do not run, until you select Start Slate Operations or this PC restarts." ([Copy.iss:360](../../infra/windows/installer/wizard/Copy.iss#L360))

1. On the server PC, open **Slate Operations settings**.
2. Select **Stop Slate Operations** ([Copy.iss:355](../../infra/windows/installer/wizard/Copy.iss#L355)).
3. Select **Stop** to confirm ([Copy.iss:361](../../infra/windows/installer/wizard/Copy.iss#L361)).
4. To start it again, select **Start Slate Operations** ([Copy.iss:357](../../infra/windows/installer/wizard/Copy.iss#L357)). The start takes about 2 minutes ([Copy.iss:365](../../infra/windows/installer/wizard/Copy.iss#L365)).

Slate Operations starts automatically when the server PC starts ([Copy.iss:371](../../infra/windows/installer/wizard/Copy.iss#L371)). Keep this on. If you turn it off, nobody can use Slate Operations after a restart, also after a Windows Update restart at night ([Copy.iss:376](../../infra/windows/installer/wizard/Copy.iss#L376)).

## 3. Updates

**Who can do this.** Only the installation owner opens **Manage** → **Updates & licensing**. Another administrator sees "Updates are managed by the installation owner." ([manage-unavailable.tsx:21-22](../../frontend/src/components/systems/manage/components/manage-unavailable.tsx#L21))

### 3.1 Check your version

Open **Manage** → **Updates & licensing**. The **Installation** panel shows these rows ([updates-panel.tsx:42-73](../../frontend/src/components/systems/manage/components/updates-panel.tsx#L42)):

| Row | What it shows |
|---|---|
| Version | The version that runs now, then "· Stable channel" ([updates-rules.ts:26-28](../../frontend/src/components/systems/manage/domain/updates-rules.ts#L26)) |
| Release check | The result of the last check for a new release |
| Latest release | A newer release, when one is known |

The **Edition and license** panel is below the **Installation** panel ([page.tsx:1589-1590](../../frontend/src/components/systems/manage/page.tsx#L1589)). Chapter 5 tells you how to use it.

Select **Refresh release status** to read the latest check again ([updates-panel.tsx:115](../../frontend/src/components/systems/manage/components/updates-panel.tsx#L115)).

**Stable releases only.** The release check reads only published, stable releases ([backup_runner.py:69-97](../../backend/operations/backup_runner.py#L69)). A test build gets no update prompt; Slate Operations support then tells you when an update is ready. The **Release check** row can show "The release check is not available" ([updates-rules.ts:12](../../frontend/src/components/systems/manage/domain/updates-rules.ts#L12)) (unverified).

### 3.2 Install an update

The person who runs your server installs updates ([page.tsx:525](../../frontend/src/components/systems/manage/page.tsx#L525)). You install it with the new setup file. Get the file from [where to get the setup file].

**Caution:** "People cannot use Slate Operations while it updates. This can take up to 1 hour." ([Copy.iss:525](../../infra/windows/installer/wizard/Copy.iss#L525))

1. Tell your people when the update starts.
2. On the server PC, open the new setup file.
3. Allow the change when Windows asks for permission ([SlateOpsSetup.iss:31](../../infra/windows/installer/SlateOpsSetup.iss#L31)).
4. On **Update Slate Operations**, read the two version numbers ([Copy.iss:522-523](../../infra/windows/installer/wizard/Copy.iss#L522)).
5. Select **Update now** ([Copy.iss:526](../../infra/windows/installer/wizard/Copy.iss#L526)).
6. Keep the server PC on until setup shows the result.

"Setup makes a backup before it changes anything." If the update fails, Slate Operations goes back to the old version by itself ([Copy.iss:524](../../infra/windows/installer/wizard/Copy.iss#L524)).

| Result | What to do |
|---|---|
| "Slate Operations is updated to version %1." ([Copy.iss:532](../../infra/windows/installer/wizard/Copy.iss#L532)) | Nothing. Tell your people. |
| "The update did not work. Slate Operations went back to version %1. Everybody must sign in again." ([Copy.iss:533](../../infra/windows/installer/wizard/Copy.iss#L533)) | Tell your people to sign in again. Tell Slate Operations support. |
| "The update did not work. Slate Operations still runs version %1. Nothing changed." ([Copy.iss:534](../../infra/windows/installer/wizard/Copy.iss#L534)) | Tell Slate Operations support. |
| Any message that says "Select Save report" ([Copy.iss:535-536](../../infra/windows/installer/wizard/Copy.iss#L535)) | Select **Save report**. Send the file to [support contact]. |

If setup says that Slate Operations is busy, wait. Setup tries again by itself ([Copy.iss:531](../../infra/windows/installer/wizard/Copy.iss#L531)).

The **Update procedure for this release** link on the Updates page is for Slate Operations support ([updates-panel.tsx:99](../../frontend/src/components/systems/manage/components/updates-panel.tsx#L99)).

## 4. Reports for support

Two files help Slate Operations support find a problem. Send them as [getting help](getting-help.md) describes. Neither file is sent automatically.

| File | Use it when |
|---|---|
| **Save report** on the server PC | Slate Operations does not open, setup or an update stops, or **Slate Operations settings** says "Needs support" |
| **Download support file** in the app | Slate Operations opens, but a page or an action fails |

### 4.1 Save report on the server PC

1. On the server PC, open the Start menu.
2. Select **Slate Operations - Save report** ([SlateOpsSetup.iss:122](../../infra/windows/installer/SlateOpsSetup.iss#L122)).
3. Wait. "This takes up to 3 minutes." ([Copy.iss:544](../../infra/windows/installer/wizard/Copy.iss#L544))
4. Find the file on your desktop. Its name starts with "SlateOps-report-" ([Copy.iss:678](../../infra/windows/installer/wizard/Copy.iss#L678)).
5. Send the file to [support contact].

You can also select **Save report** in **Slate Operations settings**, or on each setup screen that shows an error ([Copy.iss:19](../../infra/windows/installer/wizard/Copy.iss#L19); [plan section 10.6](../plans/windows-installer.md#106-save-report)).

The report holds no passwords, keys or business records. Email addresses and user names in it are replaced ([plan section 10.6](../plans/windows-installer.md#106-save-report); [Copy.iss:677](../../infra/windows/installer/wizard/Copy.iss#L677)).

The report works also when the server part does not answer. Then the report says "Linux part not reachable" ([plan section 10.6](../plans/windows-installer.md#106-save-report)) (unverified).

### 4.2 Download support file in the app

1. Open **Manage** → **System health**.
2. Select **Download support file** ([system-health-support-file.tsx:189](../../frontend/src/components/systems/manage/components/system-health-support-file.tsx#L189)).
3. Send the file to [support contact].

For an administrator, the file "holds no records, no personal data and nothing from other organizations" ([system-health-support-file.tsx:22](../../frontend/src/components/systems/manage/components/system-health-support-file.tsx#L22)). Only an administrator can download it ([system-health-support-file.tsx:37](../../frontend/src/components/systems/manage/components/system-health-support-file.tsx#L37)).

When an action fails, its message can show a reference. Send that reference with the file ([page-guides.ts:60](../../frontend/src/components/help/page-guides.ts#L60)).

### 4.3 Check whether Slate Operations works

**Manage** → **System health** says whether Slate Operations works now. **Parts of Slate Operations** shows the status of each part. Select **Check again** to see the latest check ([page-guides.ts:60](../../frontend/src/components/help/page-guides.ts#L60)).

On the server PC, **Slate Operations settings** also shows a status, for example "Running." or "Needs support." ([Copy.iss:484-488](../../infra/windows/installer/wizard/Copy.iss#L484)). When it says "Not ready.", select **Repair**. "Repair" sets up the Windows parts again, and your data does not change ([Copy.iss:502-503](../../infra/windows/installer/wizard/Copy.iss#L502)).

## 5. Edition and license file

For prices, how to buy a license file and the license states, read [editions and license files](editions-and-license.md).

Each installation runs one edition: Desk, Office or Headquarters ([editions.py:48-58](../../backend/app/systems/manage/licensing/editions.py#L48)). Setup starts every installation as Desk, the free edition ([Copy.iss:284](../../infra/windows/installer/wizard/Copy.iss#L284), [433](../../infra/windows/installer/wizard/Copy.iss#L433)). A license file from Slate Operations support unlocks Office or Headquarters. The license file works with no internet ([license-panel.tsx:195-198](../../frontend/src/components/systems/manage/components/license-panel.tsx#L195)).

**Who can do this.** Only the installation owner opens **Manage** → **Updates & licensing** and imports a license file ([workspace-navigation.ts:208](../../frontend/src/components/workspace-navigation.ts#L208); [router.py:101-102](../../backend/app/systems/manage/licensing/router.py#L101)). Another administrator sees "Updates are managed by the installation owner." ([manage-unavailable.tsx:21-22](../../frontend/src/components/systems/manage/components/manage-unavailable.tsx#L21))

### 5.1 What each edition allows

| Item | Desk | Office | Headquarters |
|---|---|---|---|
| Price that the app shows | "Free" | "$39 a month or $390 a year" | "$89 a month or $890 a year" |
| People (administrators and members) | 2 | The number in your license file. The app lists 25. | The number in your license file. The app lists 100. |
| Guests | 0 | 2 for each person in the license file | 2 for each person in the license file |
| Published departments | 2 | No limit | No limit |
| Modules in a department | 3 | No limit | No limit |
| Records in a module | 1,000 | No limit | No limit |
| Sheets | 10 | No limit | No limit |
| Rows in a sheet | 1,000 | 10,000, the size limit of every sheet | 10,000, the size limit of every sheet |
| OpenComms, dashboards, reports, automations, Gantt view, audit viewer | No | Yes | Yes |

Sources: [editions.py:48-74](../../backend/app/systems/manage/licensing/editions.py#L48); [license-rules.ts:66-72](../../frontend/src/components/systems/manage/domain/license-rules.ts#L66); [structure.py:21](../../backend/app/systems/openview/worksheets/structure.py#L21); [spec, Editions](../specs/editions.md#editions).

What counts against a limit ([usage.py:23-39](../../backend/app/systems/manage/licensing/usage.py#L23)):

- An active person and an invited person count.
- A disabled person, a deleted person and a guest whose time ended do not count.
- **Revoke invitation** does not free a place. The invitation stays until you delete the person ([service.py:299-310](../../backend/app/systems/access/users/service.py#L299)).
- For modules, records and rows, the limit applies to each department, module and sheet. The **Used** column shows the fullest one ([usage.py:94-107](../../backend/app/systems/manage/licensing/usage.py#L94)).

Backups, updates and audit recording work in every edition ([spec, Preserved](../specs/editions.md#preserved)).

### 5.2 See your edition and use

1. Open **Manage** → **Updates & licensing**.
2. Find the panel **Edition and license** ([license-panel.tsx:80](../../frontend/src/components/systems/manage/components/license-panel.tsx#L80)).

| Part of the panel | What it shows |
|---|---|
| **Edition** | The edition name. With a license file, also "Licensed to" and your organization's name in the file ([license-panel.tsx:114-125](../../frontend/src/components/systems/manage/components/license-panel.tsx#L114)). |
| **License** | The license state. See the table below ([license-panel.tsx:126-129](../../frontend/src/components/systems/manage/components/license-panel.tsx#L126)). |
| "Use against the limits of" your edition | A table with the columns **Item**, **Used** and **Limit**. A number in the **Used** column in red is at or above its limit. "No limit" means that the edition has no limit for that item ([license-panel.tsx:131-169](../../frontend/src/components/systems/manage/components/license-panel.tsx#L131); [license-rules.ts:29-38](../../frontend/src/components/systems/manage/domain/license-rules.ts#L29)). |
| **Editions** | The three editions with their prices. Your edition shows "· Current" ([license-panel.tsx:170-194](../../frontend/src/components/systems/manage/components/license-panel.tsx#L170)). |

The **License** row shows one of these states ([license-rules.ts:47-63](../../frontend/src/components/systems/manage/domain/license-rules.ts#L47); [state.py:31-32](../../backend/app/systems/manage/licensing/state.py#L31), [60-76](../../backend/app/systems/manage/licensing/state.py#L60)):

| State | The **License** row shows | What it means |
|---|---|---|
| Desk | "No license file · Desk is free" | No license file. The Desk limits apply. |
| Active | "Active until" and the end date | The edition of your license file applies. |
| Grace | "Ended" and the end date, then "renew by" and a date | The license ended up to 14 days ago. The edition still applies. |
| Warning | "Ended" and the end date, then "becomes Desk on" and a date | The 30 days after the grace period. The edition still applies. Everybody sees a warning. |
| Ended | "Ended" and the end date, then "running as Desk" | The Desk limits apply. The Office features close. |
| Ended, read-only | "Ended" and the end date, then "read-only until you import a new license file" | Your use is above a Desk limit. Only administrators can change data ([state.py:133-148](../../backend/app/systems/manage/licensing/state.py#L133)). |

Slate Operations counts the days in UTC. If somebody sets the PC clock back, the license does not get more days ([state.py:106-110](../../backend/app/systems/manage/licensing/state.py#L106); [router.py:89-90](../../backend/app/systems/manage/licensing/router.py#L89)).

### 5.3 Import a license file

Get the license file from Slate Operations support. The file name ends in ".slatelicense" or ".txt" ([license-panel.tsx:84](../../frontend/src/components/systems/manage/components/license-panel.tsx#L84)). Import the file on or after its start date ([router.py:108-109](../../backend/app/systems/manage/licensing/router.py#L108)).

1. Sign in as the installation owner.
2. Open **Manage** → **Updates & licensing**.
3. In the panel **Edition and license**, select **Import license file** ([license-panel.tsx:89](../../frontend/src/components/systems/manage/components/license-panel.tsx#L89)).
4. Select the license file, then open it.
5. Wait while the button shows "Importing license file…" ([license-panel.tsx:89](../../frontend/src/components/systems/manage/components/license-panel.tsx#L89)).
6. Read the message.

When the import works, the message is "License imported. This installation now runs" and the edition name ([license-panel.tsx:53](../../frontend/src/components/systems/manage/components/license-panel.tsx#L53)). The new edition and its limits apply at once ([spec ED-1](../specs/editions.md#acceptance-criteria)). Other open pages can need up to 30 seconds ([state.py:83-86](../../backend/app/systems/manage/licensing/state.py#L83)).

When the import fails, nothing changes ([router.py:112](../../backend/app/systems/manage/licensing/router.py#L112)):

| Message | What to do |
|---|---|
| "The file is not a Slate Operations license file" ([license_file.py:48](../../backend/app/systems/manage/licensing/license_file.py#L48), [60](../../backend/app/systems/manage/licensing/license_file.py#L60)) | Select the file that Slate Operations support sent you. |
| "The license file signature is not valid for this installation" ([license_file.py:64](../../backend/app/systems/manage/licensing/license_file.py#L64)) | Do not change the file. Ask Slate Operations support for a new file. |
| "This license file version is not supported" ([license_file.py:80](../../backend/app/systems/manage/licensing/license_file.py#L80)) | Tell Slate Operations support. |
| "The license file content is not valid" ([license_file.py:91-97](../../backend/app/systems/manage/licensing/license_file.py#L91)) | Ask Slate Operations support for a new file. |
| "This license file starts later; import it on its start date" ([router.py:109](../../backend/app/systems/manage/licensing/router.py#L109)) | Import the file again on its start date. |
| "This license file has ended" ([router.py:111](../../backend/app/systems/manage/licensing/router.py#L111)) | Ask Slate Operations support for a new file. |
| "The license file could not be imported. Try again." ([license-panel.tsx:61](../../frontend/src/components/systems/manage/components/license-panel.tsx#L61)) | Try again. If the message shows again, send a support file (section 4.2). |

### 5.4 Banners

A banner can show at the top of the pages. Only one banner shows at a time, in the order of this table ([edition-banner.tsx:32-46](../../frontend/src/components/systems/shared/components/edition-banner.tsx#L32)).

| When | Who sees it | Text | What to do |
|---|---|---|---|
| Ended, read-only | Administrators | "The license ended on &lt;date&gt;. Only administrators can change data until you import a new license file or reduce use to the Desk limits." | Import a new license file, or reduce use below each Desk limit. |
| Ended, read-only | Everybody else | "Slate Operations is read-only. The license ended on &lt;date&gt;; your administrator can renew it." | Nothing. The administrator renews. |
| Warning | Everybody | "The license ended on &lt;date&gt;. On &lt;date&gt; this installation becomes Desk." | Import a new license file. |
| Grace | Administrators | "The license ended on &lt;date&gt;. Renew it by &lt;date&gt;." | Import a new license file. |
| A limit is at 80% or more | Administrators | The item, the use and the limit, for example "Records in a module: 800 of 1,000 used on Desk." | Reduce use, or get Office or Headquarters. |

On the limit banner, another administrator also sees "The installation owner can upgrade." The installation owner sees the link **Upgrade or renew**. It opens **Updates & licensing** ([edition-banner.tsx:42-61](../../frontend/src/components/systems/shared/components/edition-banner.tsx#L42); [license-rules.ts:74-89](../../frontend/src/components/systems/manage/domain/license-rules.ts#L74)).

### 5.5 When you reach a limit

Slate Operations refuses only an action that adds an item above a limit. It deletes nothing. Your records, sheets and people stay, and they keep working ([limits.py:1-4](../../backend/app/systems/manage/licensing/limits.py#L1); [spec, Preserved](../specs/editions.md#preserved)).

The message names the edition, the limit and the next step ([limits.py:34-56](../../backend/app/systems/manage/licensing/limits.py#L34)). For example: "Desk allows 1,000 records in a module. To add more, upgrade in Manage → Updates & licensing."

| Action | Limit | Where the message shows |
|---|---|---|
| Invite a person, restore a person, change a guest to a member | People, guests | In the dialog or panel ([people.ts:793](../../frontend/src/components/systems/access/helpers/people.ts#L793); [invite-person-dialog.tsx:351](../../frontend/src/components/systems/access/components/invite-person-dialog.tsx#L351); [person-account.tsx:322](../../frontend/src/components/systems/access/components/person-account.tsx#L322); [person-details.tsx:387](../../frontend/src/components/systems/access/components/person-details.tsx#L387); [spec ED-3](../specs/editions.md#acceptance-criteria)) |
| Create or import records | Records in a module | In the dialog ([record-create-dialog.tsx:161](../../frontend/src/components/systems/openview/components/record-create-dialog.tsx#L161); [record-import-failure.ts:20](../../frontend/src/components/systems/platform/helpers/record-import-failure.ts#L20)) |
| Create, import or copy a sheet | Sheets, rows in a sheet | In the dialog ([sheet-lists.tsx:112](../../frontend/src/components/systems/openview/components/sheet-lists.tsx#L112); [sheet-import-dialog.tsx:139](../../frontend/src/components/systems/openview/components/sheet-import-dialog.tsx#L139); [sheet-copy-dialogs.tsx:69](../../frontend/src/components/systems/openview/components/sheet-copy-dialogs.tsx#L69)) |
| Add a row in the sheet grid | Rows in a sheet | "The row could not be added. Try again." ([sheet-page.tsx:493](../../frontend/src/components/systems/openview/components/sheet-page.tsx#L493)) |
| Publish a Sandbox draft that adds a department, a module or, on Desk, a trigger | Published departments, modules in a department, automations | "We could not confirm this change. Your password and note are still here so you can try again." ([review-publish-dialog.tsx:247](../../frontend/src/components/systems/sandbox/components/review-publish-dialog.tsx#L247), [410](../../frontend/src/components/systems/sandbox/components/review-publish-dialog.tsx#L410); [limits.py:157-170](../../backend/app/systems/manage/licensing/limits.py#L157)) |

The grid and the publish dialog do not name the limit. If you see one of those two messages, compare your use with the limits in section 5.2.

**Office features on Desk.** These features show "&lt;feature&gt;: available in Office" in place of the feature:

- OpenComms
- OpenView dashboards
- OpenView reports
- The Boards Gantt view
- The Sandbox **Triggers** section
- The Manage **Audit** tab

Sources: [edition-preview.tsx:21-46](../../frontend/src/components/systems/shared/components/edition-preview.tsx#L21), [68](../../frontend/src/components/systems/shared/components/edition-preview.tsx#L68); [spec ED-11](../specs/editions.md#acceptance-criteria).

In the Sandbox, the feature name is "Automations". The installation owner sees **See editions and prices**. Another administrator sees "Ask the installation owner to upgrade to Office." ([edition-preview.tsx:76-86](../../frontend/src/components/systems/shared/components/edition-preview.tsx#L76)). On Desk, triggers do not run. Audit recording continues ([spec ED-7](../specs/editions.md#acceptance-criteria)).

**Get below a limit.** Use one of these ways:

- Import a license file for Office or Headquarters (section 5.3).
- Disable or delete people that do not need access (section 1.6).
- Delete records, sheets or rows that you do not need.

### 5.6 Renew the license

1. Before the end date on the **License** row, ask Slate Operations support for a new license file.
2. Import the new file (section 5.3).

The new file replaces the old file ([router.py:117-124](../../backend/app/systems/manage/licensing/router.py#L117)). Your data does not change.

If you do not renew, the grace period lasts 14 days. The warning period lasts 30 more days. Then the installation runs as Desk ([state.py:31-32](../../backend/app/systems/manage/licensing/state.py#L31)). Slate Operations deletes no data.

## 6. Email settings

Slate Operations sends invitations and password resets from an email account that you own ([Copy.iss:229](../../infra/windows/installer/wizard/Copy.iss#L229)). You set up this account only in **Slate Operations settings** on the server PC ([email-setup-rules.ts:6](../../frontend/src/components/systems/manage/domain/email-setup-rules.ts#L6); [plan section 9.3](../plans/windows-installer.md#93-maintenance-mode)).

### 6.1 Check the email status

Open **Manage** → **Email**. The page shows one of these lines ([email-setup-rules.ts:33-54](../../frontend/src/components/systems/manage/domain/email-setup-rules.ts#L33)):

| Status | Meaning |
|---|---|
| "Email is not set up." | "Invitations and password emails cannot be sent until it is." |
| "Email is set up." | No email went out recently, so Slate Operations cannot confirm it. |
| "Email is working." | Email works. |
| "Email is not working." | "Check the email settings on the server PC." |

### 6.2 Set up or change email

Have these items ready: the email address, its password or app password, and for other providers the server name and port.

For Gmail, first turn on 2-Step Verification for the account. Then make an app password. Use the app password, not your normal password ([Copy.iss:235](../../infra/windows/installer/wizard/Copy.iss#L235); [email-setup-panel.tsx:205-221](../../frontend/src/components/systems/manage/components/email-setup-panel.tsx#L205)).

1. On the server PC, open the Start menu.
2. Open **Slate Operations settings** ([email-setup-panel.tsx:179-185](../../frontend/src/components/systems/manage/components/email-setup-panel.tsx#L179)).
3. Select **Set up email** ([Copy.iss:496](../../infra/windows/installer/wizard/Copy.iss#L496)).
4. In **Send from**, type the email address ([Copy.iss:230](../../infra/windows/installer/wizard/Copy.iss#L230)).
5. In **Provider**, select **Gmail** or **Other** ([Copy.iss:231-233](../../infra/windows/installer/wizard/Copy.iss#L231)).
6. For Gmail, type the **App password** ([Copy.iss:238](../../infra/windows/installer/wizard/Copy.iss#L238)).
7. For **Other**, fill in **Server**, **Port**, **Security**, **User name** and **Password** ([Copy.iss:239-246](../../infra/windows/installer/wizard/Copy.iss#L239)).
8. Select **Send test email** ([Copy.iss:248](../../infra/windows/installer/wizard/Copy.iss#L248)).
9. Check the administrator's inbox and its Spam folder ([Copy.iss:512](../../infra/windows/installer/wizard/Copy.iss#L512)).

The **Set up email** screen uses the same fields as setup ([Wizard.iss:6920](../../infra/windows/installer/wizard/Wizard.iss#L6920)). When it is done, it says "Slate Operations sends email from %1 now." ([Copy.iss:510](../../infra/windows/installer/wizard/Copy.iss#L510))

For **Security**, the usual choices are "SSL/TLS (usually port 465)" and "STARTTLS (usually port 587)" ([Copy.iss:244-245](../../infra/windows/installer/wizard/Copy.iss#L244)).

"Outlook.com accounts cannot send email for Slate Operations." ([Copy.iss:250](../../infra/windows/installer/wizard/Copy.iss#L250))

When you change the Gmail account password, Google cancels its app passwords. Then do this procedure again with a new app password ([plan section 2](../plans/windows-installer.md#2-current-state), Gmail item; [plan section 9.3](../plans/windows-installer.md#93-maintenance-mode)).

## 7. Uninstall

Ask Slate Operations support before you uninstall. A reinstall with kept data needs the same or a newer setup file ([Copy.iss:476](../../infra/windows/installer/wizard/Copy.iss#L476)).

### 7.1 Uninstall and keep your data

1. On the server PC, open Windows **Settings** → **Apps** ([Copy.iss:445](../../infra/windows/installer/wizard/Copy.iss#L445)).
2. Find **Slate Operations**, then select **Uninstall** ([plan section 9.1](../plans/windows-installer.md#91-uninstall)).
3. On **Uninstall Slate Operations**, select **Keep my data (recommended)** ([Copy.iss:448-449](../../infra/windows/installer/wizard/Copy.iss#L448)).
4. Select **Uninstall** ([Copy.iss:454](../../infra/windows/installer/wizard/Copy.iss#L454)).

"Slate Operations is removed. Your records, files and settings stay in %1 (%2 GB)." ([Copy.iss:450](../../infra/windows/installer/wizard/Copy.iss#L450)) In this message, "%1" is your data folder and "%2" is the size of the data.

To continue later, run setup again and choose the same data folder. Setup offers **Use the kept data** ([Copy.iss:473-474](../../infra/windows/installer/wizard/Copy.iss#L473)).

### 7.2 Uninstall and delete everything

**Caution:** this deletes all records, files and settings of Slate Operations on this PC. It cannot be undone ([Copy.iss:457](../../infra/windows/installer/wizard/Copy.iss#L457)). Make an encrypted copy first (section 2.5), if you want to keep the data.

1. Do steps 1 and 2 of section 7.1.
2. Select **Delete everything** ([Copy.iss:451](../../infra/windows/installer/wizard/Copy.iss#L451)).
3. To delete the backups too, select **Also delete the backups on %1** ([Copy.iss:453](../../infra/windows/installer/wizard/Copy.iss#L453)).
4. Select **Uninstall**.
5. In **Delete all Slate Operations data?**, select **I understand that this cannot be undone** ([Copy.iss:455](../../infra/windows/installer/wizard/Copy.iss#L455), [407](../../infra/windows/installer/wizard/Copy.iss#L460)).
6. Select **Delete everything** ([Copy.iss:461](../../infra/windows/installer/wizard/Copy.iss#L461)).

If you do not select step 3, the backups stay on the backup drive ([Copy.iss:458](../../infra/windows/installer/wizard/Copy.iss#L458)).

### 7.3 What stays on the PC

"Virtual Machine Platform and Windows Subsystem for Linux (WSL) stay on this PC, because other programs can use them." ([Copy.iss:467](../../infra/windows/installer/wizard/Copy.iss#L467))

If uninstall cannot remove an item, it says so. Setup removes the item the next time it runs ([Copy.iss:468](../../infra/windows/installer/wizard/Copy.iss#L468)).
