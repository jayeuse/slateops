# Slate Operations administrator guide

> **Draft.** This guide describes the current build of Slate Operations.
>
> **Blanks to fill:** [support contact], [support hours], [backup drive], [recovery key location], [how you get a new setup file].

## About this guide

This guide is for the administrator of your organization in Slate Operations. Your support provider installed Slate Operations on one Windows 11 PC in your office. This guide calls that PC the **server PC**.

Each statement has a source in parentheses. A source is a screen text in the product files, a runbook section, or a plan section. Your support provider uses the sources to check the guide. You can ignore them.

Text in square brackets, for example [support contact], is a blank. Your support provider fills each blank before you get this guide.

### Words in this guide

| Word | Meaning |
|---|---|
| Administrator | A person with the role "Administrator" in your organization ([people.ts:41](../../frontend/src/components/systems/access/helpers/people.ts#L41)). |
| Installation owner | The administrator that setup created. This account also manages backups and updates ([08-authentication-authorization.md](../architecture/08-authentication-authorization.md), "Only the organization owner"). |
| Server PC | The Windows 11 PC that runs Slate Operations for your office ([Copy.iss:38](../../infra/windows/installer/wizard/Copy.iss#L38)). |
| Slate Operations settings | The program on the server PC for email, backups, repair and reports ([SlateOpsSetup.iss:121](../../infra/windows/installer/SlateOpsSetup.iss#L121)). |
| Support provider | The person or company that installed Slate Operations for you. Contact: [support contact], [support hours]. |

### Where to find things

| Task | Where |
|---|---|
| Invite people, make groups, give access | Slate Operations → **Access** ([workspace-navigation.ts:62-73](../../frontend/src/components/workspace-navigation.ts#L62)) |
| Check backups and updates | Slate Operations → **Manage** → **Backup**, **Updates & licensing** ([workspace-navigation.ts:88-104](../../frontend/src/components/workspace-navigation.ts#L88)) |
| Check whether Slate Operations works | Slate Operations → **Manage** → **System health** ([workspace-navigation.ts:97](../../frontend/src/components/workspace-navigation.ts#L97)) |
| Set up email, change the backup drive, repair | Server PC → Start menu → **Slate Operations settings** ([SlateOpsSetup.iss:121](../../infra/windows/installer/SlateOpsSetup.iss#L121)) |
| Make a file for support | Server PC → Start menu → **Slate Operations - Save report** ([SlateOpsSetup.iss:122](../../infra/windows/installer/SlateOpsSetup.iss#L122)) |
| Uninstall | Windows **Settings** → **Apps** ([Copy.iss:392](../../infra/windows/installer/wizard/Copy.iss#L392)) |

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

### 1.5 Invite a guest

A guest reads only, for a limited time. Each guest has a sponsor in your organization ([invite-person-dialog.tsx:141](../../frontend/src/components/systems/access/components/invite-person-dialog.tsx#L141)).

1. Do steps 1 to 3 of section 1.4.
2. Select the **Role** "Guest".
3. Select the sponsor ([invite-person-dialog.tsx:283](../../frontend/src/components/systems/access/components/invite-person-dialog.tsx#L283)).
4. Type the **Access length in days**, from 1 to 365 ([invite-person-dialog.tsx:496](../../frontend/src/components/systems/access/components/invite-person-dialog.tsx#L496); [people.ts:503-504](../../frontend/src/components/systems/access/helpers/people.ts#L503)).
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

If email works, select **Forgot password?** on the sign-in page ([login/page.tsx:150](../../frontend/src/app/login/page.tsx#L150)). If email does not work, reset the password on the server PC:

1. On the server PC, open the Start menu.
2. Open **Slate Operations settings**.
3. Select **Reset the admin password** ([Copy.iss:340](../../infra/windows/installer/wizard/Copy.iss#L340)).
4. Type the **New password**, then type it again in **Type it again** ([Copy.iss:342-343](../../infra/windows/installer/wizard/Copy.iss#L342)).
5. Select **Change password** ([Copy.iss:344](../../infra/windows/installer/wizard/Copy.iss#L344)).
6. Sign in with the new password ([Copy.iss:347](../../infra/windows/installer/wizard/Copy.iss#L347)).

The password must have 12 to 72 characters ([Copy.iss:348](../../infra/windows/installer/wizard/Copy.iss#L348)). This action resets only the administrator that setup created ([Copy.iss:350](../../infra/windows/installer/wizard/Copy.iss#L350)).

## 2. Backups and restore

**Who can do this.** Only the installation owner opens **Manage** → **Backup**. Another administrator sees "Backup is managed by the installation owner." ([manage-unavailable.tsx:19-20](../../frontend/src/components/systems/manage/components/manage-unavailable.tsx#L19))

### 2.1 What setup made

1. Slate Operations makes a backup every night at 2:00 ([Copy.iss:264](../../infra/windows/installer/wizard/Copy.iss#L264)).
2. It keeps each backup for 30 days ([policy_default.py:14-15](../../backend/app/systems/manage/backups/policy_default.py#L14)).
3. The backups go to [backup drive].
4. The backups are locked. A recovery key opens them if the server PC breaks or is lost ([Copy.iss:357](../../infra/windows/installer/wizard/Copy.iss#L357)).
5. Setup showed the recovery key one time, to print or to save ([Copy.iss:358](../../infra/windows/installer/wizard/Copy.iss#L358)). The key is at [recovery key location].

Keep the recovery key away from the server PC and away from the backup drive ([Copy.iss:358](../../infra/windows/installer/wizard/Copy.iss#L358)).

If the backups go to a USB drive, keep it plugged in. "A backup fails while the drive is out." ([Copy.iss:271](../../infra/windows/installer/wizard/Copy.iss#L271))

**Outage.** Slate Operations is offline while a backup runs ([backup-panel.tsx:426-427](../../frontend/src/components/systems/manage/components/backup-panel.tsx#L426)). The nightly backup at 2:00 is outside normal office hours.

### 2.2 Check the backups

Open **Manage** → **Backup**. The **Status** shows four rows ([backup-status-panel.tsx:90-99](../../frontend/src/components/systems/manage/components/backup-status-panel.tsx#L90)):

| Row | What it shows |
|---|---|
| Schedule | For example, On · Daily at 02:00 · Kept 30 days ([backup-rules.ts:60-63](../../frontend/src/components/systems/manage/domain/backup-rules.ts#L60)) |
| Last good backup | The time, then "Verified" or "Not verified yet" ([backup-rules.ts:94-96](../../frontend/src/components/systems/manage/domain/backup-rules.ts#L94)) |
| Service | "Available", or a problem word such as "Not checked in recently" ([backup-rules.ts:27-33](../../frontend/src/components/systems/manage/domain/backup-rules.ts#L27)) |
| Queue | The backups that wait or run ([backup-rules.ts:64-67](../../frontend/src/components/systems/manage/domain/backup-rules.ts#L64)) |

**History** lists every backup. Each one has a status: Queued, Running, Completed, Verified, Failed, Interrupted or Expired ([backup-rules.ts:146-159](../../frontend/src/components/systems/manage/domain/backup-rules.ts#L146)).

Check the **Last good backup** row regularly. If it is older than two days, tell your support provider.

### 2.3 Change the schedule

1. Open **Manage** → **Backup**.
2. Select **Edit schedule** ([backup-status-panel.tsx:64](../../frontend/src/components/systems/manage/components/backup-status-panel.tsx#L64)).
3. In **Schedule**, select "Disabled", "Daily at 02:00" or "Weekly on Sunday at 02:00" ([backup-api.ts:356-360](../../frontend/src/components/systems/manage/adapters/backup-api.ts#L356)).
4. In **Keep backups for**, select 7, 30 or 90 days ([backup-schedule-dialog.tsx:31-35](../../frontend/src/components/systems/manage/components/backup-schedule-dialog.tsx#L31)).
5. Select **Save schedule** ([backup-schedule-dialog.tsx:269](../../frontend/src/components/systems/manage/components/backup-schedule-dialog.tsx#L269)).

"Old backups are removed only after a newer backup is checked." ([backup-schedule-dialog.tsx:92](../../frontend/src/components/systems/manage/components/backup-schedule-dialog.tsx#L92))

**Caution:** do not select "Disabled". Without backups, a broken disk loses your data.

### 2.4 Make a backup now

Make a backup before a large change, for example before an update.

**Caution:** Slate Operations goes offline while this backup runs. Tell your people before you start ([backup-panel.tsx:426-427](../../frontend/src/components/systems/manage/components/backup-panel.tsx#L426)).

1. Open **Manage** → **Backup**.
2. Select **Back up now** ([backup-status-panel.tsx:81](../../frontend/src/components/systems/manage/components/backup-status-panel.tsx#L81)).
3. Type a **Backup name** ([backup-panel.tsx:442](../../frontend/src/components/systems/manage/components/backup-panel.tsx#L442)).
4. Select **Back up now** ([backup-panel.tsx:486](../../frontend/src/components/systems/manage/components/backup-panel.tsx#L486)).

The backup goes into the queue. The backup service starts it within about one minute ([infra/supabase/RESTORE.md, "Run the installation backup policy"](../../infra/supabase/RESTORE.md#run-the-installation-backup-policy); [plan section 2](../plans/windows-installer.md#2-current-state), Backup row).

### 2.5 Make an encrypted copy

You can download one backup as an encrypted file, for example to keep a copy in another place.

1. Open **Manage** → **Backup**.
2. In **History**, select a backup with the status "Verified".
3. Select **Prepare encrypted backup** ([backup-detail.tsx:170](../../frontend/src/components/systems/manage/components/backup-detail.tsx#L170)).
4. Type a **Passphrase** with 16 to 128 printable characters ([backup-export.tsx:364](../../frontend/src/components/systems/manage/components/backup-export.tsx#L364)).
5. Type it again in **Confirm passphrase** ([backup-export.tsx:372](../../frontend/src/components/systems/manage/components/backup-export.tsx#L372)).
6. Select **Prepare encrypted backup** ([backup-export.tsx:427](../../frontend/src/components/systems/manage/components/backup-export.tsx#L427)).
7. When the copy is ready, select **Download encrypted backup** ([backup-export.tsx:212](../../frontend/src/components/systems/manage/components/backup-export.tsx#L212)).
8. Type your current password, then confirm ([backup-export.tsx:480](../../frontend/src/components/systems/manage/components/backup-export.tsx#L480)).

**Caution:** keep the passphrase in a safe place. The file is encrypted with it, and the copy cannot be opened without it ([infra/supabase/RESTORE.md, "Run the installation backup policy"](../../infra/supabase/RESTORE.md#run-the-installation-backup-policy)).

The download stops when the copy expires. The copy expires 24 hours after it is ready ([backup-export.tsx:189](../../frontend/src/components/systems/manage/components/backup-export.tsx#L189); [infra/supabase/RESTORE.md, "Run the installation backup policy"](../../infra/supabase/RESTORE.md#run-the-installation-backup-policy)).

### 2.6 Change the backup drive

**Caution:** a new backup drive has its own lock. The old recovery key does not open it. Have a printer or a USB drive ready to save the new key ([Copy.iss:463](../../infra/windows/installer/wizard/Copy.iss#L463)).

1. On the server PC, connect the new drive.
2. Open the Start menu, then open **Slate Operations settings**.
3. Select **Change backup drive** ([Copy.iss:445](../../infra/windows/installer/wizard/Copy.iss#L445)).
4. Select the new drive.
5. Save the new recovery key when setup shows it.

Backups go to the new drive from the next night at 2:00 ([Copy.iss:464](../../infra/windows/installer/wizard/Copy.iss#L464)).

### 2.7 Make a new recovery key

Make a new key when the old key is lost, or when a person who left knows it.

**Caution:** "Your current recovery key stops working." Have a printer or a USB drive ready ([Copy.iss:494](../../infra/windows/installer/wizard/Copy.iss#L494)).

1. On the server PC, open **Slate Operations settings**.
2. Select **Make a new recovery key** ([Copy.iss:447](../../infra/windows/installer/wizard/Copy.iss#L447)).
3. Confirm the change.
4. Print or save the new key.
5. Destroy the old key.

### 2.8 When a backup fails

After a failed backup, Slate Operations tries to start again by itself, up to 3 times ([fail_open.py:18](../../backend/operations/backups/fail_open.py#L18), [43](../../backend/operations/backups/fail_open.py#L43)).

These messages need action:

| Where | Message | What to do |
|---|---|---|
| **Slate Operations settings** | "Needs attention: plug in the backup drive (%1)." ([Copy.iss:432](../../infra/windows/installer/wizard/Copy.iss#L432)) | Plug in the backup drive. If the message stays, select **Repair**. |
| **Slate Operations settings** | "Needs support." ([Copy.iss:433](../../infra/windows/installer/wizard/Copy.iss#L433)) | Make a report (chapter 4). Send it to [support contact]. |
| **Manage** → **Backup** | "The person who runs your server must run backup recovery." ([backup-rules.ts:43-44](../../frontend/src/components/systems/manage/domain/backup-rules.ts#L43)) | Tell your support provider. |

In this table, "%1" is the letter of your backup drive.

### 2.9 Restore a backup

Your support provider does each restore. The restore uses a remote session and command-line tools ([infra/supabase/RESTORE.md](../../infra/supabase/RESTORE.md); [plan section 8.4](../plans/windows-installer.md#84-restore-in-v1)).

**Unverified:** no restore has been tested on a Windows installation yet. The deployment map marks Windows server operation and restore acceptance as pending ([Deployment architecture](../architecture/12-deployment-architecture.md#deployment-state-map); [plan section 8.4](../plans/windows-installer.md#84-restore-in-v1)). Keep the backup drive and the recovery key safe until a Windows restore is proven.

1. Write to [support contact].
2. Tell the support provider which date to go back to.
3. Allow the remote session when the support provider asks.
4. Tell your people that each person must sign in again after the restore.

A restore signs out every person ([infra/supabase/RESTORE.md, "Rebind while ingress is closed"](../../infra/supabase/RESTORE.md#rebind-while-ingress-is-closed)). Changes made after the backup are not in the restored data.

The **Restore procedure** link in a backup's details opens the runbook for your support provider ([backup-detail.tsx:115](../../frontend/src/components/systems/manage/components/backup-detail.tsx#L115)). You do not do these steps.

## 3. Updates

**Who can do this.** Only the installation owner opens **Manage** → **Updates & licensing**. Another administrator sees "Updates are managed by the installation owner." ([manage-unavailable.tsx:21-22](../../frontend/src/components/systems/manage/components/manage-unavailable.tsx#L21))

### 3.1 Check your version

Open **Manage** → **Updates & licensing**. The **Installation** panel shows these rows ([updates-panel.tsx:44-77](../../frontend/src/components/systems/manage/components/updates-panel.tsx#L44)):

| Row | What it shows |
|---|---|
| Version | The version that runs now |
| Release check | The result of the last check for a new release |
| Latest release | A newer release, when one is known |
| License | "No license required · Self-hosted" ([updates-rules.ts:9](../../frontend/src/components/systems/manage/domain/updates-rules.ts#L9)) |
| Limits | "None · capacity depends on your server" ([updates-rules.ts:10](../../frontend/src/components/systems/manage/domain/updates-rules.ts#L10)) |

Select **Refresh release status** to read the latest check again ([updates-panel.tsx:118](../../frontend/src/components/systems/manage/components/updates-panel.tsx#L118)).

**This build shows no update prompt.** The release check reads only published, stable releases ([backup_runner.py:69-97](../../backend/operations/backup_runner.py#L69)). Your support provider tells you when an update is ready. The **Release check** row can show "The release check is not available" ([updates-rules.ts:15](../../frontend/src/components/systems/manage/domain/updates-rules.ts#L15)) (unverified).

### 3.2 Install an update

The person who runs your server installs updates ([page.tsx:520](../../frontend/src/components/systems/manage/page.tsx#L520)). Usually your support provider does it. You can also do it with the new setup file. You get the file by [how you get a new setup file].

**Caution:** "People cannot use Slate Operations while it updates. This can take up to 1 hour." ([Copy.iss:472](../../infra/windows/installer/wizard/Copy.iss#L472))

1. Tell your people when the update starts.
2. On the server PC, open the new setup file.
3. Allow the change when Windows asks for permission ([SlateOpsSetup.iss:31](../../infra/windows/installer/SlateOpsSetup.iss#L31)).
4. On **Update Slate Operations**, read the two version numbers ([Copy.iss:469-470](../../infra/windows/installer/wizard/Copy.iss#L469)).
5. Select **Update now** ([Copy.iss:473](../../infra/windows/installer/wizard/Copy.iss#L473)).
6. Keep the server PC on until setup shows the result.

"Setup makes a backup before it changes anything." If the update fails, Slate Operations goes back to the old version by itself ([Copy.iss:471](../../infra/windows/installer/wizard/Copy.iss#L471)).

| Result | What to do |
|---|---|
| "Slate Operations is updated to version %1." ([Copy.iss:479](../../infra/windows/installer/wizard/Copy.iss#L479)) | Nothing. Tell your people. |
| "The update did not work. Slate Operations went back to version %1. Everybody must sign in again." ([Copy.iss:480](../../infra/windows/installer/wizard/Copy.iss#L480)) | Tell your people to sign in again. Tell your support provider. |
| "The update did not work. Slate Operations still runs version %1. Nothing changed." ([Copy.iss:481](../../infra/windows/installer/wizard/Copy.iss#L481)) | Tell your support provider. |
| Any message that says "Select Save report" ([Copy.iss:482-483](../../infra/windows/installer/wizard/Copy.iss#L482)) | Select **Save report**. Send the file to [support contact]. |

If setup says that Slate Operations is busy, wait. Setup tries again by itself ([Copy.iss:478](../../infra/windows/installer/wizard/Copy.iss#L478)).

The **Update procedure for this release** link on the Updates page is for your support provider ([updates-panel.tsx:102](../../frontend/src/components/systems/manage/components/updates-panel.tsx#L102)).

## 4. Reports for support

Two files help your support provider find a problem. Neither file is sent automatically.

| File | Use it when |
|---|---|
| **Save report** on the server PC | Slate Operations does not open, setup or an update stops, or **Slate Operations settings** says "Needs support" |
| **Download support file** in the app | Slate Operations opens, but a page or an action fails |

### 4.1 Save report on the server PC

1. On the server PC, open the Start menu.
2. Select **Slate Operations - Save report** ([SlateOpsSetup.iss:122](../../infra/windows/installer/SlateOpsSetup.iss#L122)).
3. Wait. "This takes up to 3 minutes." ([Copy.iss:491](../../infra/windows/installer/wizard/Copy.iss#L491))
4. Find the file on your desktop. Its name starts with "SlateOps-report-" ([Copy.iss:625](../../infra/windows/installer/wizard/Copy.iss#L625)).
5. Send the file to [support contact].

You can also select **Save report** in **Slate Operations settings**, or on each setup screen that shows an error ([Copy.iss:19](../../infra/windows/installer/wizard/Copy.iss#L19); [plan section 10.6](../plans/windows-installer.md#106-save-report)).

The report holds no passwords, keys or business records. Email addresses and user names in it are replaced ([plan section 10.6](../plans/windows-installer.md#106-save-report); [Copy.iss:624](../../infra/windows/installer/wizard/Copy.iss#L624)).

The report works also when the server part does not answer. Then the report says "Linux part not reachable" ([plan section 10.6](../plans/windows-installer.md#106-save-report)) (unverified).

### 4.2 Download support file in the app

1. Open **Manage** → **System health**.
2. Select **Download support file** ([system-health-support-file.tsx:189](../../frontend/src/components/systems/manage/components/system-health-support-file.tsx#L189)).
3. Send the file to [support contact].

For an administrator, the file "holds no records, no personal data and nothing from other organizations" ([system-health-support-file.tsx:22](../../frontend/src/components/systems/manage/components/system-health-support-file.tsx#L22)). Only an administrator can download it ([system-health-support-file.tsx:37](../../frontend/src/components/systems/manage/components/system-health-support-file.tsx#L37)).

When an action fails, its message can show a reference. Send that reference with the file ([page-guides.ts:60](../../frontend/src/components/help/page-guides.ts#L60)).

### 4.3 Check whether Slate Operations works

**Manage** → **System health** says whether Slate Operations works now. **Parts of Slate Operations** shows the status of each part. Select **Check again** to see the latest check ([page-guides.ts:60](../../frontend/src/components/help/page-guides.ts#L60)).

On the server PC, **Slate Operations settings** also shows a status, for example "Running." or "Needs support." ([Copy.iss:431-435](../../infra/windows/installer/wizard/Copy.iss#L431)). When it says "Not ready.", select **Repair**. "Repair" sets up the Windows parts again, and your data does not change ([Copy.iss:449-450](../../infra/windows/installer/wizard/Copy.iss#L449)).

## 5. License import

License import is **not available in this build**.

This build has every feature, no editions and no limits. Nothing in it checks a license ([updates-rules.ts:9-10](../../frontend/src/components/systems/manage/domain/updates-rules.ts#L9); [plan section 2](../plans/windows-installer.md#2-current-state), Editions row). Editions and license files come in a later version.

The last setup page can name an edition and a license ([Copy.iss:380](../../infra/windows/installer/wizard/Copy.iss#L380)). Ignore that text in this build. **Manage** → **Updates & licensing** shows the correct state.

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
3. Select **Set up email** ([Copy.iss:443](../../infra/windows/installer/wizard/Copy.iss#L443)).
4. In **Send from**, type the email address ([Copy.iss:230](../../infra/windows/installer/wizard/Copy.iss#L230)).
5. In **Provider**, select **Gmail** or **Other** ([Copy.iss:231-233](../../infra/windows/installer/wizard/Copy.iss#L231)).
6. For Gmail, type the **App password** ([Copy.iss:238](../../infra/windows/installer/wizard/Copy.iss#L238)).
7. For **Other**, fill in **Server**, **Port**, **Security**, **User name** and **Password** ([Copy.iss:239-246](../../infra/windows/installer/wizard/Copy.iss#L239)).
8. Select **Send test email** ([Copy.iss:248](../../infra/windows/installer/wizard/Copy.iss#L248)).
9. Check the administrator's inbox and its Spam folder ([Copy.iss:459](../../infra/windows/installer/wizard/Copy.iss#L459)).

The **Set up email** screen uses the same fields as setup ([Wizard.iss:6861](../../infra/windows/installer/wizard/Wizard.iss#L6861)). When it is done, it says "Slate Operations sends email from %1 now." ([Copy.iss:457](../../infra/windows/installer/wizard/Copy.iss#L457))

For **Security**, the usual choices are "SSL/TLS (usually port 465)" and "STARTTLS (usually port 587)" ([Copy.iss:244-245](../../infra/windows/installer/wizard/Copy.iss#L244)).

"Outlook.com accounts cannot send email for Slate Operations." ([Copy.iss:250](../../infra/windows/installer/wizard/Copy.iss#L250))

When you change the Gmail account password, Google cancels its app passwords. Then do this procedure again with a new app password ([plan section 2](../plans/windows-installer.md#2-current-state), Gmail item; [plan section 9.3](../plans/windows-installer.md#93-maintenance-mode)).

## 7. Uninstall

Ask your support provider before you uninstall. A reinstall with kept data needs the same or a newer setup file ([Copy.iss:423](../../infra/windows/installer/wizard/Copy.iss#L423)).

### 7.1 Uninstall and keep your data

1. On the server PC, open Windows **Settings** → **Apps** ([Copy.iss:392](../../infra/windows/installer/wizard/Copy.iss#L392)).
2. Find **Slate Operations**, then select **Uninstall** ([plan section 9.1](../plans/windows-installer.md#91-uninstall)).
3. On **Uninstall Slate Operations**, select **Keep my data (recommended)** ([Copy.iss:395-396](../../infra/windows/installer/wizard/Copy.iss#L395)).
4. Select **Uninstall** ([Copy.iss:401](../../infra/windows/installer/wizard/Copy.iss#L401)).

"Slate Operations is removed. Your records, files and settings stay in %1 (%2 GB)." ([Copy.iss:397](../../infra/windows/installer/wizard/Copy.iss#L397)) In this message, "%1" is your data folder and "%2" is the size of the data.

To continue later, run setup again and choose the same data folder. Setup offers **Use the kept data** ([Copy.iss:420-421](../../infra/windows/installer/wizard/Copy.iss#L420)).

### 7.2 Uninstall and delete everything

**Caution:** this deletes all records, files and settings of Slate Operations on this PC. It cannot be undone ([Copy.iss:404](../../infra/windows/installer/wizard/Copy.iss#L404)). Make an encrypted copy first (section 2.5), if you want to keep the data.

1. Do steps 1 and 2 of section 7.1.
2. Select **Delete everything** ([Copy.iss:398](../../infra/windows/installer/wizard/Copy.iss#L398)).
3. To delete the backups too, select **Also delete the backups on %1** ([Copy.iss:400](../../infra/windows/installer/wizard/Copy.iss#L400)).
4. Select **Uninstall**.
5. In **Delete all Slate Operations data?**, select **I understand that this cannot be undone** ([Copy.iss:402](../../infra/windows/installer/wizard/Copy.iss#L402), [407](../../infra/windows/installer/wizard/Copy.iss#L407)).
6. Select **Delete everything** ([Copy.iss:408](../../infra/windows/installer/wizard/Copy.iss#L408)).

If you do not select step 3, the backups stay on the backup drive ([Copy.iss:405](../../infra/windows/installer/wizard/Copy.iss#L405)).

### 7.3 What stays on the PC

"Virtual Machine Platform and Windows Subsystem for Linux (WSL) stay on this PC, because other programs can use them." ([Copy.iss:414](../../infra/windows/installer/wizard/Copy.iss#L414))

If uninstall cannot remove an item, it says so. Setup removes the item the next time it runs ([Copy.iss:415](../../infra/windows/installer/wizard/Copy.iss#L415)).
