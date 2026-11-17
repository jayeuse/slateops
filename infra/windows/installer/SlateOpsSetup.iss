; SlateOpsSetup.iss - the Slate Operations setup program (Inno Setup 6.7; plan 3.1, W7, W8).
;
; W7: the [Setup] frame of wizard spec 6.1 and 12 item 2, the Windows-side scripts and the
; desktop address shortcut (spec 12 item 13). W8: the pages (wizard\Wizard.iss), their copy
; (wizard\Copy.iss), the secret pipe channel, Save report and the payload. Uninstall and
; maintenance beyond "Send my invitation again" are W9.
;
; Build: ISCC.exe /DAppVersion=<version> [/DPayloadDir=<folder>] SlateOpsSetup.iss
; The release build (release.yml, installer job) passes PayloadDir: version.json, the pinned
; WSL MSI, the Linux image, the five receive parts (plan 5.2), THIRD-PARTY-NOTICES.txt and
; SOURCE-OFFER.txt. Without it the file compiles with no payload (the windows-installer job).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; The same AppId gives the uninstall key ..._is1 that the PC check reads (Checks.ps1).
AppId={{8B0C1D7E-3F4A-4E52-9A61-5C2D7B9E0F13}
AppName=Slate Operations
AppVersion={#AppVersion}
AppVerName=Slate Operations {#AppVersion}
AppPublisher=Slate Operations
DefaultDirName={autopf}\Slate Operations
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableWelcomePage=no
PrivilegesRequired=admin
; Spec 6.1: the modern style with no custom style, so system colors and high contrast apply;
; the largest fixed size.
WizardStyle=modern
WizardSizePercent=150,150
; Spec 12 item 2: Windows 10 and Arm reach the check's stop screen instead of Inno's own
; message; the PC check (C01, C03) decides.
MinVersion=10.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\..\..\LICENSE
OutputDir=output
OutputBaseFilename=SlateOpsSetup-{#AppVersion}
SetupLogging=yes
Compression=lzma2
; The payload parts are compressed archives already; the setup extracts each one on demand
; (ExtractTemporaryFiles), which a solid block would make slow (Inno Setup help).
SolidCompression=no
; Spec S11 is the summary page; Inno's own ready page is not shown.
DisableReadyPage=yes
UninstallDisplayName=Slate Operations

[Files]
#ifdef PayloadDir
; The payload first (help: files extracted on demand go at the top). dontcopy: the wizard
; extracts each part when its page needs it; the helper copies it into the admin-only tree.
Source: "{#PayloadDir}\version.json"; DestDir: "{tmp}\scripts"; Flags: dontcopy
Source: "{#PayloadDir}\wsl.*.x64.msi"; DestDir: "{tmp}\payload"; Flags: dontcopy nocompression
; The Linux image and the five receive parts, by their exact names (plan 5.2; Exec.ps1
; Get-ReceivePartNames, Read-SetupVersion).
Source: "{#PayloadDir}\slateops-linux-{#AppVersion}-amd64.tar.gz"; DestDir: "{tmp}\payload"; Flags: dontcopy nocompression
Source: "{#PayloadDir}\slateops-engine-{#AppVersion}.tar.gz"; DestDir: "{tmp}\payload"; Flags: dontcopy nocompression
Source: "{#PayloadDir}\slateops-server-{#AppVersion}-amd64.oci.tar"; DestDir: "{tmp}\payload"; Flags: dontcopy nocompression
Source: "{#PayloadDir}\slateops-caddy-{#AppVersion}-amd64.oci.tar"; DestDir: "{tmp}\payload"; Flags: dontcopy nocompression
Source: "{#PayloadDir}\release-manifest.json"; DestDir: "{tmp}\payload"; Flags: dontcopy
Source: "{#PayloadDir}\release-manifest.json.sigstore.json"; DestDir: "{tmp}\payload"; Flags: dontcopy
Source: "{#PayloadDir}\THIRD-PARTY-NOTICES.txt"; DestDir: "{tmp}"; Flags: dontcopy
; The installed program: version.json is the spec 4.1 signal of an installation; the notices
; and the source offer go in the program folder (TASK-0083 carry).
Source: "{#PayloadDir}\version.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\THIRD-PARTY-NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\SOURCE-OFFER.txt"; DestDir: "{app}"; Flags: ignoreversion
#endif
; The helper and its library, for the wizard before anything is installed ({tmp} is
; administrator-only when setup runs elevated).
Source: "scripts\*.ps1"; DestDir: "{tmp}\scripts"; Flags: dontcopy
Source: "scripts\lib\*.ps1"; DestDir: "{tmp}\scripts\lib"; Flags: dontcopy
; The small Windows part kept for maintenance mode (W9).
Source: "scripts\*.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "scripts\lib\*.ps1"; DestDir: "{app}\scripts\lib"; Flags: ignoreversion

[Icons]
; An Internet Shortcut (.url) with the address (spec 12 item 13). Uninstall removes it. The
; address is the DNS host name in lower case (P3-9), the name that Windows answers mDNS for.
Name: "{autodesktop}\Slate Operations"; Filename: "https://{code:DnsHostName}.local"

#include "wizard\Copy.iss"
#include "wizard\Wizard.iss"
