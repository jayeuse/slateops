# Windows setup wizard: check the PC first, then install

> **Status: done (2026-11-23), PR #115; later changes in PR #121 and #122; shipped in v1.0.0.** Company record TASK-0080 (Product Designer), revised in TASK-0097. Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/specs/windows-installer-wizard.md`.

**Plan** means `docs/plans/windows-installer.md`, the technical contract. This spec owns the screens, the order and the words. Code and copy: `infra/windows/installer/wizard/` (`Copy.iss` holds every sentence).

## 1. Outcome

A person with no technical knowledge installs Slate Operations on a Windows 11 PC and knows at each step what happens and what to do next. Setup first checks the PC and changes nothing; it installs only when the check passes. From Install on, the result is a complete installation or nothing (DEC-0041). Email is set up after the install (M02).

### 1.1 Preserved

The plan's restart-before-secrets order, its secret rules (plan 3.2), the `Exec` allow-list (plan 6.2), the self-checks (plan 10.3), Save report (plan 10.6), DEC-0028, DEC-0029 (every installation starts as Desk) and DEC-0033.

### 1.2 Excluded

Windows 10, Windows 11 Home, Windows on Arm, proxies, company domain networks, and an owner-started restore.

## 2. Design rules for every screen

1. **Verdict first.** Each result screen starts with one sentence that says the result.
2. **One main action.** Next names its result ("Install").
3. **Plain words.** No technical term on a default screen (section 3).
4. **Show the work.** Each wait shows the current action, the stages and the time (6.1, 6.3, 7.6). No marquee bar.
5. **Never a dead end.** Each failure has Save report and one next step.
6. **One fixed page size.** A page never scrolls; longer lists go into a "Show all" dialog.
7. **Nothing changes without a select.** The check is read-only.
8. **Name things.** Name what setup did by its real name, never "a feature".

## 3. Words on screen (AC-4)

Default screens say "this PC", "the server part of Slate Operations", "memory", "drive", "the address" and "report". Never on a default screen: WSL, Linux, Docker, engine, distribution, VHD, SMTP, TLS, STARTTLS, port numbers, mDNS, CA, root certificate, Hyper-V, PowerShell, registry, exit code. Exceptions: the "Other" email form, an installed program name, "CA certificate" in T01, typed values, and "Virtual Machine Platform" and "Windows Subsystem for Linux (WSL)" (rule 8).

## 4. Flow (AC-1)

### 4.1 Entry: which screen setup opens with

Setup chooses its first screen from Windows-side records only (`C:\ProgramData\SlateOps`, `version.json`, `kept.json`), never from the server part. Every start goes through the administrator prompt, and the state folder must pass the folder safety check first. Setup never continues an unfinished installation (DEC-0038, DEC-0041): only a restart that setup asked for before Install continues; any other record of an earlier run is removed at start, then S01.

First screen: nothing found → S01; a restart from the check (C04 on S02) → S02 with "Welcome back"; a restart after S05, or a C04 restart on S06 or S11 → S06, then S07; installed but key not saved → S06, then S14 with a new key; any other earlier run → the removal (4.5), then S01; an installation and a newer file → M05; an installation and the same or an older file → M01; kept data in the S07 folder → the kept-data card (4.3).

Pages run in one fixed order; failures and recheck results show in place. All server work starts after Install, on S12.

### 4.2 Fresh install

S01 → S02 (check) → S04 → S05 (only when a Windows component is off) → S06 → S07 → S08 → S10 → S11 → S12 → S14 → S15. A Stop item turns S02 into the S03 stop. S09 is not a setup page; its form is M02.

### 4.3 Reinstall with kept data (plan 9.2)

S01 → S02 → S04 → (S05) → S07 with "Use the kept data" → S11 → S12 → S15. S08, S10 and S14 are skipped. Newer kept data stops on S07.

### 4.4 Maintenance, update and uninstall

The Start menu entry "Slate Operations settings" or Settings → Apps → Modify opens M01. A newer setup file opens M05. Settings → Apps → Uninstall opens U01.

### 4.5 What is on the PC at each point, and what Cancel does

Before any change, Cancel just closes; selected S02 changes (C10, C17, C29) stay. Once setup changed the PC, Cancel and "Remove and close" run **the removal**: a modal form with five limited stages (stop the install step, stop Slate Operations, remove the server part, turn off the Windows components only if setup turned them on, remove the Windows settings). Kept data is never deleted. At a limit, the next start finishes the removal. S14 and S15 have no Cancel.

## 5. The PC check (AC-2)

### 5.1 Classes

Stop (cannot be fixed here; S03), Fix (blocks until fixed), Advice ("Recommended"; does not block), Auto (setup does it during the install; listed on S11), Log (Save report only).

### 5.2 Verdict

1. Any Stop item: "This PC cannot be the Slate Operations server." S02 changes in place to S03.
2. Else any Fix item: "Fix N things, then setup can continue." Next stays off.
3. Else: "This PC is ready to be your Slate Operations server." A second line names only the missing components that setup will turn on, then one restart.

C09, C10, C12, C13, C14 and C21 rerun on S06 and on Install. An unreadable C18 is a Fix item. R7 (C18) is read again before each password use.

### 5.3 Checks

- **C01** Windows 11 build 22621 or later; Fix (older Windows 11); Stop (Windows 10)
- **C02** Pro, Enterprise or Education; Stop (Home or other)
- **C03** 64-bit Intel or AMD; Stop (Arm)
- **C04** Virtualization on, with SLAT; Fix with "Show me how" and "Restart to startup settings" (UEFI only, BitLocker caution); Stop when SLAT is missing
- **C05** 12 GiB memory that Windows can use; Stop
- **C06** Processor cores; Log
- **C07** One internal drive with 15 GB free; Fix
- **C08** Pending restart; Log
- **C09** Connected to a network; Fix
- **C10** Network is Private; Fix ("Make this network private")
- **C11** Not on a company domain; Stop
- **C12** Internet access to the image servers; no proxy; Fix
- **C13** Clock within 30 seconds; Fix
- **C14** Ports 80 and 443 free; Fix (names the program)
- **C15** Retired (DEC-0039)
- **C16** Retired from the check (DEC-0039); the address probe runs on S08 Next
- **C17** Phones can find this PC (built-in mDNS rule); Fix ("Fix it for me", Private only)
- **C18** No policy records commands (R7); Fix
- **C19** Smart App Control; Log
- **C20** Antivirus other than Defender; Advice
- **C21** Plugged in; Advice
- **C22** Lid close keeps a plugged-in laptop on; Advice; changed during S12, restored at uninstall
- **C23** Wired network; Advice
- **C24** Drive encryption; Log; Advice only for an encrypted data drive that is not C:
- **C25** Docker Desktop; Advice
- **C26** Virtual Machine Platform and WSL; Auto (S05)
- **C27** Sleep on mains power; Auto (Never; restored at uninstall)
- **C28** Fast Startup, adapters, WSL, time zone; Log
- **C29** Parts of an earlier test or uninstall; Fix ("Remove them" with Continue and Cancel); Stop for unknown parts
- **C30** Retired (DEC-0039)

Passed checks collapse into one line: "21 checks passed. Show all checks".

### 5.4 Why these answers (design question 1)

The check comes before the license. A check blocks only when the server cannot work or cannot keep a secret. S02 changes (C10, C04, C17, C29) need a select.

## 6. Screens (AC-1)

### 6.1 Frame

`WizardStyle=modern`, `WizardSizePercent=150,150`, 165% height from the [Code]. Meaningful text is `TNewStaticText`, never `TLabel`. Started programs run as the original user.

- **Layout rules (W14-D3).**
  1. **Plain text on the page.** No grey box or band behind text.
  2. **One heading level.** An item heading is "<result word>: <check name>".
  3. **Text under its heading,** then the item's buttons.
  4. **Vertical rhythm.** 4 px inside a block, 12 px between items, 16 px between blocks.
  5. **Buttons in one row,** left aligned, 8 px apart.
  6. **The main action only in the button row.** Exception: "Restart later" on S05.
  7. **Links inline** at the end of their line; a link that opens content sits on its own line.
  8. **What fits.** At most four items; the rest behind "Show N more".
  9. **Forms (S08, S09, M02, M03).** A field block is label, help line, field at full width, then its error; on S08 Password and "Type the password again" share one row, and "Show" sits at the right end of the Password label's line and shows both fields; S09 with Other selected shows Server and Port in one row, and User name and Password in one row; M02 with Other uses the same layout.
  10. **Choice rows (S07, S10).** One radio row per drive: "<name> (D:) · 239 GB free", "· Most space", "(USB drive)".
  11. **Button row.** Each button is as wide as its caption needs.
  12. **Status inside the page.** A wait beside a form shows in the page area in the one-line form.
- **Progress block (W14-D5).** Full form: bar row, stages ("Done", "Now", "Next"), current action. One-line form: "<n> of <total>: <action> · <time>".

### 6.2 Step strip (TASK-0097, owner item 4)

Four steps, "Check this PC", "Your details", "Install", "Done"; finished steps show "✓", the current one is bold and underlined. Not navigation, no tab stop. Step 1: S02 to S06; 2: S07 to S11; 3: S12; 4: S14, S15, and S06 before S14. No strip on S01, maintenance, uninstall or dialogs. If the S15 text does not fit with the strip, the strip leaves S15 and the log says so.

### 6.3 Progress bar and time (TASK-0097, owner item 3)

The bar row (`TNewProgressBar`, 0 to 1000, never marquee, plus the time text) sits above the stages.

1. Each stage has a weight in expected seconds.
2. The current stage fills by bytes, keys or time, capped at 0.9.
3. A stage ends when the next starts or it does not run.
4. **The bar never moves back.**
5. The bar is full only when the wait ends with success.
6. **A new wait starts a new bar** at 0.
7. **Failure** shows the S13 layout in place of the bar; in the removal the bar stays where it stopped.
8. **Waiting without progress:** the bar holds; the time counts.

Time text: "6:40 so far · About 22 minutes left" (never goes up), "This step takes longer than usual", "Finished in 27:40".

### Screens

- **S01** Welcome (1); What happens and how long. Next: "Check this PC".
- **S02** Check this PC (replaces 3); The check, the verdict, at most four items, "Check again".
- **S03** This PC cannot be the server; A state of S02: a polite stop.
- **S04** License agreement (2); Elastic License 2.0; no edition choice (DEC-0029).
- **S05** Restart this PC once (3a); Turns on the C26 components, then "Restart now" or "Restart later".
- **S06** Welcome back; after a setup restart.
- **S07** Where to keep your data (4); Drive with the most space selected; kept-data card.
- **S08** Your organization (5); Organization, name, email, password twice, address line with "Change".
- **S09** Email form, used by M02 (DEC-0040).
- **S10** Backups (7); largest other drive selected.
- **S11** Ready to install (9); Summary with "Change"; Install runs the recheck.
- **S12** Installing (10); Stages 1 to 16 with the bar, time left and limits.
- **S13** Setup stopped; The failure layout, in place.
- **S14** Save your recovery key (11); Print (paper only) or USB (never the backup drive); no Cancel.
- **S15** Slate Operations is ready (12); Sign in, set up email, connect phones (v1: address as text, DEC-0036).
- **M01** Slate Operations on this PC (9.3); Status first, then actions, including "Reset the admin password" (DEC-0042).
- **M02** Set up email; S09 form; test email to the administrator, then saved.
- **M03** Change backup drive; S10 form, then a new recovery key.
- **M04** Make a new recovery key; Confirmation first; the old key stops working.
- **M05** Update (7.4); backup first, then roll back on failure.
- **U01 to U04** Uninstall (9.1); Keep your data? (default keep), confirm delete, removing, result.
- **T01** Trust page (W6b; web page); `infra/caddy/trust/index.html`: trust status and device steps.

## 7. Messages by plan ID (final copy)

The final copy is in `Copy.iss`. A failure shows in the S13 layout on its page.

### 7.1 Requirements (plan 4.2)

R1 C01, R2 C02, R3 C04, R4 C05, R5 C07, R6 C10 and C11, R7 C18, R8 C12, R9 C21.

### 7.2 Pages (plan 4.1)

A failed S12 stage reads "Setup could not <stage in lower case>."

### 7.3 Email test results (plan 4.1 page 6 and 10.7)

Each M02 result shows under its field; nothing is saved on a failure.

### 7.4 Self-checks (plan 10.3)

Each self-check maps to a C item, S13, M01 or U04.

### 7.5 Failure catalog (plan 10.7)

Each failure maps to a check, an S13 sentence or an M01 line. A blocked helper shows the antivirus message.

### 7.6 Waits and progress lines (W14-D5)

Each wait has its form, stages and one line per step key (`packaging/engine/progress.py`). No sentence ends with a drive letter before its full stop.

## 8. What the person decides and what is automatic (AC-3)

The person decides the license, the S02 fixes, the restart time, kept data, the S08 details, the email account, the backup drive and saving the key. Automatic but changeable: the data folder, the program folder, the address name. Everything else is automatic.

## 9. Accessibility and clarity

1. **Keyboard.** Every action is focusable, with an access key.
2. **Screen readers.** When a check or a step ends, focus moves to its result sentence.
3. **High DPI.** The wizard scales.
4. **Color.** System colors; status is a word.
5. **Plain language.** At most 20 words per sentence.
6. **Time.** No page moves on by itself.
7. **Motion.** Only the time and the bar move.

## 10. Changes from plan section 4 (AC-5)

The check moved before the license; server work is on S12; email is in M02.

## 11. Acceptance criteria for the build

Result rule: "met" only where a merged test names the ID. WZ-4 is met (`tests/tooling/test_windows_installer.py`); WZ-11 has only a static proxy there. No other criterion is named, so each is not recorded.

- **WZ-1** The S02 verdict in about a minute; no change before S04 unless selected.
- **WZ-2** A Stop item shows S03; nothing changes.
- **WZ-3** Each Fix item has its 5.3 action; Check again changes the verdict.
- **WZ-4** No default screen shows a word from the section 3 "never" list.
- **WZ-5** Every failure shows S13 with a section 7 sentence and Save report.
- **WZ-6** M02 offers Gmail and Other; a passed test is saved.
- **WZ-7** Nothing changes between S07 and Install except a selected restart.
- **WZ-8** S12 shows the bar, every stage and the action; a step past its limit fails.
- **WZ-9** S15 lists sign-in, then email, then phones.
- **WZ-10** M01 status first; U01 defaults to "Keep my data"; delete needs U02.
- **WZ-11** Keyboard-only install; Narrator reads each verdict. No runner.
- **WZ-12** At 100%, 150% and 200% scale, no page clips or scrolls. Owner's own scale only.
- **WZ-13** C29 removes nothing until Continue.
- **WZ-14** Retired (DEC-0041). New: with no email settings, M01 shows "Set up email".
- **WZ-15** An Outlook.com address on M02 shows the note; Next stays off.
- **WZ-16** No page opens another page out of order.
- **WZ-17** Cancel after a change runs the removal; nothing setup added stays.
- **WZ-18** After a setup restart, S06 then S07; any other earlier run is removed.
- **WZ-19** S08 address line, the in-use message, and password limits show on S08.
- **WZ-20** The step strip shows on setup pages; not focusable.
- **WZ-21** The bar never moves back; time left never goes up; no "D:." on screen.

## 12. Requests beyond the plan: decided

- **1** Prepare the server part in the background; Superseded by DEC-0041: all server work on S12.
- **2** The check before the license; `MinVersion=10.0` and `ArchitecturesAllowed=x64compatible`, so Windows 10 and Arm reach S03.
- **3** "Restart to startup settings" for C04; UEFI only, `shutdown.exe /r /fw /t 0`.
- **4** The mDNS rules; C17 turns on the built-in rule; the install adds `SlateOps-mDNS-In-UDP` (DEC-0039).
- **5** The lid for C22; Recorded on S02, changed in S12, restored at uninstall.
- **6** Memory value; `TotalPhysicalMemory` ≥ 12 GiB.
- **7** Email provider detection; Windows side only; Gmail or Other (DEC-0040); runs on M02.
- **8** Check detection; a hidden helper.
- **9** Print the key without a file; file printers refused.
- **10** The QR code; From the stored address name; v1 shows the address as text (DEC-0036).
- **11** Resend a lost invitation; Superseded by DEC-0041: setup sets the admin password.
- **12** Inno Setup fit; see 6.1.
- **13** A desktop shortcut; Accepted; uninstall removes it.
- **14** An older setup file; opens maintenance mode.
- **15** Time values; planning values.

Security Engineer findings W80-1 to W80-9 are applied.

## 13. Decisions

- **WZ-D1** Address from the computer name. Superseded by DEC-0039.
- **WZ-D2** Windows-side records choose the first screen (4.1); changed by DEC-0038 and DEC-0041.
- **DEC-0038** Setup never continues an unfinished installation.
- **DEC-0039** The address comes from the organization name.
- **DEC-0040** Microsoft 365 leaves the email provider choices (Gmail or Other).
- **DEC-0041** Setup is all or nothing, without an email page.

## 14. Where each design question is answered

Sections 3, 5, 8 and 9, rule 2.4, 4.4 and S15.

## Open items

- WZ-11 and WZ-12 are not verified.
- S15 shows no QR code in v1 (DEC-0036).
