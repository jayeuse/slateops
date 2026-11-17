; SlateOpsSetup.iss - the Slate Operations setup program (Inno Setup 6.7; plan 3.1, W7).
;
; W7 builds the skeleton: the [Setup] frame of wizard spec 6.1 and 12 item 2, the Windows-side
; scripts, the desktop address shortcut (spec 12 item 13), and the [Code] plumbing that starts
; the hidden helper and reads its result file (plan F4b). The pages and their copy, the secret
; pipe channel and Save report are W8; uninstall and maintenance are W9.
;
; Build: ISCC.exe /DAppVersion=<version> SlateOpsSetup.iss
; The payload (the WSL MSI, the Linux image, the setup payload and version.json) is added by
; the release build (W8); this file compiles without it.

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
SolidCompression=yes
UninstallDisplayName=Slate Operations

[Files]
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

[Code]
type
  TSystemTime = record
    Year, Month, DayOfWeek, Day, Hour, Minute, Second, Milliseconds: Word;
  end;

procedure GetSystemTime(var SystemTime: TSystemTime);
  external 'GetSystemTime@kernel32.dll stdcall';
function GetTickCount: Cardinal;
  external 'GetTickCount@kernel32.dll stdcall';
function GetComputerNameEx(NameType: Integer; Buffer: String; var Size: Cardinal): Boolean;
  external 'GetComputerNameExW@kernel32.dll stdcall';

var
  HelperScript: String;
  StateCheckCode: String;

function TwoDigits(Value: Word): String;
begin
  Result := IntToStr(Value);
  if Length(Result) < 2 then
    Result := '0' + Result;
end;

{ Run ID: <kind>-<UTC yyyymmddThhmmssZ>-<6 characters> (plan 10.1 item 1). The characters only
  make the ID unique; they are not a secret. }
function NewRunId(Kind: String): String;
var
  Clock: TSystemTime;
  Alphabet, Suffix: String;
  Seed: Cardinal;
  I: Integer;
begin
  GetSystemTime(Clock);
  Alphabet := 'abcdefghijklmnopqrstuvwxyz0123456789';
  Seed := GetTickCount;
  Suffix := '';
  for I := 1 to 6 do
  begin
    Suffix := Suffix + Alphabet[Integer(Seed mod 36) + 1];
    Seed := (Seed div 36) + Cardinal(I * 7919);
  end;
  Result := Kind + '-' + IntToStr(Clock.Year) + TwoDigits(Clock.Month) + TwoDigits(Clock.Day) + 'T' +
    TwoDigits(Clock.Hour) + TwoDigits(Clock.Minute) + TwoDigits(Clock.Second) + 'Z-' + Suffix;
end;

{ The DNS host name (ComputerNameDnsHostname = 1) in lower case; the NetBIOS name when the call
  fails. }
function DnsHostName(Param: String): String;
var
  Buffer: String;
  Size: Cardinal;
begin
  Size := 256;
  Buffer := StringOfChar(#0, Integer(Size));
  if GetComputerNameEx(1, Buffer, Size) then
    Result := Lowercase(Copy(Buffer, 1, Integer(Size)))
  else
    Result := Lowercase(ExpandConstant('{computername}'));
end;

function HelperParams(Action, RunId, OutFile, Extra: String): String;
begin
  Result := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ' + AddQuotes(HelperScript) +
    ' -Action ' + Action + ' -RunId ' + RunId + ' -OutFile ' + AddQuotes(OutFile);
  if Extra <> '' then
    Result := Result + ' ' + Extra;
end;

{ Starts the helper without waiting (plan F4b: the page reads the result file on a timer). }
function StartHelper(Action, RunId, OutFile, Extra: String): Boolean;
var
  ResultCode: Integer;
begin
  DeleteFile(OutFile);
  Result := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    HelperParams(Action, RunId, OutFile, Extra), '', SW_HIDE, ewNoWait, ResultCode);
end;

{ Runs a short helper action and waits (state-check, save-progress, clear-resume). }
function RunHelper(Action, RunId, OutFile, Extra: String): Boolean;
var
  ResultCode: Integer;
begin
  DeleteFile(OutFile);
  Result := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    HelperParams(Action, RunId, OutFile, Extra), '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

{ The "code" of a helper result. The helper writes compact JSON with no spaces; the code is a
  safe word ([a-z0-9_]), so a plain search is enough. Empty while the file does not exist. }
function ReadResultCode(OutFile: String): String;
var
  Text: AnsiString;
  Start, Stop: Integer;
begin
  Result := '';
  if not LoadStringFromFile(OutFile, Text) then
    Exit;
  Start := Pos('"code":"', Text);
  if Start = 0 then
    Exit;
  Start := Start + Length('"code":"');
  Stop := Start;
  while (Stop <= Length(Text)) and (Text[Stop] <> '"') do
    Stop := Stop + 1;
  Result := Copy(Text, Start, Stop - Start);
end;

function InitializeSetup(): Boolean;
var
  OutFile: String;
begin
  ExtractTemporaryFiles('{tmp}\scripts\*.ps1');
  ExtractTemporaryFiles('{tmp}\scripts\lib\*.ps1');
  HelperScript := ExpandConstant('{tmp}\scripts\setup-helper.ps1');
  { Spec 4.1: before setup reads or writes C:\ProgramData\SlateOps, the folder passes the
    safety check. W8 shows the S01 stop for unsafe_owner and chooses the first screen. }
  OutFile := ExpandConstant('{tmp}\state-check.json');
  StateCheckCode := '';
  if RunHelper('state-check', NewRunId('install'), OutFile, '') then
    StateCheckCode := ReadResultCode(OutFile);
  Log('State folder check: ' + StateCheckCode);
  Result := True;
end;
