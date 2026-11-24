# Slate Operations quick start

This guide tells you how to prepare the server PC, install Slate Operations, sign in for the first time, and connect phones and other PCs.

[seller name] installs Slate Operations with you. Keep this guide to follow the install, or to install again later.

| Help | Contact |
|---|---|
| Support | [support contact] |
| Support hours | [support hours] |

Brackets give the source of each step: "plan" is the Windows installer plan, and "spec" is the setup wizard spec. Page numbers are the plan's page numbers.

## 1. What the server PC needs

One Windows PC in your office becomes the server PC. Your people open Slate Operations from their PCs and phones on your office network (spec S01).

Setup checks these items before it changes anything (spec S02; Copy.iss `s03_suitable`).

| Item | Requirement | Source |
|---|---|---|
| Windows version | Windows 11, version 22H2 or later. Windows 10 cannot be the server PC. | plan 4.2, R1; spec C01 |
| Windows edition | Windows 11 Pro, Enterprise or Education. Windows 11 Home cannot be the server PC. | plan 4.2, R2; spec C02 |
| Processor | A 64-bit Intel or AMD processor. Setup stops on an Arm processor. | spec C03 |
| Virtualization | On, in the startup settings (BIOS) of the server PC | plan 4.2, R3; spec C04 |
| Memory | 16 GB. Windows must be able to use at least 12 GB. | plan 4.2, R4; spec C05; Checks.ps1 |
| Free space | 15 GB free on one drive inside the server PC. USB and network drives cannot hold the data. | plan 4.2, R5; spec C07, S07 |
| Network | Connected, and set as a Private network. Not a company network that an IT department manages. | plan 4.2, R6; spec C09 to C11 |
| Internet | Needed during setup. Setup cannot use a proxy server. | plan 4.2, R8; spec C12 |
| Clock | Correct to within 30 seconds. Turn on "Set time automatically". | spec C13 |
| Web connection | No other program uses it, for example a web server program. | spec C14 |
| Security policy | No policy that records the commands that programs run | plan 4.2, R7; spec C18 |
| Windows account | An administrator account on the server PC | SlateOpsSetup.iss `PrivilegesRequired=admin` |
| Power (recommended) | Mains power. A laptop stays plugged in, open and in the office. When the server PC sleeps, nobody can use Slate Operations. | plan 4.2, R9; spec C21, C22 |

Also have these items ready:

- A USB drive for the nightly backups (spec S01, S10).
- A printer, or a second USB drive, for the recovery key (spec S12, S14).

## 2. Install Slate Operations

The check takes about 1 minute. The questions take about 5 minutes. The install takes about 30 minutes (spec S01).

### Start setup

1. Get the setup file `SlateOpsSetup-<version>.exe` from [seller name]: [how the seller gives the setup file] (SlateOpsSetup.iss).
2. Sign in to the server PC with an administrator account (SlateOpsSetup.iss).
3. Plug in the USB drive for backups (spec S01).
4. Double-click the setup file (plan 11.2).
5. If Windows SmartScreen shows a warning, select More info (plan 11.2).
6. Select Run anyway (plan 11.2).
7. If Windows says that Smart App Control blocked the file, stop. Contact [support contact] (plan 11.2).
8. Accept the Windows administrator prompt (spec 4.1).

Caution: do not change Windows security settings to let setup run. Contact [support contact] instead (plan 11.2).

### Page "Set up Slate Operations on this PC" (plan page 1)

1. Select Check this PC (spec S01).

### Page "Check this PC" (plan page 3)

The check reads the items in section 1. It changes nothing on the server PC (spec S02).

1. Read the result line at the top of the page (spec S02).
2. If the result is "Fix N things", do the fix that each item shows (spec S02, 5.3).
3. Select Check again after each fix (spec S02).
4. When the result says that the server PC is ready, select Next (spec S02).

If the page says "This PC cannot be the Slate Operations server", setup stops and changes nothing. Select Save report and send the file to [support contact] (spec S03).

### Page "License agreement" (plan page 2)

1. Read the license, the Elastic License 2.0 (spec S04).
2. Select I accept the agreement (spec S04).
3. Select Next (spec S04).

### Page "Restart this PC once" (plan page 3a)

Setup shows this page only when Windows needs Virtual Machine Platform or Windows Subsystem for Linux (WSL) (spec S05, C26).

1. Save your work and close your other programs (spec S05).
2. Select Restart now (spec S05).
3. Sign in again (spec S05).
4. If setup does not open, double-click "Continue Slate Operations setup" on the desktop (spec S05).
5. If the page told you to open the setup file again, do that (Copy.iss `s05_steps_other_user`).
6. On the page "Welcome back", wait for the short check (spec S06).
7. Select Continue (Wizard.iss, S06).

### Page "Where to keep your data" (plan page 4)

1. Keep the drive that setup selected ("Most space"), or select another drive in the list (spec S07).
2. Select Next (spec S07).

### Page "Your organization" (plan page 5)

You become the administrator of Slate Operations (spec S08).

1. Type the organization name, your name and your email address (spec S08).
2. Type a password of 12 to 72 characters in both password fields (spec S08).
3. Write down the address on the line "Address for PCs and phones" (spec S08).
4. Select Next. Setup checks that no other device on the network uses the address (spec S08).

You sign in with this email address and password. Setup sends no email to the address. Setup does not keep the password, so remember it (spec S08). The address cannot change after setup (Copy.iss `s08_slug_help`).

### Page "Where to keep backups" (plan page 7)

Slate Operations makes a backup every night at 2:00 (spec S10).

1. Select the USB drive or another drive in the list (spec S10).
2. Select Next (spec S10).

Avoid "This PC's data drive": if that drive breaks, you lose the data and the backups. Keep the USB drive plugged in (spec S10).

### Page "Ready to install" (plan page 9)

1. Read the summary. To correct a row, select Change on that row (spec S11).
2. Select Install (spec S11).

The summary shows "Edition: Desk, the free edition" (Copy.iss `s11_edition`). This build checks no license and has no edition limits. Every feature is available (`frontend/src/components/systems/manage/domain/updates-rules.ts:9-10`).

### Page "Installing Slate Operations" (plan page 10)

The install takes up to 30 minutes. You can use the server PC while it installs (spec S12).

1. Keep the server PC on, plugged in and connected (spec S12).
2. Do not restart the server PC (spec S12).
3. Wait until the subtitle says "Finished." (spec S12).

If the page shows "Setup stopped", select Save report. Send the file to [support contact]. Then select Remove and close. Setup removes everything that it added, and you can start setup again (spec S13; plan 4.1, DEC-0041).

### Page "Save your recovery key" (plan page 11)

Your backups are locked. The recovery key opens them if the server PC breaks or is lost. Setup shows the key only on this page (spec S14).

1. Select Print the key, or Save to a USB drive that is not the backup drive (spec S14).
2. Keep the key in a safe place, away from the server PC and the backup drive (spec S14).
3. Select the check box "I printed or saved the recovery key" (spec S14).
4. Select Next (spec S14).

### Page "Slate Operations is ready" (plan page 12)

1. Write down the phone address in step 3, for example `http://riverside-learning.local/trust` (Wizard.iss, S15).
2. Write down the security code under the phone address (Wizard.iss, S15).
3. Select Open Slate Operations to sign in now (section 3 of this guide; spec S15).
4. Select Finish (spec S15).

The page also says "You use Desk, the free edition". This build has no license import and no edition limits (Copy.iss `s15_desk`; `updates-rules.ts:9-10`).

Slate Operations starts by itself when the server PC starts. For settings and help, open "Slate Operations settings" in the Start menu (spec S15, M01).

Email is not part of setup. Until you set it up, Slate Operations cannot send invitations or password resets. To set it up, read the [administrator guide](administrator-guide.md) (plan 4.1, page 6; DEC-0041).

## 3. Sign in for the first time

The server PC already trusts the secure connection of Slate Operations. It needs no "Trust this device" step (plan 6.2, Windows-side steps; Copy.iss `step_win_trust`).

1. On the server PC, select Open Slate Operations on the last setup page (spec S15).
2. Or double-click the "Slate Operations" shortcut on the desktop (SlateOpsSetup.iss `[Icons]`).
3. In "Email or username", type the email address from the page "Your organization" (login/page.tsx).
4. In "Password", type the password from the page "Your organization" (login/page.tsx).
5. Select Sign in (login/page.tsx).

If you forget the password before email is set up, use the server PC. Open "Slate Operations settings", then select Reset the admin password (spec M01; DEC-0042).

## 4. Trust this device: connect phones and other PCs

Each phone and other PC must trust Slate Operations once. After that, the browser shows no warning (spec section 3).

Connect the device to the same Wi-Fi as the server PC, not a guest Wi-Fi. Turn off any VPN on the device (trust page, "The page does not open?").

1. On the device, open the browser. On an iPhone or iPad, use Safari. On Android, use Chrome (trust page).
2. Type the phone address exactly, with `http://`, for example `http://riverside-learning.local/trust` (Copy.iss `s15_step3`).
3. Find the page title "Let this phone open Slate Operations". The page uses the word for your device, for example "computer" (trust page; spec T01).
4. Compare the code on the page with the security code on the server PC (trust page).
5. If the codes are different, stop. This is not your Slate Operations. Contact [support contact] (trust page).
6. Do the steps that the page shows for your device. The table below gives a summary (trust page).
7. Come back to the page (trust page).
8. Find the line "This phone trusts Slate Operations:" (trust page).
9. When this line says "Yes", select Open Slate Operations (trust page).
10. Sign in with your email address or username and your password (login/page.tsx).

To see the security code again on the server PC, open "Slate Operations settings". Then select Show the phone code (Maintenance.iss `ShowPhoneCode`).

| Device | Steps on the trust page (summary) |
|---|---|
| iPhone or iPad | In Safari, select Download the profile, then Allow. Open Settings → Profile Downloaded → Install. Open Settings → General → About → Certificate Trust Settings, and turn on Slate Operations. |
| Android | In Chrome, select Download the certificate. Open Settings, search for "CA certificate", and select it. Choose the downloaded file. Set a screen lock if the phone asks. |
| Windows PC | Select Download the certificate. Open the file and select Install Certificate. Select Current User. Put the certificate in Trusted Root Certification Authorities. Then restart the browser. |
| Mac | Select Download the certificate. Open the file in Keychain Access. Open the Slate Operations certificate. Set Trust to Always Trust. |

(Source: trust page `infra/caddy/trust/index.html`; plan 6.3.)

On Android, open Slate Operations in Chrome (plan 6.3). If Firefox still shows a warning, use another browser (trust page).

## 5. If something goes wrong

| Problem | What to do | Source |
|---|---|---|
| A page in setup shows "Setup stopped" before Install | Select Try again. If it stops again, select Save report. | spec S13 |
| Nobody can open Slate Operations | Make sure that the server PC is on, awake and connected. | spec C21 |
| You need a report for support | Open "Slate Operations - Save report" in the Start menu. The report goes to your desktop. | spec M01; SlateOpsSetup.iss `[Icons]` |

Send each report file to [support contact].

## 6. Next steps

- To set up email, invite your people and manage backups, read the [administrator guide](administrator-guide.md).
- To learn the daily tasks in Slate Operations, read the [user guide](user-guide.md).
