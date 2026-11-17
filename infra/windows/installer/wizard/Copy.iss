; Copy.iss - every sentence the wizard shows (wizard spec docs/specs/windows-installer-wizard.md,
; sections 5.3, 6 and 7; W8). Keys name the screen or the check; %1, %2 are values; %n is a
; line break. Technical names show only in keys that end in "_details" (spec section 3).

[CustomMessages]
; ---- Frame (spec 6.1)
stage_1=1 Check this PC
stage_2=2 Your details
stage_3=3 Install
stage_sep=·
btn_next=&Next
btn_close=&Close
btn_try_again=&Try again
btn_save_report=Save &report
btn_check_again=Check &again
btn_show_in_folder=Show in folder
btn_details=Details
btn_cancel=Cancel
btn_continue=Co&ntinue
btn_go_back=&Go back
btn_stop_setup=&Stop setup
word_ready=Ready
word_fix=Needs a fix
word_advice=Recommended
word_stop=Not suitable
word_fixed=Fixed
word_removed=Removed
report_saved=Report saved to your desktop: %1.
report_saving=Saving the report… (up to 3 minutes)

; ---- S01 Welcome
s01_title=Set up Slate Operations on this PC
s01_text=This PC becomes the server for your organization. Your people open Slate Operations from their PCs and phones on your office network.%n%n1. Check this PC: about 1 minute. Setup changes nothing yet.%n2. Answer a few questions: about 5 minutes.%n3. Install: about 30 minutes. You can use the PC while it installs.%n%nHave ready: the password of the email account that Slate Operations sends from, and a USB drive for backups (recommended).
s01_next=&Check this PC
s01_state_unsafe=Setup cannot use the folder C:\ProgramData\SlateOps, because a user who is not an administrator owns it. Select Save report and ask the person who manages this PC.

; ---- S02 Check this PC
s02_title=Check this PC
s02_subtitle=Setup checks whether this PC can be your Slate Operations server. It changes nothing.
s02_welcome_back=Welcome back. Setup checks this PC again.
s02_checking=Checking this PC… (about 1 minute)
s02_ready=This PC is ready to be your Slate Operations server.
s02_ready_restart=Setup will restart this PC once.
s02_needs=Fix %1 things, then setup can continue.
s02_needs_one=Fix 1 thing, then setup can continue.
s02_recommended=Recommended
s02_passed=%1 checks passed.
s02_show_all=Show all checks
s02_show_more=Show %1 more
s02_all_title=All checks
s02_fixing=Fixing…
s02_removing=Removing…
s02_restart_confirm=Save your work first. Setup opens again after you sign in and checks this PC again.
s02_restart_other_user=Setup cannot open by itself after this restart, because it runs with another administrator account.%nSign in again, then open the setup file again.%nThe setup file: %1. When you open it, Windows asks for the administrator account again.
s02_restart_unsafe=Sign in again, then open the setup file again.%nThe setup file: %1. When you open it, Windows asks for the administrator account again.

; ---- S03 This PC cannot be the server
s03_title=This PC cannot be the Slate Operations server
s03_subtitle=Nothing was changed on this PC.
s03_verdict=This PC cannot be the Slate Operations server.
s03_suitable=A suitable PC has: Windows 11 Pro, Enterprise or Education (version 22H2 or later), an Intel or AMD processor with virtualization, 16 GB of memory, 15 GB of free space and a connection to your office network.
s03_wrong=If you think this is wrong, select Save report and send the file to Slate Operations support.
s03_what=What you can do:
s03_home_todo=You can upgrade this PC to Windows 11 Pro in Settings → System → Activation. Microsoft charges for the upgrade. Or use another PC.
s03_memory_todo=A PC supplier can add memory to many PCs. Or use another PC.
s03_win10_todo=Check in Windows Update whether this PC can get Windows 11. Or use another PC.
s03_edition_todo=Ask your PC supplier whether this PC can get Windows 11 Pro. Or use another PC.

; ---- Check items (spec 5.3); name, then the message by code
c01_name=Windows version
c01_too_old=This PC has Windows 11 version %1. Slate Operations needs version 22H2 or later. Install the Windows updates, then select Check again.
c01_windows_10=This PC has Windows 10. Slate Operations needs Windows 11.
c01_btn=Open Windows Update
c02_name=Windows edition
c02_home=This PC has Windows 11 Home. Slate Operations needs Windows 11 Pro, Enterprise or Education.
c02_edition_not_supported=This PC has an edition of Windows that Slate Operations cannot use. Slate Operations needs Windows 11 Pro, Enterprise or Education.
c03_name=Processor
c03_arm=This PC has an Arm processor. Slate Operations needs an Intel or AMD processor.
c03_not_supported=This PC has a processor that Slate Operations cannot use. Slate Operations needs a 64-bit Intel or AMD processor.
c04_name=Virtualization
c04_off=Virtualization is off. Turn it on in this PC's startup settings (BIOS). Your PC supplier can help.
c04_no_slat=This PC's processor is too old for Slate Operations.
c04_cannot_read=Setup cannot read this setting. It checks it again when it prepares the server part.
c04_btn_how=Show me how
c04_btn_firmware=Restart to startup settings
c04_how_title=Turn on virtualization
c04_how_caution=Caution: have your BitLocker recovery key ready. A change in the startup settings can make Windows ask for it.
c04_how_text=Virtualization is a processor setting that lets this PC run the server part.%n%n1. Save your work and close your other programs.%n2. Select Restart to startup settings, if setup shows it. Otherwise, restart this PC and press the startup settings key while the maker's logo shows. The key shows on the screen, often F2, F10, F12, Esc or Delete.%n3. Find the virtualization setting and turn it on. Its name can be Intel Virtualization Technology, Intel VT-x, AMD-V or SVM Mode.%n4. Save the settings and exit. Windows starts again.%n5. Sign in. If setup does not open by itself, open the setup file again.%n%nYour PC supplier can help.
c04_restart_confirm=Save your work first. This PC restarts and opens its startup settings (BIOS). Turn on virtualization there, then save and exit. Setup opens again after you sign in.
c05_name=Memory
c05_too_small=This PC has %1 GB of memory. Slate Operations needs a PC with 16 GB.
c05_reserved=Windows can use %2 GB of the %1 GB of memory in this PC. Slate Operations needs 12 GB that Windows can use.
c07_name=Free space
c07_too_small=No drive in this PC has 15 GB free. The most free space is %1 GB, on %2. Free up space, then select Check again.
c07_no_drive=No drive in this PC has 15 GB free. Free up space, then select Check again.
c07_btn=Open storage settings
c08_name=Windows updates
c08_pending=Windows is waiting to restart after an update. Restart this PC, then setup checks again.
c08_btn=Restart now
c09_name=Network connection
c09_not_connected=This PC is not connected to a network. Connect it to your office network with a cable or Wi-Fi, then select Check again.
c10_name=Network type
c10_public=Windows treats this network as Public. Slate Operations works only on a Private network, so other devices can reach this PC.
c10_btn=Make this network private
c10_confirm=Do this only on your office or home network, not on public Wi-Fi.
c11_name=Company network
c11_domain=This PC is on a company network that an IT department manages. Slate Operations is not tested on such networks yet.
c12_name=Internet
c12_no_connection=Setup cannot reach the internet. Connect this PC to the internet, then select Check again.
c12_proxy=This PC uses a proxy server. Slate Operations cannot use one yet. Connect to a network without a proxy server, or ask the person who manages your network.
c13_name=Date and time
c13_wrong=This PC's clock is wrong by %1 minutes. Turn on Set time automatically, then select Check again.
c13_btn=Open date and time settings
c14_name=Web connection
c14_in_use=Another program on this PC uses the web connection that Slate Operations needs: %1. Stop or uninstall it, then select Check again.
c15_name=Address
c15_invalid_name=This PC's name cannot be used as an address. Rename this PC with letters, numbers and hyphens only.
c15_name_mismatch=Some Windows screens show this PC under a different name than its address, %1. For one name everywhere, rename this PC with 15 or fewer letters, numbers and hyphens. Do it before setup, restart this PC, then run setup again.
c15_btn=Open About settings
c16_name=Address
c16_name_in_use=Another device on this network already uses the address %1. Rename this PC, then select Check again.
c17_name=Phones can find this PC
c17_rule_off=Phones and other PCs cannot find this PC by its address. A Windows setting blocks it.
c17_policy=Phones and other PCs cannot find this PC by its address. A Windows setting blocks it. Ask the person who manages this PC.
c17_btn=Fix it for me
c18_name=Security policy
c18_policy=A security policy on this PC records the commands that programs run. Setup cannot keep passwords private while it is on. Ask the person who manages this PC to turn it off.
c18_unreadable=Setup cannot check whether a security policy on this PC records commands. Ask the person who manages this PC.
c20_name=Antivirus
c20_other_antivirus=%1 is on this PC. If setup stops, allow the folder C:\Program Files\Slate Operations in %1.
c21_name=Power
c21_laptop=This PC is a laptop. Keep it plugged in, open and in the office. Phones cannot use Slate Operations while it is away or asleep.
c21_on_battery=This laptop runs on battery now. Plug it in.
c22_name=Laptop lid
c22_sleeps=This laptop goes to sleep when you close the lid. Then Slate Operations stops for everyone.
c22_btn=Change it during the install
c22_chosen=Setup changes this during the install.
c22_undo=Undo
c23_name=Network cable
c23_wifi=This PC uses Wi-Fi. A network cable is more reliable for a server.
c24_name=Drive encryption
c24_off=Drive encryption (BitLocker) is off. Turn it on, so your data stays private if this PC is stolen.
c24_auto_unlock=Drive %1 is encrypted. Turn on automatic unlock for %1 in the BitLocker settings, so Slate Operations can start after a restart when nobody is signed in.
c24_btn=Show me how
c25_name=Docker Desktop
c25_installed=Docker Desktop is on this PC. Quit it while Slate Operations runs, so the two do not compete for memory.
c29_name=Parts of an earlier test
c29_earlier_test=This PC has parts of an earlier Slate Operations test. Setup removes them before it continues.
c29_leftover_account=This PC has a leftover of an earlier Slate Operations uninstall. Setup removes it before it continues.
c29_unknown_parts=This PC has parts of Slate Operations that setup cannot identify. Setup changes nothing. Select Save report and send the file to Slate Operations support.
c29_btn=Remove them
c29_form_title=Remove the parts of the earlier test?
c29_form_text=Setup removes the earlier test's server part and its data, its hidden account, its start tasks and its firewall rules. The test's log files stay. Your other programs and files do not change. If the normal removal does not work, setup stops the Windows feature that runs the server part for a moment, for every user of this PC.
c30_name=Address
c30_factory_name=The address of Slate Operations will be %1, from this PC's name. It cannot change after setup without every phone and PC trusting Slate Operations again. If you want a short address, rename this PC in Windows Settings before setup, restart it, then run setup again.
cannot_read=Setup cannot check this on this PC. You can continue. If setup stops later, select Save report.

; ---- S04 License agreement
s04_subtitle=Read the license, then select I accept.
s04_notices=Third-party notices

; ---- S05 Restart this PC once
s05_title=Restart this PC once
s05_subtitle=Windows needs one restart to finish a feature that Slate Operations needs.
s05_working=Turning on the Windows feature… (about 2 minutes)
s05_waiting=Another installation is running on this PC. Setup waits and tries again.
s05_done=The Windows feature is turned on. Windows finishes it when this PC restarts.
s05_steps=1. Save your work and close your other programs.%n2. Select Restart now.%n3. Sign in again. Setup opens by itself and continues.%n%nIf setup does not open, double-click Continue Slate Operations setup on the desktop.
s05_steps_other_user=1. Save your work and close your other programs.%n2. Select Restart now.%n3. Sign in again, then open the setup file again. Setup cannot open by itself after this restart, because it runs with another administrator account.%n%nThe setup file: %1. When you open it, Windows asks for the administrator account again.
s05_steps_unsafe=1. Save your work and close your other programs.%n2. Select Restart now.%n3. Sign in again, then open the setup file again.%n%nThe setup file: %1. When you open it, Windows asks for the administrator account again.
s05_details=Virtual Machine Platform, Windows Subsystem for Linux.
s05_next=&Restart now
s05_later=Restart &later
s05_failed=Setup could not turn on a Windows feature that Slate Operations needs.

; ---- S06 Welcome back
s06_title=Welcome back
s06_continue=Setup continues where it stopped.
s06_stopped=Setup stopped before it finished. It continues from the step that stopped.
s06_stopped_key=Setup stopped before you saved the recovery key.
s06_checking=Checking this PC again…
s06_still_ready=This PC is still ready. Setup checked it again.

; ---- S07 Where to keep your data
s07_title=Where to keep your data
s07_subtitle=Your records and files are kept on this drive.
s07_first=Setup chose the drive with the most free space.
s07_most_space=Most space
s07_folder=Folder: %1
s07_change_folder=Change folder
s07_change_program=Change program folder
s07_usb_note=USB and network drives are not listed. The data must stay inside this PC.
s07_not_empty=This folder is not empty. Choose an empty folder.
s07_too_small=This drive has %1 GB free. Slate Operations needs 15 GB. Choose another drive.
s07_parent_unsafe=Setup cannot keep your data in %1, because it cannot protect a folder above it. This is common for folders made in File Explorer. Setup can protect %2 for you.
s07_use_default=Use %1
s07_already=The server part is already on %1. To use another drive, select Cancel, then Remove everything, and start setup again.
s07_free=%1 GB free
s07_preparing=Preparing the server part: %1
s07_prepared=The server part is ready.
s07_prep_failed=Preparing the server part stopped. Select Next for details.
s07_start_failed=Setup could not start the server part of Slate Operations.
s07_folder_changed=Setup cannot keep your data in %1, because a folder above it changed. Select Cancel, then Remove everything, and start setup again.

; ---- S08 Your organization
s08_title=Your organization
s08_subtitle=You become the administrator of Slate Operations.
s08_name=Organization name
s08_name_help=People see this name in Slate Operations.
s08_email=Your email address
s08_email_help=Your invitation goes to this address. You set your password from it.
s08_more=More options
s08_username=User name
s08_slug=Short name
s08_more_help=Setup makes these from your email and the organization name. You can keep them.
s08_err_name=Enter the name of your organization.
s08_err_name_long=Use 100 characters or fewer.
s08_err_email=Enter an email address, for example maria@example.com.
s08_err_username=Use 3 to 100 letters, numbers, - or _.
s08_err_slug=Use only lowercase letters, numbers and single hyphens, for example riverside-learning.

; ---- S09 Email for Slate Operations
s09_title=Email for Slate Operations
s09_subtitle=Slate Operations sends invitations and password resets from this account.
s09_from=Send from
s09_provider=Provider
s09_gmail=Gmail
s09_m365=Microsoft 365
s09_other=Other
s09_detected=(detected)
s09_gmail_help=Gmail needs an app password, not your normal password.
s09_gmail_link=How to make an app password
s09_m365_note=Microsoft 365 blocks this kind of sign-in until the person who manages your Microsoft 365 turns it on for this mailbox.
s09_m365_link=Steps for your Microsoft 365 admin
s09_app_password=App password
s09_password=Password
s09_show=Show
s09_server=Server
s09_port=Port
s09_security=Security
s09_ssl=SSL/TLS (usually port 465)
s09_starttls=STARTTLS (usually port 587)
s09_user=User name
s09_sender_name=Sender name
s09_next_test=&Send test email
s09_continue_later=Continue later
s09_waiting=Getting ready to send… (about 1 minute)
s09_sending=Sending a test email to %1…
s09_passed=Test email sent to %1. It can take a few minutes to arrive. Look in Spam too.
s09_channel_failed=Setup cannot pass the password safely to the server part. Nothing was sent.
s09_outlook=Outlook.com accounts cannot send email for Slate Operations. Microsoft allows them only a sign-in method that Slate Operations cannot use yet. Use a Gmail or Microsoft 365 account, or an account from another email provider.
s09_gmail_title=How to make an app password
s09_gmail_steps=1. Select Open Google's page. Your browser opens myaccount.google.com/apppasswords.%n2. Sign in. If Google asks, turn on 2-Step Verification first.%n3. Type Slate Operations as the app name and select Create.%n4. Copy the 16-letter password and paste it here.%n%nIf you change your Google password, Google removes this app password. Then use Change email account in Slate Operations settings.
s09_gmail_open=Open Google's page
s09_m365_title=Steps for your Microsoft 365 admin
s09_m365_steps=Send these steps to the person who manages your Microsoft 365: In the Microsoft 365 admin center, open Users → Active users, select this mailbox, open Mail → Manage email apps, turn on Authenticated SMTP, and save.%n%nFrom the end of December 2026, Microsoft turns this setting off by default.%nSecurity defaults, or a policy that blocks basic authentication, also block Authenticated SMTP.
s09_m365_copy=Copy the steps
s09_err_auth_gmail=Gmail did not accept this password. Use an app password, not your normal Gmail password.
s09_err_auth=The email provider did not accept the user name or password. Check them and try again.
s09_err_m365=Microsoft 365 blocked the sign-in. The person who manages your Microsoft 365 must turn on Authenticated SMTP for this mailbox.
s09_err_unreachable=Setup cannot reach the email server %1. Check the server name and port.
s09_err_unreachable_known=Setup cannot reach %1. Check the internet connection.
s09_err_no_tls=This email server does not offer a secure connection. Slate Operations sends email only over a secure connection. Choose the other security option, or ask your email provider.
s09_err_certificate=The secure connection to %1 failed. Check the server name, and check this PC's date and time.
s09_err_sender=The email provider does not let this account send as %1. Use the address of the account.
s09_err_recipient=The email provider refused to send to %1. Check your email address on the previous page.
s09_err_other=Setup could not send the test email. Check each field, then select Send test email again.
s09_err_fields=Fill in every field of the email account.

; ---- S10 Backups
s10_title=Where to keep backups
s10_subtitle=Slate Operations makes a backup every night at 2:00.
s10_first=Keep backups on another drive, so one broken drive cannot lose everything.
s10_data_drive=This PC's data drive (%1). Not safe if this drive breaks.
s10_plug=Plug in a USB drive now. Setup finds it by itself.
s10_none=No other drive was found on this PC.
s10_confirm=I understand: if drive %1 breaks, the data and the backups are both lost.
s10_later=You can choose a backup drive later in Slate Operations settings.
s10_usb=Keep this USB drive plugged in. A backup fails while the drive is out.
s10_usb_word=USB drive
s10_not_writable=Slate Operations cannot write to %1. Plug the drive in, or choose another drive.
s10_too_small=%1 has %2 GB free. Choose a drive with more space.

; ---- S11 Ready to install
s11_title=Ready to install
s11_subtitle=Check your choices, then select Install.
s11_org=Organization: %1
s11_admin=Administrator: %1
s11_mail=Email sent from: %1 (%2, test passed)
s11_data=Data: %1
s11_backups=Backups: %1, every night at 2:00
s11_address=Address for PCs and phones: %1
s11_edition=Edition: Desk, the free edition
s11_time=Installing takes about 30 minutes. Keep this PC on and connected.
s11_change=Change
s11_what=What setup changes on this PC
s11_what_text=Adds a hidden Windows account that runs Slate Operations. Starts Slate Operations when Windows starts, also when nobody is signed in. Allows Slate Operations through Windows Firewall on Private networks. Makes this PC trust the secure connection of Slate Operations. Keeps this PC awake when it is plugged in. Adds Slate Operations to the Start menu and the desktop. Uninstall removes all of these.
s11_what_lid=Keeps this laptop running when the lid is closed and it is plugged in.
s11_next=&Install

; ---- S12 Installing
s12_title=Installing Slate Operations
s12_subtitle=This can take up to 30 minutes.
s12_stage1=Download the parts
s12_stage2=Prepare the settings
s12_stage3=Set up the secure connection
s12_stage4=Set up the database
s12_stage5=Start Slate Operations
s12_stage6=Create your administrator account and send your invitation
s12_stage7=Make the first backup
s12_stage8=Finish on this PC
s12_fail1=download the parts
s12_fail2=prepare the settings
s12_fail3=set up the secure connection
s12_fail4=set up the database
s12_fail5=start Slate Operations
s12_fail6=create your administrator account and send your invitation
s12_fail7=make the first backup
s12_fail8=finish on this PC
s12_box=While you wait: You can use this PC. Keep it on, plugged in and connected, and do not restart it. At the end, setup shows your recovery key. Have a printer or a USB drive ready.
s12_done_word=Done
s12_now_word=Now
s12_slow=This step takes longer than expected.
s12_wait=&Wait
s12_not_ready=Slate Operations did not start.
s12_disk_full=The server part of Slate Operations has no free space left. Select Save report and send the file to Slate Operations support.
s12_backup_failed=Slate Operations cannot save backups to %1.
s12_firewall=Setup could not set up Windows Firewall for Slate Operations.
s12_https=Slate Operations is installed, but this PC cannot open it at %1.
; Spec 7.5 (catalog rows "Antivirus or Smart App Control blocks a file" and "Service account cannot sign in").
av_blocked=A security program on this PC blocked part of Slate Operations setup. Allow the folder C:\Program Files\Slate Operations in the security program, then select Try again.
service_logon_failed=Windows did not let Slate Operations start. A security policy on this PC can cause this. Select Repair. If it happens again, ask the person who manages this PC.
s12_choose_drive=Choose another drive

; ---- S13 Setup stopped (layout shown in place)
s13_title=Setup stopped
s13_could_not=Setup could not %1.
s13_what=What you can do:%n1. Select Try again. Setup continues from this step. Nothing is lost.%n2. If it stops again, select Save report and send the file to Slate Operations support.

; ---- S14 Save your recovery key
s14_title=Save your recovery key
s14_subtitle=Your backups are locked. This key opens them if this PC breaks or is lost.
s14_text=Keep it somewhere safe, away from this PC and away from the backup drive. Setup shows the key only now. You can make a new key later in Slate Operations settings.
s14_making=Making your recovery key… (about 1 minute)
s14_print=&Print the key
s14_usb=Save to a &USB drive
s14_check=I printed or saved the recovery key
s14_printed=Sent to the printer.
s14_saved=Saved to %1.
s14_backup_drive=This is your backup drive. A key on it opens your backups for anyone who has the drive. Use another USB drive, print the key, or write it down.
s14_no_usb=Plug in a USB drive. Setup finds it by itself.
s14_file_printer=This printer saves a file instead of printing on paper. Choose a printer that prints on paper, or save the key to a USB drive.
s14_print_title=Print the key
s14_print_job=Slate Operations recovery key
s14_key_failed=Setup could not make the recovery key.

; ---- S15 Slate Operations is ready
s15_title=Slate Operations is ready
s15_step1=1. Set your password. Open the email from Slate Operations sent to %1 and select the link. It can take a few minutes; look in Spam too.%nNo email after 10 minutes? Open Slate Operations settings in the Start menu and select Send my invitation again.
s15_step1_no_address=1. Set your password. Open the email from Slate Operations and select the link. It can take a few minutes; look in Spam too.%nNo email after 10 minutes? Open Slate Operations settings in the Start menu and select Send my invitation again.
s15_step2=2. Open Slate Operations on this PC.
s15_open=&Open Slate Operations
s15_step3=3. Connect phones and other PCs. Connect the phone to the same Wi-Fi as this PC. In the phone's browser, type the address below exactly, with http://. The page shows the one-time steps that let the phone open Slate Operations.
s15_security=Security code: %1. The phone page shows the same code.
s15_desk=You use Desk, the free edition. To add a license later, open Manage → Updates & licensing in Slate Operations.
s15_starts=Slate Operations starts by itself when this PC starts. For settings and help, open Slate Operations settings in the Start menu.
s15_finish=&Finish

; ---- Cancel (spec 4.5)
cancel_nothing=Stop setup? Nothing was installed.
cancel_feature=Stop setup? The Windows feature that setup turned on stays on. Other programs can use it.
cancel_server=Stop setup? Setup has already added the server part to this PC.
cancel_keep=Keep it and continue later: the next time you start setup, it continues here. Your email password is not kept.
cancel_wait=Setup stops after the current step. This takes up to a minute.

; ---- M01 Slate Operations on this PC (W8 part: spec 12 item 11)
m01_title=Slate Operations on this PC
m01_subtitle=Version %1 · %2
m01_invite=Send my invitation again
m01_invite_hint=Use this only before you set your password.
m01_sending=Sending your invitation… (about 1 minute)
m01_report_hint=A file for Slate Operations support.
m01_sent=Slate Operations sent your invitation again. Look in your inbox and in Spam.
m01_already_active=Your account is already set up. Sign in with your password. If you forgot it, reset it from the sign-in page.
m01_rate_limited=Slate Operations sent several emails a short time ago. Wait a few minutes, then try again.
m01_failed=Slate Operations could not send the invitation. Check the email account with Change email account, then try again.
m01_footer=To uninstall, open Settings → Apps.
