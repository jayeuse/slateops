# Windows setup wizard: check the PC first, then install

Status: design spec, built on `feat/windows-installer` (W8 to W14). Company record TASK-0080 (Product Designer). Base revision `99c23876` on `feat/windows-installer`. First compared with `docs/plans/windows-installer.md` as it was on 2026-11-16 at 13:36 UTC (uncommitted edits). Revised after the Software Architect review in TASK-0080 (B-1, requests 1 to 15, departures D-2 to D-17) and two parent decisions (section 13), against the plan state of 2026-11-16, 14:29 UTC (plan 4.1 now names this spec). The plan stays the technical contract; this spec owns the screens, the order, the words and the states.

Revised on 2026-11-18 (TASK-0097) to `2cb80cb3` for four owner decisions: DEC-0038 (setup never continues an unfinished installation), DEC-0039 (the address comes from the organization name), DEC-0040 (no Microsoft 365 sender) and DEC-0041 (setup is all or nothing, without an email page). Where an earlier part of this spec and these decisions differ, the decisions win.

Revised on 2026-11-23 (TASK-0097, against the working tree on `ac98906a` with the uncommitted rc.28 fix round) for two owner requests from the rc.28 retest: a progress bar and the time on every progress surface (6.3), and a step strip at the top of every setup page with the header, and of S15 (6.2; S01 has none, see 6.2). The S12 stage list stays.

The Human Owner's request, 2026-11-16:

> "our installer should determine first whether the host machine can be used as a server, and if its sufficient enough to run as a server, only then we can do actual installation. BUT, do not just take my word literally, provide the BEST way to implement our installer wizard in a way that gives the best UX and requires little to no tech knowledge and shouldnt be confusing"

Labels: **Plan** means `docs/plans/windows-installer.md`. **Proposed** means this spec. **Assumption** means not checked; the Software Architect checks it. **Planning value** means a number that the installer report of the owner's first real install corrects (plan 10.2).

## 1. Outcome

A person with no technical knowledge installs Slate Operations on a Windows 11 PC and knows at each step what happens, how long it takes and what to do next.

1. Setup first checks whether this PC can be the server. The check changes nothing. It gives one clear verdict, then only the items that need the person.
2. Setup installs only when the check passes. When the PC is not suitable, setup stops politely, says why in plain words, says what to do instead, and changes nothing.
3. The person makes seven decisions: accept the license, the organization name, their own name, the email address they sign in with, their password, the backup drive and saving the recovery key. Everything else has a safe default, behind a "Change" link where a change is allowed.
4. Every failure screen says what happened and what to do, with Save report. Before Install, a failed step has Try again. From Install on, the result is a complete installation or nothing: a failed install has "Remove and close" (DEC-0041).
5. At the finish, the owner knows how to open the app on this PC and sign in, how to set up email, and how to connect phones.

### 1.1 Preserved

- The plan's technical order: the one restart comes before any secret (plan 4.1). The data location comes before the server part is prepared. The email test uses the engine. No secret crosses a restart: after a restart, setup asks the answers of S07 to S11 and the password again.
- The plan's rules for secrets, the named pipe and the recovery key (plan 3.2), the `Exec` allow-list (plan 6.2), the self-checks (plan 10.3) and Save report (plan 10.6).
- DEC-0028: a standard Windows setup wizard, a choice of drive and folder, a local certificate with a "Trust this device" page, and uninstall from Settings → Apps with "Keep your data?". The customer's own email account is set up after the install, in M02, with Gmail or Other (DEC-0040, DEC-0041).
- DEC-0029 and the owner's words in TASK-0076: no edition choice and no license file in the wizard or the maintenance mode. Every installation starts as Desk.
- DEC-0033: Save report on every failure screen and in the Start menu.

### 1.2 Excluded

- Code, the plan file, the trust page build (W6b), the glossary rows (W15 adds them).
- Windows 10, Windows 11 Home, Windows on Arm, proxies, a company domain network (plan 1.2, 4.2).
- An owner-started restore (plan 8.4, decision H7).
- A raster image or a real screenshot. The mockup is a code-led design mockup, not a product screen.

## 2. Design rules for every screen

1. **Verdict first.** Each result screen starts with one sentence that says the result. Details come after it.
2. **One main action.** The Next button always does the main action of the page, and its caption names the result: "Check this PC", "Install", "Send test email", "Try again".
3. **Plain words.** No technical term shows on a default screen (section 3). Technical names show only in "Details", in Save report and in the logs.
4. **Show the work.** Each wait shows what setup does now in plain words, the stages done and still to come, and the time so far when the wait can pass 10 seconds (6.1, progress block; copy in 7.6). A wait never shows only a spinner or only a bar (W14-D5): the progress bar of 6.3 always comes with the stages or the current action, and the time. No marquee bar.
5. **Never a dead end.** Each problem has a fix, a guided step, or a polite stop with what to do instead. Each failure has Save report and one next step: Try again before Install, "Remove and close" from Install on (DEC-0041).
6. **One fixed page size.** An Inno Setup page does not scroll. A page shows only what fits. Longer lists go into a "Show all" dialog.
7. **Nothing changes without a select.** The check is read-only. A "Fix it for me" action changes only what its caption says, and only after a select.
8. **Name things.** Each page names what setup did and what comes next, on the page, by the real name, with one plain line of why. Never "a feature", "the Windows feature", "something" or "a part". "Details" holds only technical extras, such as versions and codes (W14, owner on S05).

Correct: `This PC is ready to be your Slate Operations server.` then two recommendations.
Wrong: `Requirements: R1 pass, R2 pass, R3 pass, R4 pass, R5 pending, R6 warning ...`

Correct: `Setup could not set up the database.` then Save report and "Remove and close".
Wrong: `Engine step install.08.provision failed (exit 1).`

## 3. Words on screen (AC-4)

Each technical term is replaced on default screens. Where a person must meet the word in Windows Settings, the screen uses the Windows word and explains it in one short line.

| Technical term | On screen | Short explanation, when one is needed |
|---|---|---|
| Server, host machine | "the server", "this PC" | "This PC becomes the server: the other PCs and phones in your office use Slate Operations from it." |
| WSL, Linux distribution, Linux part, engine, Docker | "the server part of Slate Operations" | None. Technical names show only in Details. |
| `VirtualMachinePlatform`, WSL package | "Virtual Machine Platform" and "Windows Subsystem for Linux (WSL)", the names that Windows shows in Settings | Virtual Machine Platform: "Lets this PC run the server part of Slate Operations." WSL: "Runs the server part of Slate Operations inside Windows." |
| Virtualization, VT-x, AMD-V, SVM, SLAT | "virtualization" | "A processor setting that lets this PC run the server part." |
| BIOS, UEFI, firmware | "the PC's startup settings (BIOS)" | "A settings screen that opens before Windows starts." |
| RAM | "memory" | None |
| Disk, volume, NTFS, VHD | "drive", "free space" | None |
| Public, Private network profile | "Public network", "Private network" (the Windows words) | "Windows calls a trusted home or office network Private." |
| Domain, DomainAuthenticated | "a company network that an IT department manages" | None |
| Ports 80 and 443, listener | "the web connection that Slate Operations needs" | The screen names the program that uses it. |
| Proxy server | "a proxy server" (the Windows word) | "Some company networks send internet traffic through a proxy server." |
| mDNS, `.local`, DNS label | "the address", for example `riverside-learning.local`; the label is the "address name" (S08) | "Phones and PCs in your office open Slate Operations at this address." |
| SMTP, host, port, STARTTLS, TLS | "email account", "server", "secure connection" | Only the "Other" provider shows server, port and security, with the provider's words. |
| App password | "app password" (Google's word) | "A separate password that Google makes for one app." |
| Certificate, CA, root, trust store | "secure connection", "trust" | "Each phone and PC trusts Slate Operations once, so the browser shows no warning." |
| Trust page | "the phone code" (the QR code) and "Let this phone open Slate Operations" | None |
| Certificate fingerprint | "security code" (in Details only) | "The phone page shows the same code." |
| Boot-test kit | "an earlier Slate Operations test" | None |
| Restic, backup repository | "backups" | None |
| Recovery key | "recovery key" | "Your backups are locked. This key opens them if this PC breaks or is lost." |
| Service account `slateops-svc`, Task Scheduler | "a hidden Windows account that runs Slate Operations" (Ready page Details only) | None |
| Firewall rules | "Windows Firewall" (Ready page Details only) | None |
| PowerShell module logging policy | "a security policy that records commands" | None |
| Smart App Control | "Smart App Control" (the Windows word) | "A Windows security feature that blocks apps that are not signed." |
| Edition, Desk | "Desk, the free edition" | None |
| Run ID, log bundle | "report" | None |

Words that never show on a default screen: WSL, Linux, Docker, engine, distribution, VHD, SMTP, TLS, STARTTLS, port numbers, mDNS, CA, root certificate, Hyper-V, PowerShell, registry, exit code. Exceptions, each because the person must match a word that they see elsewhere: the "Other" email form (server, port, SSL/TLS, STARTTLS, as email providers write them); the name of a program that the person installed (for example "Docker Desktop", C25); "CA certificate" in the Android steps of T01, because the person types it into the Android Settings search; a value that the person typed (for example a server name); the two Windows component names "Virtual Machine Platform" and "Windows Subsystem for Linux (WSL)", because Windows shows them by these names (rule 8). "Details" and Save report are not default screens.

## 4. Flow (AC-1)

### 4.1 Entry: which screen setup opens with

Setup decides its first screen from Windows-side records only: the state folder `C:\ProgramData\SlateOps` (saved progress with its stage, the "key saved" mark, `windows-changes.json`; no secret, no answers and no email address, plan 10.1 item 7), the installed program's `version.json`, and `kept.json` in a data folder. It never reads a value from the server part to choose a screen (plan 3.2 rule 2). The person never chooses a mode.

**Every start goes through the normal administrator prompt**, also a start from the RunOnce entry or the desktop shortcut. Before setup reads or writes anything in `C:\ProgramData\SlateOps`, the folder must pass the folder safety check (plan W7-5). If a user who is not an administrator owns the folder, setup stops on S01 in place: "Setup cannot use the folder C:\ProgramData\SlateOps, because a user who is not an administrator owns it. Select Save report and ask the person who manages this PC." Setup reads nothing from that folder, and Next stays off.

**Setup never continues an unfinished installation** (DEC-0038, DEC-0041). Only a restart that setup asked for before Install continues (AC-W9). Every other record of an earlier run is removed at the next start, and setup starts at S01.

| What setup finds | First screen |
|---|---|
| Nothing from Slate Operations | S01 Welcome |
| Saved progress after a restart from the check before S05 ran ("Restart to startup settings" in C04, on S02) | S02 directly (S01 skipped). One line above the verdict: "Welcome back. Setup checks this PC again." The whole check runs again. |
| Saved progress after the restart of S05 (plan F4a, "Restart now" or "Restart later") | S06 Welcome back, then S07. S05 does not run again. |
| Saved progress after a restart from a recheck after S05 (C04 "Restart to startup settings" on S06 or S11; the progress has the mark "prepared") | S06 Welcome back, then S07, as after the S05 restart. Setup asks the answers of S07 to S11 and the password again: they live only in memory (plan 3.2). |
| An "install finished" mark with no "key saved" mark (setup closed or the PC stopped on S14) | S06 Welcome back ("Setup stopped before you saved the recovery key."), then S14 with a new key: the engine job `new-recovery-key` makes it, and the key that was shown before stops working. |
| Any other record of an earlier run: saved progress of another stage (for example "install started"), or Windows parts of setup with no saved progress | The removal form at once (section 4.5), with the line "An earlier setup did not finish. Setup removes everything it added, then starts again. Kept data from an earlier installation stays." Then S01. When the removal stops at a step limit, setup closes, and the next start removes the rest. |
| An installation, and this setup file is newer (SemVer precedence, plan page 1) | M05 Update |
| An installation, and this setup file is the same version or older | M01 Slate Operations on this PC (maintenance, plan page 1). An older file starts the installed setup copy with the maintenance switch, then closes. The installed setup copy is the small Windows part only; maintenance never needs the payload. |
| Kept data in the folder that S07 offers | S07 with the kept-data card (reinstall branch, section 4.3) |

An installed program is never removed at start. Data that an uninstall kept (`kept\`) is never deleted.

Pages run in one fixed order, and setup never jumps to another page. Setup skips the pages that a state does not need. A failure shows in place on the page where it happens, in the S13 layout. A recheck result shows in place, with the S02 item layout. Nothing runs in the background between pages: all server work starts after Install, on S12 (DEC-0041).

### 4.2 Fresh install

```text
 S01 Welcome ──"Check this PC"──► S02 PC check (read-only, runs at once)
                                    │
           ┌────────────────────────┼─────────────────────────────┐
           ▼                        ▼                             ▼
   Not suitable              Needs N fixes                      Ready
   S02 changes in place      items with Fix it for me,          (recommendations
   to the S03 stop           Remove them, Show me how,  ──────► can be chosen or
   (Save report, Close)      Check again; when all pass         left)
   nothing changed                                                │
                                                                  ▼
                                                  S04 License agreement
                                                                  │
                                       Windows component off? ─yes─► S05 Restart this PC once
                                                  │no                 │ restart, sign in
                                                  │                   ▼
                                                  │             S06 Welcome back (quick recheck in place)
                                                  ▼                   │
                                       S07 Where to keep your data ◄──┘
                                       (Next checks the folder only; nothing is written)
                                                  ▼
                                       S08 Your organization
                                       (organization, your name, email, password, address;
                                        Next checks that no other device uses the address)
                                                  ▼
                                       S10 Backups
                                                  ▼
                                       S11 Ready to install (quick recheck in place on Install)
                                                  ▼
                                       S12 Installing: the data folder, the server part and the
                                       install, as stages with limits ── a failure shows in place
                                                  │      in the S13 layout (Save report /
                                                  │      Remove and close)
                                                  ▼
                                       S14 Save your recovery key
                                                  ▼
                                       S15 Slate Operations is ready
                                       (open and sign in, set up email, phones)
```

S09 is not a setup page (DEC-0041). Its form is M02 in the settings program.

### 4.3 Reinstall with kept data (plan 9.2)

```text
 S01 Welcome ► S02 PC check ► S04 License ► (S05 restart if needed) ► S07 with the kept-data card
   "Use the kept data" (default)
        ├── kept version newer than setup ──► the card shows in place: "This data is from Slate
        │                                        Operations version W. Use setup version W or later."
        │                                        (nothing changed)
        └── OK ► S11 Ready (summary of the kept installation)
                 ► S12 Installing: the kept data moves back, the server part opens it
                   (kept data that cannot be opened shows in place, in the S13 layout: "Setup could
                   not open the kept data. The kept data is not changed." Save report and Remove
                   and close; the removal moves the data back to kept\)
                 ► S15 Finish (no S14: the recovery key from the first install still works)
```

S08 and S10 are skipped, because the kept data holds the answers (plan 9.2 step 4). The kept installation keeps its own email settings and its own address.

### 4.4 Maintenance, update and uninstall

```text
 Start menu "Slate Operations settings", or Settings → Apps → Modify
   ► M01 Slate Operations on this PC (status first, then actions)
       ├─ Set up email          ► M02 (S09 form: test email, then saved) ► result on M01
       ├─ Change backup drive  ► M03 (S10 form) ► drive checked ► S14 page (new recovery key) ► result; first backup at the next 2:00
       ├─ Make a new recovery key ► M04 (S14 page) ► the old key stops working
       ├─ Show the phone code  ► dialog with the QR code, the address and the security code
       ├─ Repair               ► progress ► result
       └─ Save report

 A newer setup file on a PC with Slate Operations
   ► M05 Update ► progress (backup first) ► result, or "went back to version X"

 Settings → Apps → Slate Operations → Uninstall
   ► U01 Keep your data? ─"Delete everything"─► U02 confirmation
   ► U03 Removing ► U04 result (or "Some items could not be removed")
```

### 4.5 What is on the PC at each point, and what Cancel does

Closing the window is the same as Cancel. The result of setup is a complete installation or nothing (DEC-0041).

| Point | What setup has added to this PC | Cancel asks | Cancel does |
|---|---|---|---|
| S01 to S11 while setup has changed nothing (S05 did not run and no restart from the check happened; S07 and S08 only read) | Nothing, unless the person selected a change on S02. These changes stay, because each was the person's choice: the network type (C10), the built-in rule for phones (C17), and the removal of the earlier test's parts (C29). | "Stop setup? Nothing was installed." Stop setup / Go back | Closes. |
| After a restart from the check, from S05 when it runs, and on the pages after either | The saved progress, the RunOnce entry and the desktop shortcut; from S05 on, perhaps Virtual Machine Platform and WSL. | "Stop setup? Setup removes everything it added to this PC, so nothing stays half installed." Stop setup / Go back (default) | The removal (below), then setup closes. |
| S05 "Restart later" | Same, plus the saved progress and the desktop shortcut "Continue Slate Operations setup". | None. "Restart later" is not Cancel. | Closes. The shortcut and the saved progress stay; the next start opens S06, then S07. |
| S12 while it runs | The data folder, the server part, the hidden account, the start tasks, the firewall rules, the Windows settings that the install made so far. | The same question | The removal; its first stage stops the step that runs. |
| S12 failed (S13 layout) | Same | No question | "Remove and close" and Cancel run the removal, then setup closes. |
| S06 when the next page is S14, S14, S15 | Slate Operations is installed. | No Cancel. On S14, Next stays off until the check box is checked (plan page 11, W8-4). A person with no printer and no USB drive writes the key down. | Closing on S06 or S14 keeps the saved stage, so the next start opens S06, then S14 again. |

**The removal.** One modal form, title "Removing what setup added", text "Setup removes everything it added to this PC. Kept data from an earlier installation stays.", the progress block (full form) with the bar row (6.3), five stages and the time so far, and a Close button that is off while the removal runs; the X, Alt+F4 and Escape are refused too (AC-O8). Every step has its limit, so the removal always ends, and Close turns on when it has ended or a step passed its limit. Each step has a limit; the limits below are the code values.

1. "Stop the install step that is running" (20 s).
2. "Stop Slate Operations" (20 s).
3. "Remove the server part and its data" (150 s). Kept data goes back to `kept\`; it is never deleted. When it cannot go back, the removal stops here: "Setup could not move your kept data back to its folder. The data is not changed. The next time setup starts, it tries again."
4. "Turn off Virtual Machine Platform and Windows Subsystem for Linux (WSL), if setup turned them on" (200 s). Only when `windows-changes.json` says that setup turned them on, and no other Linux distribution is registered for any user that setup can read; a failed or unclear check keeps them. Setup forces no restart. The last line then says: "Windows finishes turning off Virtual Machine Platform and Windows Subsystem for Linux (WSL) at the next restart. Setup does not restart this PC."
5. "Remove the Windows settings" (90 s): the start tasks, the hidden account and its profile, the firewall rules, and the state folder last.

At a limit the removal stops, logs the step, keeps the bar where it is, and shows: "A step took too long, so setup stopped the removal. The next time you start setup, it removes the rest." Then setup closes. The form closes by itself when it ends with nothing more to read.

## 5. The PC check (AC-2)

### 5.1 Classes

| Class | Meaning | Effect on the verdict |
|---|---|---|
| **Stop** | This PC cannot be the server, and setup cannot fix it here. | Verdict "not suitable"; S02 changes in place to the S03 stop. |
| **Fix** | Blocking, but the person, or setup after a select, can fix it now. | Verdict "needs N fixes". Next stays off until each Fix item passes. |
| **Advice** | A recommendation for a good server. It does not block. | Shown under "Recommended" on a ready verdict. |
| **Auto** | Setup does it during the install. | Not a check result. Listed on S11 under "What setup changes on this PC". |
| **Log** | Recorded for Save report only. | Never shown. |

### 5.2 Verdict

1. Any Stop item: **"This PC cannot be the Slate Operations server."** The S02 page changes in place to the S03 stop (header and content; no other page opens).
2. Else any Fix item: **"Fix N things, then setup can continue."** Next shows "Next" and stays off.
3. Else: **"This PC is ready to be your Slate Operations server."** When Virtual Machine Platform or WSL is missing, a second line says: "Setup will turn on Virtual Machine Platform and install Windows Subsystem for Linux (WSL), then restart this PC once." (only the missing ones are named)

Rules for running the checks:

- **Recheck.** The checks that can change run again, without a select, on S06 and on Install in S11: C08, C09, C10, C12, C13, C14 and C21. A new problem shows in place on that page, with the S02 item layout, and Next stays off until it is fixed.
- **Free space.** C07 (15 GB) runs on S02. S07 checks the drive that the person chooses ("This drive has 9 GB free…"). From Install on, the engine's free-space check before each writing step covers it (plan 10.7, "Disk full during the install").
- **After a C10 fix.** C14 and C17 run again by themselves, because the network type changes their result.
- **A check that cannot read its value.** C18 (R7) that cannot be read is a Fix item with the C18 message: setup must know that no policy records commands before any password moves. Other blocking checks (R1 to R9, and the F1 check C17) show as Advice "Setup cannot check this on this PC. You can continue. If setup stops later, select Save report." (`cannot_read`; C04 keeps its own message) and are logged; the later self-checks catch a real failure (plan 10.3). Any other check shows nothing and is logged.
- **R7 before each password use.** Setup reads R7 again right before each password moves: on S12 after the channel self-test and before the install job (it carries the administrator's password), and before the M02 test send. A hit, or a value it cannot read, stops the step in place with the C18 message, and nothing is sent.
- **How the check runs.** A hidden helper writes a progress file and a result file, and the page reads them on a timer (plan F4b). Each detection method stays an Assumption until W7 checks it (plan 10.4).

### 5.3 Checks

ID: this spec. Source: the plan requirement (R1 to R9), the plan section, or the boot-test precheck `infra/windows/boot-test/00-precheck.ps1` ("precheck"). Detection methods come from the plan and the precheck; new methods are Assumptions for the Software Architect (section 12).

| ID | Check | Name on screen | Class | Detection (source) | Fix | Message when not OK |
|---|---|---|---|---|---|---|
| C01 | Windows 11, build 22621 or later | Windows version | Fix (Windows 11 before 22H2); Stop (Windows 10 or older) | `CurrentBuildNumber` (R1, precheck) | Fix: "Open Windows Update" opens Settings → Windows Update. Then Check again. | Fix: "This PC has Windows 11 version 21H2. Slate Operations needs version 22H2 or later. Install the Windows updates, then select Check again." Stop: "This PC has Windows 10. Slate Operations needs Windows 11." |
| C02 | Windows edition Pro, Enterprise or Education | Windows edition | Stop (Home; decision H5 default) | `EditionID` (R2, precheck) | None in setup. S03 names the paid upgrade path. | Home: "This PC has Windows 11 Home. Slate Operations needs Windows 11 Pro, Enterprise or Education." Another edition (`edition_not_supported`): "This PC has an edition of Windows that Slate Operations cannot use. Slate Operations needs Windows 11 Pro, Enterprise or Education." |
| C03 | 64-bit Intel or AMD processor | Processor | Stop (Arm) | Processor architecture (precheck; plan 1.2 excludes Windows on Arm; 5.2 builds amd64 only) | None | Arm: "This PC has an Arm processor. Slate Operations needs an Intel or AMD processor." Another processor (`not_supported`): "This PC has a processor that Slate Operations cannot use. Slate Operations needs a 64-bit Intel or AMD processor." |
| C04 | Virtualization on, with SLAT | Virtualization | Pass when a hypervisor already runs. Fix when virtualization is off in the startup settings (also when SLAT then reads false). Stop only when virtualization is on and SLAT is false. Advice when setup cannot read it (plan R3). | `HypervisorPresent`; `VirtualizationFirmwareEnabled` and `SecondLevelAddressTranslationExtensions` (R3, precheck) | Fix: "Show me how" opens a dialog, title "Turn on virtualization", with general steps (no steps for each maker): "Virtualization is a processor setting that lets this PC run the server part." 1. "Save your work and close your other programs." 2. "Select Restart to startup settings, if setup shows it. Otherwise, restart this PC and press the startup settings key while the maker's logo shows. The key shows on the screen, often F2, F10, F12, Esc or Delete." 3. "Find the virtualization setting and turn it on. Its name can be Intel Virtualization Technology, Intel VT-x, AMD-V or SVM Mode." 4. "Save the settings and exit. Windows starts again." 5. "Sign in. If setup does not open by itself, open the setup file again." Then: "Your PC supplier can help." On a UEFI PC only, "Restart to startup settings" (`shutdown.exe /r /fw /t 0`) opens a confirmation first, title "Restart to startup settings", text (`c04_restart_confirm`): "Save your work first. This PC restarts and opens its startup settings (BIOS). Turn on virtualization there, then save and exit. Setup opens again after you sign in." Buttons: "Restart to startup settings", "Go back". When BitLocker protects C:, or setup cannot read the state of C:, both the dialog and the confirmation first say: "Caution: have your BitLocker recovery key ready. A change in the startup settings can make Windows ask for it." Setup never suspends BitLocker. Setup opens again after the restart and checks again. | Fix: "Virtualization is off. Turn it on in this PC's startup settings (BIOS). Your PC supplier can help." Stop: "This PC's processor is too old for Slate Operations." Advice: "Setup cannot read this setting. It checks it again when it prepares the server part." |
| C05 | Memory that Windows can use: 12 GiB or more (`TotalPhysicalMemory` ≥ 12,884,901,888 bytes; planning value, decided by the Software Architect) | Memory | Stop | `TotalPhysicalMemory` decides. The screen shows the installed memory from `GetPhysicallyInstalledSystemMemory`, rounded to whole GB; if that call fails, `TotalPhysicalMemory` rounded up. Setup logs both values. | None | Installed memory too small: "This PC has 8 GB of memory. Slate Operations needs a PC with 16 GB." 16 GB installed, but too much reserved: "Windows can use 11 GB of the 16 GB of memory in this PC. Slate Operations needs 12 GB that Windows can use." |
| C06 | Processor cores | — | Log | `Win32_Processor` cores and threads (plan 10.4) | — | None. The plan sets no processor minimum, and this spec invents none. The installer report shows whether a minimum is needed. |
| C07 | One drive inside this PC with 15 GB free (planning value; parent decision 2026-11-16: customer installs leave out Studio, postgres-meta and imgproxy, so the images take about 6 GB with the compressed layers; update space counts only the changed images; the log reserve equals the log caps; the rest is room for data, because the Linux disk never shrinks; the installer report corrects it) | Free space | Fix | The largest fixed NTFS drive that is not removable, network, compressed or EFS-encrypted (R5 and plan page 4, moved forward) | "Open storage settings" opens Settings → Storage. Then Check again. | "No drive in this PC has 15 GB free. The most free space is 12 GB, on the C: drive. Free up space, then select Check again." |
| C08 | A restart that Windows waits for | — | Log (owner, rc.28: setup never mandates Windows Update; other programs, such as Office Click-to-Run and printer drivers, set `PendingFileRenameOperations`, and it can stay after restarts; S05 restarts by itself when it turns on a feature) | `RebootPending`, `RebootRequired`, `PendingFileRenameOperations` (plan 10.7, precheck), which of them are set | None | — |
| C09 | Connected to a network | Network connection | Fix | A connected adapter with an IPv4 default gateway (precheck) | Guided. Then Check again. | "This PC is not connected to a network. Connect it to your office network with a cable or Wi-Fi, then select Check again." |
| C10 | The network is Private | Network type | Fix | Network category (R6, plan page 8; moved forward) | "Make this network private" with a confirmation: "Do this only on your office or home network, not on public Wi-Fi." | "Windows treats this network as Public. Slate Operations works only on a Private network, so other devices can reach this PC." |
| C11 | Not on a company domain network | Company network | Stop | Category `DomainAuthenticated` (R6, precheck) | None | "This PC is on a company network that an IT department manages. Slate Operations is not tested on such networks yet." |
| C12 | Internet access to the image servers | Internet | Fix | HTTPS to ghcr.io and the Docker Hub registry with a plain user agent (R8; github.com only in the second deliverable). Proxy: WinHTTP and user proxy settings (plan 10.4). | Guided. Then Check again. | No connection: "Setup cannot reach the internet. Connect this PC to the internet, then select Check again." Proxy: "This PC uses a proxy server. Slate Operations cannot use one yet. Connect to a network without a proxy server, or ask the person who manages your network." |
| C13 | The clock is correct within 30 seconds (planning value) | Date and time | Fix | The PC clock against the `Date` header of the internet check: the smallest difference of three samples, after half the round trip (plan 10.7, moved forward). 30 seconds, because sign-in codes change every 30 seconds. | "Open date and time settings". Then Check again. | "This PC's clock is wrong by 2 minutes. Turn on Set time automatically, then select Check again." |
| C14 | The web connection is free | Web connection | Fix | Listeners on TCP 80 and 443, with the process name (plan page 8 and 10.7; moved forward). A listener that belongs to Slate Operations passes. | Guided, with the program name. Then Check again. | "Another program on this PC uses the web connection that Slate Operations needs: World Wide Web Publishing Service. Stop or uninstall it, then select Check again." |
| C15 | Retired (DEC-0039) | — | — | The address no longer comes from the computer name. | — | — |
| C16 | Retired from the check (DEC-0039) | — | — | The mDNS probe for the address runs on S08 Next, for the address name that the person chose (S08). | — | — |
| C17 | Phones can find this PC | Phones can find this PC | Fix | DNS Client service runs; no policy turns multicast name resolution off; the built-in mDNS firewall rule allows the Private profile (plan 10.3, F1; rule names are an Assumption that W8 checks) | Rule off: "Fix it for me" turns on the existing built-in Windows rule, for Private networks only. This fix creates no rule, and logs the old state. (The install adds one rule of its own for the address, section 12 item 4.) Uninstall does not undo it. Policy sets the rule or blocks multicast: "Ask the person who manages this PC." | "Phones and other PCs cannot find this PC by its address. A Windows setting blocks it." |
| C18 | No policy records commands | Security policy | Fix (only the person who manages the PC can fix it). Also Fix when setup cannot read the policy. | PowerShell module logging policy (R7, precheck); read again before each password use (section 5.2) | "Ask the person who manages this PC" plus Save report | "A security policy on this PC records the commands that programs run. Setup cannot keep passwords private while it is on. Ask the person who manages this PC to turn it off." Unreadable: "Setup cannot check whether a security policy on this PC records commands. Ask the person who manages this PC." |
| C19 | Smart App Control state | — | Log | Smart App Control state (plan 10.4; registry name is an Assumption). With Smart App Control on, Windows blocks the unsigned setup file before the wizard opens, so no screen item can show. | None. Setup gives no advice to turn it off (plan 10.7: the owner reports a block and changes no setting). | — |
| C20 | Antivirus | Antivirus | Advice (only when a program other than Microsoft Defender is found) | `SecurityCenter2` `AntiVirusProduct` (plan 10.4) | None | "Norton is on this PC. If setup stops, allow the folder C:\Program Files\Slate Operations in Norton." (Advice names only that folder, which only administrators can change.) |
| C21 | Plugged in | Power | Advice | `Win32_Battery` (R9, precheck) | None | Laptop on mains power: "This PC is a laptop. Keep it plugged in, open and in the office. Phones cannot use Slate Operations while it is away or asleep." On battery: "This laptop runs on battery now. Plug it in." |
| C22 | Closing the lid does not stop a plugged-in laptop | Laptop lid | Advice (laptops only) | Lid close action on mains power (`powercfg` setting name is an Assumption that W7 checks) | "Change it during the install": the select only records the choice. Setup sets "When the lid is closed and the laptop is plugged in: do nothing" during the Windows-side steps of S12, beside the sleep setting. Uninstall restores it. After the select: "Setup changes this during the install." with "Undo". | "This laptop goes to sleep when you close the lid. Then Slate Operations stops for everyone." |
| C23 | Wired network | Network cable | Advice (on Wi-Fi only) | Media type of the adapter with the default route (Assumption) | None | "This PC uses Wi-Fi. A network cable is more reliable for a server." |
| C24 | Drive encryption | Drive encryption | Log when the data drive is not encrypted (DEC-0037: setup never suggests turning BitLocker on). Advice only when the data drive is not C: and is encrypted. | Status only (`ProtectionStatus`) of C: and of the data drive candidate; setup never reads key protectors and never suspends BitLocker (plan 10.4; plan 12 risk row; decision H5, changed by DEC-0037) | Advice: "Show me how" opens the BitLocker settings | Not encrypted: none (Log). Data drive is not C: and is encrypted: "Drive D: is encrypted. Turn on automatic unlock for D: in the BitLocker settings, so Slate Operations can start after a restart when nobody is signed in." |
| C25 | Docker Desktop | Docker Desktop | Advice | Program file or service (precheck) | None | "Docker Desktop is on this PC. Quit it while Slate Operations runs, so the two do not compete for memory." |
| C26 | Virtual Machine Platform and Windows Subsystem for Linux (WSL) | — | Auto | Feature state and WSL version (precheck; plan 3a) | Setup turns them on in S05. | Verdict line: section 5.2 item 3 (names only the missing ones). |
| C27 | Sleep and hibernate on mains power | — | Auto | Power settings (precheck; plan 6.2 Windows steps) | Setup sets Never; uninstall restores it (plan 9.1). | S11 Details: "Keep this PC awake when it is plugged in." |
| C28 | Fast Startup, network adapters, WSL distributions of the account, `.wslconfig`, time zone | — | Log | precheck; plan 10.4 | — | — |
| C29 | No parts of an earlier test or an earlier uninstall | Parts of an earlier test | Fix; Stop for unknown parts | Each part found: the account `slateops-svc`, the distribution `SlateOpsBootTest`, the tasks `\SlateOpsBootTest\*`, the rules `SlateOpsBootTest-*`, the folder `C:\ProgramData\SlateOpsBootTest` (plan 10.7, boot-test kit row). Parts of Slate Operations itself (tasks `\SlateOps\*`, the distribution `SlateOps`) with no `version.json`: unknown parts. | "Remove them" opens a modal form: title "Remove the parts of the earlier test?", text "Setup removes the earlier test's server part and its data, its hidden account, its start tasks and its firewall rules. The test's log files stay. Your other programs and files do not change. If the normal removal does not work, setup stops Windows Subsystem for Linux (WSL) for a moment, for every user of this PC." Buttons Continue and Cancel (default). Only Continue removes them, as the kit's cleanup does (the old disk is deleted, the logs stay). Then the item shows "Removing…", then "Removed". Setup never reuses an existing `slateops-svc`: it removes it and creates its own only after the removal (plan 10.7). The technical names show in "Details". Unknown parts: no removal; Save report. Parts of Slate Operations with no installed program but with an uninstall log are leftovers of an earlier uninstall (`uninstall_leftovers`, Fix): "Remove them" runs the uninstall's removal of the Windows parts. This item removes no data, so it runs without the C29 confirmation form. | Test parts: "This PC has parts of an earlier Slate Operations test. Setup removes them before it continues." Only the account found: "This PC has a leftover of an earlier Slate Operations uninstall. Setup removes it before it continues." Leftovers of an earlier uninstall: "This PC has parts left by an earlier Slate Operations uninstall. Setup removes them before it continues. Your data and backups do not change." Unknown parts (Stop): "This PC has parts of Slate Operations that setup cannot identify. Setup changes nothing. Select Save report and send the file to Slate Operations support." |
| C30 | Retired (DEC-0039) | — | — | The rename advice is gone: the address comes from the organization name. | — | — |

C15, C16 and C30 keep their IDs as retired rows, so the other IDs do not change.

The check never shows passed items one by one on S02. They collapse into one line: "21 checks passed. Show all checks" (the number is an example). "Show all checks" opens a dialog with every check, its name, its result word (Ready, Needs a fix, Recommended, Not suitable) and its value, for example "Memory: 16 GB. Ready."

### 5.4 Why these answers (design question 1)

- **Where.** The check is the page right after Welcome, before the license and before any change. The person learns in about a minute whether this PC can work. Nobody reads a license for a PC that cannot run the product.
- **Blocking versus recommendation.** A check blocks only when the server cannot work, or cannot keep a secret, without it. Laptops and Wi-Fi do not block: the plan allows them (R9), and the person may have no other PC. Their advice says what goes wrong in plain words.
- **Changes before the license.** Four changes can happen on S02, each only after the person selects it by name: C10 Private network (with the public Wi-Fi warning), C04 restart to the startup settings, C17 the built-in rule, and C29 the removal of the earlier test's parts (with Continue and Cancel). C22, the lid, is only recorded on S02 and changed during the install, so uninstall can restore it. Setup never stops another program, never changes the startup settings itself and never upgrades Windows for the person.
- **Not suitable.** S03 is a polite stop. It does not blame the PC or the person. It says what a suitable PC has, and it offers Save report for a supplier or support.
- **Address.** The address comes from the organization name that the person types on S08 (DEC-0039), not from this PC's name. The person sees it on S08 and can change it there; nothing on S02 is about the address.
- **Processor.** The plan has no processor minimum. A threshold without evidence would turn away PCs that work. C06 records the cores, and the installer report decides later.

## 6. Screens (AC-1)

### 6.1 Frame

- Each subtitle fits on one line; a longer explanation goes into the first line of the page.
- Inno Setup `WizardStyle=modern` with no custom style, so the Windows system colors and high contrast apply. `WizardSizePercent=150,150` (the largest value Inno Setup 6.7.4 accepts), and the [Code] makes the window 165% high (parent decision, 2026-11-18, TASK-0097 W14-D3: the email form with Other and every field must end inside the page, and at 150% it ended about 40 px too low; the form is now M02); fixed, not resizable. Welcome (S01) and Finish (S15) use the tall side image (`WizardImageFile`); other pages use the header with a title, a one-line subtitle and the small product mark. Assumption until W7 measures the real pixels: the page fits a screen of 1280 x 720 effective pixels.
- The button row: Back, Next and Cancel. Inno's bottom-left status text (`WizardForm.BeveledLabel`) stays empty; the status lines show inside the page (layout rule 12). Inno resets the Next and Cancel captions at each page change, so each page sets them when it opens and in each state.
- Pages run in one fixed order. A failure, a stop or a recheck result shows in place on its page (section 4.1). The removal (section 4.5) shows in a modal form.
- **Programs that the wizard starts** ("Open Google's page", "Open … settings", "Open About settings", "Show me how" links, "Open Slate Operations") run as the original signed-in user, never elevated, and each has a fixed target (a fixed URL or settings page, or the installation address). When setup cannot start it as the original user, the page shows the address or the steps as text instead.
- Standard controls only (Software Architect review, TASK-0080):

  | Element | Control |
  |---|---|
  | Text that carries meaning | `TNewStaticText`, never `TLabel` (a screen reader cannot read `TLabel`) |
  | A verdict or result sentence that takes focus | A read-only, borderless `TNewEdit` or `TNewMemo` |
  | Status icons | `TBitmapImage` with a PNG for each display scale; the result word stays beside it |
  | Verdict box | A `TPanel` with system colors, square corners |
  | Tags such as "Most space" | Text in the row caption: "Data (D:) · Most space" |
  | Drive lists | `TNewCheckListBox` radio rows with the free space as a sub-item, or one `TNewRadioButton` for each drive |
  | Link-style buttons ("Details", "More options", "Change", "Show all checks") | `TNewLinkLabel` (focusable) |
  | M01 actions with one line each | `TNewButton` in command-link style with a hint line |
  | Progress of a wait | The progress block (below): `TNewStaticText` lines and one `TNewProgressBar` in its normal style (6.3); never the marquee style |
  | Step strip | `TNewStaticText` captions and `TPanel` underlines (6.2); no tab stop |
  | Numbered steps on S01 and S15 | Plain "1." text |
  | Recovery key | `TNewStaticText` in a monospaced font on a panel; not a selectable field |
  | QR code | `TBitmapImage` drawn by the setup program, in whole-pixel modules |
  | "Show all checks", help dialogs, the C29 form, the removal form, U01, U02 | A modal form (`CreateCustomForm`) |
- Step strip under the header on every setup page that has the header, and on S15 (6.2). It replaces the stage line "1 Check this PC · 2 Your details · 3 Install" in the same height. It tells the person where they are in four steps, not twelve page numbers.
- Text uses the Windows system font and system colors. Status uses a word and an icon shape, and color only as an extra (section 9).
- **Layout rules (W14-D3).** Every page, form and message follows these rules. Sizes are at 100% display scale (`ScaleY`).
  1. **Plain text on the page.** Text, verdicts and result lines look like labels on the page background: no box, no grey band, no border. Acceptance: on S02, nothing grey shows between the header and the button row. (Assumption on the cause: the body panel and the text controls paint a grey color while the page surface is white; the fix takes one color from the page surface for the body panel, every text control and the verdict memo, and never `WizardForm.Color`. The engineer checks it in the Inno Setup 6.7.4 help.) The read-only verdict memo shows no caret.
  2. **One heading level.** A check item has one bold heading, "<result word>: <check name>" (for example "Recommended: Network cable"), and no separate group line ("Recommended" alone does not show). Bold is used only for the verdict sentence, item headings and field labels. Field errors, result lines and help text are regular.
  3. **Text under its heading.** An item's text sits directly under its heading, then the item's buttons.
  4. **Vertical rhythm.** 4 px inside a block (heading to text, text to its button row or link, field label to help to field, a result line under its button row); 12 px between items and between fields; 16 px between blocks (stage line, verdict block, the item list, the bottom block).
  5. **Buttons in one row.** The buttons of one item, or of one block, sit in one row from left to right in reading order, 8 px apart, left aligned.
  6. **The main action only in the button row.** Next, Install, Try again, Restart now and Finish are only in Inno's button row; the page holds the other actions. One exception: "Restart later" on S05 stays in the button row beside Back, because it closes setup like Cancel. On S01, Save report sits on the page under the message. On S15, "Open Slate Operations" sits on the page under step 1.
  7. **Links inline.** A link that belongs to a line ends that line ("23 checks passed. Show all checks"; "Report saved to your desktop: <file>. Show in folder"; "Folder: D:\SlateOps  Change folder"). A link that shows more content ("More options", "Details", "What setup changes on this PC") is on its own line, 4 px under the block it opens.
  8. **What fits.** A page never scrolls (rule 2.6). S02, S06 and S11 show items while they fit above the bottom block, at most four, Fix items first; the others go behind "Show N more".
  9. **Forms (S08, S09, M02, M03).** A field block is: label (bold), 4 px, help line (regular, only when the spec gives one; a help link ends that line, for example "Gmail needs an app password, not your normal password. How to make an app password"), 4 px, the field at full width, 4 px, the field's error or its "Show" check box. 12 px to the next field block. A radio group (Provider, Security) is one row of radio buttons at their own widths, 16 px apart, under its label. "More options" (M02) is a link on its own line 12 px under the last field; it hides once open, and the fields it opens follow the same blocks. On S08, the exception below also holds for the password row: Password and "Type the password again" share one row, each column a block (label, 4 px, field), "Show" sits at the right end of the Password label's line and shows both fields, and the password help and an error of either field follow the row at full width (parent decision, 2026-11-18, `2cb80cb3`); the address line follows the last field block, and its "Change" opens the address name block under it. S09 is the email form that M02 uses; it is not a setup page (DEC-0041). The only exception to the full width: S09 with Other selected shows Server and Port in one row, and User name and Password in one row; each field keeps its block (label, 4 px, field, 4 px), "Show" sits at the right end of the Password label's line, and only the password's error sits in the password column; every other error (Server, Security, Send from) stays under its own field or row at full width. The same layout holds for M02 with Other. Without it, Other with every field, More options and an error does not fit inside the page (parent decision, 2026-11-18; TASK-0097 W14-D3).
  10. **Choice rows (S07, S10).** One radio button per drive: "<drive name> (D:) · 239 GB free", with "· Most space" after the free space on the largest drive and "(USB drive)" after the name of a removable drive. The drive name is the name that Windows shows ("Local Disk" when the drive has none). 4 px between rows.
  11. **Button row.** Each of Inno's buttons is as wide as its caption needs ("Send test email", "Restart now", "Update now", "Try again" are never cut), never narrower than Inno's default; the row stays right aligned, and the buttons left of a wider button move left. The engineer checks the width call in the Inno Setup 6.7.4 help.
  12. **Status inside the page.** A wait beside a form (the S07 folder check, the S08 address check, the M02 test email) shows in the page area, 12 px under the page content, in the one-line form of the progress block, never in Inno's bottom-left line over the bevel. All server work waits on S12 in the full form.
- **Progress block (W14-D5).** Every wait follows rule 2.4 in one of two forms.
  - Full form, for a page whose main content is the wait (S02 checking, S05, S12, S14 making the key, M05, M01 Repair, the removal form): first the bar row (the progress bar with the time text on its right, 6.3), 12 px, then the stage list, one row per stage with its state word in a fixed left column ("Done", "Now", "Next"; the "Now" row bold), then 4 px under it the current action in plain words ("Now: Setting up the database."). A wait with one stage shows no list. A wait that 6.3 gives no bar shows the time text alone in the place of the bar row.
  - One-line form, for a wait beside other content (the S07 folder check, the S08 address check, the M02 test email, M01 results, Save report, U03, other modal forms): "<n> of <total>: <current action> · <time so far>", for example "3 of 4: Sending a test email to the administrator's address · 0:08"; a wait with one stage shows "<current action> · <time so far>". Where 6.3 gives the wait a bar, the compact bar sits at the start of the line (6.3).
  - The time counts in minutes and seconds from the start of the wait and updates once a second by changing the time label and the bar position only; the page is not drawn again. Every wait runs from the wizard's timer and never holds the window (parent decision, 2026-11-18).
  - The current action comes from the step key that the engine or the helper reports (7.6). A key that has no copy shows the stage name, never the key.
  - No marquee bar and no spinner. Inno's own file-copy bar (after S12) stays. U03 hides Inno's uninstall bar and shows the bar of 6.3 in its place.
- **Target layouts.** S02, ready, with two Recommended items (100% scale; one line per row):

  ```text
  1 Check this PC   2 Your details   3 Install   4 Done  (step strip, 6.2; 1 bold)
  ━━━━━━━━━━━━━                                          3 px underline
                                                         16 px from the text
  This PC is ready to be your Slate Operations server.   (bold verdict)
  Setup will turn on Virtual Machine Platform and ...     4 px
                                                         16 px
  Recommended: Network cable                             (bold)
  This PC uses Wi-Fi. A network cable is more ...         4 px
                                                         12 px
  Recommended: Laptop lid                                (bold)
  This laptop goes to sleep when you close the lid. ...   4 px
  [Change it during the install]                          4 px
                                                         16 px
  23 checks passed. Show all checks
  [Check again] [Save report]                             4 px
  ```

  S02, needs fixes, with two Fix items:

  ```text
  1 Check this PC   2 Your details   3 Install   4 Done  (step strip, 6.2; 1 bold)
  ━━━━━━━━━━━━━                                          3 px underline
                                                         16 px from the text
  Fix 2 things, then setup can continue.                 (bold verdict)
                                                         16 px
  Needs a fix: Virtualization                            (bold)
  Virtualization is off. Turn it on in this PC's ...      4 px
  [Show me how] [Restart to startup settings]             4 px
                                                         12 px
  Needs a fix: Network type                              (bold)
  Windows treats this network as Public. ...              4 px
  [Make this network private]                             4 px
                                                         16 px
  21 checks passed. Show all checks
  [Check again] [Save report]                             4 px
  ```

  The bottom block (the passed line with "Show all checks", then the Check again and Save report row) is what the S02 Controls mean by "Check again beside Show all checks".

### 6.2 Step strip (TASK-0097, owner item 4)

Owner, rc.28: "Include progress tabs as well so they know where they are currently." The strip shows the four steps of setup, marks the finished ones and highlights the current one. It is a position marker, not navigation: no step is clickable, no caption has a tab stop or a link look, and setup never jumps between pages (WZ-16).

- **Steps.** "Check this PC", "Your details", "Install", "Done". Captions: a step that is not finished shows its number, "1 Check this PC"; a finished step shows the mark, "✓ Check this PC".
- **Place and size.** Where the stage line is today: at the top of the page surface, under the header. The strip is one text row. Its underlines sit inside the 16 px gap under that row, so the content starts where it starts today: strip top + text height + 16 px (`StageLineAt` returns the same value as now). The strip adds no page height.
- **Columns.** Four equal columns across the content width, captions left aligned in each column. Each caption fits its column minus 8 px.
- **States** (system colors of 6.1; no other color):

  | State | Caption | Text | Underline (`TPanel`, `BevelOuter` none, color `clHighlight`), 3 px under the text, column width minus 8 px |
  |---|---|---|---|
  | Finished | "✓ <name>" | Regular, `clWindowText` | 1 px |
  | Current | "<n> <name>" | Bold, `clWindowText` | 3 px |
  | Next | "<n> <name>" | Regular, `clGrayText` | None |

  The states differ by mark, weight and underline thickness, never by color only (section 9 item 4). In high contrast the system colors follow the theme.
- **The mark.** "✓" (U+2713) in its own `TNewStaticText` in the font Segoe UI Symbol, at the size of the caption; the copy key holds the character, so the ASCII code files stay ASCII. Assumption: Windows 11 draws it in that font in a static text; the owner sees it in his next pass. If it does not draw, the number stays and the underline and weight still mark the step.
- **Which step each page shows.** A pure function of the page and its state:

  | Page and state | Current step | Finished |
  |---|---|---|
  | S01 Welcome | No strip (Proposed; the parent confirms): the page has the side image and no header, it comes before step 1, and its numbered list already names the steps with their times | — |
  | S02 (checking, ready, needs fixes, fixing, Welcome back), S03 (a state of S02), S04 License | 1 | None |
  | S05 (every state, also failed in the S13 layout) | 1 | None |
  | S06 after a restart (then S07) | 1 | None |
  | S07, S08, S10, S11 (also the recheck in place on S11) | 2 | 1 |
  | S12 running, all stages done, failed (S13 layout) | 3 | 1, 2 |
  | S06 before S14 ("Setup stopped before you saved the recovery key.") | 4 | 1, 2, 3 |
  | S14 | 4 | 1, 2, 3 |
  | S15 (at the top of the text column, above the title; it adds one strip height to S15) | 4 | 1, 2, 3 |
  | Maintenance and uninstall (M01 to M05, the M02 form, U01 to U04), the removal form, the C29 form and every dialog | No strip. `BuildMailPage` draws the stage line on M02 today; M02 drops it, and its content moves up by that height. | — |

- **S04.** Inno's license page has no stage line today. The strip goes at the top of the page surface; the license text and the accept choices move down by the strip height plus 16 px, and the license box gets shorter by the same amount, so the page height stays.
- **S15 fit.** S15 is the only page where the strip adds height, because it had no stage line. Assumption: its content still ends at least 12 px above the page bottom (no measurement of S15 exists yet). If self-test check 2 fails on S15, the strip leaves S15 and the content stays; the engineer reports the numbers to the Product Designer.
- **Screen readers.** The captions are plain static text, so a screen reader reads "1 Check this PC, 2 Your details …" without the current state; bold and underline do not reach it. The page title carries the position for a screen reader, as today.
- **A failure and the removal.** On a failure in place (S13 layout) the strip keeps the step of its page; it never shows an error state, because the "what happened" sentence says it. The removal is a modal form, so the strip under it does not change.
- **Kept-data reinstall.** S08, S10 and S14 do not show, so the steps run 1, 2, 3, then S15 with 4 current.
- **Word clash.** "Done" is also the state word of the stage lists. The strip shows "Done" only on S06 before S14, S14 and S15, where no stage list shows.

### 6.3 Progress bar and time (TASK-0097, owner item 3)

Owner, rc.28: "any progress related tasks should have that progress bar or something, as well as the time so it's much user friendly and easier to visualize". The stage list stays (Done, Now, Next): the owner likes its transparency. The bar adds how far the whole wait is; the time adds how long it ran and, on the long waits, about how long is left.

**Bar row (full form).** The first row of the progress block (6.1): the bar at the left, 12 px, then the time text at the right.

- The bar: `TNewProgressBar`, normal style (never `npbstMarquee`), `Min` 0, `Max` 1000, height 12 px, centered on the time text line.
- The time text takes the width of the widest text that this wait can show, measured once when the row is built with "88:88" in place of the time, so the bar keeps its width while the time runs. The bar is at least half of the content width; if it is not, the time text goes in its own row under the bar (4 px), and the fit rule still holds.
- The engineer checks the names `Min`, `Max`, `Position`, `Style` and `Visible` in the Inno Setup 6.7.4 support-classes reference before use.

**Compact bar (one-line form).** A bar 96 px wide and 8 px high at the start of the line, centered on its first text line, 8 px before the text; the text wraps under itself, never under the bar.

**Where the bar is** (6.1 full form):

```text
✓ Check this PC    ✓ Your details     3 Install          4 Done        (step strip; 3 bold)
───────────────    ───────────────    ━━━━━━━━━━━━━━━                   1 px, 1 px, 3 px
                                                                        16 px from the text
[██████████░░░░░░░░░░░░░░░░░░░░░░]  6:40 so far · About 22 minutes left  (bar row)
                                                                        12 px
Done  Prepare the data folder
Done  Add the hidden Windows account
...
Now   Receive the Slate Operations programs                             (bold)
Next  Check the server part
...
                                                                        4 px
Now: Loading the Slate Operations programs.
                                                                        16 px
While you wait: You can use this PC. Keep it on, plugged in ...
```

The bar row sits above the stage list because it is the summary of the whole wait (rule 2.1, verdict first); the list and the current action are the detail. Height cost on S12 against today: the 12 px gap under the bar row, less the old time line under the action line; about 8 px.

**How the bar moves.** One rule for every wait with a bar:

1. Each stage has a weight (its expected seconds, tables below). The bar position is `1000 × (weights of the finished stages + weight of the current stage × fill) ÷ all weights`.
2. Fill of the current stage, from 0 to 0.9: the largest of these that the stage has: the share of bytes (`bytes_done ÷ bytes_total`, the download of S12 stage 8); the share of its step keys already started (the 7.6 keys of that stage, for example 4 of the 6 `receive` keys); the share of time (seconds in the stage ÷ its weight). The fill stops at 0.9 until the stage ends, so the bar never fills a stage that has not ended.
3. A stage ends when the next stage starts, when its `done` line arrives, or when it does not run (a component already on this PC, a step that writes no line). Then its whole weight counts. A skipped stage moves the bar forward at once.
4. **The bar never moves back.** The wait keeps the highest position so far in its own state, not in the control; every redraw (a stage change rebuilds the block) and every timer tick sets `Position` from that value. A smaller result (`bytes_total` grows during the pull, so the byte share can fall; a repeated or late line of an earlier stage) leaves the bar where it is.
5. The bar is full only when the wait ends with success.
6. **A new wait starts a new bar** at 0, under its own heading: the removal after a failed S12, and M05 "Go back to version 0.2.0". Within one wait the bar never resets.
7. **Failure.** On S12, S05 and M05 a failure shows the S13 layout in place of the progress block, so no bar shows. In the removal form, at a step limit, the bar stays where it is (it does not fill) and the stop line of 4.5 shows under the block.
8. **Waiting without progress** (S05 `pc.busy`, M05 `upd.idle` and the busy state): the bar holds; the time counts.

**The time text.**

| Situation | Text |
|---|---|
| A wait with "Time left" in the table below, while no rule below stops it | "6:40 so far · About 22 minutes left"; "6:40 so far · About 1 minute left" |
| The current stage ran longer than its weight and has no byte share | "14:20 so far · This step takes longer than usual" |
| S05 `pc.busy`, M05 `upd.idle` and the busy state | "0:40 so far" |
| A wait with a usual time and no "Time left" | "0:24 so far · Usually about 2 minutes"; "0:24 so far · Usually about 1 minute" |
| Any other wait | "0:24 so far" |
| The wait ended with success and the block stays on the page (S05 ready to restart or no restart needed, S12 all stages done) | "Finished in 27:40", with a full bar |

Time left: the weights of the stages not started, plus the rest of the current stage (its weight minus its seconds so far, or its weight × the share of bytes not done), rounded up to whole minutes. It never goes up within a wait: the text shows the smaller of the new value and the last value shown. It shows again after "This step takes longer than usual" ends, under the same rule. It is a planning estimate; S12 keeps its subtitle "This can take up to 30 minutes." as the upper bound, and the time text no longer repeats that sentence (owner, rc.28: it showed twice). The subtitle does not say to keep the PC on: the "While you wait" box says it.

**Per surface.** Weights are planning values (plan 10.2) in seconds: estimates, corrected from the owner's install report. The setup log records the start and the end of each stage, so Save report carries the real times.

| Surface | Form and bar | Time text | Weights (seconds, planning values) |
|---|---|---|---|
| S12 install, fresh | Full; bar row | Time left | 1 Prepare the data folder 120; 2 Add the hidden Windows account 30; 3 Set the memory of the server part 10; 4 Copy the server part to the D: drive 60; 5 Start the server part 60; 6 Receive the Slate Operations programs 540 (key share, 6 keys); 7 Check the server part 30 (key share, 10 keys); 8 Download the database and sign-in programs 330 (byte share); 9 Load the Slate Operations programs 60; 10 Create the settings and passwords 15; 11 Set up the secure connection 10; 12 Set up the database 120; 13 Start Slate Operations 30; 14 Create your administrator account 15; 15 Make the first backup 180; 16 Finish on this PC 120. Sum 1730 ("About 29 minutes left" at the start) |
| S12 install, kept data | Full; bar row | Time left | 1 Prepare the data folder 120; 2 Add the hidden Windows account 30; 3 Set the memory of the server part 10; 4 Move your kept data back 120; 5 Open your kept data 60; 6 Start the server part 60; 7 Check the kept data 30; 8 Receive the Slate Operations programs 540 (key share); 9 Check the server part 30 (key share); 10 to 17 as fresh stages 9 to 16 (550). Sum 1550 ("About 26 minutes left") |
| S05 prepare | Full; bar row over the work rows only (Your details and Install carry no weight) | "Usually about 2 minutes"; "Finished in" at the ready state | 1 Turn on Virtual Machine Platform 45 (includes `pc.unpack`, which shows under this row); 2 Install Windows Subsystem for Linux (WSL) 75 (includes `pc.busy`); 3 Restart this PC 5 (the row that shows "Now" during `pc.check`); the rows Your details and Install 0 |
| The removal form | Full; bar row | "so far" only | 1 Stop the install step 5; 2 Stop Slate Operations 15; 3 Remove the server part and its data 60; 4 Turn off Virtual Machine Platform and WSL 60 (skipped when setup did not turn them on); 5 Remove the Windows settings 40 |
| Save report (S01, S02, S03, S13, M01, U04, the settings-program form) | One line; compact bar | "· 0:12" in the line | 1 Collect the setup logs 10; 2 Collect the server part's logs 90 (key share, 3 keys); 3 Remove passwords and personal details 15; 4 Save the file 5 |
| M01 Repair | Full, in place of the action buttons; bar row | "so far" only | 1 Check the security policy 5; 2 Set a new password for the hidden account 10; 3 Set up the start tasks 10; 4 Set up Windows Firewall 10; 5 Set the address on this PC 5; 6 Start Slate Operations 60; 7 Set the backup folder rights 10 |
| M05 update | Full; bar row | Time left | 1 Prepare the update 600; 2 Make a backup 300; 3 Update 300 (key share); 4 Check that it works 120 (key share). Going back is a new wait: 7 rows (recover and the 6 rollback keys), 30 each, "so far" only |
| M02 Send test email | One line under the form; compact bar | "· 0:08" in the line | 1 Check the password channel 3; 2 Check the security policy 3; 3 Send the test email 20; 4 Save the email account 60 |
| U03 uninstall | One line in Inno's uninstall form; a bar of 6.3 at the bounds of Inno's `UninstallProgressForm.ProgressBar`, which is hidden from `usUninstall` until U04 | "· 0:24" in the line | 1 Stop Slate Operations 20; 2 Move your data to D:\SlateOps\kept (or Delete the data) 60; 3 Remove the program and its Windows settings 30 |
| S02 PC check, S06 recheck (full), S14 making the key, M03 (one line) | Proposed: the same rules (full: bar row; M03: compact bar); waits for the parent's answer | S02 "Usually about 1 minute"; others "so far" | S02 and S06: the check count ("12 of 30") is the fill of one stage. S14: one stage 30. M03: 1 Check drive F: 5; 2 Prepare drive F: 10; 3 Set F: as the backup drive 30; 4 Make the recovery key 30 |
| S07 folder check, S08 address check, S10 drive check, M02 provider lookup, M01 status and phone code, S02 fix lines, restart lines | No bar: single read steps of a few seconds, where a bar only flashes | As today (one-line form) | — |

**U03 check.** Assumption: during `usUninstall` the script can hide Inno's bar and place its own `TNewProgressBar` on `UninstallProgressForm`, and Inno's file removal after `usUninstall` only sets the position of its own hidden bar. The engineer checks this in the Inno Setup 6.7.4 help before building. If it does not hold, U03 keeps the one line with the time and no bar, and the engineer reports it to the Product Designer; a bar that Inno resets to 0 is not allowed (rule 4).

**Self-test checks** (`SelfTest.iss`; each a `SelfRecord`, with the numbers in the message):

1. `TASK-0097 strip state per page`: for each row of the 6.2 page table, the current step, the finished steps and the next steps; the strip has no control with a tab stop; the content top under the strip equals the value of today's `StageLineAt` (no added height); each caption fits its column. Includes S06 before S14, S12 failed and S15; M02 has no strip.
2. `TASK-0097 fit with the strip and the bar`: every page and state that `SelfFits` measures today, plus S04, S14 and S15, ends at least 12 px above the page bottom (`CurY <= Bodies[Index].Height - ScaleY(12)`; S08 to S11 and M02: `StatusBandTop - ScaleY(12)`). It names S12 fresh, S12 kept data, S08 with the address name open and M02 Other with every field; the removal form with every stop line and both restart lines; the settings-program Save report form.
3. `TASK-0097 the bar never moves back`: one fixture runs the S12 stages of both sets with a redraw (`RenderPage`) between lines: a byte stage at 1.0 GB of 2.0 GB, then 1.1 GB of 3.4 GB; a `done` line for a stage that did not run; a repeated line; a late line of an earlier stage; ticks past a stage's weight. After each event, `Position` is not smaller than before, stays below 1000 until the last stage ends, stays within the 0.9 fill of the running stage, and is 1000 at the end.
4. `TASK-0097 time left never goes up`: the same fixture; the minutes left never go up; the start shows "About 29 minutes left" (fresh) and "About 26 minutes left" (kept data); past a weight with no byte share the text is "This step takes longer than usual"; the end shows "Finished in"; the S12 subtitle text never shows in the time text.
5. `TASK-0097 a tick changes only the time and the bar`: a timer tick creates and frees no control (the component count of the body stays the same), `WaitDrawn` does not change, and only the time label caption and the bar position change.

6. `TASK-0097 no drive letter before a full stop`: every copy key that takes a drive (the keys of the 7.6 drive-letter rule, with each of their placeholders set to "D:") gives a text with no ":." in it. The defect comes from placeholders ("drive %1."), so a search of Copy.iss for "D:." alone does not find it.

Tooling test (`tests.tooling.test_windows_installer`, Linux CI): the copy keys of 6.3 and 7.6 hold the exact strings of this spec; no Copy.iss value matches `[A-Z]:\.`; `npbstMarquee` stays absent.

**Copy keys** (new or changed; Copy.iss):

| Key | Value |
|---|---|
| `stage_1` to `stage_4` | "1 Check this PC", "2 Your details", "3 Install", "4 Done" (`stage_4` new) |
| `strip_name_1` to `strip_name_4` (new) | "Check this PC", "Your details", "Install", "Done" |
| `strip_done_mark` (new) | "✓" |
| `stage_sep` | Retired |
| `wait_so_far` (new) | "%1 so far" |
| `wait_join` (new) | "%1 · %2" |
| `wait_left` (new) | "About %1 minutes left" |
| `wait_left_1` (new) | "About 1 minute left" |
| `wait_longer` (new) | "This step takes longer than usual" |
| `wait_usually` (new) | "Usually about %1 minutes" |
| `wait_usually_1` (new) | "Usually about 1 minute" |
| `wait_finished` (new) | "Finished in %1" |
| `wait_time`, `wait_time_limit`, `wait_about_1`, `wait_about_2`, `wait_up_to_30`, `wait_up_to_60` | Not used in the time text of a wait with a bar row; `s12_subtitle` and `m05_people` keep their sentences. Remove a key that no wait uses then. |
| The drive-letter lines | 7.6 (S12, M01 Repair, S14 and M04, M03 rows) |

Each screen below lists: purpose, content and copy, controls, states and messages. Copy in quotes is final unless it holds an example value.

### S01 Welcome (plan page 1)

- **Purpose.** Say what happens, how long it takes and what to have ready.
- **Title.** "Set up Slate Operations on this PC"
- **Content.** "This PC becomes the server for your organization. Your people open Slate Operations from their PCs and phones on your office network."
  1. "Check this PC: about 1 minute. Setup changes nothing yet."
  2. "Answer a few questions: about 5 minutes."
  3. "Install: about 30 minutes. You can use the PC while it installs." (30 minutes is a planning value; section 12 item 15.)
  
  "Have ready: a USB drive for backups (recommended)."
- **Controls.** Next: "Check this PC". Cancel.
- **States.** Default only.

### S02 Check this PC (new; replaces plan page 3)

- **Purpose.** Decide whether this PC can be the server, and get every problem fixed here.
- **Title.** "Check this PC". Subtitle: "Setup checks whether this PC can be your Slate Operations server. It changes nothing."
- **Content, in order.** The verdict (one bold sentence; a second line only in the ready state). Then at most four items in total: Fix items first, then "Recommended" items (Advice). Each item has the result word, the name, one or two lines, and its buttons. Then one line: "21 checks passed. Show all checks".
- **Controls.** Per item: "Fix it for me", "Remove them", "Change it during the install", "Show me how", "Open … settings", "Restart to startup settings" (section 5.3). Page: "Check again" (beside "Show all checks"). Next: "Next" (off while a Fix item is open). Back. Cancel.
- **States.**
  - Checking: the progress block, full form, with the four check groups of 7.6, the current check by name and count ("Checking: Internet (12 of 30)"), and the time text "0:24 so far · Usually about 1 minute" (6.3; the bar row is Proposed, see 6.3) Below it: "Found so far: nothing that needs you." or the items found so far. Passed checks never show one by one. Next is off.
  - Ready: "This PC is ready to be your Slate Operations server." Optional second line: "Setup will restart this PC once." Recommended items show below. Next is on.
  - Needs fixes: "Fix 2 things, then setup can continue." The Fix items show first.
  - Fixing: the item that the person selected shows its action line (7.6, for example "Making this network Private…"); its buttons are off. After the fix, the item checks again by itself and shows "Fixed" or the message.
  - Not suitable: the page changes in place to the S03 stop.
  - Removing (C29): after Continue in the C29 form, the item shows its action line with the time so far (7.6), then "Removed".
  - Welcome back (after a restart from the check): one line above the verdict, "Welcome back. Setup checks this PC again."
  - Waiting for the person (after "Show me how"): the item keeps its message and shows "Check again".
- **Focus.** When the check ends, focus moves to the verdict sentence (a read-only, borderless edit field), so a screen reader reads it first (Assumption: Narrator reads it; WZ-11).
- **More than four items.** The page shows four (Fix items first) and "Show 2 more". The dialog lists all items with their buttons.

### S03 This PC cannot be the server (new; a state of the S02 page)

- **Built as.** The S02 page in its "not suitable" state: the header and the content change in place.
- **Purpose.** A polite stop. Say why, say what to do instead, change nothing.
- **Title.** "This PC cannot be the Slate Operations server". Subtitle: "Nothing was changed on this PC."
- **Content.**
  - The Stop items, each with "What you can do". Examples:
    - Windows 11 Home: "You can upgrade this PC to Windows 11 Pro in Settings → System → Activation. Microsoft charges for the upgrade. Or use another PC."
    - Another Windows edition (`s03_edition_todo`): "Ask your PC supplier whether this PC can get Windows 11 Pro. Or use another PC."
    - Memory: "A PC supplier can add memory to many PCs. Or use another PC."
    - Windows 10: "Check in Windows Update whether this PC can get Windows 11. Or use another PC."
  - "A suitable PC has: Windows 11 Pro, Enterprise or Education (version 22H2 or later), an Intel or AMD processor with virtualization, 16 GB of memory, 15 GB of free space and a connection to your office network."
  - "If you think this is wrong, select Save report and send the file to Slate Operations support."
- **Controls.** "Save report". Next is hidden. Cancel caption: "Close".
- **States.** Default; report saved ("Report saved to your desktop: SlateOps-report-check-….zip. Show in folder").

### S04 License agreement (plan page 2)

- **Purpose.** Accept the Elastic License 2.0.
- **Title.** "License agreement". Subtitle: "Read the license, then select I accept."
- **Content.** The Inno Setup license page with `LICENSE` as plain text: `infra/windows/installer/LICENSE.txt` has the same words without the Markdown markers ("## " headings, `*` and `**`), and a tooling test fails when the two differ. A link-style button: "Third-party notices". No edition choice and no license file (DEC-0029).
- **Controls.** "I accept the agreement" / "I do not accept the agreement". Next: "Next" (off until "I accept").

### S05 Restart this PC once (plan page 3a; only when C26 needs it)

- **Purpose.** Turn on Virtual Machine Platform and install Windows Subsystem for Linux (WSL), then restart, before any secret is typed.
- **Title.** "Restart this PC once". Subtitle: it names what Windows finishes at the restart. Before the work, from C26; after it, from the helper's results.
  - Both: "Windows finishes Virtual Machine Platform and WSL when this PC restarts."
  - Only Virtual Machine Platform: "Windows finishes Virtual Machine Platform when this PC restarts."
  - Only WSL: "Windows finishes Windows Subsystem for Linux (WSL) when this PC restarts."
  - No restart needed: "This PC does not need a restart." This line wins in the no-restart state, also when setup installed WSL just now.
- **Content.**
  - While it works: the progress block, full form (7.6, S05), with the bar row and "0:24 so far · Usually about 2 minutes" (6.3). When the work ends, the bar is full and the time text says "Finished in 1:52".
  - Then the stage list stays, with its states: "Done: Turn on Virtual Machine Platform", "Done: Install Windows Subsystem for Linux (WSL)", "Now: Restart this PC", "Next: Your details", "Next: Install" (in the order the helper ran them; a component that was already on this PC shows "Done" with "(already on this PC)").
  - The verdict says only what setup did, from the helper's results:
    - Setup turned on Virtual Machine Platform and installed WSL: "Setup turned on Virtual Machine Platform and installed Windows Subsystem for Linux (WSL). Windows finishes them when this PC restarts."
    - Only Virtual Machine Platform turned on now: "Setup turned on Virtual Machine Platform. Windows finishes it when this PC restarts."
    - Only WSL installed now: "Setup installed Windows Subsystem for Linux (WSL). Windows finishes it when this PC restarts."
    - Virtual Machine Platform was already turned on and waits for a restart: "Virtual Machine Platform is already turned on. Windows finishes it when this PC restarts."
  - Under the verdict, one line each: "Virtual Machine Platform: lets this PC run the server part of Slate Operations." "Windows Subsystem for Linux (WSL): runs the server part of Slate Operations inside Windows."
  - Then: 1. "Save your work and close your other programs." 2. "Select Restart now." 3. "Sign in again. Setup opens by itself, checks this PC again (about 1 minute) and continues with Where to keep your data." "If setup does not open, double-click Continue Slate Operations setup on the desktop."
  - "Details" (link-style button) shows only technical extras: the WSL version and the result codes of the two steps. The version is the one on this PC when WSL was already there (C26), else the version in this setup file. The "Now:" line of pc.wsl uses the same version.
- **Controls.** Next: "Restart now". "Restart later" (closes setup; the shortcut and the saved progress stay). Cancel runs the removal (section 4.5): it turns Virtual Machine Platform and WSL off again when setup turned them on.
- **States.** Working; ready to restart; no restart needed; waiting ("Another installation is running on this PC. Setup waits and tries again." for plan code 1618, three tries); failed (in place, in the S13 layout, with the component by its name: "Setup could not turn on Virtual Machine Platform." or "Setup could not install Windows Subsystem for Linux (WSL).").
- **No restart needed** (the helper finished, and neither component asks for a restart): the subtitle "This PC does not need a restart."; the stage list without the restart stage ("Done: Turn on Virtual Machine Platform", "Done: Install Windows Subsystem for Linux (WSL)", "Now: Your details", "Next: Install", with "(already on this PC)" where it applies); the verdict "Virtual Machine Platform and Windows Subsystem for Linux (WSL) are ready on this PC." No why lines, no steps, no Details and no "Restart later". Next: "Next", on; it opens S07.

### S06 Welcome back (new)

- **Purpose.** Show where setup continues after a restart that setup asked for, or before the recovery key.
- **Entries.** After the S05 restart, or after a restart from a recheck after S05 (section 4.1): S06, then S07. After an "install finished" mark without the "key saved" mark: S06, then S14.
- **Title.** "Welcome back". Subtitle: "Setup continues where it stopped." Before S14, one line on the page: "Setup stopped before you saved the recovery key."
- **Content.** The quick recheck runs (section 5.2) with "Checking this PC again…", then "This PC is still ready. Setup checked it again." A new problem shows in place, with the S02 item layout and its buttons; Next stays off until it is fixed. A helper that does not answer shows the antivirus message (7.5) in the S13 layout, with Try again.
- **Controls.** Next: "Continue". Cancel (none when S14 comes next, section 4.5).

### S07 Where to keep your data (plan page 4)

- **Purpose.** Choose the drive for all business data. The best drive is already selected.
- **Title.** "Where to keep your data". Subtitle: "Your records and files are kept on this drive." First line of the page: "Setup chose the drive with the most free space."
- **Content.** A list of the drives that qualify, each with its name, letter and free space; the largest is selected and marked "Most space". Below: "Folder: D:\SlateOps" with "Change folder". One line: "USB and network drives are not listed. The data must stay inside this PC." Small link-style button: "Change program folder" (default `C:\Program Files\Slate Operations`).
- **Kept-data card** (when the folder holds kept data): "This folder holds data from an earlier installation: Riverside Learning Center, version 0.2.0, kept on 12 November 2026." ( ) "Use the kept data" (default) ( ) "Start new. Choose another folder." Kept data from an older version (until W13b adds its update steps): "This data is from Slate Operations version 0.1.0. This setup cannot open it. Install with setup version 0.1.0 first, then run this setup to update."
- **Controls.** Drive list, Change folder, Change program folder. Next: "Next". Back. Cancel.
- **States.** Default; folder not empty and not kept data ("This folder is not empty. Choose an empty folder."); drive too small (the drive is not listed; when the person picks a folder on it: "This drive has 9 GB free. Slate Operations needs 15 GB. Choose another drive."); a folder above the chosen folder fails the safety check (section 7.5, `setup.data.data_folder_parent_unsafe`): the message shows under the Folder line, with the button "Use D:\SlateOps"; the helper does not answer within 60 seconds: "A security program on this PC blocked part of Slate Operations setup. Allow the folder C:\Program Files\Slate Operations in the security program, then select Next again." with Save report.
- **On Next.** Setup checks the chosen folder (read only; one-line form, "Checking the folder D:\SlateOps…", limit 60 seconds) and opens S08. Nothing is written before Install (DEC-0041): the data folder and the server part are prepared on S12.

### S08 Your organization (plan page 5)

- **Purpose.** Get the organization name and the first administrator's account: name, email address and password. Setup creates this account with the password, so no email is needed (DEC-0041).
- **Title.** "Your organization". Subtitle: "You become the administrator of Slate Operations."
- **Fields, in order** (6.1 rule 9).
  - "Organization name". Help: "People see this name in Slate Operations." No placeholder text; the label stays visible.
  - "Your name".
  - "Your email address". Help: "You sign in to Slate Operations with this address." Any valid address works; setup sends no email.
  - "Password" and "Type the password again", in one row (6.1 rule 9), with "Show" at the right end of the Password label line; "Show" shows both fields and resets to hidden when the page changes. Help under the row: "Use 12 to 72 characters. You sign in with this password."
  - The address line: "Address for PCs and phones: https://riverside-learning.local" ending with the link "Change". It updates as the person types the organization name.
  - "Change" opens, under the address line, the field "Address name" (the link "Change" hides). Help: "Phones and PCs use it in the address. Use lowercase letters, numbers and single hyphens. It cannot change after setup."
- **Defaults made by setup, not shown** (section 8): the address name from the organization name (lowercase letters and numbers, every other run of characters one hyphen, cut at 30 characters at a whole word when it can; "org-" before a name of digits only; "slate-operations" when nothing is left); the short name (slug) of the organization from the organization name; the administrator's user name from "Your name" (from the email address when the name has no letter or number).
- **Controls.** Next: "Next". Back. Cancel.
- **Messages under the field.** Name empty: "Enter the name of your organization." Name too long: "Use 100 characters or fewer." Your name empty: "Enter your name." Email: "Enter an email address, for example maria@example.com." Password: "Use 12 to 72 characters." Password longer than 72 bytes but not 72 characters (letters with accents and other characters count as more than one): "This password is too long. Use a shorter password." Second entry: "The two passwords are not the same. Type them again." Address name (the block opens by itself): "Use 1 to 63 lowercase letters and numbers, with single hyphens between them and at least one letter, for example riverside-learning."
- **On Next.** After the fields pass, setup asks the office network whether another device already uses the address (one mDNS probe; read only; one-line form "Checking that no other device on this network uses riverside-learning.local…", limit 30 seconds). In use: under the address name field, "Another device on this network already uses riverside-learning.local. Choose another address name." The check runs again only when the address name changes. The address is fixed at Install.
- **The password.** Hidden characters. Never saved by setup; it stays in memory until the install job takes it through the pipe (plan 3.2). After a restart, setup asks it again.

### S09 Email for Slate Operations (not a setup page; the M02 form)

- **Not in setup** (DEC-0041). Setup has no email page and no "Continue later". The app works without email; invitations and password resets say that email is not set up. The owner sets up email after the install in the settings program (M02). This section defines the form that M02 shows.
- **Fields, in order.**
  1. "Send from" (email).
  2. "Provider": ( ) Gmail ( ) Other (DEC-0040). Setup selects Gmail and marks it "(detected)" for gmail.com and googlemail.com, else from the MX records of the domain, on the Windows side only (section 12 item 7). The MX answer only selects Gmail by an exact match of the mail host to a fixed list of Google hosts; it fills no field. Any other address selects Other. The person can change the choice.
  3. Gmail: "App password". Help, above the field: "Gmail needs an app password, not your normal password. First turn on 2-Step Verification for this Google account, then make an app password." Two links: "Turn on 2-Step Verification" (https://myaccount.google.com/signinoptions/two-step-verification) and "Make an app password" (https://myaccount.google.com/apppasswords) (W14 owner round, AC-F3).
  4. Other: "Server", "Port", "Security" ( ) "SSL/TLS (usually port 465)" ( ) "STARTTLS (usually port 587)", "User name" (default: the address), "Password". A business on Microsoft 365 uses a Gmail sender or the mail server of another provider (DEC-0040).
  5. "More options": "Sender name" (default: "Slate Operations", because the settings program does not know the organization name).
- **Gmail help dialog.** "1. Select Open Google's page. Your browser opens myaccount.google.com/apppasswords. 2. Sign in. If Google asks, turn on 2-Step Verification first. 3. Type Slate Operations as the app name and select Create. 4. Copy the 16-letter password and paste it here." Note: "If you change your Google password, Google removes this app password. Then use Set up email in Slate Operations settings." Buttons: "Open Google's page", "Close".
- **Outlook.com address** (`outlook.com`, `hotmail.com`, `live.com`, `msn.com`): no provider is selected, and a note shows in place of the password and the Other fields: "Outlook.com accounts cannot send email for Slate Operations. Use a Gmail account, or the mail server of another email provider." The Next button stays off until the address changes or the person selects Other.
- **The password field.** Hidden characters, a "Show" toggle that resets to hidden after each test send and when the page changes. Never saved by setup (plan 3.2 check 4); it goes only with the test email, after the channel self-test and R7.
- **States and messages.** M02 (section M02 to M04) and section 7.3.

### S10 Backups (plan page 7)

- **Purpose.** Choose where the nightly backup goes. A second drive is the safe default.
- **Title.** "Where to keep backups". Subtitle: "Slate Operations makes a backup every night at 2:00." First line of the page: "Keep backups on another drive, so one broken drive cannot lose everything."
- **Content.** A list of the other drives (USB drives and other internal drives) with free space. The largest is selected. The last entry: "This PC's data drive (D:). Not safe if this drive breaks."
- **No other drive.** A card: "Plug in a USB drive now. Setup finds it by itself." and "No other drive was found on this PC." The list updates when a drive is plugged in. If the person selects the data drive, a check box shows: "I understand: if drive D: breaks, the data and the backups are both lost." Next stays off until it is checked. One line: "You can choose a backup drive later in Slate Operations settings."
- **USB drive selected.** One line: "Keep this USB drive plugged in. A backup fails while the drive is out."
- **Controls.** The list, the check box. Next: "Next". Back. Cancel.
- **Messages.** "Slate Operations cannot write to the E: drive. Plug the drive in, or choose another drive." "E: has 2 GB free. Choose a drive with more space."

### S11 Ready to install (plan page 9)

- **Purpose.** One summary before the long wait. Last chance to change.
- **Title.** "Ready to install". Subtitle: "Check your choices, then select Install."
- **Content.** Rows, each with "Change" where a change is allowed. "Change" goes back to the page of that row (Back, with the pages between skipped); after it, Next comes back to S11 (the pages between skipped). The copy stays the same.
  - "Organization: Riverside Learning Center" (Change: S08)
  - "Administrator: maria@example.com. You sign in with this address." (Change: S08)
  - "Data: D:\SlateOps"
  - "Backups: E: (USB drive), every night at 2:00" (Change: S10)
  - "Address for PCs and phones: https://riverside-learning.local"
  - "Edition: Desk, the free edition"

  Kept-data reinstall: the organization, the data folder, the address of the kept installation and the edition, with no "Change".

  "Installing takes about 30 minutes. Keep this PC on and connected." (planning value)

  "What setup changes on this PC" (link-style button) opens a dialog: "Adds a hidden Windows account that runs Slate Operations. Starts Slate Operations when Windows starts, also when nobody is signed in. Allows Slate Operations through Windows Firewall on Private networks. Makes this PC trust the secure connection of Slate Operations. Keeps this PC awake when it is plugged in. Adds Slate Operations to the Start menu and the desktop. Uninstall removes all of these." When the person chose C22, one more line: "Keeps this laptop running when the lid is closed and it is plugged in."
- **Controls.** Next: "Install". Back. Cancel.
- **On Install.** The quick recheck (section 5.2). A new problem shows in place on S11, with the S02 item layout; Next stays off until it is fixed. A C04 "Restart to startup settings" here continues after the restart at S06, then S07 (section 4.1).

### S12 Installing (plan page 10)

- **Purpose.** Do all the server work after Install, show it in plain stages, give a time, say what the person can do (DEC-0041).
- **Title.** "Installing Slate Operations". Subtitle: "This can take up to 30 minutes." (planning value; the server part is now prepared here too, so the owner's install report corrects it.)
- **Stages,** in the progress block, full form: the bar row with the time left (6.3), then the stage list, then the current action from the helper or engine step key (7.6, S12). Each stage is "Done", "Now" or "Next".
  1. "Prepare the data folder" (unpack the server part, prepare the data folder)
  2. to 8. The server part (7.6 "S12 server part"): "Add the hidden Windows account", "Set the memory of the server part", "Copy the server part to the D: drive", "Start the server part", "Receive the Slate Operations programs", "Check the server part", "Download the database and sign-in programs". Kept data: "Add the hidden Windows account", "Set the memory of the server part", "Move your kept data back", "Open your kept data", "Start the server part", "Check the kept data", "Receive the Slate Operations programs", "Check the server part".
  9. to 16. The install (plan 6.2 steps in brackets):
     1. "Load the Slate Operations programs" (the backup folder, 1, 3)
     2. "Create the settings and passwords" (2, 4, 5)
     3. "Set up the secure connection" (6)
     4. "Set up the database" (7, 8)
     5. "Start Slate Operations" (9, 10)
     6. "Create your administrator account" (11; the password from S08)
     7. "Make the first backup" (12)
     8. "Finish on this PC" (13, the Windows-side steps and the check that Slate Operations opens on this PC)

  Before the install job, setup saves the "install started" stage, sets the time zone, runs the channel self-test (plan F4d) and reads R7 again (section 5.2). Only then does the install job get the answers and the password through the pipe.
- **Limits.** Every step has a limit, and past it the install fails with "This step took longer than setup allows." (code values: the data folder 30 minutes; each server part step and each Windows-side step 10 minutes; the install job 45 minutes; a job submit and each job answer 2 minutes). The time shows in the time text of the bar row. The weights of 6.3 are expected times, not limits.
- **Box.** "While you wait: You can use this PC. Keep it on, plugged in and connected, and do not restart it. At the end, setup shows your recovery key. Have a printer or a USB drive ready."
- **Finished.** When every stage is done, the subtitle is "Finished." and the "While you wait" box goes (owner, rc.32).
- **Controls.** Next is off. Cancel (section 4.5: the removal).
- **States.**
  - Running.
  - Failed: in place, in the S13 layout, with Save report and "Remove and close".
- **Numbers.** The step key and, while images download, "1.2 GB of 3.4 GB" come from the engine's progress lines (a fixed step key and whole numbers). The Windows side reads them as integers and uses them only for display (plan 3.2 rule 2): the action line and the fill of stage 8 (6.3, byte share).

### S13 Setup stopped (one layout for every failure, shown in place)

- **Built as.** A state of the page where the failure shows (S02, S05, S06, S12), or a modal form (the channel self-test on M02). Never a separate page.
- **Purpose.** Say what happened and what to do.
- **Title.** "Setup stopped". Subtitle: the stage, for example "Set up the database".
- **Content before Install** (S02, S05, S06):
  - What happened, one sentence (section 7), for example: "Setup could not turn on Virtual Machine Platform."
  - "What you can do:" 1. "Select Try again. Setup continues from this step. Nothing is lost." 2. "If it stops again, select Save report and send the file to Slate Operations support."
  - Controls: Next: "Try again". "Save report". Cancel (section 4.5).
- **Content on S12** (DEC-0041: a complete installation or nothing):
  - What happened, one sentence (section 7), for example: "Setup could not set up the database."
  - "Select Save report first if you want to send the details to Slate Operations support. Then select Remove and close. Setup removes everything it added, and you can start setup again."
  - Controls: "Save report" on the page. Next: "Remove and close" (the removal of section 4.5, then setup closes). Cancel does the same, without a question. No Try again.
- **States.** Default; saving the report (one-line form of the 7.6 Save report row, for example "2 of 4: Collecting the server part's logs · 0:12"); report saved ("Report saved to your desktop: SlateOps-report-install-20261116T1402Z-k3f9qa.zip." "Show in folder"); report not saved ("Setup could not save the report. Select Save report again.").
- **Focus.** On open, focus moves to the "what happened" sentence.

### S14 Save your recovery key (plan page 11)

- **Purpose.** Make sure the key leaves this PC before setup ends.
- **Title.** "Save your recovery key". Subtitle: "Your backups are locked. This key opens them if this PC breaks or is lost."
- **Content.** The key in large monospaced groups. "Keep it somewhere safe, away from this PC and away from the backup drive. Setup shows the key only now. You can make a new key later in Slate Operations settings."
- **Controls.** "Print the key": the setup process prints with Windows printing calls (no file, no helper program, no PowerShell; the spool file is the plan W8-5 exception), with the fixed print job name "Slate Operations recovery key". "Save to a USB drive" lists removable USB drives only. Check box: "I printed or saved the recovery key". Next: "Next" (off until checked). No Cancel (section 4.5). The key is static text that cannot be selected, and the page has no Copy button.
- **States.** Printed ("Sent to the printer."); saved ("Saved to F:\SlateOps-recovery-key.txt."); the chosen drive is the backup drive: setup refuses and writes nothing: "This is your backup drive. A key on it opens your backups for anyone who has the drive. Use another USB drive, print the key, or write it down." (Security Engineer finding W80-1: refuse); no USB drive: "Plug in a USB drive. Setup finds it by itself."; a printer that writes a file (for example Microsoft Print to PDF): setup refuses: "This printer saves a file instead of printing on paper. Choose a printer that prints on paper, or save the key to a USB drive."

### S15 Slate Operations is ready (plan page 12)

- **Purpose.** Three next steps in order, and how to come back.
- **Title.** "Slate Operations is ready"
- **Content.**
  1. "Open Slate Operations on this PC at https://riverside-learning.local. Sign in with maria@example.com and the password that you typed in setup." Button under it: "Open Slate Operations" (default browser at the address). When setup does not know the email address (S06 before S14, section 4.1), step 1 reads (`s15_step1_no_address`): "Open Slate Operations on this PC at https://riverside-learning.local. Sign in with your email address and the password that you typed in setup."
  2. "Set up email, so Slate Operations can send invitations and password resets. Open Slate Operations settings in the Start menu and select Set up email."
  3. "Connect phones and other PCs. On the same Wi-Fi as this PC, scan this code with the phone's camera. It shows the one-time steps that let the phone open Slate Operations." The QR code to `http://riverside-learning.local/trust` (made on the Windows side from the stored address name, section 12 item 10), and the address in text below it. "Details" (link-style button) shows: "Security code: 3F:A2:…:9C. The phone page shows the same code." The code is the fingerprint of the Slate Operations certificate in this PC's trusted certificates, computed on Windows (plan 6.3).
     In v1 (parent decision DEC-0036, no QR code), step 3 reads: "Connect phones and other PCs. Connect the phone to the same Wi-Fi as this PC. In the phone's browser, type the address below exactly, with http://. The page shows the one-time steps that let the phone open Slate Operations." The address `http://riverside-learning.local/trust` shows below it. When the security code is not known (S06 before S14), its line does not show.

  "You use Desk, the free edition. To add a license later, open Manage → Updates & licensing in Slate Operations."

  "Slate Operations starts by itself when this PC starts. For settings and help, open Slate Operations settings in the Start menu."

  Kept-data reinstall: no step 1 and no step 2, because the kept installation keeps its accounts and its email settings; the button and step 3 stay.
- **Controls.** Next: "Finish". No Back. No Cancel.

### M01 Slate Operations on this PC (maintenance, plan 9.3)

- **Purpose.** Status first, then the few things the owner can do from Windows.
- **Title.** "Slate Operations on this PC". Subtitle: "Version 0.2.0 · https://riverside-learning.local" (the stored address).
- **Status, one sentence, and one line under it.** "Running. Last backup: today at 2:04, on the E: drive." When a "Needs attention" sentence shows, the line under it says whether Slate Operations runs and when the last backup was, for example "Slate Operations is running." (while the engine reports no last-backup time). Other states, from the engine status (plan 9.3, 10.2, 10.7): "Updating", "Needs attention: plug in the backup drive (E:). If you see this again after you plug it in, select Repair." (Repair sets the backup folder rights again when the drive is present.), "Needs attention: email sign-in fails. Select Set up email.", "Needs attention: the network changed. Select Repair.", "Not ready since 09:12. Select Repair. If that does not help, select Save report.", "Needs support. Select Save report and send the file to Slate Operations support." A "Details" link shows memory, disk and start time in plain words ("Memory used: 4.1 GB, highest 5.3 GB").
- **Email status** (DEC-0041). While the engine status reports no email settings (`email_configured` false) and Slate Operations runs, one more line under the status: "Email is not set up, so Slate Operations cannot send invitations or password resets. Select Set up email." No other value from the server part decides what M01 shows (plan 3.2 rule 2).
- **Actions** (command buttons with one line each): "Open Slate Operations" ("In your browser on this PC."); "Show the phone code" ("Connect a phone or another PC."); "Set up email" ("Slate Operations sends invitations and password resets from it."); "Change backup drive" ("Backups go there from the next night."); "Make a new recovery key" ("The old key stops working."); "Repair" ("Sets up the Windows parts again. Your data does not change."); "Save report" ("A file for Slate Operations support."); "Reset the admin password" ("Choose a new password for the administrator.") (DEC-0042).
- **No "Send my invitation again".** Setup creates the first administrator with a password (DEC-0041), so no invitation exists to send again. A person who forgets the password resets it from the sign-in page once email is set up, or with "Reset the admin password" here.
- **"Reset the admin password"** (DEC-0042). A modal form: "Use 12 to 72 characters. You sign in with this password.", "New password", "Type it again", "Show" (the S08 rule and its errors), and the buttons "Change password" and "Go back". The password goes to the engine job `admin-password` through the pipe (input `run_id`, `admin_password`; plan 3.2 rule 3), never to a file or the log. One line while it runs: "Changing the admin password." Result line by the job's code: `reset`: "The admin password is changed. Sign in with the new password."; `invalid_input`: "Slate Operations did not accept this password. Use 12 to 72 characters."; `not_installed`: "Slate Operations is not installed on this PC, so setup cannot change the admin password."; `admin_missing` (also an administrator made by an invitation before DEC-0041): "Setup can reset only the admin that setup created."; `reset_failed` (Auth or the database is down): "Setup could not change the admin password. Select Repair, then try again."; any other code: "Setup could not change the admin password. Select Save report and send the file to Slate Operations support."
- **"Repair".** While Repair runs, its progress block (full form with the bar row, 6.3; 7.6 "M01 Repair") takes the place of the action buttons, so the page keeps its size. The buttons come back with the result line: "Repair finished. Slate Operations starts again."; on a security policy that records commands, or one that setup cannot read, the C18 message; when the helper does not answer, the antivirus message of 7.5; otherwise "Repair did not finish. Select Save report and send the file to Slate Operations support."
- **"Show the phone code".** A modal form with the QR code, the address in text, and "Security code: 3F:A2:…:9C. The phone page shows the same code." (computed on Windows, as on S15).
- **Footer line.** "To uninstall, open Settings → Apps."
- **Start menu and the settings program.** The settings program is `C:\Program Files\Slate Operations\SlateOpsSettings.exe` (the program folder: standard users can run it, only administrators can change it; it asks for administrator rights itself); the two Start menu entries and Modify in Settings → Apps open it there. An update moves it from its earlier place, `C:\ProgramData\SlateOps\settings`, which Explorer cannot open; uninstall removes it with the program folder. Its window title is "Slate Operations settings". "Slate Operations settings" opens M01. "Slate Operations - Save report" first shows "Setup saves a report for Slate Operations support. This takes up to 3 minutes.", then the result line in a message box. On a PC with no installation, the settings program shows "Slate Operations is not installed on this PC. To install it, open the Slate Operations setup file."
- **Controls.** Cancel caption: "Close".
- **No license import** (DEC-0029).

### M02 to M04 (maintenance forms)

- **M02 Set up email** (DEC-0041, DEC-0040). The S09 form, title "Set up email", subtitle "Slate Operations sends invitations and password resets from this account." Next: "Send test email" while the fields are not saved.
  - On Next, in order, one line under the form (7.6 "M02"): 1 the channel self-test (plan F4d), 2 R7 (section 5.2), 3 the test email, 4 saving the account (`set-email`, which restarts sign-ins). The test email goes to the administrator's stored address, never to an address typed here. The password goes only with step 3.
  - Passed and saved: "Slate Operations sent a test email to maria@example.com. Check that inbox and its Spam folder." (the address from the engine's answer). Next becomes "Done". Done returns to M01 with the result line "Slate Operations sends email from office@example.com now."
  - Failed test: the message by class (section 7.3), under the field that it is about; nothing is saved. A changed field allows Next again.
  - Channel self-test failed: a modal form in the S13 layout: "Setup cannot pass the password safely to the server part. Nothing was sent."
  - Saving failed: back on M01, "Slate Operations could not change the email account. Select Save report and send the file to Slate Operations support."
- **M03 Change backup drive.** The S10 form. On Next, setup checks that Slate Operations can write to the drive, without a backup (a backup stops Slate Operations for everyone): "Checking drive F:…". The new drive gets its own backup lock, so M03 ends with the S14 page for its new recovery key, with the first line: "Your new backup drive has its own lock. The old recovery key does not open it." The final button is "Done". Result: "Backups go to F: from tonight at 2:00." Failure in place: "Slate Operations cannot write to the F: drive. Plug the drive in, or choose another drive." When the drive changed but the key could not be made, M01 shows: "Backups now go to F:, but setup could not make their recovery key. Select Make a new recovery key now." (Engine side: `set-backup-target` sets up the new backup store and returns the new key through the secret channel; W10b.)
- **M04 Make a new recovery key.** The engine removes the old key when it makes the new one, so the old key cannot be kept (D-B, TASK-0096; Security Engineer accepted with the consequence stated before the job). Before the job, a confirmation: title "Make a new recovery key?", text "Your current recovery key stops working. Have a printer or a USB drive ready to save the new key.", buttons "Make a new key" and "Go back" (default). Then the S14 page, with a first line: "Your old recovery key no longer works. Save this new key now." The final button is "Finish", off until the check box "I printed or saved the recovery key" is checked (as S14, W8-4). No Cancel, as on S14.

### M05 Update (plan 7.4, setup-program path)

- **Purpose.** Update with a backup first, and say what the people in the office notice.
- **Title.** "Update Slate Operations". Subtitle: "Version 0.2.0 is installed. This setup installs version 0.2.1."
- **Content.** "Setup makes a backup before it changes anything. If the update fails, Slate Operations goes back to version 0.2.0 by itself." Then: "People cannot use Slate Operations while it updates. This can take up to 1 hour. Tell your people before you start." (1 hour is a planning value; it matches the slow line at 60 minutes.)
- **Controls.** Next: "Update now". Cancel.
- **Progress.** The progress block, full form, in the order the steps run: "Prepare the update" (the wait for a free moment, the new version from this setup file, the WSL update), "Make a backup", "Update", "Check that it works", with the bar row and the time left (6.3), and the current action from the step key (7.6, M05). Going back to the old version is a new wait with its own bar from 0 (6.3 rule 6). Result: "Slate Operations is updated to version 0.2.1." or "The update did not work. Slate Operations went back to version 0.2.0. Everybody must sign in again." (plan 7.5 revokes sessions) with "Save report".
- **Messages** (S13 layout in place, with Save report; Try again unless the line says otherwise):
  - Busy: "Slate Operations is busy with a backup or another task. Setup waits and tries again by itself." (a waiting line, not a failure). The step that receives the new version waits and tries again the same way when the engine answers `engine_busy` or `runner_busy`, at most 10 times, 30 seconds apart; then it fails with the next line.
  - A failure before the update changed anything: "The update did not work. Slate Operations still runs version 0.2.0. Nothing changed."
  - No answer from the server part: "Setup cannot reach the server part of Slate Operations. Nothing changed."
  - Not enough space: "The server part of Slate Operations needs 12 GB of free space for a safe update. Nothing changed. Select Save report and send the file to Slate Operations support." No Try again.
  - A rollback that could not finish: "The update did not finish, and Slate Operations could not go back by itself. Select Save report and send the file to Slate Operations support." No Try again.
  - The engine updated, the Windows part did not finish: "Slate Operations is updated to version 0.2.1, but setup could not finish its part on this PC."
  - Every failure line has "Details" under it (as S13, AC-O9): the code that the step or the engine job answered ("Code: engine_busy") and the job's `detail` when it sent one, as selectable text; the setup log has both.
  - Slow state of the engine job: "This step takes longer than expected." and "The update goes on by itself. You can close setup now. Later, run this setup again and select Update now. Setup then finishes the update on this PC." with Save report; no Try again.

### U01 to U04 Uninstall (plan 9.1)

- **U01 Keep your data?** Title "Uninstall Slate Operations". ( ) "Keep my data (recommended). Slate Operations is removed. Your records, files and settings stay in D:\SlateOps\kept (14 GB). Install Slate Operations again to continue where you stopped." ( ) "Delete everything. Removes all records, files and settings from this PC." Under "Delete everything" only: [ ] "Also delete the backups on E:". Buttons: "Uninstall", "Cancel". Closing the window cancels; nothing is removed (plan F4c).
- **U02 Confirm delete.** Title "Delete all Slate Operations data?". "This deletes all your records, files and settings in Slate Operations on this PC. It cannot be undone. The backups on E: are kept." (Windows does not keep the organization name.) (or "are deleted too."). [ ] "I understand that this cannot be undone". Buttons: "Delete everything" (off until checked), "Go back" (default).
- **U03 Removing.** "Removing Slate Operations… (about 2 minutes)" with three stages: "Stop Slate Operations", "Moving your data to D:\SlateOps\kept…" (only with "Keep my data"), "Remove the program and its Windows settings". The one line with the time, and the bar of 6.3 in the place of Inno's uninstall bar (6.3, U03 check).
- **U04 Result.** "Slate Operations is removed. Your data is kept in D:\SlateOps\kept." or "Slate Operations and its data are removed." One line: "Virtual Machine Platform and Windows Subsystem for Linux (WSL) stay on this PC, because other programs can use them." Leftovers state: "Uninstall finished. Some items could not be removed. Setup removes them the next time it runs." with "Save report". Keep-data failure (plan F3): "Setup could not keep your data safely. Nothing was removed." with "Save report".

### T01 Trust page on a phone (web page, built in W6b; not a wizard screen)

The QR code on S15 and "Show the phone code" in M01 open this page. It is a static page that Slate Operations serves on the office network (plan 6.3). Revised after the W6b screen review (TASK-0088).

- **The device word.** iPhone and Android: "phone". iPad: "iPad". Windows and Mac: "computer". An unknown device, and the static page without JavaScript: "device". The word fills the title, the status label and "The page does not open?".
- **Title.** "Let this phone open Slate Operations" (with the device word). The static default in the page: "Let this device open Slate Operations".
- **Status line, first.** "This phone trusts Slate Operations:" (with the device word), then "Checking…", "Yes" or "Not yet" (the page checks `https://<name>.local/trust/ok`; plan 10.7). With "Yes", the only action is "Open Slate Operations".
- **Without JavaScript,** in place of the status line: "This page cannot check this device by itself. When you have done the steps, change http:// to https:// at the start of this page's address. If the browser shows a warning, stop and do the steps again. With no warning, this device trusts Slate Operations."
- **Steps,** for the detected device, with links to the other devices ("Other device:"). Without JavaScript, or for an unknown device, all four sets show. Button captions have no final period.
  - iPhone or iPad:
    1. "Use Safari. Other browsers cannot install the profile."
    2. Button "Download the profile", with the line "When asked, select Allow." under it.
    3. "Open Settings → Profile Downloaded → Install."
    4. "Open Settings → General → About → Certificate Trust Settings, and turn on Slate Operations."
    5. "Come back to this page."
  - Android (Android 11 and later install a CA certificate only from Settings, not from the browser):
    1. "Use Chrome."
    2. Button "Download the certificate".
    3. "Open Settings, search for CA certificate, and select it. Choose the file you downloaded."
    4. "If the phone asks for a screen lock, set one. If it warns you, choose to install anyway."
    5. "Come back to this page."
    
    The steps use the Settings search, not a menu path, because the menu names differ by maker (Assumption; the owner's W14 pass shows it).
  - Windows PC:
    1. Button "Download the certificate".
    2. "Open the downloaded file, then select Install Certificate."
    3. "Select Current User, then Next."
    4. "Select Place all certificates in the following store, then Browse → Trusted Root Certification Authorities → OK → Next."
    5. "Select Finish, then Yes."
    6. "Close the browser, open it again, and come back to this page."
    
    Line after the steps: "If Firefox still shows a warning, use Edge or Chrome."
  - Mac:
    1. Button "Download the certificate".
    2. "Open the downloaded file. Keychain Access opens and adds it."
    3. "In Keychain Access, open the Slate Operations certificate."
    4. "Open Trust, and set When using this certificate to Always Trust."
    5. "Close the window, enter your Mac password, and come back to this page."
    
    Line after the steps: "If Firefox still shows a warning, use Safari or Chrome." (Assumption: Firefox can keep its own certificate list.)
- **"The page does not open?"** "Connect the phone to the same Wi-Fi as the server PC. A guest Wi-Fi often blocks this. Turn off a VPN on the phone." (with the device word). "Another subnet" (plan 10.7) is not named: "subnet" is a banned term (section 3), and "the same Wi-Fi" says what to do.
- **"Check the code"** (Details): the security code (the certificate fingerprint), with "It must match the security code on the finish page or in Slate Operations settings on the server PC."
- **Type.** The system font stack, with 16 px body text. The page loads nothing from another host (W6b-2), so it has no product font files; it is outside the app, so DESIGN.md does not change.

## 7. Messages by plan ID (final copy)

These replace the draft messages in plan 4.1, 4.2, 10.3 and 10.7. In the tables, "S13" means the S13 layout: shown in place on the page where the failure happens (section 4.1). Before Install it adds "Try again" and "Save report"; on S12 it adds "Save report" and "Remove and close" (S13), unless the row says otherwise.

### 7.1 Requirements (plan 4.2)

| Plan ID | Spec ID | Final message |
|---|---|---|
| R1 | C01 | Section 5.3, C01 |
| R2 | C02 | Section 5.3, C02, and S03 |
| R3 | C04 | Section 5.3, C04 |
| R4 | C05 | Section 5.3, C05, and S03 |
| R5 | C07 and S07 | Section 5.3, C07; S07 messages |
| R6 | C10, C11 | Section 5.3, C10 and C11 |
| R7 | C18 | Section 5.3, C18 |
| R8 | C12 | Section 5.3, C12 |
| R9 | C21 | Section 5.3, C21 |

### 7.2 Pages (plan 4.1)

| Plan page | Situation | Final message | Screen and actions |
|---|---|---|---|
| 3a | Restart needed | S05 content | S05 |
| 4 | Drive too small, wrong drive type, folder not empty | S07 messages | S07 |
| 4a | The server part does not start | "Setup could not start the server part of Slate Operations." | S12 (S13 layout) |
| 5 | Field errors | S08 messages | S08 |
| 6 | Email errors | Section 7.3 | M02 (after the install) |
| 7 | Backup drive errors | S10 messages | S10 |
| 8 | Public network, port in use, address in use | C10, C14; the address check on S08 Next | S02 (moved from page 8); S08 |
| 10 | A step fails | "Setup could not <stage in lower case>." For example "Setup could not set up the database." | S13 |
| 10 | Check from this PC fails | "Slate Operations is installed, but this PC cannot open it at https://riverside-learning.local." | S13 |

### 7.3 Email test results (plan 4.1 page 6 and 10.7)

Each message shows under the field it is about.

| Class | Final message | Under |
|---|---|---|
| Password refused (Gmail) | "Gmail did not accept this password. Use an app password, not your normal Gmail password." plus "How to make an app password" | Password |
| Password refused (other providers) | "The email provider did not accept the user name or password. Check them and try again." | Password |
| Cannot connect | "Setup cannot reach the email server smtp.example.com. Check the server name and port." (Gmail: "Setup cannot reach Gmail. Check the internet connection.") | Server, or Provider |
| No secure connection offered | "This email server does not offer a secure connection. Slate Operations sends email only over a secure connection. Choose the other security option, or ask your email provider." | Security |
| Secure connection certificate fails | "The secure connection to smtp.example.com failed. Check the server name, and check this PC's date and time." | Server |
| Sender refused | "The email provider does not let this account send as office@example.com. Use the address of the account." | Send from |
| Recipient refused | "The email provider refused to send the test email to the administrator's address. Use another sending account, or ask your email provider." | Send from |
| Any other result | "Setup could not send the test email. Check each field, then select Send test email again." | Password |

### 7.4 Self-checks (plan 10.3)

| Plan ID | Final message | Screen and extra action |
|---|---|---|
| F1 | C17; the address check (S08) | S02; S08 |
| F2 | "Slate Operations is installed, but this PC cannot open it at https://riverside-learning.local." | S13 |
| F3 (uninstall) | "Setup could not keep your data safely. Nothing was removed." | U04 with Save report |
| F3 (reinstall) | "Setup could not open the kept data. The kept data is not changed." | S12 (S13 layout) with Save report and Remove and close |
| F4a | S05 content names the desktop shortcut. | S05 |
| F4b | "This step took longer than setup allows." | S12 (S13 layout) with Save report and Remove and close; every S12 step has a limit (S12) |
| F4c | "Uninstall stopped. Nothing was removed." | Windows message box with Save report |
| F4d | "Setup cannot pass the password safely to the server part. Nothing was sent." | S12 stage "Create your administrator account" (S13 layout, Remove and close); M02 in a modal form |
| F5 | "Slate Operations cannot save backups to the E: drive." | S12 in place (S13 layout) with Save report and Remove and close |
| F6 | Same as F2 | S13 |
| F10 | "The server part did not start again after Windows updated Windows Subsystem for Linux (WSL)." | S13 |
| W4-5 | "Setup could not start the server part of Slate Operations." | S13 |
| W7-6 | M01: "Not ready since 09:12. Select Repair. If that does not help, select Save report." | M01 |

### 7.5 Failure catalog (plan 10.7)

| Plan row | Final message | Screen and recovery |
|---|---|---|
| Virtualization off | C04 | S02 |
| Windows too old, or Home | C01, C02 | S02, S03 |
| Restart pending | C08, recorded only (Log) | None: setup goes on; Save report holds the values |
| WSL or Windows feature install fails | "Setup could not turn on Virtual Machine Platform." or "Setup could not install Windows Subsystem for Linux (WSL)." Code 1618: "Another installation is running on this PC. Setup waits and tries again." | S05 waiting state; then S13 |
| Resume does not start | S05 content | Desktop shortcut |
| Antivirus or Smart App Control blocks a file | Antivirus: "A security program on this PC blocked part of Slate Operations setup. Allow the folder C:\Program Files\Slate Operations in the security program, then select Try again." On S07 the last words are "then select Next again". On S12: "A security program on this PC blocked part of Slate Operations setup. Allow the folder C:\Program Files\Slate Operations in the security program, then start setup again." The blocked file name shows only in Details and Save report; the advice names only the program folder, which only administrators can change. Smart App Control: "Windows blocked part of Slate Operations setup. Select Save report and send the file to Slate Operations support." No advice to turn Smart App Control off (plan 10.7; C19 is Log only). If Windows blocks the setup file itself, no screen shows; `README.txt` and the release notes describe this case. | In place (S13 layout) |
| Import fails | "Setup could not start the server part of Slate Operations." | S12 (S13 layout) |
| Docker or systemd does not start | "Setup could not start the server part of Slate Operations." | S13 |
| No internet, proxy, name lookup, rate limit, secure connection | C12 messages on S02; on S12 the stage message, for example "Setup could not load the Slate Operations programs." | S02; S12 (S13 layout) |
| Disk full during the install (the server part's own disk: the engine checks the free space inside the server part, so free space on the Windows drive does not help; Assumption until W14) | "The server part of Slate Operations has no free space left. Select Save report and send the file to Slate Operations support." | S13 |
| Disk full later | M01: "Needs attention: drive D: is almost full. Free some space." | M01 |
| Ports in use | C14 | S02 |
| Firewall rule fails | "Setup could not set up Windows Firewall for Slate Operations." | S13; Repair in M01 |
| Public network or domain | C10, C11 | S02, S03 |
| Address does not open on a phone or a computer | S15 step 3 and T01 "The page does not open?" (with the device word) | T01 |
| Certificate not trusted | Server PC: F2 message. Phone: T01 status "Not yet". | S13; T01 |
| Email errors | Section 7.3; later M01: "Needs attention: email sign-in fails. Select Set up email." | M02; M01 |
| Database, migration, readiness | "Setup could not set up the database." / "Slate Operations did not start." | S13 |
| Service account cannot sign in | M01 and M02: "Windows did not let Slate Operations start. A security policy on this PC can cause this. Select Repair. If it happens again, ask the person who manages this PC." S12: "Windows did not let Slate Operations start. A security policy on this PC can cause this. Ask the person who manages this PC, then start setup again." | M01; S12 (S13 layout) |
| WSL stops the idle server part | None (automatic) | — |
| Windows Update installs a newer WSL | None; known-bad version: M01 "Needs support…" | M01 |
| Power cut, or setup closed before the install finished | The next start runs the removal: "An earlier setup did not finish. Setup removes everything it added, then starts again. Kept data from an earlier installation stays." Chosen from the Windows-side records (section 4.1), not from the server part (DEC-0038). | Removal form, then S01 |
| Clock wrong | C13 | S02; later M01 |
| Low memory | M01: "Needs attention: Slate Operations is short of memory. Close other programs on this PC." | M01 |
| Wi-Fi not connected at start | M01: "Needs attention: this PC was not on the network after it started. Set the Wi-Fi to connect automatically, or use a network cable." | M01 |
| IP address changes | M01: "Needs attention: the network changed. Select Repair." | M01 |
| Uninstall leftovers | U04 leftovers state | U04 |
| Kept data does not match | Section 4.3; F3 reinstall message | S12 (S13 layout) |
| Parts of the boot-test kit are on the PC | C29: "This PC has parts of an earlier Slate Operations test. Setup removes them before it continues." "Remove them" opens the C29 form with Continue and Cancel. | S02; removal only after Continue |
| `C:\ProgramData\SlateOps` owned by a user who is not an administrator | "Setup cannot use the folder C:\ProgramData\SlateOps, because a user who is not an administrator owns it. Select Save report and ask the person who manages this PC." | S01 in place; setup reads nothing from the folder |
| A folder above the chosen data folder fails the safety check (`setup.data.data_folder_parent_unsafe`; TASK-0091 S91-2) | "Setup cannot keep your data in D:\Office\SlateOps, because it cannot protect a folder above it. This is common for folders made in File Explorer. Setup can protect D:\SlateOps for you." Button: "Use D:\SlateOps". One message for every value of `reason`; the value never shows on screen and goes only to the log and Save report. | S07 in place, under the Folder line; "Change folder" stays. On Next, setup stays on S07 until the folder check answers; only then does S08 open. When the folder changes between S07 and S12, S12 shows "Setup cannot keep your data in D:\SlateOps, because a folder above it changed." (S13 layout). "Use D:\SlateOps" sets the folder to `\SlateOps` on the drive of the chosen folder when the drive list holds that drive, else on the drive selected in the list; then the S07 checks run again. Setup never changes a folder above. |
| Setup was approved with another administrator account, so it cannot add its automatic restart entries (`setup.resume.resume_other_user`; TASK-0091 S91-7) | In place of S05 step 3 and the line "If setup does not open…": "3. Sign in again, then open the setup file again. Setup cannot open by itself after this restart, because it runs with another administrator account." Under the steps: "The setup file: C:\Users\maria\Downloads\SlateOpsSetup-0.2.0.exe. When you open it, Windows asks for the administrator account again." | S05 "ready to restart" state, before the person selects Restart now: setup saves its progress when this state opens, and this code means the progress is saved. The same sentences, without the step number, show in the confirmation before C08 "Restart now" and C04 "Restart to startup settings" on S02, S06 and S11. Not a failure: no S13 layout, Next stays "Restart now", and "Restart later" closes setup with no shortcut. The saved progress stays, so the setup file continues as section 4.1 says. |

### 7.6 Waits and progress lines (W14-D5)

Every wait in setup, the settings program and the uninstaller, with its form (6.1, progress block), its stages and one action line per step. Every wait runs from the wizard's timer, so its time counts (parent decision, 2026-11-18). Example values: riverside-learning.local, D:, E:, F:, 0.2.0, 0.2.1, maria@example.com, WSL 2.6.1.

Where the current step comes from:

- **Engine** keys (`job.key`) are the fixed step keys of `packaging/engine/progress.py` `STEPS` (`8fd301f0`): the engine writes `progress <job> <n>/<total> <key> <state>` on standard error as each step starts, and the wizard reads only lines of that shape. A `done` state (an install rerun) shows the stage as "Done". A step that does not run writes no line.
- **Windows** keys are the wizard's own sequence or the helper's steps. The helper keys (`pc.*`, `bg.*`, `win.*`, `repair.*`, `upd.*`, the check counts) are new and Proposed; the helper writes them to its progress file (plan F4b).
- A key with no line here shows its stage name, never the key.
- The bar and the time text of each wait: 6.3 (per-surface table).
- **No sentence on screen ends with a drive letter before its full stop** (owner, rc.28: "drive D:." reads as a double stop). The letter goes before a noun: "the D: drive", "the E: backup drive". Changed in this revision: the S12 stage name "Copy the server part to the D: drive" (`bg_stages`), the action lines bg.import, upd.copy, backup.check, install.backup, repair.backup, new-recovery-key.mount and .key, set-backup-target.unmount, .mount and .repository (7.6), and the sentences C07, S10 and M03 "cannot write to", M01 "Last backup", F5 (`s12_backup_failed`). A drive letter inside a path ("D:\SlateOps.") is not affected.

| Wait | Form | Stages ("Done", "Now", "Next") | Action lines (key: line) | Side |
|---|---|---|---|---|
| S02 PC check | Full; "Usually about 1 minute" (bar: 6.3, Proposed) | 1 Windows and processor (C01 to C06); 2 Space and updates (C07, C08); 3 Network and address (C09 to C14, C17); 4 Security, power and earlier tests (C18 to C29) | "Checking: <check name> (12 of 30)." (name and count from the helper) | Windows (helper) |
| S02 fixes | One line in the item | — | C10: "Making this network Private…" C17: "Turning on the Windows rule that lets phones find this PC…" C29 test parts: "1 of 3: Stopping the earlier test's server part", "2 of 3: Removing its data", "3 of 3: Removing its account, tasks and firewall rules". C29 uninstall leftovers: "Removing the tasks, account and firewall rules of the earlier uninstall…" Then "Checking again…" | Windows (helper) |
| S02, S06 and S11 restart (C04) | One line | — | "Saving your progress…", then "Restarting this PC…" | Windows |
| S05 prepare | Full with the bar row; "Usually about 2 minutes" | 1 Turn on Virtual Machine Platform; 2 Install Windows Subsystem for Linux (WSL); 3 Restart this PC; then "Next: Your details", "Next: Install" | pc.unpack: "Unpacking Windows Subsystem for Linux (WSL) from this setup file." pc.vmp: "Turning on Virtual Machine Platform." pc.wsl: "Installing Windows Subsystem for Linux (WSL) 2.6.1." pc.busy: "Another installation is running on this PC. Setup waits and tries again (2 of 3)." pc.check: "Checking whether Windows needs a restart." | Windows (helper) |
| S06 and S11 recheck | Full on S06; one line on S11 | — | "Checking this PC again: <check name> (3 of 7)." | Windows (helper) |
| S07 drives, kept data | One line | — | "Looking for drives…"; "Reading the kept data in D:\SlateOps\kept…" | Windows |
| S07 Next | One line under the Folder line; limit 60 seconds | — | "Checking the folder D:\SlateOps…" (read only) | Windows (helper) |
| S08 Next | One line under the form; limit 30 seconds | — | "Checking that no other device on this network uses riverside-learning.local…" | Windows (helper) |
| S12 data folder (stage 1) | Full, inside S12 | Stage 1 "Prepare the data folder" | data.unpack: "Unpacking the server part from this setup file." data.folder: "Preparing the data folder D:\SlateOps." | Windows |
| S12 server part (stages 2 to 8) | Full, inside S12 | 1 Add the hidden Windows account; 2 Set the memory of the server part; 3 Copy the server part to the D: drive (kept data: Move your kept data back; Open your kept data); 4 Start the server part; 5 Receive the Slate Operations programs; 6 Check the server part; 7 Download the database and sign-in programs; kept data adds 8 Check the kept data | Windows: bg.service: "Adding the hidden Windows account that runs Slate Operations." bg.wslconfig: "Setting the memory of the server part to 6 GB." bg.import: "Copying the server part to the D: drive." bg.restore_kept: "Moving your kept data back into D:\SlateOps." bg.import_kept: "Opening your kept data." bg.start: "Starting the server part." bg.kept_status: "Checking that the kept data belongs to this installation." Engine, stage 5: receive.space: "Checking the free space for the new programs." receive.stage: "Copying the Slate Operations programs into the server part." receive.signature: "Checking the signature of the Slate Operations programs." receive.check: "Checking each program against its signature." receive.load: "Loading the Slate Operations programs." receive.keep: "Keeping the checked programs for the install." Stage 6: prepare.systemd: "Checking that the server part has started." prepare.docker: "Checking that the server part can run services." prepare.container: "Starting a test service in the server part." prepare.networking: "Checking the network of the server part." prepare.time: "Checking the clock of the server part." prepare.listeners: "Checking that the web connection of the server part is free." prepare.interop: "Checking that the server part cannot start Windows programs." prepare.mounts: "Checking that the server part cannot open your Windows drives." prepare.shells: "Checking the user accounts of the server part." prepare.bundle: "Checking the Slate Operations program files." Stage 7: prefetch.start_pull: "Downloading the database and sign-in programs (1.2 GB of 3.4 GB)." (the numbers from `status`) | Windows (stages 1 to 4, 8); engine (stages 5 to 7) |
| M02 provider lookup | One line under Provider | — | "Looking up the email provider of example.com…" | Windows |
| M02 Send test email | One line under the form, with the compact bar | 1 Check the password channel; 2 Check the security policy; 3 Send the test email; 4 Save the email account | "Checking that setup can pass the password safely."; "Checking the security policy of this PC."; "Sending a test email to the administrator's address."; set-email.write: "Saving the new email account in Slate Operations." set-email.auth: "Restarting sign-ins with the new email account (about 1 minute)." | Windows (1, 2); engine (3, 4) |
| S10 Next | One line under the list | — | "Checking drive E:…" | Windows |
| S12 install (stages 9 to 16) | Full with the bar row and the time left; subtitle "This can take up to 30 minutes." (only there) | The eight install stages of S12 | Stage 1: backup.check (Windows): "Checking the E: backup drive." install.release: "Checking the signature of the Slate Operations programs." install.images: "Loading the Slate Operations programs." Stage 2: install.folders: "Creating the folders for the settings." install.secrets: "Creating the passwords that Slate Operations uses inside the server part." install.env: "Writing the settings." Stage 3: install.tls: "Creating the security certificate for riverside-learning.local." Stage 4: install.providers: "Starting the database, sign-in and file storage." install.provision: "Setting up the database." Stage 5: install.api: "Starting Slate Operations." install.caddy: "Starting the secure web connection." Stage 6: install.admin: "Creating your administrator account for maria@example.com." Stage 7: install.backup: "Making the first backup on the E: drive." install.finish: "Saving the installation details." Stage 8 (Windows): win.firewall: "Allowing Slate Operations through Windows Firewall on Private networks." win.hosts: "Making riverside-learning.local open Slate Operations on this PC." win.trust: "Making this PC trust the security certificate of Slate Operations." win.power: "Keeping this PC awake when it is plugged in." win.lid: "Keeping this laptop running when the lid is closed." win.https: "Checking that https://riverside-learning.local opens on this PC." | Engine (stages 1 to 7, except backup.check); Windows (backup.check, stage 8) |
| After S12 (Inno file copy) | Inno's own page and bar | — | "Copying the Slate Operations settings program to this PC." | Inno |
| S14 key and M04 | Full on S14; one line on M01 | — | new-recovery-key.mount: "Connecting the E: backup drive." new-recovery-key.key: "Making your recovery key." (M04: "Making your new recovery key and removing the old one."); print: "Looking for printers…", then "Sending the key to <printer name>…"; USB: "Saving the key to F:…" | Engine (key); Windows (print, USB) |
| Save report (S01, S02, S03, S12, S13, M01, M02, U04, Start menu) | One line with the compact bar, beside the Save report button or in the S13 form; in the settings program a small form with the one line | 1 Collect the setup logs; 2 Collect the server part's logs; 3 Remove passwords and personal details; 4 Save the file to your desktop | "1 of 4: Collecting the setup logs"; stage 2: log-bundle.facts: "2 of 4: Collecting facts about the server part" log-bundle.snapshot: "2 of 4: Collecting the server part's logs" log-bundle.bundle: "2 of 4: Packing the server part's logs" (or "The server part is busy, so its logs are left out."); "3 of 4: Removing passwords and personal details"; "4 of 4: Saving SlateOps-report-….zip to your desktop". Stage 4 starts only when stage 3 reports that it collected everything; any other result, or no answer within the time limit, saves no file. Result lines: "Report saved to your desktop: <file>." with "Show in folder", or "Setup could not save the report. Select Save report again." | Windows (1, 3, 4); engine (2) |
| The removal (Cancel, closing the window, a failed install, an earlier run at start; section 4.5) | Full with the bar row, in the removal form | 1 Stop the install step that is running; 2 Stop Slate Operations; 3 Remove the server part and its data; 4 Turn off Virtual Machine Platform and Windows Subsystem for Linux (WSL), if setup turned them on; 5 Remove the Windows settings | "Stopping the install step that is running…"; "Stopping Slate Operations…"; "Removing the server part and its data…"; "Turning off Virtual Machine Platform and Windows Subsystem for Linux (WSL), if setup turned them on…"; "Removing the Windows settings…" | Windows (helper) |
| M01 status | Full, one stage | — | "Checking Slate Operations…" | Windows |
| M01 Repair | Full with the bar row, in place of the action buttons until the result | 1 Check the security policy; 2 Set a new password for the hidden account; 3 Set up the start tasks; 4 Set up Windows Firewall; 5 Set the address on this PC; 6 Start Slate Operations; 7 Set the backup folder rights | repair.r7: "Checking the security policy of this PC." repair.account: "Setting a new password for the hidden Windows account." repair.tasks: "Setting up the tasks that start Slate Operations." repair.firewall: "Allowing Slate Operations through Windows Firewall on Private networks." repair.hosts: "Making riverside-learning.local open Slate Operations on this PC." repair.start: "Starting Slate Operations." repair.backup: "Setting the rights of the backup folder on the E: drive." | Windows (helper) |
| M01 phone code | One line | — | "Reading the security code…" | Windows |
| M03 | One line under the list | 1 Check drive F:; 2 Prepare drive F: for backups; 3 Set F: as the backup drive; 4 Make the recovery key for F: | Windows: "Checking drive F:…"; "Preparing drive F: for backups…". Engine: set-backup-target.unmount: "Disconnecting the E: backup drive." set-backup-target.mount: "Connecting the F: drive." set-backup-target.repository: "Preparing the backup store on the F: drive." new-recovery-key.mount: "Connecting the F: drive." new-recovery-key.key: "Making the recovery key for the F: drive." | Windows (1, 2); engine (3, 4) |
| M05 update | Full with the bar row and the time left ("This can take up to 1 hour." stays in the page text) | 1 Prepare the update; 2 Make a backup; 3 Update; 4 Check that it works; when it fails after the backup: "Go back to version 0.2.0" | Stage 1, Windows: upd.idle: "Waiting until Slate Operations is free (a backup or another task runs)." upd.unpack: "Unpacking version 0.2.1 from this setup file." upd.copy: "Copying version 0.2.1 to the D: drive." Engine: the receive lines of the background row, for version 0.2.1. Windows: upd.wsl: "Updating Windows Subsystem for Linux (WSL) to 2.6.1." Engine: update.lock: "Making sure no backup runs during the update." update.release: "Checking version 0.2.1." update.space: "Checking the free space in the server part." update.images: "Loading the programs of version 0.2.1." Stage 2: update.backup: "Stopping Slate Operations and making a backup." Stage 3: update.env: "Writing the settings of version 0.2.1." update.providers: "Starting the database, sign-in and file storage on version 0.2.1." update.health: "Waiting until the database, sign-in and file storage are ready." update.provision: "Updating the database." Stage 4: update.api: "Starting Slate Operations 0.2.1 and checking its version." update.caddy: "Starting the secure web connection." update.switch: "Finishing the update." Windows: upd.scripts: "Finishing the update on this PC." Going back (stage "Go back to version 0.2.0", under the line "The update did not work. Setup goes back to version 0.2.0."): recover.recover: "Starting version 0.2.0 again with its settings." rollback.down: "Stopping version 0.2.1." rollback.restore: "Restoring the backup made before the update." rollback.rebind: "Connecting Slate Operations to the restored data." rollback.finalize: "Checking the restored data." rollback.start: "Starting version 0.2.0." rollback.adopt: "Making version 0.2.0 the running version again." | Windows and engine, as marked |
| U03 uninstall | One line in Inno's uninstall form ("Removing Slate Operations… (about 2 minutes)" first); each helper step has a limit (DEC-0041), and a step past it counts as failed (U04 leftovers state) | 1 Stop Slate Operations; 2 Move your data to D:\SlateOps\kept (or Delete the data in D:\SlateOps); 3 Remove the program and its Windows settings | Engine, stage 1 with "Keep my data": prepare-uninstall.stop_timer: "1 of 3: Stopping the nightly backups" prepare-uninstall.stop_docker: "1 of 3: Stopping Slate Operations". Windows: "2 of 3: Moving your data to D:\SlateOps\kept" or "2 of 3: Deleting the data in D:\SlateOps"; "3 of 3: Removing <item>" | Engine (stage 1, keep path); Windows (the rest) |

The engine job `renew-certificate` runs from the nightly runner, not from a wizard page, so the wizard shows no line for it. If a later page runs it: renew-certificate.renew: "Making a new security certificate." renew-certificate.check: "Checking the new certificate." renew-certificate.trust: "Updating the phone page with the new certificate." renew-certificate.reload: "Starting the secure web connection with the new certificate."

Waits before any window exists, so no progress shows: the start of setup (the state folder check and the entry), the start after a restart (the administrator prompt, then the same check) and the start of the uninstaller (the state check and the uninstall information before U01). Each must stay short; a slow start goes to Save report.

## 8. What the person decides and what is automatic (AC-3)

| Item | Decided by | Default | Where a change is possible | Reason |
|---|---|---|---|---|
| License | Person | — | S04 | A legal acceptance. |
| Fixes in the check | Person, per item | — | S02 | Each changes Windows; nothing changes without a select. |
| Remove the parts of an earlier test (C29) | Person | — | S02, C29 form (Continue or Cancel) | It deletes the earlier test's data; setup cannot continue without it, because the account name is the same (plan 10.7). |
| Laptop lid (C22) | Person | Not changed | S02 ("Change it during the install") | Changed during the install, so uninstall can restore it. |
| Restart time | Person | Restart now | S05 ("Restart later") | The person may have open work. After the restart, setup continues at S06 (section 4.1). |
| Data drive and folder | Automatic, can change | The largest qualifying drive, `\SlateOps` | S07 | DEC-0028 gives the choice. The default is right for most PCs, so the person only confirms. |
| Program folder | Automatic, can change | `C:\Program Files\Slate Operations` | S07 "Change program folder" | DEC-0028 gives the choice. Few people need it, so it is a link. |
| Use kept data | Person | Use it | S07 card | A new start on old data is a real choice. |
| Organization name | Person | — | S08 | Setup cannot guess it. |
| Administrator name | Person | — | S08 "Your name" | Setup cannot guess it. |
| Administrator email | Person | — | S08 | The person signs in with it. Any valid address works; setup sends no email (DEC-0041). |
| Administrator password | Person | — | S08 (12 to 72 characters, typed twice) | A secret. Setup creates the account with it, so no invitation is needed (DEC-0041). |
| Administrator user name | Automatic | From "Your name" (from the email when the name has no letter or number) | Not shown in setup | The default is valid and readable. |
| Short name of the organization (slug) | Automatic | From the organization name | Not shown in setup | Few people need it. |
| Address name | Automatic, can change | From the organization name, cut at 30 characters | S08 "Change" on the address line; fixed at Install | DEC-0039. A changed address means that every phone and PC trusts Slate Operations again. |
| Email account (sending address, provider, password, server, port, security, sender name) | Person, after the install | Gmail detected from the address, else Other; sender name "Slate Operations" | M02 (DEC-0041, DEC-0040) | The app works without email; invitations and password resets wait for it. |
| Backup drive | Automatic when a second drive exists, else person | Largest other drive | S10 | A second drive protects the data; the person must plug in a USB drive or accept the risk. |
| Backup time | Automatic | Every night at 2:00, PC time zone | Not in the wizard; in the app (Manage → Backups) | The app already owns the schedule (plan 6.2 step 12). |
| Address | Automatic | `<address name>.local` | S08 (the address name); not after Install (plan F1) | One address per installation (plan 1.1; DEC-0039). |
| Edition | Automatic | Desk | In the app only (DEC-0029, TASK-0076) | The owner's rule. |
| Firewall, start task, hidden account, trust on this PC | Automatic | — | Not changeable; listed on S11 | Needed for the server to work. |
| Sleep on mains power | Automatic | Never; uninstall restores | Not changeable | A sleeping server stops for everyone. |
| Server part memory | Automatic | 6 GB (planning value, plan 10.2) | Not changeable; support | A person cannot judge it. |
| Start menu and desktop entries | Automatic | Both | Not changeable | Non-technical users find the app from the desktop. |
| Recovery key saved | Person | — | S14 | Only the person can keep it safe off the PC. |
| Open the app at the end | Person | — | S15 button | The person signs in with the S08 email address and password. |

## 9. Accessibility and clarity

No accessibility conformance is claimed (`PRODUCT.md`: no certification target).

1. **Keyboard.** Every action is a button or a focusable control. The tab order follows the reading order. Enter selects the Next button; Esc selects Cancel. Each button has an access key (an underlined letter). Link-style buttons are real focusable controls, never plain text with a click handler only.
2. **Screen readers.** Text that carries meaning uses `TNewStaticText`, a windowed control that a screen reader can read; never `TLabel`, which a screen reader cannot read. A sentence that must take focus is a read-only, borderless edit field (Assumption: Narrator reads it; WZ-11). Each result uses a word ("Ready", "Needs a fix", "Recommended", "Not suitable", "Fixed"), not only an icon or a color. When a check, a test send or a step ends, focus moves to its result sentence, so a screen reader reads it.
3. **High DPI.** The wizard scales with the Windows display scale (`WizardSizePercent=150,150` and 165% height from the [Code], section 6.1; assumed to fit a screen of 1280 x 720 effective pixels: about 745 x 633 with the title bar). The side image, the small mark and the status icons come in sizes for 100% to 250%. The QR code scales in whole pixels, so it stays sharp.
4. **Color and contrast.** Text uses the Windows system colors, so high-contrast themes work. Status colors are an extra beside the word and the icon shape.
5. **Plain language.** One instruction per sentence, at most 20 words. The full name "Slate Operations" in every sentence that names the product (`PRODUCT.md`). "Organization", never "business", because the users are schools, clinics, shops and offices too. No term from the "never" list in section 3 on a default screen.
6. **Time.** No page moves on by itself. No message disappears by itself. Only the install and the removal run on their own, and both show their state.
7. **Motion.** During a wait only the time text and the progress bar change (6.1, 6.3); the bar moves forward only. Inno's own file-copy bar moves. No other animation; no marquee.

## 10. Changes from plan section 4 (AC-5)

| # | Plan | This spec | What it improves | What it removes or costs |
|---|---|---|---|---|
| 1 | Page 2 License, then page 3 Requirements | S02 PC check right after Welcome; S04 License after a pass | The person knows in about a minute whether this PC can work, before reading a license or changing anything. This is the owner's request. | Nothing. The license is still accepted before the first install change. |
| 2 | Requirements as a list of R1 to R9 with pass or fail per line | One verdict first, then only the items that need the person; passed items collapse into one line | A non-technical person reads one sentence, not nine technical lines. | The full list moves into "Show all checks". |
| 3 | R1 to R9 | C01 to C29 (C15, C16, C30 retired by DEC-0039): adds processor type, early free space, pending restart, clock, ports and the phone check (from page 8), earlier test parts (plan 10.7), antivirus, laptop lid, Wi-Fi, drive encryption (the automatic-unlock advice only; DEC-0037), Docker Desktop; Smart App Control is logged only | Problems that the plan finds late (page 4, page 8, the install) show before any change. | More detection code on the Windows side (section 12 item 8). |
| 4 | "Next stays off until every blocking line passes" | Fix it for me, Show me how, Open … settings, Restart to startup settings, Check again per item | Each problem has a way forward on the same page. | Four Windows changes can happen before the license, each selected by name: C10, C04, C17, C29 (section 5.4). |
| 5 | No screen for an unsuitable PC | S03, a polite stop with what to do instead and Save report (a state of the S02 page) | The person is not left with a disabled Next button. | — |
| 6 | Page 3a message | S05 with numbered steps, "Restart later", Details | The person can choose when to restart, and knows how setup comes back. | — |
| 7 | — | S06 Welcome back | The person sees where setup continues after a restart that setup asked for, or before the recovery key. | One extra page on resume. |
| 8 | Page 4: program folder and data folder fields | S07: drive list with the best drive selected; program folder behind a link; kept-data card | One Next for most people; the DEC-0028 choice stays. | The program folder is less visible. |
| 9 | Page 4a "Getting Linux ready" progress page | All server work after Install, as stages on S12 (DEC-0041); nothing runs in the background before Install | One wait, with stages and limits; Cancel before Install leaves nothing half done. | The install wait is longer, because S12 also prepares the server part. |
| 10 | Page 5 "Business name", user name visible, slug shown | S08 "Organization name", "Your name", "Your email address", the password typed twice, and the address line with "Change"; the user name and the slug are made by setup and not shown | "Organization" fits schools, clinics and offices (`PRODUCT.md`). The person sees the address before Install. | Two more fields (the password), because setup creates the account (DEC-0041). |
| 11 | Page 6 provider choice, all fields, "Send test email" | No email page in setup; M02 after the install: Gmail or Other, provider detected but visible, Gmail help before the password, a test email to the administrator, then saved (DEC-0040, DEC-0041) | Setup asks no email password; a wrong email account cannot stop the install. | The app sends no invitations or password resets until email is set up; S15 and M01 say so. |
| 12 | Page 7 a choice of two | S10: second drive selected by itself; "Plug in a USB drive now" with live detection; check box for the data drive | The safe choice is the easy choice. | — |
| 13 | Page 8 Network name | Removed as a page. The network checks move to S02 (C10, C14, C17); the address comes from the organization name, shows on S08 with "Change", and S08 Next checks that no other device uses it (DEC-0039); the address shows on S11 and S15. | One page fewer; an address that people recognize. | The address cannot change after Install. |
| 14 | Page 9 Ready, a summary | S11 with Change links, "What setup changes on this PC" and the time | The person sees what changes on the PC before it changes. | — |
| 15 | Page 10 step list of engine steps | S12: the data folder, the server part and the eight install stages in plain words, the current action, the time so far, "While you wait", a limit on every step | The person knows what happens and what to do. | — |
| 16 | Failure messages per page | S13, one failure layout for every failure, shown in place on its page | The same "what happened, what to do, Save report" every time, with Try again before Install and Remove and close on S12. | — |
| 17 | Page 11 the key, Print, Save to USB, check box | S14 with an explanation and the backup-drive warning; no Cancel, as in the plan | The person understands why the key matters. | — |
| 18 | Page 12 four lines of text and a QR code | S15: three numbered steps in order (open and sign in, set up email, phones), the QR code, Desk line, how to come back | The owner does the steps in the right order. | — |
| 19 | Cancel after page 4a | Cancel rules per point (section 4.5): nothing to remove before any change; the removal once setup changed this PC | Clear answers at every point. | — |
| 20 | Section 9 uninstall and maintenance | U01 to U04, M01 to M05 with status first | The owner sees the state before the actions. | — |
| 21 | Trust page "steps for iOS, Android, Windows and macOS" | T01: the trust status first; steps for the detected device that work on current versions (Safari on iPhone and iPad, the Settings path on Android 11 and later); causes when the page does not open; a no-JavaScript line that says to stop at a warning | The device shows "Yes" when it is done, and no step leads to a dead end. | — |
| 22 | Plan 10.7 row "Parts of the boot-test kit are on the PC" (page 3) | C29 on S02 with "Remove them", the C29 form, Continue and Cancel | Removal happens only after a select, with a clear list of what goes | The earlier test's data is deleted (as the plan) |
| 23 | Page 12 and maintenance: no way to get a lost invitation | Retired by DEC-0041: setup creates the first administrator with a password, so S15 names the sign-in and M01 has no "Send my invitation again" | The administrator can sign in at once | — |
| 24 | — | M02 (S09 form) note for Outlook.com addresses before the password | The person learns before a failed test that Outlook.com cannot work | — |
| 25 | — | Cancel, closing the window, a failed install and an unfinished earlier run remove everything that setup added (section 4.5; DEC-0038, DEC-0041) | The result is a complete installation or nothing. | A failed install cannot try a step again; the person starts setup again. |

## 11. Acceptance criteria for the build

These criteria add to the plan's W6b, W7, W8 and W9 criteria. Each is checked on the screen by the Product Designer screen review and by the owner's end-user pass (DEC-0031).

- **WZ-1.** Setup on a suitable PC shows S01, then S02 with the verdict "This PC is ready…" within about a minute, and changes nothing before S04 unless the person selects a fix.
- **WZ-2.** Setup on a PC with a Stop item shows S03 with the plain reason, "What you can do" and Save report, and nothing on the PC changes.
- **WZ-3.** Each Fix item has the action of section 5.3, and Check again changes the verdict when the problem is gone.
- **WZ-4.** No default screen shows a word from the "never" list in section 3.
- **WZ-5.** Every failure shows S13 with a "what happened" sentence from section 7 and Save report. Before Install, Try again continues from the failed step; on S12, "Remove and close" runs the removal and closes setup.
- **WZ-6.** On M02, a refused Gmail password shows the Gmail message under the password field; Provider offers Gmail and Other only; a passed test says the address it went to and to check the inbox and the Spam folder, and the account is saved.
- **WZ-7.** Nothing changes on the PC between S07 and Install except a restart that the person selects; S07 Next and S08 Next only read (the folder check, the address check).
- **WZ-8.** S12 shows the bar row (bar, time so far, time left), every stage (the data folder, the server part, the eight install stages) with its state, the current action in plain words and the "While you wait" box. "This can take up to 30 minutes" shows once, in the subtitle. A step past its limit fails with the limit message.
- **WZ-9.** S15 lists the sign-in step with the "Open Slate Operations" button first, the email step second and the QR code (v1: the phone address) third. It opens the trust page on a phone on the same Wi-Fi.
- **WZ-10.** M01 shows one status sentence first, then the actions. U01 defaults to "Keep my data"; "Delete everything" needs U02 with its check box.
- **WZ-11.** With the keyboard only, the person completes the whole install; with Narrator on, each verdict and result sentence is read when it appears.
- **WZ-12.** At 100%, 150% and 200% display scale, on a screen of at least 1280 x 720 effective pixels, no page clips text or controls and no page needs scrolling.
- **WZ-13.** On a PC with parts of the earlier test, S02 shows C29. Nothing is removed until Continue in the C29 form; after the removal, the item shows "Removed", and the verdict changes.
- **WZ-14.** Retired (DEC-0041): M01 has no "Send my invitation again". New: with no email settings, M01 shows the email line with "Set up email".
- **WZ-15.** With an Outlook.com address on M02, no provider is selected, the Outlook.com note shows before the password, and Next stays off.
- **WZ-16.** No page opens another page out of order: failures, the S03 stop and recheck results show in place.
- **WZ-17.** Cancel or closing the window once setup changed this PC (S05 ran, a restart from the check, or Install), and "Remove and close" on a failed S12, show the removal form with its bar, its five stages and the time; afterwards nothing that setup added stays, except kept data and the S02 changes that the person selected; Virtual Machine Platform and WSL go only when setup turned them on. A step past its limit stops the removal, and the next start finishes it before S01.
- **WZ-18.** After the S05 restart, or a C04 restart on S06 or S11, setup opens S06, then S07, and removes nothing; after a C04 restart on S02, it opens S02 with "Welcome back". Any other earlier run is removed at start.
- **WZ-19.** On S08, the address line follows the organization name; "Change" opens the address name; Next with an address that another device answers for shows the in-use message under the field; a password outside 12 to 72 characters (UTF-8 bytes counted for the upper limit) shows its message on S08, never on S12.
- **WZ-20.** Every setup page with the header, and S15, shows the step strip of 6.2 with the current step and the finished steps of its row in the 6.2 table; no step is clickable or takes focus; no page is taller than before (S12 with kept data ends at least 12 px above the page bottom).
- **WZ-21.** Every wait that 6.3 gives a bar shows it with the time; the bar never moves back, not across a stage change and not while the download total grows; S12 and M05 show "About N minutes left", and the number never goes up; a stage past its weight shows "This step takes longer than usual"; no sentence on screen ends with "D:." or another drive letter before a full stop.

WZ-11 and WZ-12 have no runner today: Narrator and display scale are not end-user steps (DEC-0031), and nobody else runs Windows. Static proxy for the W7 and W8 review: the setup script creates no `TLabel`; every action is a `TNewButton` or `TNewLinkLabel` with a tab stop and an access key; the tab order follows the reading order. WZ-12 at the owner's own display scale is an observation in his end-user pass (W14); the other scales stay unverified.

## 12. Requests beyond the plan: decided

The Software Architect decided each request (TASK-0080 Notes, "Software Architect review", 2026-11-16). Plan 4.1 says: where this spec differs from plan 4.1, 4.2 or the 6.2 allow-list, the spec wins once the Software Architect accepts it, and for the allow-list also the Security Engineer. No item changes a public API, a database schema, a storage format or a wire format.

| # | Request | Decision | What the spec does now |
|---|---|---|---|
| 1 | Prepare the server part in the background after S07 | Accepted, with conditions | The wizard runs one `Exec` job at a time and queues the next. The timer never opens a dialog; a failure shows on the next Next or on the test send (S08, S09). Cancel waits for the running job. Whether `prefetch` returns at once stays a plan question for W5b. Superseded by DEC-0041: no background work before Install; the server part is prepared on S12. |
| 2 | The check before the license | Accepted; count corrected | Five person-selected changes before the license (section 5.4). `MinVersion=10.0`, so Windows 10 reaches the S03 stop. `ArchitecturesAllowed=x64compatible` and `ArchitecturesInstallIn64BitMode=x64compatible`, so an Arm PC reaches the S03 stop (C03). |
| 3 | "Restart to startup settings" for C04 | Accepted, with conditions | UEFI PCs only (`GetFirmwareType`). `shutdown.exe /r /fw /t 0`, never a delay above 0 (it closes programs without a warning). Resume as plan F4a: `C:\ProgramData\SlateOps` holds only the saved progress (no copy of the setup file before the space check; re-check N-1); the RunOnce entry and the desktop shortcut start the original setup file, always through the administrator prompt; the folder passes the safety check before any read or write (W80-5). Cancel removes the three. Which RunOnce key elevates after the sign-in stays open for W7. The BitLocker caution depends on C: (W80-4). |
| 4 | Turn on the mDNS rule for C17; the address rule | Accepted; changed by DEC-0039 (OD-1) | C17: the existing built-in rule, Private profile only; the C17 fix creates no rule; old state logged; not undone by uninstall. Policy: "Ask the person who manages this PC". The address (DEC-0039, option B): the install adds one inbound rule of its own for the responder that answers `<address name>.local`: `SlateOps-mDNS-In-UDP`, UDP to local port 5353, Private profile, local subnet only, program `%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe` (the start task's process); it is recorded with the other firewall rules and removed with them by the removal, Repair rewrites it, and uninstall removes it. |
| 5 | The lid for C22 | Changed | S02 records the choice; the Windows-side steps of S12 change it; uninstall restores it. |
| 6 | Which memory value R4 reads | Decided | R4 passes at `TotalPhysicalMemory` ≥ 12 GiB. The screen shows the installed memory from `GetPhysicallyInstalledSystemMemory` (C05). Planning value. |
| 7 | Email provider detection | Accepted; changed | Windows side only: known domains, then MX records; the MX answer only selects Gmail or Microsoft 365 by an exact host match and fills no field (W80-7); the choice stays visible. Outlook.com addresses get the S09 note and never Microsoft 365. The Microsoft 365 admin dialog adds the security-defaults line. Changed by DEC-0040: Gmail and Other only; the MX answer selects only Gmail; a Microsoft 365 domain gets Other. The detection runs on M02 (DEC-0041). |
| 8 | Detection for the new checks | Accepted; changed | A hidden helper in `{tmp}` writes progress and result files. An unreadable blocking check shows as Advice "Setup cannot read …" (section 5.2). Each method stays an Assumption until W7. |
| 9 | Print the recovery key without a file | Accepted, with constraints | Printing inside the setup process with Windows printing calls: no file, no helper program, no PowerShell; fixed print job name; printers that write a file are refused (W80-3). The spool file stays the W8-5 exception. "Save to a USB drive" offers removable drives only (W80-2) and refuses the backup drive (W80-1). |
| 10 | The QR code on the Windows side | Accepted; changed | Drawn by the setup program from the computer name. S15 Details and the M01 phone-code form also show the security code (the certificate fingerprint from this PC's trusted certificates; plan 6.3). A copied QR encoder needs its third-party notice. Changed by DEC-0039: the address and the trust page address come from the stored address name (`host_label` in `state\install.json`), not the computer name. v1 shows the address as text (DEC-0036). |
| 11 | A way to get a lost invitation | Accepted: new allow-listed job `resend-invitation` | Input: the run ID only. Output: `sent`, `already_active`, `rate_limited` or a failure class. M01 always shows "Send my invitation again" (section 6, M01); S15 names it. Work: W5b (job) and W8 (M01). Subject to the Security Engineer's review, which runs now. A wrong email address stays a support case in v1. Superseded by DEC-0041: the first administrator gets a password in setup, so M01 no longer shows the action (Product Designer, 2026-11-18). Whether the job leaves the allow-list is for the Software Architect. |
| 12 | Inno Setup fit | Accepted; changed | The controls of section 6.1; `WizardStyle=modern`; `WizardSizePercent=150,150` with 165% height from the [Code] (6.1); the status text inside the page (6.1 Frame; `BeveledLabel` stays empty); captions set when a page opens and in each state; focusable read-only edit fields for verdicts; WZ-12 screen size. |
| 13 | A desktop shortcut | Accepted | An `[Icons]` entry with the address (an Internet Shortcut); uninstall removes it (plan 9.1 list, W7). |
| 14 | An older setup file on a newer installation | Accepted | The older file starts the installed setup copy with the maintenance switch, then closes (section 4.1). The installed copy is the small Windows part only. |
| 15 | Time values and progress numbers | Accepted; changed | Planning values as proposed. The engine writes whole numbers for progress (bytes done, bytes total, step number); the Windows side uses them only for display (S12). |

Security Engineer review (TASK-0080 History, 2026-11-16; 0 BLOCKING; `resend-invitation` accepted for the allow-list with fixed bootstrap arguments and no raw output in logs). Changes applied:

- W80-1 refuse the backup drive for the recovery key (S14); W80-2 removable USB drives only; W80-3 fixed print job name, file printers refused.
- W80-4 the C04 BitLocker caution depends on C:, or an unreadable state; setup never suspends BitLocker. W80-9 BitLocker status only (`ProtectionStatus`) of C: and the data drive, with the automatic-unlock advice (C24).
- W80-5 every start through the administrator prompt; the state folder passes the safety check first (section 4.1). W80-6 programs started as the original user with fixed targets (section 6.1). W80-7 the MX answer selects a provider only. W80-8 C18 unreadable is Fix, and R7 runs again before each password use (section 5.2).
- Item conditions: the "Show" toggle resets (S09); the key is non-selectable text with no Copy, M04 asks for confirmation before the job and states that the current key stops working, because the engine removes the old key when it makes the new one (D-B, Security Engineer accepted; this replaces "M04 Cancel removes the new key"), and a resume without the "key saved" mark runs `new-recovery-key` (S14, 4.1); antivirus advice names only the program folder (C20, 7.5); C29 never reuses `slateops-svc`, stops on unknown Slate Operations parts, and names the fallback.
- Parent decision on open point 1: "Keep it and continue later" deletes the staged email settings with the `discard` mode of the existing `smtp-test` job (input: the run ID only); no new job name. Superseded by DEC-0041: no "Continue later" and no staged email settings.
- Parent decisions after the re-check: N-1 (state folder holds only the saved progress; RunOnce and the shortcut start the original file), N-2 (a lone `slateops-svc` is an uninstall leftover in the C29 copy), N-3 (the "install started" record holds no answers or email), the small maintenance copy, and M03 ending with the S14 page.

Other review changes in this spec: D-3 (C14 to C17 rerun after C10), D-6 (C04 classes), D-7 (C12 hosts), D-8 (C13 at 30 seconds), D-9 (C19 Log only), D-11 (Continue later resumes at S06, then S08; superseded by DEC-0041), D-12 (no 15 GB recheck after S07), D-13 (no page jumps), D-14 (M03 checks the drive without a backup), D-17 (security code on S15), and B-1 (C29).

New terms for the glossary (W15 adds them; this spec does not edit the glossary): PC check, server part (on-screen name), phone code, security code, Welcome back page, earlier test, address name, the removal (of what setup added), step strip, bar row, compact bar, time text.

## 13. Decisions

| ID | Decision | Result |
|---|---|---|
| WZ-D1 | An easy address | Decided by the parent: keep `<computer name>.local` (option a). C30 advises a rename in Windows Settings before setup when the name looks like a factory name; it is never a required step. Option b (a rename inside setup) is not built: it added a decision and a restart, and other PCs would have to reconnect shared folders and printers. Superseded by DEC-0039: the address comes from the organization name. |
| WZ-D2 | First screen after a restart or a power cut | Decided by the parent: a Windows-side "install started" record in `C:\ProgramData\SlateOps` (no secret) chooses it, not the journal in the server part (plan 3.2 rule 2). Section 4.1. Changed by DEC-0038 and DEC-0041: the records still choose the first screen, but an unfinished install is removed, not continued. |
| DEC-0038 | Setup never continues an unfinished installation | Owner decision, 2026-11-18. Section 4.1. |
| DEC-0039 | The address comes from the organization name | Owner decision, 2026-11-18; OD-1 option B (setup's own responder and rule). Sections 4.1, 5.3 (C15, C16, C30 retired), S08, section 12 item 4. |
| DEC-0040 | Microsoft 365 leaves the email provider choices | Parent decision under DEC-0036, 2026-11-18. S09 form, M02, 7.3. |
| DEC-0041 | Setup is all or nothing, without an email page | Owner decision, 2026-11-18. Sections 1, 4, S08, S09, S12, S13, S15, M01, M02. |

## 14. Where each design question is answered

| # | Question in TASK-0080 | Answer |
|---|---|---|
| 1 | The PC check: where, what, how it reads, how problems are fixed, the stop | Sections 5.1 to 5.4; screens S02 and S03 |
| 2 | The fewest decisions; what goes behind "Change" | Section 8; S07, S08 (the address "Change"), M02 "More options" |
| 3 | The technical parts in plain words: restart, email, network name and phones, backups, recovery key | Section 3; S05, the S09 form in M02 (with the Gmail help), C10 and C14 to C17 with S15 and T01, S10, S14 |
| 4 | Progress, time, what to do while waiting, failure | Section 2 rule 4; S12 and S13; section 7 |
| 5 | The finish and the first minutes on this PC and on phones | S15 (open and sign in first, then email, then phones) and T01 |
| 6 | Uninstall and the maintenance mode | Section 4.4; M01 to M05; U01 to U04 |
| 7 | Accessibility and clarity | Sections 2, 3 and 9 |

