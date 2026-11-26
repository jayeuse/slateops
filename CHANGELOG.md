# Changelog

This file lists what changed in each release of Slate Operations, in plain words.

- The newest release is at the top.
- A small release uses the sections **Added**, **Changed**, **Fixed** and **Removed**. The first release (1.0.0) is grouped by feature area, because everything in it is new.
- A version number follows [docs/release-process.md](docs/release-process.md).
- Each "History" line shows how a feature grew: the first commit date, then the pull requests that built it, oldest first.
- Each pull request adds one short line under **Unreleased**. A release moves these lines under its version number.

## [Unreleased]

### Added

- A new README with a banner and a screenshot, a contributing guide, and templates for pull requests, bug reports and feature requests. (#127)
- A changelog for Slate Operations, and a rule that each pull request adds one line to it. (#127)

### Changed

- The security policy now covers the Windows setup program and the installation it makes. (#127)
- Internal: shorter agent instructions, a documentation index, and finished specs and plans cut down to their contract (about 275,000 fewer words). (#127)
- Internal: the architecture docs and the README now describe the shipped Windows setup program (its own WSL2 image with Docker Engine) and what its acceptance covers. (#127)

## [1.0.1] - 2026-11-25

This is the first published release. It is the same product as 1.0.0. The 1.0.0 release build stopped before it published (see 1.0.0 below), so 1.0.1 is the first version that customers can install.

### Fixed

- The release check that installs and then updates a test copy of Slate Operations now works on a stable version. Before, it made its two test versions only from a test (rc) number, so the 1.0.0 build stopped at this check. A stable build X.Y.Z now tests an update to X.Y.(Z+1)-rc.1 and rc.2. This change is in the release pipeline only. The setup program and the app have no change. (#125)

## [1.0.0] - 2026-11-25 (tagged, not published)

The first complete release of Slate Operations: one system that an organization designs for itself, installed on one Windows PC in its office.

Note: the tag `v1.0.0` exists, but its release build stopped at the install check, so no 1.0.0 setup program was published. Version 1.0.1 contains all of the items below. (#124)

### Install and run on a Windows server PC

- **One setup program.** `SlateOpsSetup-<version>.exe` installs everything on one Windows 11 Pro, Enterprise or Education PC (22H2 or later). A Linux part (WSL2) inside Windows runs the database, the sign-in service, file storage, the app and the web server. Phones and other PCs on the office network open the app in a browser.
- **Setup wizard.** The wizard checks the PC, shows the license agreement, restarts the PC once if Windows needs it, and asks for the data folder, the organization name, the first administrator and the backup drive. At the end it shows a recovery key one time, to print or save.
- **Trusted local address.** The app runs over HTTPS with a local certificate. A "Trust this device" page helps people connect phones and other PCs. The PC answers to a `.local` name on the office network.
- **Slate Operations settings program** on the server PC: set up email, change the backup drive, make a new recovery key, restore the latest backup, reset the administrator password, stop and start Slate Operations, start it with Windows, repair, and save a report.
- **Updates.** Run a newer setup program to update. Setup makes a backup first, and goes back to the old version by itself if the update fails. The app checks for a new stable release about every 6 hours and shows it in Manage.
- **Uninstall** from Windows Settings, with "Keep my data" or "Delete everything". Backups stay unless you also choose to delete them.
- **Signed releases.** Each release has checksums, a signed manifest and signed container images, which you can check with cosign and the GitHub CLI.
- History: production runs as one app server with no separate web process (#13, 2026-09-20); self-hosted database, sign-in and file storage (#21, 2026-09-27); Windows boot test kit (#113); Windows installer, setup wizard and settings program (#115, 2026-11-23); one-button restore (#121); Stop, Start and Start with Windows (#122).

### Editions and license files

- Every installation starts as **Desk**, the free edition. A license file unlocks **Office** or **Headquarters**. The check works with no internet connection.
- Desk limits: 2 people, no guests, 2 published departments, 3 modules in a department, 1,000 records in a module, 10 sheets, 1,000 rows in a sheet.
- Office and Headquarters add OpenComms, department dashboards, reports, automations (triggers), the Gantt view and the audit viewer, and raise or remove the limits.
- At a limit, the app blocks only the action that adds a new item. It deletes nothing.
- A license that ends goes through grace (14 days) and warning (30 days) banners, then the installation runs as Desk. Nothing is deleted. A new license file brings the edition back.
- The installation owner imports the license file in **Manage → Updates & licensing**.
- History: Elastic License 2.0 (#113); editions, license file, limits and the licensing page (#123, 2026-11-25).

### Sandbox: design your organization

- Administrators design the organization in a **draft**: departments, modules (the tables of a department), fields and links between modules. People do not see the draft until it is published.
- Four sections: **Build** (lay out departments, modules and fields on a canvas), **Triggers**, **Test** and **History**.
- Field types: text, long text, number, whole number, date, date and time, checkbox, choice list, user, email and web link. Modules can link to other modules, also in other departments.
- **Triggers** change a field on a record when something happens. **Test** tries the design and its triggers with values that you type; a test never makes real records.
- **Checkpoints** save a named copy of the draft. **History** compares two versions and restores one into the draft.
- **Review & Publish** shows the list of changes and asks for the administrator password before the change goes live.
- A newly published department gets its working parts in the same publish: three access groups (managers, members, viewers), an empty dashboard, its board, and an OpenComms channel. The review lists them first.
- Close, reopen and permanently delete departments, modules and fields.
- The draft saves as you work, through a save queue that keeps your changes in order.
- History: dynamic tables and links (first commits 2026-08-19 to 2026-08-30); first Sandbox page (2026-09-08); #8, #14 (designs that save and run), #17, #24 (schema redesign), #25 (close, reopen, delete), #29 (links between departments), #54, #61, #100 (department setup, Triggers and Test redesign), #101 (save queue), #102, #103.

### OpenView: records, saved views, dashboards and reports

- Each department has its own pages in the sidebar: **Dashboard**, **Announcements** and one page for each module.
- A module page has three tabs: **Records**, **Reports** and **Sheets**.
- **Records:** search, sort, filter, and show the list as a table, grid or gallery. Choose the columns. People with Manage save views that all readers of the module can use.
- **Record panel:** Details, Linked records, Files, History and Sheets tabs. Move to the next or previous record without closing the panel. Copy a link to a record.
- Add, change and delete records. "Create and add another" keeps the form open. The app warns you when someone else changed a record while you edited it.
- Change one choice-list or checkbox field on many records at the same time.
- A deleted record can be brought back with **Undo**, or later with the "deleted" filter. Only an administrator deletes a record forever.
- **Export** up to 10,000 records to CSV or Excel.
- **Department dashboards** show charts and numbers from the department's records. People with Manage change the layout and add widgets.
- **Reports** are saved lists of records. Make a copy now or on a schedule; each copy keeps the rows as they were. Print a copy or download it as CSV.
- History: record lists with paging and filters (first commit 2026-08-19); saved views and export (#2); #9, #15, #23, #24, #32 (record attachments), #34 (charts, dashboard widgets, batch change, export), #53, #68 (department pages), #107, #108, #109, #110.

### Sheets

- A **sheet** is your own table on a record or on a module, for notes, checklists, costs or plans. A sheet never changes the record.
- Start from a blank sheet, a template file (.json) or a data file (CSV or Excel). You check the rows of a data file before they are added.
- Column types: text, long text, number, whole number, checkbox, date, date and time, choice list, user, email, web link, link to records, lookup, from another sheet, and computed.
- Share a sheet with people or groups at **View** or **Edit**. A guest gets View only. A share gives no access to the record.
- Import, export (CSV, Excel, columns-only template), make a copy, rename, see sheet history, delete and restore.
- **My sheets** in the sidebar lists the sheets you own and the sheets shared with you.
- History: #117 (2026-11-24).

### Boards: the team space

- A **Company** board for the whole organization, one board for each department (**Announcements**), and project boards that administrators create.
- Each board has four tabs: **Posts**, **Calendar**, **Kanban** and **Gantt**.
- **Posts:** write, attach files and links, save as draft, schedule, pin, edit (with earlier revisions shown) and archive.
- **Calendar:** month and week views, all-day and repeating events, location, details and reminders. **My calendar** puts the events of all your boards in one calendar.
- **Kanban:** cards move through stages by drag and drop or by keyboard. A card can be a task or a record. Cards have details, files, linked records and activity.
- **Gantt:** cards with dates on a time line. Drag a bar or use the keyboard to change dates.
- History: #10 (2026-09-16), #15, #31 (attachments), #53, #69 (team space relayout), #96.

### OpenComms: team messages

- Channels for the whole organization or for one department, direct messages, and group messages.
- Mentions, files and records in messages, scheduled send, replies, threads, reactions, pins, edits with edit history, and delete.
- A message counts as sent only after the server accepts it. A message that fails shows **Not sent** and a **Retry** button, and your text stays in the box.
- Live delivery, presence and typing signs. Message text never goes through the live channel.
- Inbox, Activity, Threads, Starred, Browse channels and "Records you follow". Search inside a conversation. Notifications per conversation: All, Mentions or Mute.
- Administrators cannot read direct or group messages that they are not part of. An export of these messages needs the administrator's password and a reason, and the audit records it. People can report a message to the moderators.
- History: #56 (2026-10-22), #63, #65, #97 (counts and search).

### Access: people, groups and security

- Three roles: **Administrator**, **Member** and **Guest**. Groups give each department **Read**, **Write** or **Manage**. No access means the department is hidden.
- A guest can only read, for 1 to 365 days, and has a sponsor.
- Invite by email, or copy a one-time link that works for 24 hours. Resend, revoke, disable, enable, delete, restore, or set a temporary password.
- Department managers change the members of their department's groups.
- **Security:** an account policy (session timeout, password rules, allowed network addresses), two-step verification with an authenticator app, active sessions with sign-out, and sign-in history (kept 365 days by default).
- History: sign-in and access checks (first commits 2026-08-31 to 2026-09-07); #12 (sessions and invitations), #15, #21 (self-hosted sign-in), #24, #25 (security policy and two-step verification), #52, #60, #88, #99, #109 (one-step Add access).

### Manage: run the installation

- **Organization:** name, region, look and the organization profile.
- **System health:** says whether Slate Operations works now and shows the status of each part, with a history. **Download support file** makes a file for support that holds no records and no personal data.
- **Error references:** a failed action shows an eight-character reference to give to the administrator.
- **Email:** check the status and set up or change the email account.
- **Backup:** status, history, schedule (daily or weekly, kept 7, 30 or 90 days), back up now, and an encrypted copy to download.
- **Audit:** who changed what and when. Audit records are sealed so that a change to old records shows. Old records are kept in monthly parts and removed on a schedule.
- **Jobs** (background tasks) and **Updates & licensing**.
- Only the installation owner manages backups, updates and the license file.
- History: organization settings (#2); #25, #34 (job list), #62 (Manage relayout), #81, #87 and #88 (error references, System health, personal history), #89, #91 (member audit page), #94, #95, #96 (audit seals), #99.

### Backups and restore

- A backup runs every night at 2:00 to the drive that you choose, and each one is checked. Backups are encrypted; the recovery key opens them if the PC is lost.
- After a failed backup, Slate Operations tries to start again by itself, up to 3 times. The settings program tells you when the backup drive is missing.
- **Restore the latest backup** with one button in the settings program. If the restore stops early, it puts the old data back.
- History: encrypted backup foundation (#12); backup runner and retention (#25); backup drive and recovery key in setup (#115); one-button restore (#121).

### Everyday use

- Sidebar with Departments, Tools, My sheets, OpenComms and your profile. A slim layout that also works on a phone.
- **Search** across records, people, posts, events, messages and files that you can read (Ctrl+K or Command+K).
- **Notifications** bell for mentions and reminders.
- **Help panel** on every page with a short guide, keyboard shortcuts and your administrator's contact.
- **Account settings:** photo, name, job title, sign-in email, password, two-step verification, sessions, color mode, motion, shortcuts, start page, timezone and date formats. A **Profile** view shows a person's details.
- **Files** page for department documents, and an **Import & export** page for administrators. Files are private and the app checks access on each download.
- A band under the top bar tells you when the app cannot reach its server, and it tries again by itself.
- Signed-out pages (sign in, password reset, invitation) use the same look, with a plain sign-in error and a new home page.
- A calm light mode, short motion only on the item you act on, and instant page changes with loading placeholders.
- History: first UI (2026-08-21); major UI overhaul (2026-09-09); #7, #16, #19, #22, #23 (instant navigation), #25 (search, import and export), #32 (department files), #50, #67 (Profile and Account settings), #108, #109, #110, #111, #112.

### Customer documents

- A quick start, an administrator guide, a user guide, a getting-help page, an editions and license page, and a data and privacy statement, in `docs/customer/`.
- History: #120.

### Changed

- The product name changed from OpenSlate to **Slate Operations** (short form: Slate Ops). (#84, #85)
- The software license is the Elastic License 2.0. (#113)

### Removed

- The file virus scan. Files are checked for type and access only. (#31)

### Behind the scenes

These items have no new screen, but they make the system faster, safer or more stable.

- **Organizations:** the system can hold more than one organization and keeps their data apart. Every edition allows 1 organization. (#52)
- **Database:** stronger data rules, faster lists (capped totals and paging), one access check per transaction, tuned server settings, and sign-in events kept in the app's own audit. (#18, #53, #81, #91, #94, #95, #96, #97, #98, #99)
- **Stability:** fixes for lost updates and deadlocks when many people work at the same time, found with large sample organizations. (#30, #64, #70, #71, #73)
- **Security work:** a security policy, dependency updates, secret scanning and pinned build actions. (#39, #40, #44, #47, #51, #57, and the dependency pull requests)
- **Tests and CI:** coverage gates, a faster and more stable CI (under 8 minutes), and root-cause fixes for unstable tests. (#6, #26, #34, #35, #72, #92, #93)
- **Sample organizations:** seven sample packs (for example a harbor business, a school and a clinic) for demos and testing. (#25, #70, #71, #73)
- **Cleanup:** dead code, unused packages, old migration chains and unused automation removed. (#32, #104, #105, #106)

[1.0.1]: https://github.com/jayeuse/slateops/releases/tag/v1.0.1
[1.0.0]: https://github.com/jayeuse/slateops/tree/v1.0.0
