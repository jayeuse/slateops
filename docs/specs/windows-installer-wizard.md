# Windows setup wizard: check the PC first, then install

Status: **proposed** design spec. Nothing here is built. Company record TASK-0080 (Product Designer). Base revision `99c23876` on `feat/windows-installer`. First compared with `docs/plans/windows-installer.md` as it was on 2026-11-16 at 13:36 UTC (uncommitted edits). Revised after the Software Architect review in TASK-0080 (B-1, requests 1 to 15, departures D-2 to D-17) and two parent decisions (section 13), against the plan state of 2026-11-16, 14:29 UTC (plan 4.1 now names this spec). The plan stays the technical contract; this spec owns the screens, the order, the words and the states.

The Human Owner's request, 2026-11-16:

> "our installer should determine first whether the host machine can be used as a server, and if its sufficient enough to run as a server, only then we can do actual installation. BUT, do not just take my word literally, provide the BEST way to implement our installer wizard in a way that gives the best UX and requires little to no tech knowledge and shouldnt be confusing"

Labels: **Plan** means `docs/plans/windows-installer.md`. **Proposed** means this spec. **Assumption** means not checked; the Software Architect checks it. **Planning value** means a number that the installer report of the owner's first real install corrects (plan 10.2).

## 1. Outcome

A person with no technical knowledge installs Slate Operations on a Windows 11 PC and knows at each step what happens, how long it takes and what to do next.

1. Setup first checks whether this PC can be the server. The check changes nothing. It gives one clear verdict, then only the items that need the person.
2. Setup installs only when the check passes. When the PC is not suitable, setup stops politely, says why in plain words, says what to do instead, and changes nothing.
3. The person makes six decisions: accept the license, the organization name, their own email, the email account password, the backup drive and saving the recovery key. Everything else has a safe default, behind a "Change" link where a change is allowed.
4. Every failure screen says what happened and what to do, with Try again and Save report.
5. At the finish, the owner knows how to set a password, open the app on this PC, and connect phones.

### 1.1 Preserved

- The plan's technical order: the one restart comes before any secret (plan 4.1). The data location comes before the server part is prepared. The email test uses the engine. No secret crosses a restart.
- The plan's rules for secrets, the named pipe and the recovery key (plan 3.2), the `Exec` allow-list (plan 6.2), the self-checks (plan 10.3) and Save report (plan 10.6).
- DEC-0028: a standard Windows setup wizard, a choice of drive and folder, the customer's own email account with Gmail, Microsoft 365 and Other, a local certificate with a "Trust this device" page, and uninstall from Settings → Apps with "Keep your data?".
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
4. **Name the time.** Each wait says what happens and about how long it takes. A wait never shows only a spinner.
5. **Never a dead end.** Each problem has a fix, a guided step, or a polite stop with what to do instead. Each failure has Try again and Save report.
6. **One fixed page size.** An Inno Setup page does not scroll. A page shows only what fits. Longer lists go into a "Show all" dialog.
7. **Nothing changes without a select.** The check is read-only. A "Fix it for me" action changes only what its caption says, and only after a select.

Correct: `This PC is ready to be your Slate Operations server.` then two recommendations.
Wrong: `Requirements: R1 pass, R2 pass, R3 pass, R4 pass, R5 pending, R6 warning ...`

Correct: `Setup could not set up the database. Select Try again. Setup continues from this step.`
Wrong: `Engine step install.08.provision failed (exit 1).`

## 3. Words on screen (AC-4)

Each technical term is replaced on default screens. Where a person must meet the word in Windows Settings, the screen uses the Windows word and explains it in one short line.

| Technical term | On screen | Short explanation, when one is needed |
|---|---|---|
| Server, host machine | "the server", "this PC" | "This PC becomes the server: the other PCs and phones in your office use Slate Operations from it." |
| WSL, Linux distribution, Linux part, engine, Docker | "the server part of Slate Operations" | None. Technical names show only in Details. |
| `VirtualMachinePlatform`, Windows features, WSL MSI | "a Windows feature that Slate Operations needs" | "Windows finishes turning it on with one restart." |
| Virtualization, VT-x, AMD-V, SVM, SLAT | "virtualization" | "A processor setting that lets this PC run the server part." |
| BIOS, UEFI, firmware | "the PC's startup settings (BIOS)" | "A settings screen that opens before Windows starts." |
| RAM | "memory" | None |
| Disk, volume, NTFS, VHD | "drive", "free space" | None |
| Public, Private network profile | "Public network", "Private network" (the Windows words) | "Windows calls a trusted home or office network Private." |
| Domain, DomainAuthenticated | "a company network that an IT department manages" | None |
| Ports 80 and 443, listener | "the web connection that Slate Operations needs" | The screen names the program that uses it. |
| Proxy server | "a proxy server" (the Windows word) | "Some company networks send internet traffic through a proxy server." |
| mDNS, `.local`, DNS label | "the address", for example `office-pc.local` | "Phones and PCs in your office open Slate Operations at this address." |
| SMTP, host, port, STARTTLS, TLS | "email account", "server", "secure connection" | Only the "Other" provider shows server, port and security, with the provider's words. |
| App password | "app password" (Google's word) | "A separate password that Google makes for one app." |
| Microsoft 365 SMTP AUTH | "Authenticated SMTP" (Microsoft's word, only in the admin steps and the Microsoft 365 error, because the admin must find that exact setting) | "A setting that the person who manages your Microsoft 365 turns on." |
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

Words that never show on a default screen: WSL, Linux, Docker, engine, distribution, VHD, SMTP, TLS, STARTTLS, port numbers, mDNS, CA, root certificate, Hyper-V, PowerShell, registry, exit code. Exceptions, each because the person must match a word that they see elsewhere: the "Other" email form (server, port, SSL/TLS, STARTTLS, as email providers write them); "Authenticated SMTP" (row above); the name of a program that the person installed (for example "Docker Desktop", C25); "CA certificate" in the Android steps of T01, because the person types it into the Android Settings search; a value that the person typed (for example a server name). "Details" and Save report are not default screens.

## 4. Flow (AC-1)

### 4.1 Entry: which screen setup opens with

Setup decides its first screen from Windows-side records only: the state folder `C:\ProgramData\SlateOps` (saved progress, the "install started" record and the "key saved" mark; no secret, no answers and no email address, plan 10.1 item 7), the installed program's `version.json`, and `kept.json` in a data folder. It never reads a value from the server part to choose a screen (plan 3.2 rule 2). The person never chooses a mode.

**Every start goes through the normal administrator prompt**, also a resume from the RunOnce entry or the desktop shortcut. Before setup reads or writes anything in `C:\ProgramData\SlateOps`, the folder must pass the folder safety check (plan W7-5). If a user who is not an administrator owns the folder, setup stops on S01 in place: "Setup cannot use the folder C:\ProgramData\SlateOps, because a user who is not an administrator owns it. Select Save report and ask the person who manages this PC." Setup reads nothing from that folder, and Next stays off.

| What setup finds | First screen |
|---|---|
| Nothing from Slate Operations | S01 Welcome |
| Saved progress after a restart from the check ("Restart now" in C08, "Restart to startup settings" in C04) | S02 directly (S01 skipped). One line above the verdict: "Welcome back. Setup checks this PC again." The whole check runs again. |
| A restart from a recheck after S07 ("Restart now" in C08 on S06 or S11; the server part exists) | Setup never saves the check-restart progress here, because the S02 check would stop on C29 at the server part. If the install started, setup keeps the saved stage, and the next start follows that row of this table. Else setup deletes the staged email settings through the pipe (the `discard` mode of `smtp-test`, as "Keep it and continue later") and saves "continue later": S06 Welcome back, then S08. |
| Saved progress after the restart of S05 (plan F4a) | S06 Welcome back, then S07 |
| Saved progress after "Keep it and continue later" (server part exists, no answers sent) | S06 Welcome back, then S08 (plan page 5) |
| An "install started" record with no "install finished" mark (a failure, a power cut, or setup closed during the install) | S06 Welcome back ("Setup stopped before it finished"), then S12. The record holds no answers; the rerun of `install` uses the engine's stored answers, finds its own journal and repeats only the step that did not finish (plan 6.1; W5b contract). When setup deleted the staged email values (the Cancel answer "Keep it and continue later"), the record says so, and S09 comes before S12. |
| An "install finished" mark with no "key saved" mark (setup closed or the PC stopped on S14) | S06 Welcome back ("Setup stopped before you saved the recovery key"), then S14 with a new key: the engine job `new-recovery-key` makes it, and the key that was shown before stops working. |
| An installation, and this setup file is newer (SemVer precedence, plan page 1) | M05 Update |
| An installation, and this setup file is the same version or older | M01 Slate Operations on this PC (maintenance, plan page 1). An older file starts the installed setup copy with the maintenance switch, then closes. The installed setup copy is the small Windows part only; maintenance never needs the payload (W7 decides how the setup program splits). |
| Kept data in the folder that S07 offers | S07 with the kept-data card (reinstall branch, section 4.3) |

Pages run in one fixed order, and setup never jumps to another page. Setup skips the pages that a state does not need. A failure shows in place on the page where it happens, in the S13 layout. A failure of background work shows in a modal form with the S13 layout. A recheck result shows in place, with the S02 item layout.

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
                                       Windows feature off? ──yes──► S05 Restart this PC once
                                                  │no                 │ restart, sign in
                                                  │                   ▼
                                                  │             S06 Welcome back (quick recheck in place)
                                                  ▼                   │
                                       S07 Where to keep your data ◄──┘
                                                  │ Next: the server part is prepared
                                                  │ in the background (status line at the bottom)
                                                  ▼
                                       S08 Your organization
                                                  ▼
                                       S09 Email for Slate Operations
                                       (Send test email; waits for the server part if needed)
                                                  ▼
                                       S10 Backups
                                                  ▼
                                       S11 Ready to install (quick recheck in place on Install)
                                                  ▼
                                       S12 Installing ── a failure shows in place in the S13 layout
                                                  │      (Try again / Save report)
                                                  ▼
                                       S14 Save your recovery key
                                                  ▼
                                       S15 Slate Operations is ready
                                       (set password, open, phones by QR code)
```

### 4.3 Reinstall with kept data (plan 9.2)

```text
 S01 Welcome ► S02 PC check ► S04 License ► (S05 restart if needed) ► S07 with the kept-data card
   "Use the kept data" (default)
        ├── kept version newer than setup ──► the card shows in place: "This data is from Slate
        │                                        Operations version W. Use setup version W or later."
        │                                        (nothing changed)
        ├── kept data cannot be opened ─────► S12 shows in place, in the S13 layout: "Setup could not
        │                                        open the kept data. The kept data is not changed."
        │                                        (Save report)
        └── OK ► S11 Ready (summary of the kept installation; "Change email account" link)
                 ► S12 Installing (update steps when the kept version is older)
                 ► S15 Finish (no S14: the recovery key from the first install still works)
```

S08 to S10 are skipped, because the kept data holds the answers (plan 9.2 step 4).

### 4.4 Maintenance, update and uninstall

```text
 Start menu "Slate Operations settings", or Settings → Apps → Modify
   ► M01 Slate Operations on this PC (status first, then actions)
       ├─ Send my invitation again ► result line on M01 (engine job resend-invitation)
       ├─ Change email account ► M02 (S09 form) ► result
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

The plan's rule "Cancel after page 4a" maps to "Cancel after S07", because the server part is prepared from the Next select on S07.

| Point | What setup has added to this PC | Cancel asks | Cancel does |
|---|---|---|---|
| S01 to S04 | Nothing, unless the person selected a change on S02. These changes stay, because each was the person's choice: the network type (C10), the built-in rule for phones (C17), and the removal of the earlier test's parts (C29). After a restart from the check (C08, C04): the state folder `C:\ProgramData\SlateOps` with the saved progress only, the RunOnce entry and the desktop shortcut; both point at the original setup file (plan F4a). | "Stop setup? Nothing was installed." Stop setup / Go back | Closes. Lists the changes that stay. Removes the saved progress, the RunOnce entry and the shortcut. |
| S05 before Restart now | The Windows feature and the WSL package may be on (plan 3a). | "Stop setup? The Windows feature that setup turned on stays on. Other programs can use it." Stop setup / Go back | Closes. Removes the saved progress and the desktop shortcut. |
| S05 "Restart later" | Same, plus the saved progress and the desktop shortcut "Continue Slate Operations setup". | None. "Restart later" is not Cancel. | Closes. The shortcut and the resume stay. |
| S06, S07 | Same as S05. | Same as S05 | Same as S05 |
| S06 when the next page is S14 (the install finished, the key is not saved) | Slate Operations is installed. | No Cancel, as on S14. | Closing the window keeps the saved stage, so the next start opens S06, then S14 again. |
| S08 to S11 | The server part: the hidden account, the server part on the data drive, the start task. After a passing email test, the email settings wait inside the server part. | "Stop setup? Setup has already added the server part to this PC." ( ) Remove everything setup added (default) ( ) Keep it and continue later: "The next time you start setup, it continues here. Your email password is not kept." Buttons: Stop setup / Go back (default) | Remove: the uninstall steps with "Delete everything" (plan 4.1). Keep: the server part stays; setup deletes the staged email settings with the `discard` mode of the existing `smtp-test` job (input: the run ID only); the next start opens S06, then S08. |
| While a background step or an install step runs | Same | "Setup stops after the current step. This takes up to a minute." | Waits for the step to end, then asks the two answers above. |
| A failure state (S13 layout) | Same | The two answers above | Same |
| S14 | Slate Operations is installed. | No Cancel. Next stays off until the check box is checked (plan page 11, W8-4). A person with no printer and no USB drive writes the key down. | — |
| S15 | Installed | No Cancel | — |

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
3. Else: **"This PC is ready to be your Slate Operations server."** When the Windows feature is off, a second line says: "Setup will restart this PC once."

Rules for running the checks:

- **Recheck.** The checks that can change run again, without a select, on S06 and on Install in S11: C08, C09, C10, C12, C13, C14 and C21. A new problem shows in place on that page, with the S02 item layout, and Next stays off until it is fixed.
- **Free space after S07.** C07 (15 GB) runs only while no server part exists: on S02, and on the S02 resume after a restart from the check. After S07, the server part already uses part of that space, so the engine's free-space check before each writing step covers it (plan 10.7, "Disk full during the install").
- **After a C10 fix.** C14 to C17 run again by themselves, because the network type changes their result.
- **A check that cannot read its value.** C18 (R7) that cannot be read is a Fix item with the C18 message: setup must know that no policy records commands before any password moves. Other blocking checks (R1 to R9, and the F1 checks C15 to C17) show as Advice "Setup cannot check this on this PC. You can continue. If setup stops later, select Save report." (`cannot_read`; C04 keeps its own message) and are logged; the later self-checks catch a real failure (plan 10.3). Any other check shows nothing and is logged.
- **R7 before each password use.** Setup reads R7 again right before each password moves (the S09 test send, M02). A hit, or a value it cannot read, stops the step in place with the C18 message, and nothing is sent.
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
| C07 | One drive inside this PC with 15 GB free (planning value; parent decision 2026-11-16: customer installs leave out Studio, postgres-meta and imgproxy, so the images take about 6 GB with the compressed layers; update space counts only the changed images; the log reserve equals the log caps; the rest is room for data, because the Linux disk never shrinks; the installer report corrects it) | Free space | Fix | The largest fixed NTFS drive that is not removable, network, compressed or EFS-encrypted (R5 and plan page 4, moved forward) | "Open storage settings" opens Settings → Storage. Then Check again. | "No drive in this PC has 15 GB free. The most free space is 12 GB, on C:. Free up space, then select Check again." |
| C08 | No restart is waiting | Windows updates | Fix | `RebootPending`, `RebootRequired`, `PendingFileRenameOperations` (plan 10.7, precheck; moved forward) | "Restart now" (after "Save your work first"). Setup opens again after the sign-in and checks again. | "Windows is waiting to restart after an update. Restart this PC, then setup checks again." |
| C09 | Connected to a network | Network connection | Fix | A connected adapter with an IPv4 default gateway (precheck) | Guided. Then Check again. | "This PC is not connected to a network. Connect it to your office network with a cable or Wi-Fi, then select Check again." |
| C10 | The network is Private | Network type | Fix | Network category (R6, plan page 8; moved forward) | "Make this network private" with a confirmation: "Do this only on your office or home network, not on public Wi-Fi." | "Windows treats this network as Public. Slate Operations works only on a Private network, so other devices can reach this PC." |
| C11 | Not on a company domain network | Company network | Stop | Category `DomainAuthenticated` (R6, precheck) | None | "This PC is on a company network that an IT department manages. Slate Operations is not tested on such networks yet." |
| C12 | Internet access to the image servers | Internet | Fix | HTTPS to ghcr.io and the Docker Hub registry with a plain user agent (R8; github.com only in the second deliverable). Proxy: WinHTTP and user proxy settings (plan 10.4). | Guided. Then Check again. | No connection: "Setup cannot reach the internet. Connect this PC to the internet, then select Check again." Proxy: "This PC uses a proxy server. Slate Operations cannot use one yet. Connect to a network without a proxy server, or ask the person who manages your network." |
| C13 | The clock is correct within 30 seconds (planning value) | Date and time | Fix | The PC clock against the `Date` header of the internet check: the smallest difference of three samples, after half the round trip (plan 10.7, moved forward). 30 seconds, because sign-in codes change every 30 seconds. | "Open date and time settings". Then Check again. | "This PC's clock is wrong by 2 minutes. Turn on Set time automatically, then select Check again." |
| C14 | The web connection is free | Web connection | Fix | Listeners on TCP 80 and 443, with the process name (plan page 8 and 10.7; moved forward). A listener that belongs to Slate Operations passes. | Guided, with the program name. Then Check again. | "Another program on this PC uses the web connection that Slate Operations needs: World Wide Web Publishing Service. Stop or uninstall it, then select Check again." |
| C15 | The PC name can be an address | Address | Fix; Advice when the name is longer than 15 characters or differs from the Windows network name (`name_mismatch`) | The computer name is a valid DNS label (plan 10.3, F1) | "Open About settings" (Rename this PC needs a restart). Then Check again. | Fix: "This PC's name cannot be used as an address. Rename this PC with letters, numbers and hyphens only." Advice: "Some Windows screens show this PC under a different name than its address, office-pc.local. For one name everywhere, rename this PC with 15 or fewer letters, numbers and hyphens. Do it before setup, restart this PC, then run setup again." |
| C16 | No other device uses the address | Address | Fix | mDNS probe for `<name>.local` (plan page 8, F1) | Same as C15 | "Another device on this network already uses the address office-pc.local. Rename this PC, then select Check again." |
| C17 | Phones can find this PC | Phones can find this PC | Fix | DNS Client service runs; no policy turns multicast name resolution off; the built-in mDNS firewall rule allows the Private profile (plan 10.3, F1; rule names are an Assumption that W8 checks) | Rule off: "Fix it for me" turns on the existing built-in Windows rule, for Private networks only. Setup never creates a rule, and logs the old state. Uninstall does not undo it. Policy sets the rule or blocks multicast: "Ask the person who manages this PC." | "Phones and other PCs cannot find this PC by its address. A Windows setting blocks it." |
| C18 | No policy records commands | Security policy | Fix (only the person who manages the PC can fix it). Also Fix when setup cannot read the policy. | PowerShell module logging policy (R7, precheck); read again before each password use (section 5.2) | "Ask the person who manages this PC" plus Save report | "A security policy on this PC records the commands that programs run. Setup cannot keep passwords private while it is on. Ask the person who manages this PC to turn it off." Unreadable: "Setup cannot check whether a security policy on this PC records commands. Ask the person who manages this PC." |
| C19 | Smart App Control state | — | Log | Smart App Control state (plan 10.4; registry name is an Assumption). With Smart App Control on, Windows blocks the unsigned setup file before the wizard opens, so no screen item can show. | None. Setup gives no advice to turn it off (plan 10.7: the owner reports a block and changes no setting). | — |
| C20 | Antivirus | Antivirus | Advice (only when a program other than Microsoft Defender is found) | `SecurityCenter2` `AntiVirusProduct` (plan 10.4) | None | "Norton is on this PC. If setup stops, allow the folder C:\Program Files\Slate Operations in Norton." (Advice names only that folder, which only administrators can change.) |
| C21 | Plugged in | Power | Advice | `Win32_Battery` (R9, precheck) | None | Laptop on mains power: "This PC is a laptop. Keep it plugged in, open and in the office. Phones cannot use Slate Operations while it is away or asleep." On battery: "This laptop runs on battery now. Plug it in." |
| C22 | Closing the lid does not stop a plugged-in laptop | Laptop lid | Advice (laptops only) | Lid close action on mains power (`powercfg` setting name is an Assumption that W7 checks) | "Change it during the install": the select only records the choice. Setup sets "When the lid is closed and the laptop is plugged in: do nothing" during the Windows-side steps of S12, beside the sleep setting. Uninstall restores it. After the select: "Setup changes this during the install." with "Undo". | "This laptop goes to sleep when you close the lid. Then Slate Operations stops for everyone." |
| C23 | Wired network | Network cable | Advice (on Wi-Fi only) | Media type of the adapter with the default route (Assumption) | None | "This PC uses Wi-Fi. A network cable is more reliable for a server." |
| C24 | Drive encryption | Drive encryption | Advice | Status only (`ProtectionStatus`) of C: and of the data drive candidate; setup never reads key protectors and never suspends BitLocker (plan 10.4; plan 12 risk row; decision H5) | "Show me how" opens the BitLocker settings | Data drive not encrypted: "Drive encryption (BitLocker) is off. Turn it on, so your data stays private if this PC is stolen." Data drive is not C: and is encrypted: "Drive D: is encrypted. Turn on automatic unlock for D: in the BitLocker settings, so Slate Operations can start after a restart when nobody is signed in." |
| C25 | Docker Desktop | Docker Desktop | Advice | Program file or service (precheck) | None | "Docker Desktop is on this PC. Quit it while Slate Operations runs, so the two do not compete for memory." |
| C26 | The Windows feature and WSL | — | Auto | Feature state and WSL version (precheck; plan 3a) | Setup turns it on in S05. | Verdict line: "Setup will restart this PC once." |
| C27 | Sleep and hibernate on mains power | — | Auto | Power settings (precheck; plan 6.2 Windows steps) | Setup sets Never; uninstall restores it (plan 9.1). | S11 Details: "Keep this PC awake when it is plugged in." |
| C28 | Fast Startup, network adapters, WSL distributions of the account, `.wslconfig`, time zone | — | Log | precheck; plan 10.4 | — | — |
| C29 | No parts of an earlier test or an earlier uninstall | Parts of an earlier test | Fix; Stop for unknown parts | Each part found: the account `slateops-svc`, the distribution `SlateOpsBootTest`, the tasks `\SlateOpsBootTest\*`, the rules `SlateOpsBootTest-*`, the folder `C:\ProgramData\SlateOpsBootTest` (plan 10.7, boot-test kit row). Parts of Slate Operations itself (tasks `\SlateOps\*`, the distribution `SlateOps`) with no `version.json`: unknown parts. | "Remove them" opens a modal form: title "Remove the parts of the earlier test?", text "Setup removes the earlier test's server part and its data, its hidden account, its start tasks and its firewall rules. The test's log files stay. Your other programs and files do not change. If the normal removal does not work, setup stops the Windows feature that runs the server part for a moment, for every user of this PC." Buttons Continue and Cancel (default). Only Continue removes them, as the kit's cleanup does (the old disk is deleted, the logs stay). Then the item shows "Removing…", then "Removed". Setup never reuses an existing `slateops-svc`: it removes it and creates its own only after the removal (plan 10.7). The technical names show in "Details". Unknown parts: no removal; Save report. Parts of Slate Operations with no installed program but with an uninstall log are leftovers of an earlier uninstall (`uninstall_leftovers`, Fix): "Remove them" runs the uninstall's removal of the Windows parts. This item removes no data, so it runs without the C29 confirmation form. | Test parts: "This PC has parts of an earlier Slate Operations test. Setup removes them before it continues." Only the account found: "This PC has a leftover of an earlier Slate Operations uninstall. Setup removes it before it continues." Leftovers of an earlier uninstall: "This PC has parts left by an earlier Slate Operations uninstall. Setup removes them before it continues. Your data and backups do not change." Unknown parts (Stop): "This PC has parts of Slate Operations that setup cannot identify. Setup changes nothing. Select Save report and send the file to Slate Operations support." |
| C30 | The address is easy to use | Address | Advice | The computer name looks like a factory name: `DESKTOP-` or `LAPTOP-` followed by random letters and numbers (pattern is an Assumption that W7 checks) | "Open About settings". Never a required step (parent decision on WZ-D1). | "The address of Slate Operations will be desktop-7gh2k1.local, from this PC's name. It cannot change after setup without every phone and PC trusting Slate Operations again. If you want a short address, rename this PC in Windows Settings before setup, restart it, then run setup again." |

The check never shows passed items one by one on S02. They collapse into one line: "21 checks passed. Show all checks" (the number is an example). "Show all checks" opens a dialog with every check, its name, its result word (Ready, Needs a fix, Recommended, Not suitable) and its value, for example "Memory: 16 GB. Ready."

### 5.4 Why these answers (design question 1)

- **Where.** The check is the page right after Welcome, before the license and before any change. The person learns in about a minute whether this PC can work. Nobody reads a license for a PC that cannot run the product.
- **Blocking versus recommendation.** A check blocks only when the server cannot work, or cannot keep a secret, without it. Laptops and Wi-Fi do not block: the plan allows them (R9), and the person may have no other PC. Their advice says what goes wrong in plain words.
- **Changes before the license.** Five changes can happen on S02, each only after the person selects it by name: C10 Private network (with the public Wi-Fi warning), C08 restart, C04 restart to the startup settings, C17 the built-in rule, and C29 the removal of the earlier test's parts (with Continue and Cancel). C22, the lid, is only recorded on S02 and changed during the install, so uninstall can restore it. Setup never stops another program, never changes the startup settings itself and never upgrades Windows for the person.
- **Not suitable.** S03 is a polite stop. It does not blame the PC or the person. It says what a suitable PC has, and it offers Save report for a supplier or support.
- **Address.** The address comes from this PC's name (decided: keep `<computer name>.local`). A factory name gives a hard address, so C30 advises a rename before setup. It is never required.
- **Processor.** The plan has no processor minimum. A threshold without evidence would turn away PCs that work. C06 records the cores, and the installer report decides later.

## 6. Screens (AC-1)

### 6.1 Frame

- Each subtitle fits on one line; a longer explanation goes into the first line of the page.
- Inno Setup `WizardStyle=modern` with no custom style, so the Windows system colors and high contrast apply. `WizardSizePercent=150,150` (the largest size; fixed, not resizable). Welcome (S01) and Finish (S15) use the tall side image (`WizardImageFile`); other pages use the header with a title, a one-line subtitle and the small product mark. Assumption until W7 measures the real pixels: the page fits a screen of 1280 x 720 effective pixels.
- The button row: Back, Next and Cancel. The bottom-left status text is `WizardForm.BeveledLabel`, set at run time; it shows the background preparation on S08 to S10: "Preparing the server part: 40%". Inno resets the Next and Cancel captions at each page change, so each page sets them when it opens and in each state.
- Pages run in one fixed order. A failure, a stop or a recheck result shows in place on its page; a background failure shows in a modal form (section 4.1).
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
  | Small progress in an item | `TNewProgressBar`, marquee style |
  | Numbered steps on S01 and S15 | Plain "1." text |
  | Recovery key | `TNewStaticText` in a monospaced font on a panel; not a selectable field |
  | QR code | `TBitmapImage` drawn by the setup program, in whole-pixel modules |
  | "Show all checks", help dialogs, the C29 form, U01, U02 | A modal form (`CreateCustomForm`) |
- Stage line under the header on S02 to S12: "1 Check this PC · 2 Your details · 3 Install", with the current stage in bold. It tells the person where they are in three words, not twelve page numbers.
- Text uses the Windows system font and system colors. Status uses a word and an icon shape, and color only as an extra (section 9).

Each screen below lists: purpose, content and copy, controls, states and messages. Copy in quotes is final unless it holds an example value.

### S01 Welcome (plan page 1)

- **Purpose.** Say what happens, how long it takes and what to have ready.
- **Title.** "Set up Slate Operations on this PC"
- **Content.** "This PC becomes the server for your organization. Your people open Slate Operations from their PCs and phones on your office network."
  1. "Check this PC: about 1 minute. Setup changes nothing yet."
  2. "Answer a few questions: about 5 minutes."
  3. "Install: about 30 minutes. You can use the PC while it installs." (30 minutes is a planning value; section 12 item 15.)
  
  "Have ready: the password of the email account that Slate Operations sends from, and a USB drive for backups (recommended)."
- **Controls.** Next: "Check this PC". Cancel.
- **States.** Default only.

### S02 Check this PC (new; replaces plan page 3)

- **Purpose.** Decide whether this PC can be the server, and get every problem fixed here.
- **Title.** "Check this PC". Subtitle: "Setup checks whether this PC can be your Slate Operations server. It changes nothing."
- **Content, in order.** The verdict (one bold sentence; a second line only in the ready state). Then at most four items in total: Fix items first, then "Recommended" items (Advice). Each item has the result word, the name, one or two lines, and its buttons. Then one line: "21 checks passed. Show all checks".
- **Controls.** Per item: "Fix it for me", "Remove them", "Change it during the install", "Show me how", "Open … settings", "Restart now", "Restart to startup settings" (section 5.3). Page: "Check again" (beside "Show all checks"). Next: "Next" (off while a Fix item is open). Back. Cancel.
- **States.**
  - Checking: the verdict area says "Checking this PC… (about 1 minute)" with a progress bar, then one line: "Checking: Internet (12 of 23)". Below it: "Found so far: nothing that needs you." or the items found so far. Passed checks never show one by one. Next is off.
  - Ready: "This PC is ready to be your Slate Operations server." Optional second line: "Setup will restart this PC once." Recommended items show below. Next is on.
  - Needs fixes: "Fix 2 things, then setup can continue." The Fix items show first.
  - Fixing: the item that the person selected shows "Fixing…" with a small progress bar; its buttons are off. After the fix, the item checks again by itself and shows "Fixed" or the message.
  - Not suitable: the page changes in place to the S03 stop.
  - Removing (C29): after Continue in the C29 form, the item shows "Removing…" with a small progress bar, then "Removed".
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
- **Content.** The Inno Setup license page with `LICENSE`. A link-style button: "Third-party notices". No edition choice and no license file (DEC-0029).
- **Controls.** "I accept the agreement" / "I do not accept the agreement". Next: "Next" (off until "I accept").

### S05 Restart this PC once (plan page 3a; only when C26 needs it)

- **Purpose.** Turn on the Windows feature and restart, before any secret is typed.
- **Title.** "Restart this PC once". Subtitle: "Windows needs one restart to finish a feature that Slate Operations needs."
- **Content.**
  - While it works: "Turning on the Windows feature… (about 2 minutes)" with a progress bar. Then the verdict: "The Windows feature is turned on. Windows finishes it when this PC restarts."
  - Then: 1. "Save your work and close your other programs." 2. "Select Restart now." 3. "Sign in again. Setup opens by itself and continues." "If setup does not open, double-click Continue Slate Operations setup on the desktop."
  - "Details" (link-style button) shows: "Virtual Machine Platform, Windows Subsystem for Linux."
- **Controls.** Next: "Restart now". "Restart later" (closes setup; the shortcut stays). Cancel.
- **States.** Working; ready to restart; waiting ("Another installation is running on this PC. Setup waits and tries again." for plan code 1618, three tries); failed (in place, in the S13 layout: "Setup could not turn on a Windows feature.").

### S06 Welcome back (new)

- **Purpose.** Show where setup continues after a restart, a "continue later" or a stop.
- **Title.** "Welcome back". Subtitle by entry: "Setup continues where it stopped." or "Setup stopped before it finished. It continues from the step that stopped."
- **Content.** The stages with the done ones ticked. The quick recheck runs (section 5.2) with "Checking this PC again…", then "This PC is still ready. Setup checked it again." A new problem shows in place, with the S02 item layout and its buttons; Next stays off until it is fixed.
- **Controls.** Next: "Continue". Cancel.

### S07 Where to keep your data (plan page 4)

- **Purpose.** Choose the drive for all business data. The best drive is already selected.
- **Title.** "Where to keep your data". Subtitle: "Your records and files are kept on this drive." First line of the page: "Setup chose the drive with the most free space."
- **Content.** A list of the drives that qualify, each with its name, letter and free space; the largest is selected and marked "Most space". Below: "Folder: D:\SlateOps" with "Change folder". One line: "USB and network drives are not listed. The data must stay inside this PC." Small link-style button: "Change program folder" (default `C:\Program Files\Slate Operations`).
- **Kept-data card** (when the folder holds kept data): "This folder holds data from an earlier installation: Riverside Learning Center, version 0.2.0, kept on 12 November 2026." ( ) "Use the kept data" (default) ( ) "Start new. Choose another folder." Kept data from an older version (until W13b adds its update steps): "This data is from Slate Operations version 0.1.0. This setup cannot open it. Install with setup version 0.1.0 first, then run this setup to update."
- **Controls.** Drive list, Change folder, Change program folder. Next: "Next". Back. Cancel.
- **States.** Default; folder not empty and not kept data ("This folder is not empty. Choose an empty folder."); drive too small (the drive is not listed; when the person picks a folder on it: "This drive has 9 GB free. Slate Operations needs 15 GB. Choose another drive."); a folder above the chosen folder fails the safety check (section 7.5, `setup.data.data_folder_parent_unsafe`): the message shows under the Folder line, with the button "Use D:\SlateOps".
- **On Next.** The server part is prepared in the background (plan page 4a; accepted with conditions, section 12 item 1). The status text at the bottom shows its progress on S08 to S10.
- **Back from S08.** S07 shows the chosen drive and folder as text, not as a choice, with one line: "The server part is already on D:. To use another drive, select Cancel, then Remove everything, and start setup again."

### S08 Your organization (plan page 5)

- **Purpose.** Get the organization name and the administrator's email.
- **Title.** "Your organization". Subtitle: "You become the administrator of Slate Operations."
- **Fields.**
  - "Organization name". Help: "People see this name in Slate Operations." No placeholder text; the label stays visible.
  - "Your email address". Help: "Your invitation goes to this address. You set your password from it."
  - "More options" (link-style button) shows: "User name" (default: the part of the email before @, cleaned) and "Short name" (default from the organization name). Help: "Setup makes these from your email and the organization name. You can keep them."
- **Controls.** Next: "Next". Back. Cancel.
- **Messages under the field.** Name empty: "Enter the name of your organization." Name too long: "Use 100 characters or fewer." Email: "Enter an email address, for example maria@example.com." User name: "Use 3 to 100 letters, numbers, - or _." Short name: "Use only lowercase letters, numbers and single hyphens, for example riverside-learning."
- **Background states (bottom status text).** "Preparing the server part: 40%"; "The server part is ready."; failed: "Preparing the server part stopped. Select Next for details." Next then opens a modal form in the S13 layout, with Try again and Save report.

### S09 Email for Slate Operations (plan page 6)

- **Purpose.** Connect the email account that sends invitations and password resets, and prove that it works.
- **Title.** "Email for Slate Operations". Subtitle: "Slate Operations sends invitations and password resets from this account."
- **Fields, in order.**
  1. "Send from" (email). Default: the address from S08.
  2. "Provider": ( ) Gmail ( ) Microsoft 365 ( ) Other. Setup selects one from the address and marks it "(detected)": a list of known domains first, then the MX records of the domain, on the Windows side only (section 12 item 7). The MX answer only selects Gmail or Microsoft 365, by an exact match of the mail host to a fixed list of Google and Microsoft hosts; it fills no field and sets no server name. The person can change the choice. Setup never selects Microsoft 365 for an Outlook.com address.
  3. Gmail: "App password". Help, above the field: "Gmail needs an app password, not your normal password." Link-style button: "How to make an app password".
  4. Microsoft 365: a note above the password: "Microsoft 365 blocks this kind of sign-in until the person who manages your Microsoft 365 turns it on for this mailbox." Link-style button: "Steps for your Microsoft 365 admin". Then "Password".
  5. Other: "Server", "Port", "Security" ( ) "SSL/TLS (usually port 465)" ( ) "STARTTLS (usually port 587)", "User name" (default: the address), "Password".
  6. "More options": "Sender name" (default: the organization name).
- **Gmail help dialog.** "1. Select Open Google's page. Your browser opens myaccount.google.com/apppasswords. 2. Sign in. If Google asks, turn on 2-Step Verification first. 3. Type Slate Operations as the app name and select Create. 4. Copy the 16-letter password and paste it here." Note: "If you change your Google password, Google removes this app password. Then use Change email account in Slate Operations settings." Buttons: "Open Google's page", "Close".
- **Microsoft 365 help dialog.** "Send these steps to the person who manages your Microsoft 365: In the Microsoft 365 admin center, open Users → Active users, select this mailbox, open Mail → Manage email apps, turn on Authenticated SMTP, and save." Notes: "From the end of December 2026, Microsoft turns this setting off by default." and "Security defaults, or a policy that blocks basic authentication, also block Authenticated SMTP." Buttons: "Copy the steps", "Close". (The admin steps match Microsoft Learn, "Enable or disable SMTP AUTH in Exchange Online", as checked by the Software Architect.)
- **Controls.** Next caption: "Send test email" until a test passes, then "Next". Link-style button: "Continue later" (the Cancel "Keep it and continue later" answer: the `discard` mode of `smtp-test` deletes the staged email settings; the next start opens S06, then S08). Back. Cancel.
- **States.**
  - Idle.
  - Waiting for the server part: "Getting ready to send… (about 1 minute)". The test starts by itself when the server part is ready.
  - Sending: "Sending a test email to maria@example.com…" with a progress bar. Fields are off.
  - Passed: "Test email sent to maria@example.com. It can take a few minutes to arrive. Look in Spam too." Next: "Next".
  - Failed: the message by class (section 7.3), under the field that it is about, and focus moves to it. A changed field turns the caption back to "Send test email".
  - Channel self-test failed (plan F4d): in place, in the S13 layout: "Setup cannot pass the password safely to the server part. Nothing was sent."
  - Outlook.com address (`outlook.com`, `hotmail.com`, `live.com`, `msn.com`): no provider is selected, and a note shows in place of the password: "Outlook.com accounts cannot send email for Slate Operations. Microsoft allows them only a sign-in method that Slate Operations cannot use yet. Use a Gmail or Microsoft 365 account, or an account from another email provider." "Send test email" stays off until the address changes or the person selects Other.
- **The password field.** Hidden characters, a "Show" toggle that resets to hidden after each test send and when the page changes. Never saved by setup (plan 3.2 check 4).

### S10 Backups (plan page 7)

- **Purpose.** Choose where the nightly backup goes. A second drive is the safe default.
- **Title.** "Where to keep backups". Subtitle: "Slate Operations makes a backup every night at 2:00." First line of the page: "Keep backups on another drive, so one broken drive cannot lose everything."
- **Content.** A list of the other drives (USB drives and other internal drives) with free space. The largest is selected. The last entry: "This PC's data drive (D:). Not safe if this drive breaks."
- **No other drive.** A card: "Plug in a USB drive now. Setup finds it by itself." and "No other drive was found on this PC." The list updates when a drive is plugged in. If the person selects the data drive, a check box shows: "I understand: if drive D: breaks, the data and the backups are both lost." Next stays off until it is checked. One line: "You can choose a backup drive later in Slate Operations settings."
- **USB drive selected.** One line: "Keep this USB drive plugged in. A backup fails while the drive is out."
- **Controls.** The list, the check box. Next: "Next". Back. Cancel.
- **Messages.** "Slate Operations cannot write to E:. Plug the drive in, or choose another drive." "E: has 2 GB free. Choose a drive with more space."

### S11 Ready to install (plan page 9)

- **Purpose.** One summary before the long wait. Last chance to change.
- **Title.** "Ready to install". Subtitle: "Check your choices, then select Install."
- **Content.** Rows, each with "Change" where a change is allowed. "Change" goes back to the page of that row (Back, with the pages between skipped); after it, Next comes back to S11 (the pages between skipped). The copy stays the same. A changed email account needs a new passing test. Data has no "Change", because the server part is already on that drive (S07).
  - "Organization: Riverside Learning Center"
  - "Administrator: maria@example.com"
  - "Email sent from: office@example.com (Microsoft 365, test passed)"
  - "Data: D:\SlateOps"
  - "Backups: E: (USB drive), every night at 2:00"
  - "Address for PCs and phones: https://office-pc.local"
  - "Edition: Desk, the free edition"
  
  "Installing takes about 30 minutes. Keep this PC on and connected." (planning value)
  
  "What setup changes on this PC" (link-style button) opens a dialog: "Adds a hidden Windows account that runs Slate Operations. Starts Slate Operations when Windows starts, also when nobody is signed in. Allows Slate Operations through Windows Firewall on Private networks. Makes this PC trust the secure connection of Slate Operations. Keeps this PC awake when it is plugged in. Adds Slate Operations to the Start menu and the desktop. Uninstall removes all of these." When the person chose C22, one more line: "Keeps this laptop running when the lid is closed and it is plugged in."
- **Controls.** Next: "Install". Back. Cancel.
- **On Install.** The quick recheck (section 5.2). A new problem shows in place on S11, with the S02 item layout; Next stays off until it is fixed.

### S12 Installing (plan page 10)

- **Purpose.** Show progress in plain stages, give a time, say what the person can do.
- **Title.** "Installing Slate Operations". Subtitle: "About 25 minutes left." (from the download speed and the stage times; "This can take up to 30 minutes" until it is known).
- **Stages** (plan 6.2 steps in brackets). Each has a state: done, now (with a progress bar for downloads: "1.2 GB of 3.4 GB"), waiting.
  1. "Download the parts" (1, 3)
  2. "Prepare the settings" (2, 4, 5)
  3. "Set up the secure connection" (6)
  4. "Set up the database" (7, 8)
  5. "Start Slate Operations" (9, 10)
  6. "Create your administrator account and send your invitation" (11)
  7. "Make the first backup" (12)
  8. "Finish on this PC" (13, the Windows-side steps and the check that Slate Operations opens on this PC)
- **Box.** "While you wait: You can use this PC. Keep it on, plugged in and connected, and do not restart it. At the end, setup shows your recovery key. Have a printer or a USB drive ready."
- **Controls.** Next is off. Cancel (section 4.5).
- **States.**
  - Running.
  - Automatic retry: "The download server is busy. Setup tries again at 14:32." (plan 10.7: time-outs and HTTP 429, three tries.)
  - Slow (plan F4b): "This step takes longer than expected." Buttons: "Wait", "Try again", "Save report".
  - Failed: in place, in the S13 layout.
- **Numbers.** "1.2 GB of 3.4 GB", the step number and the time left come from whole numbers that the engine writes to its progress file (bytes done, bytes total, step number). The Windows side reads them as integers and uses them only for display (plan 3.2 rule 2).

### S13 Setup stopped (one layout for every failure, shown in place)

- **Built as.** A state of the page where the failure shows (S05, S09, S12, the S07 kept-data branch), or a modal form for a failure of background work (S08 to S10). Never a separate page.

- **Purpose.** Say what happened and what to do, and keep the work.
- **Title.** "Setup stopped". Subtitle: the stage, for example "Set up the database".
- **Content.**
  - What happened, one sentence (section 7), for example: "Setup could not set up the database."
  - "What you can do:" 1. "Select Try again. Setup continues from this step. Nothing is lost." 2. "If it stops again, select Save report and send the file to Slate Operations support."
  - An extra action when the catalog row has one, for example "Choose another drive" (plan F5; it opens a modal form with the S10 drive list) or "Open Windows Update".
- **Controls.** Next: "Try again". "Save report". Cancel (the two answers of section 4.5).
- **States.** Default; saving the report ("Saving the report… (up to 3 minutes)"); report saved ("Report saved to your desktop: SlateOps-report-install-20261116T1402Z-k3f9qa.zip." "Show in folder"); trying again (progress of the step).
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
  1. "Set your password. Open the email from Slate Operations sent to maria@example.com and select the link. It can take a few minutes; look in Spam too." Second line: "No email after 10 minutes? Open Slate Operations settings in the Start menu and select Send my invitation again." When setup does not know the email address (after a resume, section 4.1), step 1 reads (`s15_step1_no_address`): "Set your password. Open the email from Slate Operations and select the link. It can take a few minutes; look in Spam too." with the same second line.
  2. "Open Slate Operations on this PC." Button: "Open Slate Operations" (default browser at the address). If the person selects it before step 1, the browser shows the Slate Operations sign-in page, and the person has no password yet. That is why step 1 comes first. The sign-in page is app work, outside this spec.
  3. "Connect phones and other PCs. On the same Wi-Fi as this PC, scan this code with the phone's camera. It shows the one-time steps that let the phone open Slate Operations." The QR code to `http://office-pc.local/trust` (made on the Windows side from the computer name), and the address in text below it. "Details" (link-style button) shows: "Security code: 3F:A2:…:9C. The phone page shows the same code." The code is the fingerprint of the Slate Operations certificate in this PC's trusted certificates, computed on Windows (plan 6.3).
     In v1 (parent decision DEC-0036, no QR code), step 3 reads: "Connect phones and other PCs. Connect the phone to the same Wi-Fi as this PC. In the phone's browser, type the address below exactly, with http://. The page shows the one-time steps that let the phone open Slate Operations." The address `http://office-pc.local/trust` shows below it. When the security code is not known (after a resume), its line does not show.
  
  "You use Desk, the free edition. To add a license later, open Manage → Updates & licensing in Slate Operations."
  
  "Slate Operations starts by itself when this PC starts. For settings and help, open Slate Operations settings in the Start menu."
- **Controls.** Next: "Finish". No Back. No Cancel.

### M01 Slate Operations on this PC (maintenance, plan 9.3)

- **Purpose.** Status first, then the few things the owner can do from Windows.
- **Title.** "Slate Operations on this PC". Subtitle: "Version 0.2.0 · https://office-pc.local"
- **Status, one sentence, and one line under it.** "Running. Last backup: today at 2:04, on E:." When a "Needs attention" sentence shows, the line under it says whether Slate Operations runs and when the last backup was, for example "Slate Operations is running." (while the engine reports no last-backup time). Other states, from the engine status (plan 9.3, 10.2, 10.7): "Updating", "Needs attention: plug in the backup drive (E:). If you see this again after you plug it in, select Repair." (Repair sets the backup folder rights again when the drive is present.), "Needs attention: email sign-in fails. Select Change email account.", "Needs attention: the network changed. Select Repair.", "Not ready since 09:12. Select Repair. If that does not help, select Save report.", "Needs support. Select Save report and send the file to Slate Operations support." A "Details" link shows memory, disk and start time in plain words ("Memory used: 4.1 GB, highest 5.3 GB").
- **Actions** (command buttons with one line each): "Open Slate Operations" ("In your browser on this PC."); "Send my invitation again" ("Use this only before you set your password."); "Show the phone code" ("Connect a phone or another PC."); "Change email account" ("When the email password or provider changes."); "Change backup drive" ("Backups go there from the next night."); "Make a new recovery key" ("The old key stops working."); "Repair" ("Sets up the Windows parts again. Your data does not change."); "Save report" ("A file for Slate Operations support.").
- **"Send my invitation again".** Always shown; no value from the server part decides whether it shows (plan 3.2 rule 2). It runs the new allow-listed engine job `resend-invitation` (input: the run ID only; the engine reads the name, the email and the user name from its own answers). While the job runs, the status line says "Sending your invitation… (about 1 minute)" (`m01_sending`). The result line on M01 comes from the job's code (subject to the Security Engineer's review):
  - `sent`: "Slate Operations sent your invitation again. Look in your inbox and in Spam."
  - `already_active`: "Your account is already set up. Sign in with your password. If you forgot it, reset it from the sign-in page."
  - `rate_limited`: "Slate Operations sent several emails a short time ago. Wait a few minutes, then try again."
  - A failure class: "Slate Operations could not send the invitation. Check the email account with Change email account, then try again." with "Save report".
- **"Show the phone code".** A modal form with the QR code, the address in text, and "Security code: 3F:A2:…:9C. The phone page shows the same code." (computed on Windows, as on S15).
- **Footer line.** "To uninstall, open Settings → Apps."
- **Start menu and the settings program.** "Slate Operations settings" opens M01. "Slate Operations - Save report" first shows "Setup saves a report for Slate Operations support. This takes up to 3 minutes.", then the result line in a message box. On a PC with no installation, the settings program shows "Slate Operations is not installed on this PC. To install it, open the Slate Operations setup file."
- **Controls.** Cancel caption: "Close".
- **No license import** (DEC-0029).

### M02 to M04 (maintenance forms)

- **M02 Change email account.** The S09 form, title "Change email account". The final button is "Done". After a passing test: "Slate Operations sends email from office@example.com now. Sign-ins stop for about a minute while it restarts." (plan 9.3: `set-email` recreates `auth`.)
- **M03 Change backup drive.** The S10 form. On Next, setup checks that Slate Operations can write to the drive, without a backup (a backup stops Slate Operations for everyone): "Checking drive F:…". The new drive gets its own backup lock, so M03 ends with the S14 page for its new recovery key, with the first line: "Your new backup drive has its own lock. The old recovery key does not open it." The final button is "Done". Result: "Backups go to F: from tonight at 2:00." Failure in place: "Slate Operations cannot write to F:. Plug the drive in, or choose another drive." When the drive changed but the key could not be made, M01 shows: "Backups now go to F:, but setup could not make their recovery key. Select Make a new recovery key now." (Engine side: `set-backup-target` sets up the new backup store and returns the new key through the secret channel; W10b.)
- **M04 Make a new recovery key.** The engine removes the old key when it makes the new one, so the old key cannot be kept (D-B, TASK-0096; Security Engineer accepted with the consequence stated before the job). Before the job, a confirmation: title "Make a new recovery key?", text "Your current recovery key stops working. Have a printer or a USB drive ready to save the new key.", buttons "Make a new key" and "Go back" (default). Then the S14 page, with a first line: "Your old recovery key no longer works. Save this new key now." The final button is "Finish", off until the check box "I printed or saved the recovery key" is checked (as S14, W8-4). No Cancel, as on S14.

### M05 Update (plan 7.4, setup-program path)

- **Purpose.** Update with a backup first, and say what the people in the office notice.
- **Title.** "Update Slate Operations". Subtitle: "Version 0.2.0 is installed. This setup installs version 0.2.1."
- **Content.** "Setup makes a backup before it changes anything. If the update fails, Slate Operations goes back to version 0.2.0 by itself." Then: "People cannot use Slate Operations while it updates. This can take up to 1 hour. Tell your people before you start." (1 hour is a planning value; it matches the slow line at 60 minutes.)
- **Controls.** Next: "Update now". Cancel.
- **Progress.** In the order the steps run: "Prepare the update" (the idle check, the parts from this setup file, the Windows feature), "Make a backup", "Update", "Check that it works". Stages 2 to 4 show "Now" together while the engine job runs. Result: "Slate Operations is updated to version 0.2.1." or "The update did not work. Slate Operations went back to version 0.2.0. Everybody must sign in again." (plan 7.5 revokes sessions) with "Save report".
- **Messages** (S13 layout in place, with Save report; Try again unless the line says otherwise):
  - Busy: "Slate Operations is busy with a backup or another task. Setup waits and tries again by itself." (a waiting line, not a failure)
  - A failure before the update changed anything: "The update did not work. Slate Operations still runs version 0.2.0. Nothing changed."
  - No answer from the server part: "Setup cannot reach the server part of Slate Operations. Nothing changed."
  - Not enough space: "The server part of Slate Operations needs 12 GB of free space for a safe update. Nothing changed. Select Save report and send the file to Slate Operations support." No Try again.
  - A rollback that could not finish: "The update did not finish, and Slate Operations could not go back by itself. Select Save report and send the file to Slate Operations support." No Try again.
  - The engine updated, the Windows part did not finish: "Slate Operations is updated to version 0.2.1, but setup could not finish its part on this PC."
  - Slow state of the engine job: "This step takes longer than expected." and "The update goes on by itself. You can close setup now. Later, run this setup again and select Update now. Setup then finishes the update on this PC." with Save report; no Try again.

### U01 to U04 Uninstall (plan 9.1)

- **U01 Keep your data?** Title "Uninstall Slate Operations". ( ) "Keep my data (recommended). Slate Operations is removed. Your records, files and settings stay in D:\SlateOps\kept (14 GB). Install Slate Operations again to continue where you stopped." ( ) "Delete everything. Removes all records, files and settings from this PC." Under "Delete everything" only: [ ] "Also delete the backups on E:". Buttons: "Uninstall", "Cancel". Closing the window cancels; nothing is removed (plan F4c).
- **U02 Confirm delete.** Title "Delete all Slate Operations data?". "This deletes all your records, files and settings in Slate Operations on this PC. It cannot be undone. The backups on E: are kept." (Windows does not keep the organization name.) (or "are deleted too."). [ ] "I understand that this cannot be undone". Buttons: "Delete everything" (off until checked), "Go back" (default).
- **U03 Removing.** "Removing Slate Operations… (about 2 minutes)" with three stages: "Stop Slate Operations", "Moving your data to D:\SlateOps\kept…" (only with "Keep my data"), "Remove the program and its Windows settings".
- **U04 Result.** "Slate Operations is removed. Your data is kept in D:\SlateOps\kept." or "Slate Operations and its data are removed." One line: "The Windows feature that Slate Operations used stays on, because other programs can use it." Leftovers state: "Uninstall finished. Some items could not be removed. Setup removes them the next time it runs." with "Save report". Keep-data failure (plan F3): "Setup could not keep your data safely. Nothing was removed." with "Save report".

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

These replace the draft messages in plan 4.1, 4.2, 10.3 and 10.7. In the tables, "S13" means the S13 layout: shown in place on the page where the failure happens, or in a modal form for background work (section 4.1). It always adds "Try again" and "Save report" unless the row says otherwise.

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
| 4a | The server part does not start | "Setup could not start the server part of Slate Operations." | S13 |
| 5 | Field errors | S08 messages | S08 |
| 6 | Email errors | Section 7.3 | S09 |
| 7 | Backup drive errors | S10 messages | S10 |
| 8 | Public network, port in use, name in use | C10, C14, C16 | S02 (moved from page 8) |
| 10 | A step fails | "Setup could not <stage in lower case>." For example "Setup could not set up the database." | S13 |
| 10 | Check from this PC fails | "Slate Operations is installed, but this PC cannot open it at https://office-pc.local." | S13 |

### 7.3 Email test results (plan 4.1 page 6 and 10.7)

Each message shows under the field it is about.

| Class | Final message | Under |
|---|---|---|
| Password refused (Gmail) | "Gmail did not accept this password. Use an app password, not your normal Gmail password." plus "How to make an app password" | Password |
| Password refused (other providers) | "The email provider did not accept the user name or password. Check them and try again." | Password |
| Microsoft 365 sign-in off (reply 535 5.7.139) | "Microsoft 365 blocked the sign-in. The person who manages your Microsoft 365 must turn on Authenticated SMTP for this mailbox." plus "Steps for your Microsoft 365 admin" | Password |
| Cannot connect | "Setup cannot reach the email server smtp.example.com. Check the server name and port." (Gmail and Microsoft 365: "Setup cannot reach Gmail. Check the internet connection.") | Server, or Provider |
| No secure connection offered | "This email server does not offer a secure connection. Slate Operations sends email only over a secure connection. Choose the other security option, or ask your email provider." | Security |
| Secure connection certificate fails | "The secure connection to smtp.example.com failed. Check the server name, and check this PC's date and time." | Server |
| Sender refused | "The email provider does not let this account send as office@example.com. Use the address of the account." | Send from |
| Recipient refused | "The email provider refused to send to maria@example.com. Check your email address on the previous page." | Send from (with a Back hint) |
| Any other result | "Setup could not send the test email. Check each field, then select Send test email again." | Password |

### 7.4 Self-checks (plan 10.3)

| Plan ID | Final message | Screen and extra action |
|---|---|---|
| F1 | C15, C16, C17 | S02 |
| F2 | "Slate Operations is installed, but this PC cannot open it at https://office-pc.local." | S13 |
| F3 (uninstall) | "Setup could not keep your data safely. Nothing was removed." | U04 with Save report |
| F3 (reinstall) | "Setup could not open the kept data. The kept data is not changed." | S13 with Save report; no Try again |
| F4a | S05 content names the desktop shortcut. | S05 |
| F4b | "This step takes longer than expected." | S12 with Wait, Try again, Save report |
| F4c | "Uninstall stopped. Nothing was removed." | Windows message box with Save report |
| F4d | "Setup cannot pass the password safely to the server part. Nothing was sent." | S13 |
| F5 | "Slate Operations cannot save backups to E:." | S12 in place (S13 layout) with "Choose another drive" (a modal form with the S10 drive list) |
| F6 | Same as F2 | S13 |
| F10 | "The server part did not start again after a Windows update of one of its parts." | S13 |
| W4-5 | "Setup could not start the server part of Slate Operations." | S13 |
| W7-6 | M01: "Not ready since 09:12. Select Repair. If that does not help, select Save report." | M01 |

### 7.5 Failure catalog (plan 10.7)

| Plan row | Final message | Screen and recovery |
|---|---|---|
| Virtualization off | C04 | S02 |
| Windows too old, or Home | C01, C02 | S02, S03 |
| Restart pending | C08 | S02; in place on S06 and S11 |
| WSL or Windows feature install fails | "Setup could not turn on a Windows feature that Slate Operations needs." Code 1618: "Another installation is running on this PC. Setup waits and tries again." | S05 waiting state; then S13 |
| Resume does not start | S05 content | Desktop shortcut |
| Antivirus or Smart App Control blocks a file | Antivirus: "A security program on this PC blocked part of Slate Operations setup. Allow the folder C:\Program Files\Slate Operations in the security program, then select Try again." The blocked file name shows only in Details and Save report; the advice names only the program folder, which only administrators can change. Smart App Control: "Windows blocked part of Slate Operations setup. Select Save report and send the file to Slate Operations support." No advice to turn Smart App Control off (plan 10.7; C19 is Log only). If Windows blocks the setup file itself, no screen shows; `README.txt` and the release notes describe this case. | In place (S13 layout) |
| Import fails | "Setup could not start the server part of Slate Operations." When the cause is space: "The data drive is full. Free 8 GB on D:, then select Try again." | S13 |
| Docker or systemd does not start | "Setup could not start the server part of Slate Operations." | S13 |
| No internet, proxy, name lookup, rate limit, secure connection | C12 messages; "The download server is busy. Setup tries again at 14:32."; "A secure connection to ghcr.io failed. Check this PC's date and time." | S12 automatic retry, then S13 |
| Disk full during the install (the server part's own disk: the engine checks the free space inside the server part, so free space on the Windows drive does not help; Assumption until W14) | "The server part of Slate Operations has no free space left. Select Save report and send the file to Slate Operations support." | S13 |
| Disk full later | M01: "Needs attention: drive D: is almost full. Free some space." | M01 |
| Ports in use | C14 | S02 |
| Firewall rule fails | "Setup could not set up Windows Firewall for Slate Operations." | S13; Repair in M01 |
| Public network or domain | C10, C11 | S02, S03 |
| Address does not open on a phone or a computer | S15 step 3 and T01 "The page does not open?" (with the device word) | T01 |
| Certificate not trusted | Server PC: F2 message. Phone: T01 status "Not yet". | S13; T01 |
| Email errors | Section 7.3; later M01: "Needs attention: email sign-in fails. Select Change email account." | S09; M01 |
| Database, migration, readiness | "Setup could not set up the database." / "Slate Operations did not start." | S13 |
| Service account cannot sign in | "Windows did not let Slate Operations start. A security policy on this PC can cause this. Select Repair. If it happens again, ask the person who manages this PC." | S13 or M01 |
| WSL stops the idle server part | None (automatic) | — |
| Windows Update installs a newer WSL | None; known-bad version: M01 "Needs support…" | M01 |
| Power cut | S06 "Setup stopped before it finished. It continues from the step that stopped." Chosen from the Windows-side "install started" record (section 4.1), not from the server part. | S06, then S12 |
| Clock wrong | C13 | S02; later M01 |
| Low memory | M01: "Needs attention: Slate Operations is short of memory. Close other programs on this PC." | M01 |
| Wi-Fi not connected at start | M01: "Needs attention: this PC was not on the network after it started. Set the Wi-Fi to connect automatically, or use a network cable." | M01 |
| IP address changes | M01: "Needs attention: the network changed. Select Repair." | M01 |
| Uninstall leftovers | U04 leftovers state | U04 |
| Kept data does not match | Section 4.3 stop; F3 reinstall message | S07 branch; S13 |
| Parts of the boot-test kit are on the PC | C29: "This PC has parts of an earlier Slate Operations test. Setup removes them before it continues." "Remove them" opens the C29 form with Continue and Cancel. | S02; removal only after Continue |
| `C:\ProgramData\SlateOps` owned by a user who is not an administrator | "Setup cannot use the folder C:\ProgramData\SlateOps, because a user who is not an administrator owns it. Select Save report and ask the person who manages this PC." | S01 in place; setup reads nothing from the folder |
| A folder above the chosen data folder fails the safety check (`setup.data.data_folder_parent_unsafe`; TASK-0091 S91-2) | "Setup cannot keep your data in D:\Office\SlateOps, because it cannot protect a folder above it. This is common for folders made in File Explorer. Setup can protect D:\SlateOps for you." Button: "Use D:\SlateOps". One message for every value of `reason`; the value never shows on screen and goes only to the log and Save report. | S07 in place, under the Folder line; "Change folder" stays. On Next, setup stays on S07 until the data folder step answers; only then does the rest of the preparation continue in the background and S08 open. "Use D:\SlateOps" sets the folder to `\SlateOps` on the drive of the chosen folder when the drive list holds that drive, else on the drive selected in the list; then the S07 checks run again. Setup never changes a folder above. |
| Setup was approved with another administrator account, so it cannot add its automatic restart entries (`setup.resume.resume_other_user`; TASK-0091 S91-7) | In place of S05 step 3 and the line "If setup does not open…": "3. Sign in again, then open the setup file again. Setup cannot open by itself after this restart, because it runs with another administrator account." Under the steps: "The setup file: C:\Users\maria\Downloads\SlateOpsSetup-0.2.0.exe. When you open it, Windows asks for the administrator account again." | S05 "ready to restart" state, before the person selects Restart now: setup saves its progress when this state opens, and this code means the progress is saved. The same sentences, without the step number, show in the confirmation before C08 "Restart now" and C04 "Restart to startup settings" on S02. Not a failure: no S13 layout, Next stays "Restart now", and "Restart later" closes setup with no shortcut. The saved progress stays, so the setup file continues as section 4.1 says. |

## 8. What the person decides and what is automatic (AC-3)

| Item | Decided by | Default | Where a change is possible | Reason |
|---|---|---|---|---|
| License | Person | — | S04 | A legal acceptance. |
| Fixes in the check | Person, per item | — | S02 | Each changes Windows; nothing changes without a select. |
| Remove the parts of an earlier test (C29) | Person | — | S02, C29 form (Continue or Cancel) | It deletes the earlier test's data; setup cannot continue without it, because the account name is the same (plan 10.7). |
| Laptop lid (C22) | Person | Not changed | S02 ("Change it during the install") | Changed during the install, so uninstall can restore it. |
| Restart time | Person | Restart now | S05 ("Restart later") | The person may have open work. |
| Data drive and folder | Automatic, can change | The largest qualifying drive, `\SlateOps` | S07 | DEC-0028 gives the choice. The default is right for most PCs, so the person only confirms. |
| Program folder | Automatic, can change | `C:\Program Files\Slate Operations` | S07 "Change program folder" | DEC-0028 gives the choice. Few people need it, so it is a link. |
| Use kept data | Person | Use it | S07 card | A new start on old data is a real choice. |
| Organization name | Person | — | S08 | Setup cannot guess it. |
| Administrator email | Person | — | S08 | Setup cannot guess it, and the invitation goes there. |
| Administrator user name | Automatic, can change | From the email | S08 "More options" | The default is valid and readable. |
| Short name (slug) | Automatic, can change | From the organization name | S08 "More options" | Plan 4.1 lets the person edit it. Few need to. |
| Sending address | Automatic, can change | The administrator email | S09 | Most small organizations send from the owner's account. |
| Email provider | Automatic, can change | Detected from the address | S09 (visible) | Detection can be wrong, so the choice stays in view. |
| Email password | Person | — | S09 | A secret. |
| Server, port, security | Automatic for Gmail and Microsoft 365 | Provider values | S09 "Other" only | Only "Other" needs them. |
| Sender name | Automatic, can change | Organization name | S09 "More options" | The name people expect to see. |
| Backup drive | Automatic when a second drive exists, else person | Largest other drive | S10 | A second drive protects the data; the person must plug in a USB drive or accept the risk. |
| Backup time | Automatic | Every night at 2:00, PC time zone | Not in the wizard; in the app (Manage → Backups) | The app already owns the schedule (plan 6.2 step 12). |
| Address | Automatic | `<computer name>.local` | Not in v1 (plan F1). Before setup, the person can rename the PC in Windows Settings (C30 advice). | One address per installation (plan 1.1). Decided by the parent (section 13). |
| Edition | Automatic | Desk | In the app only (DEC-0029, TASK-0076) | The owner's rule. |
| Firewall, start task, hidden account, trust on this PC | Automatic | — | Not changeable; listed on S11 | Needed for the server to work. |
| Sleep on mains power | Automatic | Never; uninstall restores | Not changeable | A sleeping server stops for everyone. |
| Server part memory | Automatic | 6 GB (planning value, plan 10.2) | Not changeable; support | A person cannot judge it. |
| Start menu and desktop entries | Automatic | Both | Not changeable | Non-technical users find the app from the desktop. |
| Recovery key saved | Person | — | S14 | Only the person can keep it safe off the PC. |
| Open the app at the end | Person | — | S15 button | The password step comes first. |

## 9. Accessibility and clarity

No accessibility conformance is claimed (`PRODUCT.md`: no certification target).

1. **Keyboard.** Every action is a button or a focusable control. The tab order follows the reading order. Enter selects the Next button; Esc selects Cancel. Each button has an access key (an underlined letter). Link-style buttons are real focusable controls, never plain text with a click handler only.
2. **Screen readers.** Text that carries meaning uses `TNewStaticText`, a windowed control that a screen reader can read; never `TLabel`, which a screen reader cannot read. A sentence that must take focus is a read-only, borderless edit field (Assumption: Narrator reads it; WZ-11). Each result uses a word ("Ready", "Needs a fix", "Recommended", "Not suitable", "Fixed"), not only an icon or a color. When a check, a test send or a step ends, focus moves to its result sentence, so a screen reader reads it.
3. **High DPI.** The wizard scales with the Windows display scale (`WizardSizePercent=150,150`; assumed to fit a screen of 1280 x 720 effective pixels). The side image, the small mark and the status icons come in sizes for 100% to 250%. The QR code scales in whole pixels, so it stays sharp.
4. **Color and contrast.** Text uses the Windows system colors, so high-contrast themes work. Status colors are an extra beside the word and the icon shape.
5. **Plain language.** One instruction per sentence, at most 20 words. The full name "Slate Operations" in every sentence that names the product (`PRODUCT.md`). "Organization", never "business", because the users are schools, clinics, shops and offices too. No term from the "never" list in section 3 on a default screen.
6. **Time.** No page moves on by itself. No message disappears by itself. Only the background preparation and the install run on their own, and both show their state.
7. **Motion.** Only progress bars move. No animation.

## 10. Changes from plan section 4 (AC-5)

| # | Plan | This spec | What it improves | What it removes or costs |
|---|---|---|---|---|
| 1 | Page 2 License, then page 3 Requirements | S02 PC check right after Welcome; S04 License after a pass | The person knows in about a minute whether this PC can work, before reading a license or changing anything. This is the owner's request. | Nothing. The license is still accepted before the first install change. |
| 2 | Requirements as a list of R1 to R9 with pass or fail per line | One verdict first, then only the items that need the person; passed items collapse into one line | A non-technical person reads one sentence, not nine technical lines. | The full list moves into "Show all checks". |
| 3 | R1 to R9 | C01 to C30: adds processor type, early free space, pending restart, clock, ports and address checks (from page 8), earlier test parts (plan 10.7), antivirus, laptop lid, Wi-Fi, drive encryption, Docker Desktop, the address advice; Smart App Control is logged only | Problems that the plan finds late (page 4, page 8, the install) show before any change. | More detection code on the Windows side (section 12 item 8). |
| 4 | "Next stays off until every blocking line passes" | Fix it for me, Show me how, Open … settings, Restart now, Check again per item | Each problem has a way forward on the same page. | Five Windows changes can happen before the license, each selected by name: C10, C08, C04, C17, C29 (section 5.4). |
| 5 | No screen for an unsuitable PC | S03, a polite stop with what to do instead and Save report (a state of the S02 page) | The person is not left with a disabled Next button. | — |
| 6 | Page 3a message | S05 with numbered steps, "Restart later", Details | The person can choose when to restart, and knows how setup comes back. | — |
| 7 | — | S06 Welcome back | The person sees where setup continues after a restart, a stop or a power cut. | One extra page on resume. |
| 8 | Page 4: program folder and data folder fields | S07: drive list with the best drive selected; program folder behind a link; kept-data card | One Next for most people; the DEC-0028 choice stays. | The program folder is less visible. |
| 9 | Page 4a "Getting Linux ready" progress page | Background preparation with a status line on S08 to S10 (accepted with conditions) | Removes a wait of several minutes from the person's path. | Needs a background job with polling in the wizard (section 12 item 1). Fallback: the plan's page 4a with plain words. |
| 10 | Page 5 "Business name", user name visible, slug shown | S08 "Organization name"; user name and short name behind "More options" | Two fields instead of four. "Organization" fits schools, clinics and offices (`PRODUCT.md`). | — |
| 11 | Page 6 provider choice, all fields, "Send test email" | S09: sending address defaults to the administrator; provider detected but visible; Gmail and Microsoft 365 help before the password; one Next caption "Send test email"; messages under the field; "Continue later" | The hardest page gets guided help before the error, not after. A stuck person has a way out. | Provider detection is new (section 12 item 7). |
| 12 | Page 7 a choice of two | S10: second drive selected by itself; "Plug in a USB drive now" with live detection; check box for the data drive | The safe choice is the easy choice. | — |
| 13 | Page 8 Network name | Removed as a page. The checks move to S02 (C10, C14 to C17); C30 advises a rename before setup when the name looks like a factory name; the address shows on S11 and S15. | One page fewer; problems found before any change. | The address is never a choice (as in the plan). |
| 14 | Page 9 Ready, a summary | S11 with Change links, "What setup changes on this PC" and the time | The person sees what changes on the PC before it changes. | — |
| 15 | Page 10 step list of engine steps | S12: eight stages in plain words, time left, "While you wait", automatic retry and slow states | The person knows what happens and what to do. | — |
| 16 | Failure messages per page | S13, one failure layout for every failure, shown in place on its page or in a modal form | The same "what happened, what to do, Try again, Save report" every time. | — |
| 17 | Page 11 the key, Print, Save to USB, check box | S14 with an explanation and the backup-drive warning; no Cancel, as in the plan | The person understands why the key matters. | — |
| 18 | Page 12 four lines of text and a QR code | S15: three numbered steps in order (password first), the QR code, Desk line, how to come back | The owner does the steps in the right order. | — |
| 19 | Cancel after page 4a | Cancel rules per point (section 4.5), from S07 | Clear answers at every point. | — |
| 20 | Section 9 uninstall and maintenance | U01 to U04, M01 to M05 with status first | The owner sees the state before the actions. | — |
| 21 | Trust page "steps for iOS, Android, Windows and macOS" | T01: the trust status first; steps for the detected device that work on current versions (Safari on iPhone and iPad, the Settings path on Android 11 and later); causes when the page does not open; a no-JavaScript line that says to stop at a warning | The device shows "Yes" when it is done, and no step leads to a dead end. | — |
| 22 | Plan 10.7 row "Parts of the boot-test kit are on the PC" (page 3) | C29 on S02 with "Remove them", the C29 form, Continue and Cancel | Removal happens only after a select, with a clear list of what goes | The earlier test's data is deleted (as the plan) |
| 23 | Page 12 and maintenance: no way to get a lost invitation | S15 hint line and "Send my invitation again" on M01 (engine job `resend-invitation`) | The administrator can always get in | A new allow-listed job (Security Engineer review) |
| 24 | — | S09 note for Outlook.com addresses before the password | The person learns before a failed test that Outlook.com cannot work | — |

## 11. Acceptance criteria for the build

These criteria add to the plan's W6b, W7, W8 and W9 criteria. Each is checked on the screen by the Product Designer screen review and by the owner's end-user pass (DEC-0031).

- **WZ-1.** Setup on a suitable PC shows S01, then S02 with the verdict "This PC is ready…" within about a minute, and changes nothing before S04 unless the person selects a fix.
- **WZ-2.** Setup on a PC with a Stop item shows S03 with the plain reason, "What you can do" and Save report, and nothing on the PC changes.
- **WZ-3.** Each Fix item has the action of section 5.3, and Check again changes the verdict when the problem is gone.
- **WZ-4.** No default screen shows a word from the "never" list in section 3.
- **WZ-5.** Every failure shows S13 with a "what happened" sentence from section 7, Try again and Save report, and Try again continues from the failed step.
- **WZ-6.** On S09, a refused Gmail password shows the Gmail message under the password field; the Microsoft 365 note shows before the password; "Continue later" opens S06, then S08, at the next start.
- **WZ-7.** The background preparation shows its state at the bottom of S08 to S10, and the test send waits for it with "Getting ready to send…". (Fallback build: the plan's page 4a.)
- **WZ-8.** S12 shows the eight stages, the time left and the "While you wait" box. A busy download server shows the retry time.
- **WZ-9.** S15 lists the password step first, the "Open Slate Operations" button second and the QR code third. The QR code opens the trust page on a phone on the same Wi-Fi.
- **WZ-10.** M01 shows one status sentence first, then the actions. U01 defaults to "Keep my data"; "Delete everything" needs U02 with its check box.
- **WZ-11.** With the keyboard only, the person completes the whole install; with Narrator on, each verdict and result sentence is read when it appears.
- **WZ-12.** At 100%, 150% and 200% display scale, on a screen of at least 1280 x 720 effective pixels, no page clips text or controls and no page needs scrolling.
- **WZ-13.** On a PC with parts of the earlier test, S02 shows C29. Nothing is removed until Continue in the C29 form; after the removal, the item shows "Removed", and the verdict changes.
- **WZ-14.** On M01, "Send my invitation again" shows the result line for the job's code (`sent`, `already_active`, `rate_limited`, or a failure class with Save report).
- **WZ-15.** With an Outlook.com address on S09, no provider is selected, the Outlook.com note shows before the password, and "Send test email" stays off.
- **WZ-16.** No page opens another page out of order: failures, the S03 stop and recheck results show in place, and background failures in a modal form.

WZ-11 and WZ-12 have no runner today: Narrator and display scale are not end-user steps (DEC-0031), and nobody else runs Windows. Static proxy for the W7 and W8 review: the setup script creates no `TLabel`; every action is a `TNewButton` or `TNewLinkLabel` with a tab stop and an access key; the tab order follows the reading order. WZ-12 at the owner's own display scale is an observation in his end-user pass (W14); the other scales stay unverified.

## 12. Requests beyond the plan: decided

The Software Architect decided each request (TASK-0080 Notes, "Software Architect review", 2026-11-16). Plan 4.1 says: where this spec differs from plan 4.1, 4.2 or the 6.2 allow-list, the spec wins once the Software Architect accepts it, and for the allow-list also the Security Engineer. No item changes a public API, a database schema, a storage format or a wire format.

| # | Request | Decision | What the spec does now |
|---|---|---|---|
| 1 | Prepare the server part in the background after S07 | Accepted, with conditions | The wizard runs one `Exec` job at a time and queues the next. The timer never opens a dialog; a failure shows on the next Next or on the test send (S08, S09). Cancel waits for the running job. Whether `prefetch` returns at once stays a plan question for W5b. |
| 2 | The check before the license | Accepted; count corrected | Five person-selected changes before the license (section 5.4). `MinVersion=10.0`, so Windows 10 reaches the S03 stop. `ArchitecturesAllowed=x64compatible` and `ArchitecturesInstallIn64BitMode=x64compatible`, so an Arm PC reaches the S03 stop (C03). |
| 3 | "Restart to startup settings" for C04 | Accepted, with conditions | UEFI PCs only (`GetFirmwareType`). `shutdown.exe /r /fw /t 0`, never a delay above 0 (it closes programs without a warning). Resume as plan F4a: `C:\ProgramData\SlateOps` holds only the saved progress (no copy of the setup file before the space check; re-check N-1); the RunOnce entry and the desktop shortcut start the original setup file, always through the administrator prompt; the folder passes the safety check before any read or write (W80-5). Cancel removes the three. Which RunOnce key elevates after the sign-in stays open for W7. The BitLocker caution depends on C: (W80-4). |
| 4 | Turn on the mDNS rule for C17 | Accepted | The existing built-in rule, Private profile only; never a new rule; old state logged; not undone by uninstall. Policy: "Ask the person who manages this PC". |
| 5 | The lid for C22 | Changed | S02 records the choice; the Windows-side steps of S12 change it; uninstall restores it. |
| 6 | Which memory value R4 reads | Decided | R4 passes at `TotalPhysicalMemory` ≥ 12 GiB. The screen shows the installed memory from `GetPhysicallyInstalledSystemMemory` (C05). Planning value. |
| 7 | Email provider detection | Accepted; changed | Windows side only: known domains, then MX records; the MX answer only selects Gmail or Microsoft 365 by an exact host match and fills no field (W80-7); the choice stays visible. Outlook.com addresses get the S09 note and never Microsoft 365. The Microsoft 365 admin dialog adds the security-defaults line. |
| 8 | Detection for the new checks | Accepted; changed | A hidden helper in `{tmp}` writes progress and result files. An unreadable blocking check shows as Advice "Setup cannot read …" (section 5.2). Each method stays an Assumption until W7. |
| 9 | Print the recovery key without a file | Accepted, with constraints | Printing inside the setup process with Windows printing calls: no file, no helper program, no PowerShell; fixed print job name; printers that write a file are refused (W80-3). The spool file stays the W8-5 exception. "Save to a USB drive" offers removable drives only (W80-2) and refuses the backup drive (W80-1). |
| 10 | The QR code on the Windows side | Accepted; changed | Drawn by the setup program from the computer name. S15 Details and the M01 phone-code form also show the security code (the certificate fingerprint from this PC's trusted certificates; plan 6.3). A copied QR encoder needs its third-party notice. |
| 11 | A way to get a lost invitation | Accepted: new allow-listed job `resend-invitation` | Input: the run ID only. Output: `sent`, `already_active`, `rate_limited` or a failure class. M01 always shows "Send my invitation again" (section 6, M01); S15 names it. Work: W5b (job) and W8 (M01). Subject to the Security Engineer's review, which runs now. A wrong email address stays a support case in v1. |
| 12 | Inno Setup fit | Accepted; changed | The controls of section 6.1; `WizardStyle=modern`; `WizardSizePercent=150,150`; `BeveledLabel` for the status text; captions set when a page opens and in each state; focusable read-only edit fields for verdicts; WZ-12 screen size. |
| 13 | A desktop shortcut | Accepted | An `[Icons]` entry with the address (an Internet Shortcut); uninstall removes it (plan 9.1 list, W7). |
| 14 | An older setup file on a newer installation | Accepted | The older file starts the installed setup copy with the maintenance switch, then closes (section 4.1). The installed copy is the small Windows part only. |
| 15 | Time values and progress numbers | Accepted; changed | Planning values as proposed. The engine writes whole numbers for progress (bytes done, bytes total, step number); the Windows side uses them only for display (S12). |

Security Engineer review (TASK-0080 History, 2026-11-16; 0 BLOCKING; `resend-invitation` accepted for the allow-list with fixed bootstrap arguments and no raw output in logs). Changes applied:

- W80-1 refuse the backup drive for the recovery key (S14); W80-2 removable USB drives only; W80-3 fixed print job name, file printers refused.
- W80-4 the C04 BitLocker caution depends on C:, or an unreadable state; setup never suspends BitLocker. W80-9 BitLocker status only (`ProtectionStatus`) of C: and the data drive, with the automatic-unlock advice (C24).
- W80-5 every start through the administrator prompt; the state folder passes the safety check first (section 4.1). W80-6 programs started as the original user with fixed targets (section 6.1). W80-7 the MX answer selects a provider only. W80-8 C18 unreadable is Fix, and R7 runs again before each password use (section 5.2).
- Item conditions: the "Show" toggle resets (S09); the key is non-selectable text with no Copy, M04 asks for confirmation before the job and states that the current key stops working, because the engine removes the old key when it makes the new one (D-B, Security Engineer accepted; this replaces "M04 Cancel removes the new key"), and a resume without the "key saved" mark runs `new-recovery-key` (S14, 4.1); antivirus advice names only the program folder (C20, 7.5); C29 never reuses `slateops-svc`, stops on unknown Slate Operations parts, and names the fallback.
- Parent decision on open point 1: "Keep it and continue later" deletes the staged email settings with the `discard` mode of the existing `smtp-test` job (input: the run ID only); no new job name.
- Parent decisions after the re-check: N-1 (state folder holds only the saved progress; RunOnce and the shortcut start the original file), N-2 (a lone `slateops-svc` is an uninstall leftover in the C29 copy), N-3 (the "install started" record holds no answers or email), the small maintenance copy, and M03 ending with the S14 page.

Other review changes in this spec: D-3 (C14 to C17 rerun after C10), D-6 (C04 classes), D-7 (C12 hosts), D-8 (C13 at 30 seconds), D-9 (C19 Log only), D-11 (Continue later resumes at S06, then S08), D-12 (no 15 GB recheck after S07), D-13 (no page jumps), D-14 (M03 checks the drive without a backup), D-17 (security code on S15), and B-1 (C29).

New terms for the glossary (W15 adds them; this spec does not edit the glossary): PC check, server part (on-screen name), phone code, security code, Welcome back page, earlier test.

## 13. Decisions

| ID | Decision | Result |
|---|---|---|
| WZ-D1 | An easy address | Decided by the parent: keep `<computer name>.local` (option a). C30 advises a rename in Windows Settings before setup when the name looks like a factory name; it is never a required step. Option b (a rename inside setup) is not built: it added a decision and a restart, and other PCs would have to reconnect shared folders and printers. |
| WZ-D2 | First screen after a restart or a power cut | Decided by the parent: a Windows-side "install started" record in `C:\ProgramData\SlateOps` (no secret) chooses it, not the journal in the server part (plan 3.2 rule 2). Section 4.1. |

## 14. Where each design question is answered

| # | Question in TASK-0080 | Answer |
|---|---|---|
| 1 | The PC check: where, what, how it reads, how problems are fixed, the stop | Sections 5.1 to 5.4; screens S02 and S03 |
| 2 | The fewest decisions; what goes behind "Change" | Section 8; S07, S08, S09 "More options" |
| 3 | The technical parts in plain words: restart, email, network name and phones, backups, recovery key | Section 3; S05, S09 (with the Gmail and Microsoft 365 help), C10 and C14 to C17 with S15 and T01, S10, S14 |
| 4 | Progress, time, what to do while waiting, failure | Section 2 rule 4; S12 and S13; section 7 |
| 5 | The finish and the first minutes on this PC and on phones | S15 (password first; what happens if "Open Slate Operations" comes first) and T01 |
| 6 | Uninstall and the maintenance mode | Section 4.4; M01 to M05; U01 to U04 |
| 7 | Accessibility and clarity | Sections 2, 3 and 9 |

