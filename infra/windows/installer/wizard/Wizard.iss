; Wizard.iss - the [Code] of the Slate Operations setup program (Inno Setup 6.7; plan 4.1, W7, W8).
;
; W7: the run ID, the helper start, the result-code read and the state-folder check. W8: the
; pages S01 to S15 of the wizard spec, the first-screen rule (spec 4.1), the secret channel (a
; named pipe, plan 3.2 rule 3), Save report (plan 10.6) and the M01 action "Send my invitation
; again" (spec 12 item 11). Every sentence comes from Copy.iss. ASCII only.
;
; Long work never blocks: the helper or the Exec job runs in the background and one timer reads
; its result file (plan F4b). The SMTP password and the recovery key exist only in this process
; and in the pipe; they are never logged (Log is never called with them) and never saved with
; SetPreviousData.

[Code]
type
  TSystemTime = record
    Year, Month, DayOfWeek, Day, Hour, Minute, Second, Milliseconds: Word;
  end;
  TSecurityAttributes = record
    nLength: Longword;
    lpSecurityDescriptor: Longword;
    bInheritHandle: Longword;
  end;
  TDocInfo = record
    cbSize: Integer;
    lpszDocName: Longword;
    lpszOutput: Longword;
    lpszDatatype: Longword;
    fwType: Longword;
  end;
  TCheckItem = record
    Id, Cls, Code, Raw: String;
  end;

const
  PIPE_ACCESS_DUPLEX = 3;
  FILE_FLAG_FIRST_PIPE_INSTANCE = $00080000;
  PIPE_NOWAIT = 1;
  PIPE_REJECT_REMOTE_CLIENTS = 8;
  INVALID_HANDLE = $FFFFFFFF;
  { W8 correction 5: every helper wait has a time limit; a helper that never answers is most
    often a security program that blocked it (spec 7.5). }
  HELPER_LIMIT_MS = 600000;
  { W9: the small settings program (/DSettingsBuild) and the main build that carries it. }
#ifdef SettingsBuild
  SETTINGS_BUILD = True;
#else
  SETTINGS_BUILD = False;
#endif
#ifdef SettingsExe
  HAS_SETTINGS = True;
#else
  HAS_SETTINGS = False;
#endif
  { W14-D1: the [Code] self-test build (/DSelfTest, wizard\SelfTest.iss) installs nothing. }
#ifdef SelfTest
  SELF_TEST = True;
#else
  SELF_TEST = False;
#endif
  UNINSTALL_KEY = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{8B0C1D7E-3F4A-4E52-9A61-5C2D7B9E0F13}_is1';
  CHECK_LIMIT_MS = 300000;
  DATA_LIMIT_MS = 1800000;
  SUBMIT_LIMIT_MS = 120000;
  ERROR_BROKEN_PIPE = 109;
  ERROR_NO_DATA = 232;
  ERROR_PIPE_CONNECTED = 535;
  ERROR_PIPE_LISTENING = 536;
  DRIVE_REMOVABLE = 2;
  DRIVE_FIXED = 3;
  FILE_ATTRIBUTE_REPARSE = $400;
  WM_COPY = $0301;
  LOGPIXELSY = 90;
  HORZRES = 8;
  P_CHECK = 0; P_RESTART = 1; P_BACK = 2; P_DATA = 3; P_ORG = 4; P_EMAIL = 5; P_BACKUP = 6; P_READY = 7;
  P_INSTALL = 8; P_KEY = 9; P_MAINT = 10; P_UPDATE = 11; P_COUNT = 12;
  { W13b part 2 (M05): the WSL step's own limit: the idle check, msiexec with three 60 s waits
    on code 1618, then 10 minutes for the engine status (F10). The wait between two idle
    checks, and the planning time after which the update shows the slow line. }
  WSL_LIMIT_MS = 1800000;
  UPDATE_WAIT_MS = 30000;
  UPDATE_SLOW_MINUTES = 60;
  JOB_IDLE = 0; JOB_SUBMIT = 1; JOB_WAIT = 2; JOB_DONE = 3;

procedure GetSystemTime(var SystemTime: TSystemTime);
  external 'GetSystemTime@kernel32.dll stdcall';
function GetTickCount: Cardinal;
  external 'GetTickCount@kernel32.dll stdcall';
function GetComputerNameEx(NameType: Integer; Buffer: String; var Size: Cardinal): Boolean;
  external 'GetComputerNameExW@kernel32.dll stdcall';
function SetTimer(hWnd, nIDEvent, uElapse, lpTimerFunc: Longword): Longword;
  external 'SetTimer@user32.dll stdcall';
function CreateNamedPipe(Name: String; OpenMode, PipeMode, MaxInstances, OutSize, InSize, Timeout: Longword; var Attributes: TSecurityAttributes): Longword;
  external 'CreateNamedPipeW@kernel32.dll stdcall';
function ConnectNamedPipe(Pipe: Longword; Overlapped: Longword): Boolean;
  external 'ConnectNamedPipe@kernel32.dll stdcall';
function PeekNamedPipe(Pipe: Longword; Buffer: Longword; Size: Longword; Read: Longword; var Available: Longword; Left: Longword): Boolean;
  external 'PeekNamedPipe@kernel32.dll stdcall';
function ReadFile(Handle: Longword; Buffer: AnsiString; Count: Longword; var Done: Longword; Overlapped: Longword): Boolean;
  external 'ReadFile@kernel32.dll stdcall';
function WriteFile(Handle: Longword; Buffer: AnsiString; Count: Longword; var Done: Longword; Overlapped: Longword): Boolean;
  external 'WriteFile@kernel32.dll stdcall';
function CloseHandle(Handle: Longword): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';
function ConvertSddl(Sddl: String; Revision: Longword; var Descriptor: Longword; Size: Longword): Boolean;
  external 'ConvertStringSecurityDescriptorToSecurityDescriptorW@advapi32.dll stdcall';
function LocalFree(Memory: Longword): Longword;
  external 'LocalFree@kernel32.dll stdcall';
function RtlGenRandom(Buffer: AnsiString; Length: Longword): Boolean;
  external 'SystemFunction036@advapi32.dll stdcall';
function GetDriveType(Root: String): Longword;
  external 'GetDriveTypeW@kernel32.dll stdcall';
function GetFileAttributes(Path: String): Longword;
  external 'GetFileAttributesW@kernel32.dll stdcall';
function GlobalAlloc(Flags, Bytes: Longword): Longword;
  external 'GlobalAlloc@kernel32.dll stdcall';
function GlobalFree(Memory: Longword): Longword;
  external 'GlobalFree@kernel32.dll stdcall';
function StrCopyTo(Destination: Longword; Source: String): Longword;
  external 'lstrcpyW@kernel32.dll stdcall';
function CreateDC(Driver, Device: String; Output, Mode: Longword): Longword;
  external 'CreateDCW@gdi32.dll stdcall';
function StartDoc(DC: Longword; var Info: TDocInfo): Integer;
  external 'StartDocW@gdi32.dll stdcall';
function StartPage(DC: Longword): Integer;
  external 'StartPage@gdi32.dll stdcall';
function EndPage(DC: Longword): Integer;
  external 'EndPage@gdi32.dll stdcall';
function EndDoc(DC: Longword): Integer;
  external 'EndDoc@gdi32.dll stdcall';
function AbortDoc(DC: Longword): Integer;
  external 'AbortDoc@gdi32.dll stdcall';
function DeleteDC(DC: Longword): Boolean;
  external 'DeleteDC@gdi32.dll stdcall';
function GetDeviceCaps(DC: Longword; Index: Integer): Integer;
  external 'GetDeviceCaps@gdi32.dll stdcall';
function CreateFont(Height, Width, Escapement, Orientation, Weight: Integer; Italic, Underline, StrikeOut, CharSet, OutPrecision, ClipPrecision, Quality, PitchAndFamily: Longword; Face: String): Longword;
  external 'CreateFontW@gdi32.dll stdcall';
function SelectObject(DC, GdiObject: Longword): Longword;
  external 'SelectObject@gdi32.dll stdcall';
function DeleteObject(GdiObject: Longword): Boolean;
  external 'DeleteObject@gdi32.dll stdcall';
function TextOut(DC: Longword; X, Y: Integer; Text: String; Count: Integer): Boolean;
  external 'TextOutW@gdi32.dll stdcall';

var
  HelperScript, StateCheckCode, RunId, SetupVersion, ServiceSid, HostName: String;
  EntryScreen, EntryNext: String;
  EntryWelcomeBack, StateUnsafe, ForceClose, ModalOpen, Ticking: Boolean;
  Pages: array of TWizardPage;
  Bodies: array of TPanel;
  Cur: TPanel;
  CurY, OutSeq: Integer;
  ExtraButton: TNewButton;
  NoticesLink: TNewLinkLabel;

  { S02, S06, S11: the check }
  CheckOut, CheckVerdict, CheckText, CheckFor: String;
  CheckRunning, CheckDone, NeedPrepare, RestartNeeded, LidChosen, FixRunning: Boolean;
  { W14-D1: S02 shows the draw failure; Next runs the check again. }
  CheckDrawFailed: Boolean;
  Items: array of TCheckItem;
  FixOut, FixAction: String;

  { S05 }
  PrepOut, PrepState, ResumeCode: String;
  PrepDetails: Boolean;

  { S07 and the background preparation }
  DriveLetters: array of String;
  DriveFree: array of Int64;
  DriveRadios: array of TNewRadioButton;
  DataRoot, DataError, DataErrorValue: String;
  DataPrepared, DataStarted, BgFailed: Boolean;
  BgIndex: Integer;
  BgOut, BgCode: String;

  { S08 }
  OrgName, OrgEmail, OrgUser, OrgSlug: TNewEdit;
  OrgMoreLink: TNewLinkLabel;
  OrgUserLabel, OrgSlugLabel, OrgMoreHelp, OrgError: TNewStaticText;

  { S09 }
  MailFrom, MailPassword, MailServer, MailPort, MailUser, MailSender: TNewEdit;
  MailGmail, MailM365, MailOther, MailSsl, MailStartTls: TNewRadioButton;
  MailShow: TNewCheckBox;
  MailNote, MailStatus, MailError, MailPasswordLabel, MailServerLabel, MailPortLabel, MailSecurityLabel, MailUserLabel, MailSenderLabel, MailFromLabel, MailProviderLabel: TNewStaticText;
  MailHelpLink, MailMoreLink: TNewLinkLabel;
  MailPassed, MailSelfTested, MailOutlook, MailMore, MailWaitingBg: Boolean;
  MailPhase, MailDetected, MailCheckedDomain, MailProviderName: String;
  MailErrorAfter: TControl;
  MailChangedAt: Cardinal;

  { S10 }
  BackupLetters: array of String;
  BackupRadios: array of TNewRadioButton;
  BackupConfirm: TNewCheckBox;
  BackupDrive, BackupSeen, BackupError: String;

  { S11 }
  JumpTarget: Integer;
  ReturnToReady, RecheckPassed: Boolean;

  { S12 }
  InstallStep: Integer;
  InstallStarted, InstallDone, InstallFailed, InstallSlow: Boolean;
  InstallFailText, InstallFailStage, InstallOut, PemText, SecurityCode: String;
  InstallNoRetry, InstallBackupFailed: Boolean;
  InstallStartedAt: Cardinal;

  { S14 }
  KeyText, KeyState, KeyStateText: String;
  KeyChecked: Boolean;
  KeyCheck: TNewCheckBox;
  KeyUsb: TNewComboBox;
  KeyUsbLetters: array of String;

  { M01 }
  MaintLine: String;

  { The Exec job runner (one job at a time; spec 12 item 1) }
  JobName, JobRequestId, JobOut, JobResultOut, JobText, JobCode, JobPurpose: String;
  JobState, JobExit: Integer;
  JobStartedAt, JobLimitMs: Cardinal;
  PipeHandle: Longword;
  PipeFrame, PipeOutput: AnsiString;
  PipeConnected, PipeExpectOutput: Boolean;
  { W8 correction 1: the job's own flag; PollPipe clears PipeExpectOutput when the service closes. }
  JobPipeOut: Boolean;
  FailureStatus: TNewStaticText;
  CheckStartedAt, FixStartedAt, PrepStartedAt, BgStartedAt, InstallOutAt, DataStartedAt: Cardinal;
  BgResume, MailShowReport: Boolean;
  { W9: reinstall with kept data (spec S07 kept-data card, plan 9.2). }
  KeptState, KeptVersion, KeptName, KeptOn, KeptFor: String;
  KeptUse, WizardReady: Boolean;
  { W9 maintenance (Maintenance.iss). }
  MaintAction, MaintPhase, MaintStatus, MaintStatusOut, MaintTarget, MaintState, MaintBackup, MaintBackupFolder: String;
  MaintStatusAt: Cardinal;
  MaintNetwork: Boolean;
  KeyFormOpen: Boolean;
  KeyFormStatus: TNewStaticText;
  KeyFormDone: TNewButton;
  KeyFormCheck: TNewCheckBox;
  KeyFormUsbSeen: String;
  MailReportButton: TNewButton;

  { Save report }
  ReportLine, ReportPath: String;

  { W13b part 2: M05 Update (Maintenance.iss). JobRaw is the job-result text of the last job. }
  InstalledVersion, UpdPhase, UpdNext, UpdOut, UpdState, UpdNeedsGb, UpdFailText, UpdFailStage, JobRaw: String;
  UpdAt: Cardinal;
  UpdFailed, UpdRetry, UpdWaiting, UpdSlowShown, UpdEngineDone: Boolean;

procedure RenderPage(Index: Integer); forward;
procedure SaveReport(Sender: TObject); forward;
procedure StartBackground; forward;
function BgDone: Boolean; forward;
{ W9, in Maintenance.iss. }
procedure RefreshKeyState; forward;
procedure FillKeyFormUsb; forward;
procedure RenderMaint; forward;
procedure StartMaintStatus; forward;
procedure PollMaint; forward;
function MaintNext(PageID: Integer): Boolean; forward;
function MaintSkip(PageID: Integer): Boolean; forward;
function AskCancelChoice: Integer; forward;
procedure RemoveEverything; forward;
function SettingsEntry: Boolean; forward;
#ifdef SelfTest
procedure RunSelfTest; forward;
#endif
{ W9 review item 1: SaveContinueLater reads the kept mode. }
function KeptMode: Boolean; forward;
{ W13b part 2, in Maintenance.iss. }
procedure RenderUpdate; forward;
procedure PollUpdate; forward;
function UpdateNext: Boolean; forward;
function UpdCanStop: Boolean; forward;

{ ------------------------------------------------------------------------------------------- }
{ W7 plumbing: run ID, host name, helper start and result read                                  }
{ ------------------------------------------------------------------------------------------- }

function TwoDigits(Value: Word): String;
begin
  Result := IntToStr(Value);
  if Length(Result) < 2 then
    Result := '0' + Result;
end;

{ Run ID: <kind>-<UTC yyyymmddThhmmssZ>-<6 characters> (plan 10.1 item 1). }
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

function HelperParams(Action, ARunId, OutFile, Extra: String): String;
begin
  Result := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ' + AddQuotes(HelperScript) +
    ' -Action ' + Action + ' -RunId ' + ARunId + ' -OutFile ' + AddQuotes(OutFile);
  if Extra <> '' then
    Result := Result + ' ' + Extra;
end;

{ Starts the helper without waiting (plan F4b: the page reads the result file on a timer). }
function StartHelper(Action, ARunId, OutFile, Extra: String): Boolean;
var
  ResultCode: Integer;
begin
  DeleteFile(OutFile);
  Result := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    HelperParams(Action, ARunId, OutFile, Extra), '', SW_HIDE, ewNoWait, ResultCode);
end;

{ Runs a short helper action and waits. }
function RunHelper(Action, ARunId, OutFile, Extra: String): Boolean;
var
  ResultCode: Integer;
begin
  DeleteFile(OutFile);
  Result := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    HelperParams(Action, ARunId, OutFile, Extra), '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

{ The "code" of a helper result: the first "code" in the file (P2-2). }
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

{ ------------------------------------------------------------------------------------------- }
{ Small helpers                                                                                 }
{ ------------------------------------------------------------------------------------------- }

function CM(Key: String): String;
begin
  try
    Result := CustomMessage(Key);
  except
    Result := '';
  end;
end;

{ W14-D1: FmtMessage gets a bracket literal only. A script routine with an "array of String"
  parameter that handed it on raised "Type Mismatch" on the first S02 item. }
function FM1(Key, A: String): String;
begin
  Result := FmtMessage(CM(Key), [A]);
end;

function FM2(Key, A, B: String): String;
begin
  Result := FmtMessage(CM(Key), [A, B]);
end;

function FM3(Key, A, B, C: String): String;
begin
  Result := FmtMessage(CM(Key), [A, B, C]);
end;

function HasMessage(Key: String): Boolean;
begin
  Result := CM(Key) <> '';
end;

function NewOut(Name: String): String;
begin
  OutSeq := OutSeq + 1;
  Result := ExpandConstant('{tmp}\') + Name + '-' + IntToStr(OutSeq) + '.json';
end;

{ Runs a short helper action and waits; returns its result file. }
function NewOutRun(Action, Extra: String): String;
begin
  Result := NewOut(Action);
  RunHelper(Action, RunId, Result, Extra);
end;

function ReadText(FileName: String): String;
var
  Raw: AnsiString;
begin
  Result := '';
  if LoadStringFromFile(FileName, Raw) then
    Result := Utf8Decode(Raw);
end;

{ The value of "Key":"..." at or after From (1-based), with JSON escapes undone; '' if absent. }
function JsonValueFrom(Text, Key: String; From: Integer): String;
var
  Rest, Hex: String;
  Start, I: Integer;
  C: String;
begin
  Result := '';
  Rest := Copy(Text, From, Length(Text));
  Start := Pos('"' + Key + '":"', Rest);
  if Start = 0 then
    Exit;
  I := Start + Length(Key) + 4;
  while I <= Length(Rest) do
  begin
    C := Copy(Rest, I, 1);
    if C = '"' then
      Exit;
    if C = '\' then
    begin
      I := I + 1;
      C := Copy(Rest, I, 1);
      if C = 'n' then Result := Result + #10
      else if C = 'r' then Result := Result + #13
      else if C = 't' then Result := Result + #9
      else if C = 'u' then
      begin
        Hex := Copy(Rest, I + 1, 4);
        Result := Result + Chr(StrToIntDef('$' + Hex, 63));
        I := I + 4;
      end
      else Result := Result + C;
    end
    else
      Result := Result + C;
    I := I + 1;
  end;
end;

function JsonValue(Text, Key: String): String;
begin
  Result := JsonValueFrom(Text, Key, 1);
end;

{ A number or a literal (true, false) after "Key": ; '' if absent. }
function JsonLiteral(Text, Key: String): String;
var
  Start, I: Integer;
begin
  Result := '';
  Start := Pos('"' + Key + '":', Text);
  if Start = 0 then
    Exit;
  I := Start + Length(Key) + 3;
  while (I <= Length(Text)) and (Pos(Copy(Text, I, 1), ',}] ') = 0) do
  begin
    Result := Result + Copy(Text, I, 1);
    I := I + 1;
  end;
end;

{ The first string of the list "Key":["...", ...]; '' if absent or empty. }
function JsonFirstItem(Text, Key: String): String;
var
  Start: Integer;
begin
  Result := '';
  Start := Pos('"' + Key + '":["', Text);
  if Start = 0 then
    Exit;
  Result := JsonValueFrom('"x":"' + Copy(Text, Start + Length(Key) + 5, Length(Text)), 'x', 1);
end;

{ A JSON string with every character outside printable ASCII as \uXXXX, so the frame is ASCII. }
function JsonText(S: String): String;
var
  I, Code: Integer;
begin
  Result := '"';
  for I := 1 to Length(S) do
  begin
    Code := Ord(S[I]);
    if (S[I] = '"') or (S[I] = '\') then
      Result := Result + '\' + S[I]
    else if (Code < 32) or (Code > 126) then
      Result := Result + '\u' + Lowercase(Format('%.4x', [Code]))
    else
      Result := Result + S[I];
  end;
  Result := Result + '"';
end;

{ Bytes from the system's random source, as lower-case hex. }
function RandomHex(Bytes: Integer): String;
var
  Buffer: AnsiString;
  I: Integer;
begin
  Result := '';
  SetLength(Buffer, Bytes);
  if not RtlGenRandom(Buffer, Bytes) then
    RaiseException('random_failed');
  for I := 1 to Bytes do
    Result := Result + Lowercase(Format('%.2x', [Ord(Buffer[I])]));
end;

{ A random GUID (version 4): the request ID and the pipe name (plan 3.2 check 1). }
function NewRequestId: String;
var
  H: String;
begin
  H := RandomHex(16);
  Result := Copy(H, 1, 8) + '-' + Copy(H, 9, 4) + '-4' + Copy(H, 14, 3) + '-8' + Copy(H, 18, 3) + '-' + Copy(H, 21, 12);
end;

function Elapsed(Since: Cardinal): Cardinal;
begin
  Result := GetTickCount - Since;
end;

procedure OpenAsUser(Target, Params: String);
var
  ErrorCode: Integer;
begin
  { Spec 6.1 (W80-6): programs the wizard starts run as the original user, with fixed targets. }
  ShellExecAsOriginalUser('open', Target, Params, '', SW_SHOWNORMAL, ewNoWait, ErrorCode);
end;

function AddressUrl: String;
begin
  Result := 'https://' + HostName + '.local';
end;

{ ------------------------------------------------------------------------------------------- }
{ Layout: each dynamic page has one body panel that is rebuilt for each state.                  }
{ ------------------------------------------------------------------------------------------- }

procedure BeginBody(Index: Integer);
begin
  if Bodies[Index] <> nil then
    Bodies[Index].Free;
  Bodies[Index] := TPanel.Create(WizardForm);
  Bodies[Index].Parent := Pages[Index].Surface;
  Bodies[Index].BevelOuter := bvNone;
  Bodies[Index].ParentBackground := True;
  Bodies[Index].SetBounds(0, 0, Pages[Index].SurfaceWidth, Pages[Index].SurfaceHeight);
  Cur := Bodies[Index];
  CurY := 0;
end;

function AddTextTo(Parent: TWinControl; Top: Integer; S: String; Bold: Boolean): TNewStaticText;
begin
  Result := TNewStaticText.Create(WizardForm);
  Result.Parent := Parent;
  Result.AutoSize := False;
  Result.WordWrap := True;
  Result.ShowAccelChar := False;
  Result.SetBounds(0, Top, Parent.Width, ScaleY(15));
  Result.Caption := S;
  if Bold then
    Result.Font.Style := [fsBold];
  WizardForm.AdjustLabelHeight(Result);
end;

function AddText(S: String; Bold: Boolean): TNewStaticText;
begin
  Result := AddTextTo(Cur, CurY, S, Bold);
  CurY := CurY + Result.Height + ScaleY(6);
end;

{ A sentence that takes focus when it appears (spec 9 item 2): a read-only, borderless memo that
  wraps (design B6). Its height comes from a bold static text of the same width. }
function AddVerdict(S: String): TNewMemo;
var
  Measure: TNewStaticText;
  Height: Integer;
begin
  Measure := AddTextTo(Cur, CurY, S, True);
  Height := Measure.Height + ScaleY(4);
  Measure.Free;
  Result := TNewMemo.Create(WizardForm);
  Result.Parent := Cur;
  Result.ReadOnly := True;
  Result.BorderStyle := bsNone;
  Result.WordWrap := True;
  Result.ScrollBars := ssNone;
  Result.ParentBackground := True;
  Result.Color := WizardForm.Color;
  Result.Font.Style := [fsBold];
  Result.SetBounds(0, CurY, Cur.Width, Height);
  Result.Text := S;
  CurY := CurY + Result.Height + ScaleY(6);
end;

function AddButtonAt(Caption: String; Left, Tag: Integer): TNewButton;
begin
  Result := TNewButton.Create(WizardForm);
  Result.Parent := Cur;
  Result.Caption := Caption;
  Result.Tag := Tag;
  Result.SetBounds(Left, CurY, WizardForm.CalculateButtonWidth([Caption]), WizardForm.NextButton.Height);
end;

function AddLink(Caption: String; Tag: Integer): TNewLinkLabel;
begin
  Result := TNewLinkLabel.Create(WizardForm);
  Result.Parent := Cur;
  Result.Caption := '<a href="' + IntToStr(Tag) + '">' + Caption + '</a>';
  Result.Tag := Tag;
  Result.Left := 0;
  Result.Top := CurY;
  Result.Width := Cur.Width;
  Result.AdjustHeight;
  CurY := CurY + Result.Height + ScaleY(6);
end;

function AddMarquee: TNewProgressBar;
begin
  Result := TNewProgressBar.Create(WizardForm);
  Result.Parent := Cur;
  Result.Style := npbstMarquee;
  Result.SetBounds(0, CurY, Cur.Width, ScaleY(14));
  CurY := CurY + Result.Height + ScaleY(8);
end;

{ The stage line under the header on S02 to S12 (spec 6.1). }
procedure AddStageLine(Stage: Integer);
var
  Labels: array of TNewStaticText;
  I, Left: Integer;
begin
  SetArrayLength(Labels, 3);
  Left := 0;
  for I := 1 to 3 do
  begin
    Labels[I - 1] := TNewStaticText.Create(WizardForm);
    Labels[I - 1].Parent := Cur;
    Labels[I - 1].ShowAccelChar := False;
    Labels[I - 1].Caption := CM('stage_' + IntToStr(I));
    if I < 3 then
      Labels[I - 1].Caption := Labels[I - 1].Caption + '  ' + CM('stage_sep') + '  ';
    if I = Stage then
      Labels[I - 1].Font.Style := [fsBold];
    Labels[I - 1].Left := Left;
    Labels[I - 1].Top := CurY;
    Left := Left + Labels[I - 1].Width;
  end;
  CurY := CurY + Labels[0].Height + ScaleY(10);
end;

function ConfirmBox(Instruction, Text: String; Yes, No: String): Boolean;
begin
  ModalOpen := True;
  try
    Result := TaskDialogMsgBox(Instruction, Text, mbConfirmation, MB_YESNO, [Yes, No], 0) = IDYES;
  finally
    ModalOpen := False;
  end;
end;

procedure InfoForm(Title, Text: String);
var
  Form: TSetupForm;
  Memo: TNewMemo;
  Button: TNewButton;
begin
  Form := CreateCustomForm(ScaleX(460), ScaleY(300), False, False);
  try
    Form.Caption := Title;
    Memo := TNewMemo.Create(Form);
    Memo.Parent := Form;
    Memo.ReadOnly := True;
    Memo.WordWrap := True;
    Memo.ScrollBars := ssVertical;
    Memo.SetBounds(ScaleX(10), ScaleY(10), Form.ClientWidth - ScaleX(20), Form.ClientHeight - ScaleY(56));
    Memo.Text := Text;
    Button := TNewButton.Create(Form);
    Button.Parent := Form;
    Button.Caption := CM('btn_close');
    Button.ModalResult := mrOk;
    Button.Cancel := True;
    Button.Default := True;
    Button.SetBounds(Form.ClientWidth - ScaleX(10) - ScaleX(90), Form.ClientHeight - ScaleY(36), ScaleX(90), ScaleY(26));
    ModalOpen := True;
    Form.ShowModal;
  finally
    ModalOpen := False;
    Form.Free;
  end;
end;

{ ------------------------------------------------------------------------------------------- }
{ The secret channel, the wizard's side (plan 3.2 rule 3, checks 1 and 4)                       }
{ ------------------------------------------------------------------------------------------- }

procedure ClosePipe;
begin
  if (PipeHandle <> 0) and (PipeHandle <> INVALID_HANDLE) then
    CloseHandle(PipeHandle);
  PipeHandle := 0;
  PipeConnected := False;
  PipeFrame := '';
end;

{ One pipe for one request: a random name, the first and only instance, remote clients refused,
  owner Administrators, access for Administrators and the service account only. }
function OpenPipe(RequestId: String): Boolean;
var
  Attributes: TSecurityAttributes;
  Descriptor: Longword;
begin
  Result := False;
  ClosePipe;
  PipeOutput := '';
  if ServiceSid = '' then
    Exit;
  Descriptor := 0;
  if not ConvertSddl('O:BAD:P(A;;GRGW;;;BA)(A;;GRGW;;;' + ServiceSid + ')', 1, Descriptor, 0) then
    Exit;
  Attributes.nLength := 12;
  Attributes.lpSecurityDescriptor := Descriptor;
  Attributes.bInheritHandle := 0;
  PipeHandle := CreateNamedPipe('\\.\pipe\SlateOps-' + RequestId, PIPE_ACCESS_DUPLEX or FILE_FLAG_FIRST_PIPE_INSTANCE,
    PIPE_NOWAIT or PIPE_REJECT_REMOTE_CLIENTS, 1, 65536, 65536, 0, Attributes);
  LocalFree(Descriptor);
  Result := (PipeHandle <> 0) and (PipeHandle <> INVALID_HANDLE);
  if not Result then
    PipeHandle := 0;
end;

function Frame(Text: String): AnsiString;
begin
  Result := AnsiString(Format('%.8d', [Length(Text)]) + Text);
end;

{ One step of the pipe: connect, send the input frame, read the output. Never blocks. }
procedure PollPipe;
var
  Done, Available: Longword;
  Chunk: AnsiString;
  Error: Integer;
begin
  if PipeHandle = 0 then
    Exit;
  if not PipeConnected then
  begin
    if ConnectNamedPipe(PipeHandle, 0) then
      PipeConnected := True
    else
    begin
      Error := DLLGetLastError;
      if Error = ERROR_PIPE_CONNECTED then
        PipeConnected := True
      else if Error <> ERROR_PIPE_LISTENING then
      begin
        Log('Secret channel: the client closed before the transfer (' + IntToStr(Error) + ').');
        ClosePipe;
        Exit;
      end;
    end;
  end;
  if not PipeConnected then
    Exit;
  if Length(PipeFrame) > 0 then
  begin
    Done := 0;
    if WriteFile(PipeHandle, PipeFrame, Length(PipeFrame), Done, 0) and (Done > 0) then
      PipeFrame := Copy(PipeFrame, Done + 1, Length(PipeFrame));
  end;
  if not PipeExpectOutput then
    Exit;
  Available := 0;
  if PeekNamedPipe(PipeHandle, 0, 0, 0, Available, 0) then
  begin
    if Available > 0 then
    begin
      SetLength(Chunk, Available);
      Done := 0;
      if ReadFile(PipeHandle, Chunk, Available, Done, 0) then
        PipeOutput := PipeOutput + Copy(Chunk, 1, Done);
    end;
  end
  else if DLLGetLastError = ERROR_BROKEN_PIPE then
    PipeExpectOutput := False;
end;

{ The output frame's text once it is complete, else ''. }
function PipeResult: String;
var
  Size: Integer;
begin
  Result := '';
  if Length(PipeOutput) < 8 then
    Exit;
  Size := StrToIntDef(Copy(PipeOutput, 1, 8), -1);
  if (Size > 0) and (Length(PipeOutput) >= 8 + Size) then
    Result := Copy(PipeOutput, 9, Size);
end;

{ ------------------------------------------------------------------------------------------- }
{ The Exec job runner                                                                           }
{ ------------------------------------------------------------------------------------------- }

function ExecResultFile: String;
begin
  Result := ExpandConstant('{commonappdata}\SlateOps\svc-out\exec-result.json');
end;

{ Starts one allow-listed job. InputJson goes through the pipe when PipeIn, else into the
  request's input file. PipeOut makes the job's output come back through the pipe. }
function StartJob(Name, InputJson, Purpose: String; PipeIn, PipeOut: Boolean; LimitMinutes: Integer): Boolean;
var
  InFile, Extra: String;
begin
  Result := False;
  JobName := Name;
  JobPurpose := Purpose;
  JobCode := '';
  JobText := '';
  JobRaw := '';
  JobExit := -1;
  JobRequestId := NewRequestId;
  JobLimitMs := LimitMinutes * 60000;
  Extra := '-Job ' + Name + ' -RequestId ' + JobRequestId;
  PipeExpectOutput := PipeOut;
  JobPipeOut := PipeOut;
  if PipeIn or PipeOut then
  begin
    if not OpenPipe(JobRequestId) then
    begin
      JobState := JOB_DONE;
      JobCode := 'pipe_unavailable';
      Exit;
    end;
    if PipeIn then
      PipeFrame := Frame(InputJson);
  end;
  if not PipeIn then
  begin
    InFile := ExpandConstant('{tmp}\job-input.json');
    SaveStringToFile(InFile, AnsiString(InputJson), False);
    Extra := Extra + ' -InputFile ' + AddQuotes(InFile);
  end;
  JobOut := NewOut('job');
  JobResultOut := '';
  JobState := JOB_SUBMIT;
  JobStartedAt := GetTickCount;
  Result := StartHelper('job', RunId, JobOut, Extra);
  if not Result then
  begin
    JobState := JOB_DONE;
    JobCode := 'helper_failed';
    ClosePipe;
  end;
end;

{ The code of a job that gave no result in its time limit: the task's last result, read once;
  a sign-in failure of the account is service_logon_failed (plan 10.7, spec 7.5). }
function TaskTimeoutCode: String;
var
  OutFile: String;
begin
  OutFile := NewOut('job-result');
  RunHelper('job-result', RunId, OutFile, '-RequestId ' + JobRequestId);
  if Pos('"logon_failed":true', ReadText(OutFile)) > 0 then
    Result := 'service_logon_failed'
  else
    Result := 'job_timeout';
end;

{ One step of the runner, from the timer. Done when JobState = JOB_DONE. }
procedure PollJob;
var
  Code, Text: String;
begin
  if (JobState = JOB_IDLE) or (JobState = JOB_DONE) then
    Exit;
  PollPipe;
  if JobState = JOB_SUBMIT then
  begin
    Code := ReadResultCode(JobOut);
    if (Code = '') and (Elapsed(JobStartedAt) > SUBMIT_LIMIT_MS) then
      Code := 'helper_timeout';
    if Code = '' then
      Exit;
    if Code <> 'started' then
    begin
      JobState := JOB_DONE;
      JobCode := Code;
      ClosePipe;
      Exit;
    end;
    JobState := JOB_WAIT;
  end;
  if JobState = JOB_WAIT then
  begin
    if JobResultOut = '' then
    begin
      { Cheap check first: the result file names this request (it holds no secret). }
      Text := ReadText(ExecResultFile);
      { W13b P2-5: no verdict at a limit on a running update either; the engine has its own. }
      if (Pos('"request_id":"' + JobRequestId + '"', Text) = 0) and (JobPurpose <> 'install') and (JobPurpose <> 'update') and (Elapsed(JobStartedAt) > JobLimitMs) then
      begin
        { W8 correction 5: at the limit, the task's last result once (spec 7.5). }
        JobCode := TaskTimeoutCode;
        JobState := JOB_DONE;
        ClosePipe;
        Exit;
      end;
      if Pos('"request_id":"' + JobRequestId + '"', Text) = 0 then
        Exit;
      JobResultOut := NewOut('job-result');
      StartHelper('job-result', RunId, JobResultOut, '-RequestId ' + JobRequestId);
      Exit;
    end;
    Code := ReadResultCode(JobResultOut);
    if Code = '' then
      Exit;
    if Code <> 'done' then
    begin
      JobResultOut := '';
      Exit;
    end;
    Text := ReadText(JobResultOut);
    JobRaw := Text;
    JobCode := JsonValueFrom(Text, 'code', Pos('"exec":', Text));
    JobExit := StrToIntDef(JsonLiteral(Copy(Text, Pos('"exec":', Text), Length(Text)), 'exit_code'), -1);
    if JobPipeOut then
    begin
      { The engine wrote its output frame before the result file. }
      PollPipe;
      JobText := PipeResult;
      PipeOutput := '';
    end;
    ClosePipe;
    JobState := JOB_DONE;
  end;
end;

function JobRunning: Boolean;
begin
  Result := (JobState = JOB_SUBMIT) or (JobState = JOB_WAIT);
end;

function JobSlow: Boolean;
begin
  Result := JobRunning and (Elapsed(JobStartedAt) > JobLimitMs);
end;

{ A short job without the pipe, waited for here (Cancel's discard, Save report's log-bundle). }
function RunJobBlocking(Name, InputJson, ARunId: String; LimitSeconds: Integer): String;
var
  InFile, OutFile, Id, Text: String;
  Start: Cardinal;
begin
  Result := 'job_timeout';
  Id := NewRequestId;
  InFile := ExpandConstant('{tmp}\job-input.json');
  SaveStringToFile(InFile, AnsiString(InputJson), False);
  OutFile := NewOut('job');
  RunHelper('job', ARunId, OutFile, '-Job ' + Name + ' -RequestId ' + Id + ' -InputFile ' + AddQuotes(InFile));
  if ReadResultCode(OutFile) <> 'started' then
  begin
    Result := ReadResultCode(OutFile);
    Exit;
  end;
  Start := GetTickCount;
  while Elapsed(Start) < Cardinal(LimitSeconds * 1000) do
  begin
    Sleep(1000);
    if Pos('"request_id":"' + Id + '"', ReadText(ExecResultFile)) > 0 then
    begin
      OutFile := NewOut('job-result');
      RunHelper('job-result', ARunId, OutFile, '-RequestId ' + Id);
      Text := ReadText(OutFile);
      Result := JsonValueFrom(Text, 'code', Pos('"exec":', Text));
      Exit;
    end;
  end;
end;

{ A pipe job waited for here (W8 correction 2): the smtp-test discard goes through the pipe like
  every smtp-test, so Exec's input_on_disk refusal stays. Returns the job's code. }
function RunPipeJobBlocking(Name, InputJson: String; LimitSeconds: Integer): String;
var
  Start: Cardinal;
begin
  Start := GetTickCount;
  while JobRunning and (Elapsed(Start) < 120000) do
  begin
    Sleep(500);
    PollJob;
  end;
  if JobRunning then
  begin
    Result := 'exec_busy';
    Exit;
  end;
  StartJob(Name, InputJson, 'blocking', True, False, (LimitSeconds div 60) + 1);
  Start := GetTickCount;
  while JobRunning and (Elapsed(Start) < Cardinal(LimitSeconds * 1000)) do
  begin
    Sleep(500);
    PollJob;
  end;
  if JobRunning then
    Result := 'job_timeout'
  else
    Result := JobCode;
  JobState := JOB_IDLE;
  ClosePipe;
end;

{ "Keep it and continue later" (spec 4.5) and D2: the staged email settings go through the pipe
  (smtp-test discard); the mark email_discarded is saved only when the engine confirms it. The
  install_started stage is kept only once the install job ran (correction 6). }
procedure SaveContinueLater;
var
  OutFile, Extra: String;
  Discarded: Boolean;
begin
  Discarded := RunPipeJobBlocking('smtp-test', '{"run_id":"' + RunId + '","mode":"discard"}', 120) = 'smtp_discarded';
  OutFile := NewOut('save');
  { W9 review item 6 (D2): the S09 resume of a started install keeps install_started too. }
  if (InstallStep >= 2) or (EntryNext = 'S12') or (EntryNext = 'S09') then
  begin
    Extra := '-Stage install_started';
    if Discarded then
      Extra := Extra + ' -EmailDiscarded';
  end
  else
  begin
    Extra := '-Stage continue_later';
    if BgDone then
      Extra := Extra + ' -BackgroundDone';
  end;
  if KeptMode then
    Extra := Extra + ' -KeptMark';
  RunHelper('save-progress', RunId, OutFile, Extra);
end;

{ ------------------------------------------------------------------------------------------- }
{ Save report (plan 10.6; DEC-0033)                                                             }
{ ------------------------------------------------------------------------------------------- }

{ Plan 10.6 item 3: the wizard removes the email password that it holds from the staged files. }
procedure DropFilesWithPassword(Staging: String);
var
  Find: TFindRec;
  Content: AnsiString;
  Password: String;
begin
  Password := '';
  if MailPassword <> nil then
    Password := MailPassword.Text;
  if Length(Password) < 4 then
    Exit;
  if FindFirst(Staging + '\*', Find) then
  try
    repeat
      if (Find.Attributes and FILE_ATTRIBUTE_DIRECTORY) = 0 then
        if LoadStringFromFile(Staging + '\' + Find.Name, Content) then
          if Pos(AnsiString(Password), Content) > 0 then
          begin
            DeleteFile(Staging + '\' + Find.Name);
            SaveStringToFile(Staging + '\report.txt', AnsiString('  ' + Find.Name + ' (holds a secret that cannot be removed)' + #13#10), True);
          end;
    until not FindNext(Find);
  finally
    FindClose(Find);
  end;
end;

procedure SaveReport(Sender: TObject);
var
  ReportRun, OutFile, InnoCopy: String;
begin
  { W8 correction 3: Save report works while a job runs; only the Linux part waits for Exec,
    so it is left out then and report.txt says the Linux part was not reachable. }
  ReportRun := NewRunId('report');
  ReportLine := CM('report_saving');
  if WizardReady then
  begin
    WizardForm.BeveledLabel.Caption := ' ' + ReportLine;
    WizardForm.Refresh;
  end;
  { The Linux part, when the server part answers (plan 10.6 item 1). }
  if (ServiceSid <> '') and not JobRunning then
    RunJobBlocking('log-bundle', '{"run_id":"' + ReportRun + '"}', ReportRun, 120);
  InnoCopy := ExpandConstant('{tmp}\setup-program.log');
  if ExpandConstant('{log}') <> '' then
    CopyFile(ExpandConstant('{log}'), InnoCopy, False);
  OutFile := NewOut('report');
  RunHelper('report-collect', ReportRun, OutFile, '-InputFile ' + AddQuotes(InnoCopy));
  DropFilesWithPassword(ExpandConstant('{tmp}\report-') + ReportRun);
  OutFile := NewOut('report');
  RunHelper('report-zip', ReportRun, OutFile, '');
  ReportPath := JsonValue(ReadText(OutFile), 'path');
  if ReportPath <> '' then
    ReportLine := FM1('report_saved', ExtractFileName(ReportPath))
  else
    ReportLine := '';
  if not WizardReady then
    Exit;
  WizardForm.BeveledLabel.Caption := '';
  { Design B2: the result line also shows in the modal S13 form. }
  if FailureStatus <> nil then
    FailureStatus.Caption := ReportLine;
  RenderPage(-1);
end;

procedure ShowReportClick(Sender: TObject; const Link: String; LinkType: TSysLinkType);
begin
  if ReportPath <> '' then
    OpenAsUser(ExpandConstant('{win}\explorer.exe'), '/select,' + AddQuotes(ReportPath));
end;

{ The Save report button and, once saved, the result line with "Show in folder". }
procedure AddReportControls;
var
  Button: TNewButton;
  Link: TNewLinkLabel;
begin
  Button := AddButtonAt(CM('btn_save_report'), 0, 0);
  Button.OnClick := @SaveReport;
  CurY := CurY + Button.Height + ScaleY(6);
  if ReportLine <> '' then
  begin
    AddText(ReportLine, False);
    if ReportPath <> '' then
    begin
      Link := AddLink(CM('btn_show_in_folder'), 0);
      Link.OnLinkClick := @ShowReportClick;
    end;
  end;
end;

{ ------------------------------------------------------------------------------------------- }
{ S13: one failure layout, shown in place (spec S13)                                            }
{ ------------------------------------------------------------------------------------------- }

procedure AddFailure(Stage, WhatHappened: String; TryAgain: Boolean);
var
  Verdict: TNewMemo;
begin
  WizardForm.PageNameLabel.Caption := CM('s13_title');
  WizardForm.PageDescriptionLabel.Caption := Stage;
  Verdict := AddVerdict(WhatHappened);
  if TryAgain then
    AddText(CM('s13_what'), False);
  AddReportControls;
  if TryAgain then
  begin
    WizardForm.NextButton.Caption := CM('btn_try_again');
    WizardForm.NextButton.Enabled := True;
  end
  else
    WizardForm.NextButton.Enabled := False;
  if Verdict.CanFocus then
    WizardForm.ActiveControl := Verdict;
end;

{ A failure of background work, in a modal form with the S13 layout (spec 4.1). Returns True
  for Try again. }
function FailureForm(Stage, WhatHappened: String; TryAgain: Boolean): Boolean;
var
  Form: TSetupForm;
  Text: TNewStaticText;
  Again, Report, CloseButton: TNewButton;
begin
  Form := CreateCustomForm(ScaleX(440), ScaleY(220), False, False);
  try
    Form.Caption := CM('s13_title');
    Text := AddTextTo(Form, ScaleY(10), Stage, True);
    Text.Left := ScaleX(10);
    Text.Width := Form.ClientWidth - ScaleX(20);
    Text := AddTextTo(Form, ScaleY(36), WhatHappened, False);
    Text.Left := ScaleX(10);
    Text.Width := Form.ClientWidth - ScaleX(20);
    if TryAgain then
    begin
      Text := AddTextTo(Form, ScaleY(80), CM('s13_what'), False);
      Text.Left := ScaleX(10);
      Text.Width := Form.ClientWidth - ScaleX(20);
    end;
    { Design B2: SaveReport writes its result line here. }
    FailureStatus := AddTextTo(Form, ScaleY(140), '', False);
    FailureStatus.Left := ScaleX(10);
    FailureStatus.Width := Form.ClientWidth - ScaleX(20);
    Again := TNewButton.Create(Form);
    Again.Parent := Form;
    Again.Caption := CM('btn_try_again');
    Again.ModalResult := mrRetry;
    Again.Enabled := TryAgain;
    Again.Default := TryAgain;
    Again.SetBounds(ScaleX(10), Form.ClientHeight - ScaleY(36), ScaleX(110), ScaleY(26));
    Report := TNewButton.Create(Form);
    Report.Parent := Form;
    Report.Caption := CM('btn_save_report');
    Report.OnClick := @SaveReport;
    Report.SetBounds(ScaleX(130), Form.ClientHeight - ScaleY(36), ScaleX(120), ScaleY(26));
    CloseButton := TNewButton.Create(Form);
    CloseButton.Parent := Form;
    CloseButton.Caption := CM('btn_close');
    CloseButton.ModalResult := mrCancel;
    CloseButton.Cancel := True;
    CloseButton.SetBounds(Form.ClientWidth - ScaleX(100), Form.ClientHeight - ScaleY(36), ScaleX(90), ScaleY(26));
    ModalOpen := True;
    Result := Form.ShowModal = mrRetry;
  finally
    ModalOpen := False;
    FailureStatus := nil;
    Form.Free;
  end;
end;

{ ------------------------------------------------------------------------------------------- }
{ The PC check (S02, S03, S06 and the S11 recheck; spec 5)                                      }
{ ------------------------------------------------------------------------------------------- }

procedure ParseCheck(Text: String);
var
  Rest: String;
  Start, Next, Count: Integer;
  Item: TCheckItem;
begin
  SetArrayLength(Items, 0);
  CheckVerdict := JsonValue(Text, 'code');
  RestartNeeded := Pos('"restart_needed":true', Text) > 0;
  Rest := Text;
  Count := 0;
  Start := Pos('{"id":"C', Rest);
  while Start > 0 do
  begin
    Rest := Copy(Rest, Start + 1, Length(Rest));
    Next := Pos('{"id":"C', Rest);
    if Next > 0 then
      Item.Raw := Copy(Rest, 1, Next - 1)
    else
      Item.Raw := Rest;
    Item.Id := JsonValue('{' + Item.Raw, 'id');
    Item.Cls := JsonValue('{' + Item.Raw, 'class');
    Item.Code := JsonValue('{' + Item.Raw, 'code');
    SetArrayLength(Items, Count + 1);
    Items[Count] := Item;
    Count := Count + 1;
    Start := Next;
  end;
  NeedPrepare := False;
  for Count := 0 to GetArrayLength(Items) - 1 do
    if (Items[Count].Id = 'C26') and (Items[Count].Cls = 'auto') then
      NeedPrepare := True;
end;

function ItemName(Item: TCheckItem): String;
begin
  Result := CM(Lowercase(Item.Id) + '_name');
  if Result = '' then
    Result := Item.Id;
end;

function ItemMessage(Item: TCheckItem): String;
var
  Key, V: String;
begin
  Key := Lowercase(Item.Id) + '_' + Item.Code;
  if not HasMessage(Key) then
  begin
    Result := FM1('cannot_read', Lowercase(ItemName(Item)));
    Exit;
  end;
  V := '';
  if Item.Id = 'C01' then V := JsonValue(Item.Raw, 'display_version')
  else if Item.Id = 'C07' then V := JsonLiteral(Item.Raw, 'free_gb')
  else if Item.Id = 'C13' then V := JsonLiteral(Item.Raw, 'offset_minutes')
  else if Item.Id = 'C14' then V := JsonFirstItem(Item.Raw, 'programs')
  else if (Item.Id = 'C15') or (Item.Id = 'C16') or (Item.Id = 'C30') then V := JsonValue(Item.Raw, 'address')
  else if Item.Id = 'C20' then V := JsonFirstItem(Item.Raw, 'products')
  else if Item.Id = 'C24' then V := JsonValue(Item.Raw, 'letter');
  if Item.Id = 'C05' then
    Result := FM2(Key, JsonLiteral(Item.Raw, 'installed_gb'), JsonLiteral(Item.Raw, 'usable_gb'))
  else if Item.Id = 'C07' then
    Result := FM2(Key, V, JsonValue(Item.Raw, 'letter'))
  else
    Result := FM1(Key, V);
end;

function ItemWord(Item: TCheckItem): String;
begin
  if Item.Cls = 'stop' then Result := CM('word_stop')
  else if Item.Cls = 'fix' then Result := CM('word_fix')
  else if Item.Cls = 'advice' then Result := CM('word_advice')
  else Result := CM('word_ready');
end;

procedure StartCheck(Action: String; ForPage: String);
begin
  CheckOut := NewOut('check');
  CheckRunning := True;
  CheckDone := False;
  CheckFor := ForPage;
  CheckStartedAt := GetTickCount;
  if CheckVerdict = 'helper_timeout' then
    CheckVerdict := '';
  StartHelper(Action, RunId, CheckOut, '');
end;

{ Design B1: S06 and S11 run the recheck again, never the full check (the server part exists,
  so the full check would stop on C29). }
procedure CheckAgainFor;
begin
  if (CheckFor = 'S06') or (CheckFor = 'S11') then
    StartCheck('recheck', CheckFor)
  else
    StartCheck('check', 'S02');
end;

function CountClass(Cls: String): Integer;
var
  I: Integer;
begin
  Result := 0;
  for I := 0 to GetArrayLength(Items) - 1 do
    if Items[I].Cls = Cls then
      Result := Result + 1;
end;

{ Fix actions; a button's Tag is item index * 16 + action. }
procedure FixDone;
begin
  FixRunning := False;
  CheckAgainFor;
end;

procedure StartFix(Action, Extra: String);
begin
  FixRunning := True;
  FixAction := Action;
  FixOut := NewOut('fix');
  FixStartedAt := GetTickCount;
  StartHelper(Action, RunId, FixOut, Extra);
end;

function RestartResumeText(Code: String; Prefix: String): String;
begin
  Result := '';
  if Code = 'resume_other_user' then
    Result := FM1(Prefix + '_other_user', ExpandConstant('{srcexe}'))
  else if Code = 'resume_path_unsafe' then
    Result := FM1(Prefix + '_unsafe', ExpandConstant('{srcexe}'));
end;

{ C08 "Restart now" and C04 "Restart to startup settings": save the progress (with the resume
  entries), then restart (spec 5.3, F4a). }
procedure CheckRestart(Firmware: Boolean; Index: Integer);
var
  OutFile, Code, Text, Extra, Title: String;
begin
  Code := '';
  if not DataPrepared then
  begin
    OutFile := NewOut('save');
    RunHelper('save-progress', RunId, OutFile, '-Stage check_restart -SetupPath ' + AddQuotes(ExpandConstant('{srcexe}')));
    Code := ReadResultCode(OutFile);
  end;
  { D1: the firmware restart has its own title, text and, when BitLocker can ask, the caution. }
  if Firmware then
  begin
    Title := CM('c04_btn_firmware');
    Text := CM('c04_restart_confirm');
    if (Index >= 0) and (JsonLiteral(Items[Index].Raw, 'bitlocker_caution') = 'true') then
      Text := CM('c04_how_caution') + #13#10#13#10 + Text;
  end
  else
  begin
    Title := CM('c08_btn');
    Text := CM('s02_restart_confirm');
  end;
  if RestartResumeText(Code, 's02_restart') <> '' then
    Text := Text + #13#10#13#10 + RestartResumeText(Code, 's02_restart');
  if not ConfirmBox(Title, Text, Title, CM('btn_go_back')) then
    Exit;
  { D2: after S07 the check-restart stage is never saved. A started install keeps its stage;
    else the staged email settings go and "continue later" is saved (spec 4.1). }
  if DataPrepared and (InstallStep < 2) and (EntryNext <> 'S12') and (EntryNext <> 'S14') then
    SaveContinueLater;
  Extra := '';
  if Firmware then
    Extra := '-Firmware';
  OutFile := NewOut('restart');
  RunHelper('restart', RunId, OutFile, Extra);
  if ReadResultCode(OutFile) = 'restarting' then
  begin
    ForceClose := True;
    WizardForm.Close;
  end;
end;

procedure ShowFirmwareHelp(Index: Integer);
var
  Text: String;
begin
  Text := '';
  if JsonLiteral(Items[Index].Raw, 'bitlocker_caution') = 'true' then
    Text := CM('c04_how_caution') + #13#10#13#10;
  Text := Text + FM1('c04_how_text', JsonValue(Items[Index].Raw, 'maker'));
  InfoForm(CM('c04_how_title'), Text);
end;

procedure RemoveKitParts;
var
  Form: TSetupForm;
  Text: TNewStaticText;
  Go, Stop: TNewButton;
  Answer: Integer;
begin
  Form := CreateCustomForm(ScaleX(440), ScaleY(200), False, False);
  try
    Form.Caption := CM('c29_form_title');
    Text := AddTextTo(Form, ScaleY(10), CM('c29_form_text'), False);
    Text.Left := ScaleX(10);
    Text.Width := Form.ClientWidth - ScaleX(20);
    WizardForm.AdjustLabelHeight(Text);
    Go := TNewButton.Create(Form);
    Go.Parent := Form;
    Go.Caption := CM('btn_continue');
    Go.ModalResult := mrOk;
    Go.SetBounds(Form.ClientWidth - ScaleX(210), Form.ClientHeight - ScaleY(36), ScaleX(95), ScaleY(26));
    Stop := TNewButton.Create(Form);
    Stop.Parent := Form;
    Stop.Caption := CM('btn_cancel');
    Stop.ModalResult := mrCancel;
    Stop.Cancel := True;
    Stop.Default := True;
    Stop.SetBounds(Form.ClientWidth - ScaleX(105), Form.ClientHeight - ScaleY(36), ScaleX(95), ScaleY(26));
    ModalOpen := True;
    Answer := Form.ShowModal;
  finally
    ModalOpen := False;
    Form.Free;
  end;
  if Answer = mrOk then
    StartFix('remove-kit', '');
end;

procedure ItemButtonClick(Sender: TObject);
var
  Index, Action: Integer;
  Id: String;
begin
  Index := TNewButton(Sender).Tag div 16;
  Action := TNewButton(Sender).Tag mod 16;
  Id := Items[Index].Id;
  if Id = 'C01' then OpenAsUser('ms-settings:windowsupdate', '')
  else if (Id = 'C04') and (Action = 0) then ShowFirmwareHelp(Index)
  else if (Id = 'C04') and (Action = 1) then CheckRestart(True, Index)
  else if Id = 'C07' then OpenAsUser('ms-settings:storagesense', '')
  else if Id = 'C08' then CheckRestart(False, Index)
  else if Id = 'C10' then
  begin
    if ConfirmBox(CM('c10_btn'), CM('c10_confirm'), CM('c10_btn'), CM('btn_go_back')) then
      StartFix('fix-network-private', '');
  end
  else if Id = 'C13' then OpenAsUser('ms-settings:dateandtime', '')
  else if (Id = 'C15') or (Id = 'C16') or (Id = 'C30') then OpenAsUser('ms-settings:about', '')
  else if Id = 'C17' then StartFix('fix-mdns', '')
  else if Id = 'C18' then SaveReport(nil)
  else if Id = 'C22' then begin LidChosen := not LidChosen; RenderPage(-1); end
  else if Id = 'C24' then OpenAsUser(ExpandConstant('{sys}\control.exe'), '/name Microsoft.BitLockerDriveEncryption')
  { W9 review item 3: the leftovers of an earlier uninstall go with the uninstall's own step. }
  else if (Id = 'C29') and (Items[Index].Code = 'uninstall_leftovers') then
    StartFix('remove-windows', '')
  else if Id = 'C29' then RemoveKitParts;
end;

{ The buttons of one item (spec 5.3 Fix column). }
procedure AddItemButtons(Index: Integer);
var
  Item: TCheckItem;
  Caption, Caption2: String;
  Button: TNewButton;
begin
  Item := Items[Index];
  Caption := '';
  Caption2 := '';
  if (Item.Id = 'C01') and (Item.Code = 'too_old') then Caption := CM('c01_btn')
  else if (Item.Id = 'C04') and (Item.Code = 'off') then
  begin
    Caption := CM('c04_btn_how');
    if JsonLiteral(Item.Raw, 'uefi') = 'true' then
      Caption2 := CM('c04_btn_firmware');
  end
  else if Item.Id = 'C07' then Caption := CM('c07_btn')
  else if Item.Id = 'C08' then Caption := CM('c08_btn')
  else if Item.Id = 'C10' then Caption := CM('c10_btn')
  else if Item.Id = 'C13' then Caption := CM('c13_btn')
  else if (Item.Id = 'C15') or (Item.Id = 'C16') or (Item.Id = 'C30') then Caption := CM('c15_btn')
  else if (Item.Id = 'C17') and (Item.Code = 'rule_off') then Caption := CM('c17_btn')
  else if Item.Id = 'C18' then Caption := CM('btn_save_report')
  else if Item.Id = 'C22' then
  begin
    if LidChosen then Caption := CM('c22_undo') else Caption := CM('c22_btn');
  end
  else if Item.Id = 'C24' then Caption := CM('c24_btn')
  else if (Item.Id = 'C29') and (Item.Code <> 'unknown_parts') then Caption := CM('c29_btn');
  if Caption = '' then
    Exit;
  Button := AddButtonAt(Caption, 0, Index * 16);
  Button.OnClick := @ItemButtonClick;
  Button.Enabled := not FixRunning;
  if Caption2 <> '' then
  begin
    Button := AddButtonAt(Caption2, Button.Width + ScaleX(8), Index * 16 + 1);
    Button.OnClick := @ItemButtonClick;
    Button.Enabled := not FixRunning;
  end;
  CurY := CurY + Button.Height + ScaleY(8);
end;

procedure AddItem(Index: Integer);
begin
  AddText(ItemWord(Items[Index]) + ': ' + ItemName(Items[Index]), True);
  if (Items[Index].Id = 'C22') and LidChosen then
    AddText(CM('c22_chosen'), False)
  else
    AddText(ItemMessage(Items[Index]), False);
  if FixRunning and (((FixAction = 'remove-kit') or (FixAction = 'remove-windows')) and (Items[Index].Id = 'C29')) then
  begin
    AddText(CM('s02_removing'), False);
    AddMarquee;
  end
  else
    AddItemButtons(Index);
  { Design B2: the C18 item's Save report shows its result line here. }
  if (Items[Index].Id = 'C18') and (ReportLine <> '') then
    AddText(ReportLine, False);
end;

procedure ShowAllChecks(Sender: TObject; const Link: String; LinkType: TSysLinkType);
var
  Text: String;
  I: Integer;
begin
  Text := '';
  for I := 0 to GetArrayLength(Items) - 1 do
    if (Items[I].Cls <> 'log') and (Items[I].Cls <> 'auto') then
    begin
      Text := Text + ItemName(Items[I]) + ': ' + ItemWord(Items[I]) + '.';
      if Items[I].Cls <> 'pass' then
        Text := Text + ' ' + ItemMessage(Items[I]);
      Text := Text + #13#10;
    end;
  InfoForm(CM('s02_all_title'), Text);
end;

procedure CheckAgainClick(Sender: TObject);
begin
  CheckAgainFor;
  RenderPage(-1);
end;

{ The items that need the person: Fix first, then Advice; at most four, then "Show N more". }
procedure AddCheckItems(OnlyFix: Boolean);
var
  I, Shown, Passed, More: Integer;
  Link: TNewLinkLabel;
  Button: TNewButton;
begin
  Shown := 0;
  More := 0;
  Passed := 0;
  for I := 0 to GetArrayLength(Items) - 1 do
    if Items[I].Cls = 'pass' then
      Passed := Passed + 1;
  for I := 0 to GetArrayLength(Items) - 1 do
    if Items[I].Cls = 'fix' then
    begin
      if Shown < 4 then begin AddItem(I); Shown := Shown + 1; end else More := More + 1;
    end;
  if not OnlyFix then
  begin
    if CountClass('advice') > 0 then
      AddText(CM('s02_recommended'), True);
    for I := 0 to GetArrayLength(Items) - 1 do
      if Items[I].Cls = 'advice' then
      begin
        if Shown < 4 then begin AddItem(I); Shown := Shown + 1; end else More := More + 1;
      end;
  end;
  if More > 0 then
  begin
    Link := AddLink(FM1('s02_show_more', IntToStr(More)), 0);
    Link.OnLinkClick := @ShowAllChecks;
  end;
  AddText(FM1('s02_passed', IntToStr(Passed)), False);
  Link := AddLink(CM('s02_show_all'), 0);
  Link.OnLinkClick := @ShowAllChecks;
  Button := AddButtonAt(CM('btn_check_again'), 0, 0);
  Button.OnClick := @CheckAgainClick;
  Button.Enabled := not FixRunning;
  CurY := CurY + Button.Height + ScaleY(6);
  { W14-D1: Save report on S02 whatever the result. }
  AddReportControls;
end;

function StopTodo(Item: TCheckItem): String;
begin
  Result := '';
  if (Item.Id = 'C02') and (Item.Code = 'home') then Result := CM('s03_home_todo')
  else if (Item.Id = 'C02') and (Item.Code = 'edition_not_supported') then Result := CM('s03_edition_todo')
  else if Item.Id = 'C05' then Result := CM('s03_memory_todo')
  else if (Item.Id = 'C01') and (Item.Code = 'windows_10') then Result := CM('s03_win10_todo');
end;

procedure RenderCheckBody;
var
  Verdict: TNewMemo;
  I: Integer;
begin
  BeginBody(P_CHECK);
  WizardForm.PageNameLabel.Caption := CM('s02_title');
  WizardForm.PageDescriptionLabel.Caption := CM('s02_subtitle');
  WizardForm.NextButton.Visible := True;
  WizardForm.NextButton.Caption := CM('btn_next');
  WizardForm.CancelButton.Caption := SetupMessage(msgButtonCancel);
  AddStageLine(1);
  if EntryWelcomeBack then
    AddText(CM('s02_welcome_back'), False);
  if StateUnsafe then
  begin
    { Spec 4.1: setup reads nothing from an unsafe state folder; Next stays off. }
    AddVerdict(CM('s01_state_unsafe'));
    AddReportControls;
    WizardForm.NextButton.Enabled := False;
    Exit;
  end;
  if CheckVerdict = 'helper_timeout' then
  begin
    { Correction 5: the check helper never answered (spec 7.5 antivirus row). }
    AddFailure(CM('s02_title'), CM('av_blocked'), True);
    Exit;
  end;
  if CheckRunning or not CheckDone then
  begin
    AddText(CM('s02_checking'), True);
    AddMarquee;
    WizardForm.NextButton.Enabled := False;
    Exit;
  end;
  if CheckVerdict = 'not_suitable' then
  begin
    { S03: the same page in its "not suitable" state (spec S03). }
    WizardForm.PageNameLabel.Caption := CM('s03_title');
    WizardForm.PageDescriptionLabel.Caption := CM('s03_subtitle');
    Verdict := AddVerdict(CM('s03_verdict'));
    for I := 0 to GetArrayLength(Items) - 1 do
      if Items[I].Cls = 'stop' then
      begin
        AddText(ItemName(Items[I]), True);
        AddText(ItemMessage(Items[I]), False);
        if StopTodo(Items[I]) <> '' then
          AddText(CM('s03_what') + ' ' + StopTodo(Items[I]), False);
      end;
    AddText(CM('s03_suitable'), False);
    AddText(CM('s03_wrong'), False);
    AddReportControls;
    WizardForm.NextButton.Visible := False;
    WizardForm.CancelButton.Caption := CM('btn_close');
  end
  else if CheckVerdict = 'needs_fixes' then
  begin
    if CountClass('fix') = 1 then
      Verdict := AddVerdict(CM('s02_needs_one'))
    else
      Verdict := AddVerdict(FM1('s02_needs', IntToStr(CountClass('fix'))));
    AddCheckItems(False);
    WizardForm.NextButton.Enabled := False;
  end
  else
  begin
    Verdict := AddVerdict(CM('s02_ready'));
    if RestartNeeded then
      AddText(CM('s02_ready_restart'), False);
    AddCheckItems(False);
    WizardForm.NextButton.Enabled := not FixRunning;
  end;
  if Verdict.CanFocus then
    WizardForm.ActiveControl := Verdict;
end;


{ W14-D1: a fault while S02 draws the check result never leaves the page without its way on.
  The fault goes to the setup log (Save report), and S02 shows the S13 layout with Save report;
  Try again runs the check again. Only calls that ran on the owner's PC draw it. }
procedure RenderCheck;
var
  Button: TNewButton;
begin
  try
    RenderCheckBody;
  except
    Log('S02 draw failed: ' + GetExceptionMessage);
    CheckDrawFailed := True;
    BeginBody(P_CHECK);
    WizardForm.PageNameLabel.Caption := CM('s13_title');
    WizardForm.PageDescriptionLabel.Caption := CM('s02_title');
    AddVerdict(CM('s02_draw_failed'));
    AddText(CM('s13_what'), False);
    try
      Button := AddButtonAt(CM('btn_save_report'), 0, 0);
      Button.OnClick := @SaveReport;
      CurY := CurY + Button.Height + ScaleY(6);
      if ReportLine <> '' then
        AddText(ReportLine, False);
    except
      Log('S02 Save report button failed: ' + GetExceptionMessage);
    end;
    WizardForm.NextButton.Visible := True;
    WizardForm.NextButton.Caption := CM('btn_try_again');
    WizardForm.NextButton.Enabled := True;
  end;
end;
{ ------------------------------------------------------------------------------------------- }
{ S05 Restart this PC once                                                                      }
{ ------------------------------------------------------------------------------------------- }

procedure RestartLaterClick(Sender: TObject);
begin
  ForceClose := True;
  WizardForm.Close;
end;

procedure PrepDetailsClick(Sender: TObject; const Link: String; LinkType: TSysLinkType);
begin
  PrepDetails := not PrepDetails;
  RenderPage(P_RESTART);
end;

procedure StartPrepare;
begin
  try
    ExtractTemporaryFiles('{tmp}\payload\wsl.*.msi');
  except
    Log('The WSL package is not in this setup file.');
  end;
  PrepOut := NewOut('prepare-pc');
  PrepState := 'working';
  PrepStartedAt := GetTickCount;
  StartHelper('prepare-pc', RunId, PrepOut, '');
end;

procedure RenderRestart;
var
  Steps: String;
  Link: TNewLinkLabel;
begin
  BeginBody(P_RESTART);
  { Design B8: the header comes back after a failure and Try again. }
  WizardForm.PageNameLabel.Caption := CM('s05_title');
  WizardForm.PageDescriptionLabel.Caption := CM('s05_subtitle');
  AddStageLine(1);
  WizardForm.NextButton.Caption := CM('btn_next');
  if ExtraButton <> nil then
    ExtraButton.Visible := False;
  if PrepState = 'working' then
  begin
    AddText(CM('s05_working'), True);
    AddMarquee;
    WizardForm.NextButton.Enabled := False;
  end
  else if PrepState = 'failed' then
    AddFailure(CM('s05_title'), CM('s05_failed'), True)
  else if PrepState = 'failed_av' then
    AddFailure(CM('s05_title'), CM('av_blocked'), True)
  else if PrepState = 'restart' then
  begin
    AddVerdict(CM('s05_done'));
    Steps := RestartResumeText(ResumeCode, 's05_steps');
    if Steps = '' then
      Steps := CM('s05_steps');
    AddText(Steps, False);
    Link := AddLink(CM('btn_details'), 0);
    Link.OnLinkClick := @PrepDetailsClick;
    if PrepDetails then
      AddText(CM('s05_details'), False);
    WizardForm.NextButton.Caption := CM('s05_next');
    WizardForm.NextButton.Enabled := True;
    if ExtraButton <> nil then
    begin
      ExtraButton.Caption := CM('s05_later');
      ExtraButton.OnClick := @RestartLaterClick;
      ExtraButton.Visible := True;
    end;
  end
  else
  begin
    AddVerdict(CM('s05_done'));
    WizardForm.NextButton.Enabled := True;
  end;
end;

{ ------------------------------------------------------------------------------------------- }
{ S06 Welcome back                                                                              }
{ ------------------------------------------------------------------------------------------- }

procedure RenderWelcomeBack;
begin
  BeginBody(P_BACK);
  AddStageLine(1);
  WizardForm.NextButton.Caption := CM('btn_continue');
  if EntryNext = 'S14' then
    AddText(CM('s06_stopped_key'), True)
  else if EntryNext = 'S12' then
    AddText(CM('s06_stopped'), True)
  else
    AddText(CM('s06_continue'), True);
  if CheckVerdict = 'helper_timeout' then
  begin
    AddFailure(CM('s06_title'), CM('av_blocked'), True);
    Exit;
  end;
  if CheckRunning or not CheckDone then
  begin
    AddText(CM('s06_checking'), False);
    AddMarquee;
    WizardForm.NextButton.Enabled := False;
    Exit;
  end;
  if CountClass('fix') = 0 then
  begin
    AddVerdict(CM('s06_still_ready'));
    WizardForm.NextButton.Enabled := True;
  end
  else
  begin
    AddCheckItems(True);
    WizardForm.NextButton.Enabled := False;
  end;
end;

{ ------------------------------------------------------------------------------------------- }
{ S07 Where to keep your data, and the background preparation (plan page 4a)                    }
{ ------------------------------------------------------------------------------------------- }

procedure ReadDataDrives;
var
  OutFile, Text, Rest, Letter, DriveType, FileSystem: String;
  Start, Count, I, J: Integer;
  FreeBytes: Int64;
  SwapS: String;
  SwapF: Int64;
begin
  SetArrayLength(DriveLetters, 0);
  SetArrayLength(DriveFree, 0);
  OutFile := NewOut('drives');
  RunHelper('drives', RunId, OutFile, '');
  Text := ReadText(OutFile);
  Count := 0;
  Rest := Text;
  Start := Pos('"letter":"', Rest);
  while Start > 0 do
  begin
    Rest := Copy(Rest, Start, Length(Rest));
    Letter := JsonValue(Rest, 'letter');
    DriveType := JsonValue(Copy(Rest, 1, Pos('}', Rest)), 'drive_type');
    FileSystem := JsonValue(Copy(Rest, 1, Pos('}', Rest)), 'file_system');
    FreeBytes := StrToInt64Def(JsonLiteral(Copy(Rest, 1, Pos('}', Rest)), 'free_bytes'), 0);
    { Plan page 4: fixed NTFS drives inside this PC with 15 GB free (C07, R5). }
    if (DriveType = 'Fixed') and (FileSystem = 'NTFS') and (Pos('"compressed":true', Copy(Rest, 1, Pos('}', Rest))) = 0)
      and (Pos('"encrypted":true', Copy(Rest, 1, Pos('}', Rest))) = 0) and (FreeBytes >= Int64(15) * 1073741824) then
    begin
      SetArrayLength(DriveLetters, Count + 1);
      SetArrayLength(DriveFree, Count + 1);
      DriveLetters[Count] := Letter;
      DriveFree[Count] := FreeBytes;
      Count := Count + 1;
    end;
    Rest := Copy(Rest, 2, Length(Rest));
    Start := Pos('"letter":"', Rest);
  end;
  for I := 0 to Count - 2 do
    for J := I + 1 to Count - 1 do
      if DriveFree[J] > DriveFree[I] then
      begin
        SwapS := DriveLetters[I]; DriveLetters[I] := DriveLetters[J]; DriveLetters[J] := SwapS;
        SwapF := DriveFree[I]; DriveFree[I] := DriveFree[J]; DriveFree[J] := SwapF;
      end;
  if (DataRoot = '') and (Count > 0) then
    DataRoot := DriveLetters[0] + '\SlateOps';
end;

function GB(Bytes: Int64): String;
begin
  Result := IntToStr(Integer(Bytes div 1073741824));
end;

{ W9: the S07 card uses the kept data (plan 9.2) when the folder holds it and the person keeps
  the default "Use the kept data". }
function KeptMode: Boolean;
begin
  Result := (KeptState = 'kept') and KeptUse;
end;

{ Reads kept.json through the helper, after its folder checks (never a Pascal read, which
  would follow a link). }
procedure RefreshKept;
var
  Text: String;
begin
  if KeptFor = DataRoot then
    Exit;
  KeptFor := DataRoot;
  KeptState := '';
  KeptUse := True;
  if (DataRoot = '') or not DirExists(AddBackslash(DataRoot) + 'kept') then
    Exit;
  Text := ReadText(NewOutRun('kept-read', '-DataRoot ' + AddQuotes(DataRoot)));
  KeptState := JsonValue(Text, 'code');
  KeptVersion := JsonValue(Text, 'version');
  KeptName := JsonValue(Text, 'business_name');
  KeptOn := JsonValue(Text, 'kept_on');
end;

procedure KeptChoiceClick(Sender: TObject);
begin
  KeptUse := TNewRadioButton(Sender).Tag = 1;
  RenderPage(P_DATA);
end;

procedure DriveRadioClick(Sender: TObject);
begin
  DataRoot := DriveLetters[TNewRadioButton(Sender).Tag] + '\SlateOps';
  DataError := '';
  RenderPage(P_DATA);
end;

procedure ChangeFolderClick(Sender: TObject; const Link: String; LinkType: TSysLinkType);
var
  Folder: String;
begin
  Folder := ExtractFileDir(DataRoot);
  ModalOpen := True;
  try
    if not BrowseForFolder(CM('s07_change_folder'), Folder, True) then
      Exit;
  finally
    ModalOpen := False;
  end;
  if CompareText(ExtractFileName(RemoveBackslash(Folder)), 'SlateOps') <> 0 then
    Folder := AddBackslash(Folder) + 'SlateOps';
  DataRoot := Folder;
  DataError := '';
  RenderPage(P_DATA);
end;

procedure ChangeProgramClick(Sender: TObject; const Link: String; LinkType: TSysLinkType);
var
  Folder: String;
begin
  Folder := WizardForm.DirEdit.Text;
  ModalOpen := True;
  try
    if BrowseForFolder(CM('s07_change_folder'), Folder, True) then
      WizardForm.DirEdit.Text := Folder;
  finally
    ModalOpen := False;
  end;
end;

procedure UseDefaultClick(Sender: TObject);
var
  I: Integer;
  Drive: String;
begin
  { Spec 7.5: \SlateOps on the drive of the chosen folder when the list holds it, else on the
    drive selected in the list. Setup never changes a folder above. }
  Drive := Copy(DataRoot, 1, 2);
  for I := 0 to GetArrayLength(DriveLetters) - 1 do
    if CompareText(DriveLetters[I], Drive) = 0 then
    begin
      DataRoot := DriveLetters[I] + '\SlateOps';
      DataError := '';
      RenderPage(P_DATA);
      Exit;
    end;
  if GetArrayLength(DriveLetters) > 0 then
    DataRoot := DriveLetters[0] + '\SlateOps';
  DataError := '';
  RenderPage(P_DATA);
end;

function DefaultFolderFor(Root: String): String;
var
  I: Integer;
begin
  Result := Copy(Root, 1, 2) + '\SlateOps';
  for I := 0 to GetArrayLength(DriveLetters) - 1 do
    if CompareText(DriveLetters[I], Copy(Root, 1, 2)) = 0 then
      Exit;
  if GetArrayLength(DriveLetters) > 0 then
    Result := DriveLetters[0] + '\SlateOps';
end;

procedure RenderData;
var
  I: Integer;
  Caption: String;
  Radio: TNewRadioButton;
  Link: TNewLinkLabel;
  Button: TNewButton;
begin
  BeginBody(P_DATA);
  AddStageLine(2);
  WizardForm.NextButton.Caption := CM('btn_next');
  if DataPrepared then
  begin
    AddText(FM1('s07_folder', DataRoot), True);
    AddText(FM1('s07_already', Copy(DataRoot, 1, 2)), False);
    WizardForm.NextButton.Enabled := True;
    Exit;
  end;
  AddText(CM('s07_first'), False);
  SetArrayLength(DriveRadios, GetArrayLength(DriveLetters));
  for I := 0 to GetArrayLength(DriveLetters) - 1 do
  begin
    Caption := DriveLetters[I];
    if I = 0 then
      Caption := Caption + ' ' + CM('stage_sep') + ' ' + CM('s07_most_space');
    Caption := Caption + '   ' + FM1('s07_free', GB(DriveFree[I]));
    Radio := TNewRadioButton.Create(WizardForm);
    Radio.Parent := Cur;
    Radio.Caption := Caption;
    Radio.Tag := I;
    Radio.SetBounds(0, CurY, Cur.Width, ScaleY(18));
    Radio.Checked := CompareText(Copy(DataRoot, 1, 2), DriveLetters[I]) = 0;
    Radio.OnClick := @DriveRadioClick;
    Radio.Enabled := not DataStarted;
    DriveRadios[I] := Radio;
    CurY := CurY + Radio.Height + ScaleY(4);
  end;
  CurY := CurY + ScaleY(6);
  AddText(FM1('s07_folder', DataRoot), False);
  RefreshKept;
  if KeptState = 'kept' then
  begin
    { Spec S07 kept-data card. }
    AddText(FM3('s07_kept', KeptName, KeptVersion, KeptOn), True);
    Radio := TNewRadioButton.Create(WizardForm);
    Radio.Parent := Cur;
    Radio.Caption := CM('s07_use_kept');
    Radio.Tag := 1;
    Radio.Checked := KeptUse;
    Radio.OnClick := @KeptChoiceClick;
    Radio.SetBounds(0, CurY, Cur.Width, ScaleY(18));
    CurY := CurY + ScaleY(22);
    Radio := TNewRadioButton.Create(WizardForm);
    Radio.Parent := Cur;
    Radio.Caption := CM('s07_start_new');
    Radio.Tag := 0;
    Radio.Checked := not KeptUse;
    Radio.OnClick := @KeptChoiceClick;
    Radio.SetBounds(0, CurY, Cur.Width, ScaleY(18));
    CurY := CurY + ScaleY(24);
  end
  else if KeptState = 'kept_newer' then
    AddText(FM1('s07_kept_newer', KeptVersion), True)
  else if KeptState = 'kept_older' then
    AddText(FM1('s07_kept_older', KeptVersion), True)
  else if KeptState = 'kept_unreadable' then
  begin
    AddText(CM('s07_kept_unreadable'), True);
    AddReportControls;
  end;
  if DataError = 'data_folder_parent_unsafe' then
  begin
    AddText(FM2('s07_parent_unsafe', DataRoot, DefaultFolderFor(DataRoot)), False);
    Button := AddButtonAt(FM1('s07_use_default', DefaultFolderFor(DataRoot)), 0, 0);
    Button.OnClick := @UseDefaultClick;
    CurY := CurY + Button.Height + ScaleY(6);
  end
  else if DataError = 'not_empty' then
    AddText(CM('s07_not_empty'), False)
  else if DataError = 'too_small' then
    AddText(FM1('s07_too_small', DataErrorValue), False)
  else if DataError = 'drive_not_fixed_ntfs' then
    AddText(CM('s07_usb_note'), True)
  else if (DataError = 'start_failed') or (DataError = 'helper_timeout') then
  begin
    { In place, never from the timer as a dialog (spec 12 item 1). }
    if DataError = 'helper_timeout' then AddText(CM('av_blocked'), True) else AddText(CM('s07_start_failed'), True);
    AddReportControls;
  end;
  if not DataStarted then
  begin
    Link := AddLink(CM('s07_change_folder'), 0);
    Link.OnLinkClick := @ChangeFolderClick;
  end;
  if DataError <> 'drive_not_fixed_ntfs' then
    AddText(CM('s07_usb_note'), False);
  Link := AddLink(CM('s07_change_program'), 0);
  Link.OnLinkClick := @ChangeProgramClick;
  Link.Enabled := not DataStarted;
  if DataStarted then
  begin
    AddText(FM1('s07_preparing', '0%'), False);
    AddMarquee;
  end;
  { W9-3: newer, older (W13b) or unreadable kept data, and "Start new" in a kept folder, keep
    Next off until the folder changes. }
  WizardForm.NextButton.Enabled := (DataRoot <> '') and not DataStarted and ((KeptState = '') or KeptMode);
end;

{ The folder that the person picked must be on a listed drive (spec S07 "drive too small"). }
function DataDriveListed: Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 0 to GetArrayLength(DriveLetters) - 1 do
    if CompareText(DriveLetters[I], Copy(DataRoot, 1, 2)) = 0 then
      Result := True;
end;

procedure StartDataPrepare;
var
  FreeBytes: Int64;
  Ignored: Int64;
begin
  { Design B5: a folder on a USB or network drive gets the USB and network message. }
  if GetDriveType(Copy(DataRoot, 1, 3)) <> DRIVE_FIXED then
  begin
    DataError := 'drive_not_fixed_ntfs';
    RenderPage(P_DATA);
    Exit;
  end;
  if not DataDriveListed then
  begin
    DataError := 'too_small';
    if GetSpaceOnDisk64(Copy(DataRoot, 1, 3), FreeBytes, Ignored) then
      DataErrorValue := GB(FreeBytes)
    else
      DataErrorValue := '0';
    RenderPage(P_DATA);
    Exit;
  end;
  DataStarted := True;
  DataError := '';
  RenderPage(P_DATA);
  WizardForm.Refresh;
  try
    ExtractTemporaryFiles('{tmp}\payload\slateops-*');
    ExtractTemporaryFiles('{tmp}\payload\release-manifest.json*');
  except
    Log('The setup payload is not in this setup file.');
  end;
  BgOut := NewOut('prepare-data');
  DataStartedAt := GetTickCount;
  if KeptMode then
    StartHelper('prepare-data', RunId, BgOut, '-DataRoot ' + AddQuotes(DataRoot) + ' -UseKept')
  else
    StartHelper('prepare-data', RunId, BgOut, '-DataRoot ' + AddQuotes(DataRoot));
end;

{ The background preparation after prepare-data (plan page 4a; spec 12 item 1): one step at a
  time, each an Exec job or a helper action. }
{ W9: with kept data the disk comes back and is checked (F3) before receive; no image import
  and no download (the images are inside the kept disk). }
function KeptStepName(Index: Integer): String;
begin
  case Index of
    0: Result := 'service';
    1: Result := 'wslconfig';
    2: Result := 'restore-kept';
    3: Result := 'import-kept';
    4: Result := 'start-boot';
    5: Result := 'kept-status';
    6: Result := 'receive';
    7: Result := 'prepare';
  else
    Result := '';
  end;
end;

function BgCount: Integer;
begin
  if KeptMode then Result := 8 else Result := 7;
end;

function IsHelperStep(Name: String): Boolean;
begin
  Result := (Name = 'service') or (Name = 'start-boot') or (Name = 'restore-kept') or (Name = 'kept-status');
end;

function HelperStepCode(Name: String): String;
begin
  if Name = 'service' then Result := 'created'
  else if Name = 'start-boot' then Result := 'started'
  else if Name = 'restore-kept' then Result := 'restored'
  else Result := 'match';
end;

function BgStepName(Index: Integer): String;
begin
  if KeptMode then
  begin
    Result := KeptStepName(Index);
    Exit;
  end;
  case Index of
    0: Result := 'service';
    1: Result := 'wslconfig';
    2: Result := 'import-distro';
    3: Result := 'start-boot';
    4: Result := 'receive';
    5: Result := 'prepare';
    6: Result := 'prefetch';
  else
    Result := '';
  end;
end;

function BgDone: Boolean;
begin
  Result := DataPrepared and (BgIndex >= BgCount) and not BgFailed;
end;

procedure UpdateBgStatus;
begin
  if not DataPrepared then
    Exit;
  if (WizardForm.CurPageID <> Pages[P_ORG].ID) and (WizardForm.CurPageID <> Pages[P_EMAIL].ID) and (WizardForm.CurPageID <> Pages[P_BACKUP].ID)
    and not (KeptMode and (WizardForm.CurPageID = Pages[P_READY].ID)) then
  begin
    WizardForm.BeveledLabel.Caption := '';
    Exit;
  end;
  if BgFailed then
    WizardForm.BeveledLabel.Caption := ' ' + CM('s07_prep_failed')
  else if BgDone then
    WizardForm.BeveledLabel.Caption := ' ' + CM('s07_prepared')
  else
    WizardForm.BeveledLabel.Caption := ' ' + FM1('s07_preparing', IntToStr((BgIndex * 100) div BgCount) + '%');
  WizardForm.BeveledLabel.Visible := True;
end;

procedure StartBgStep;
var
  Name, Input: String;
begin
  Name := BgStepName(BgIndex);
  if Name = '' then
    Exit;
  BgCode := '';
  if IsHelperStep(Name) then
  begin
    BgOut := NewOut(Name);
    BgStartedAt := GetTickCount;
    StartHelper(Name, RunId, BgOut, '');
    Exit;
  end;
  if Name = 'receive' then
    Input := '{"run_id":"' + RunId + '","setup_version":"' + SetupVersion + '"}'
  else if (Name = 'prepare') or (Name = 'prefetch') then
    Input := '{"run_id":"' + RunId + '","version":"' + SetupVersion + '"}'
  else
    Input := '';
  StartJob(Name, Input, 'bg', False, False, 15);
end;

procedure StartBackground;
begin
  BgIndex := 0;
  BgFailed := False;
  StartBgStep;
end;

{ W9 review item 2: S11 of a kept reinstall shows a background failure when it arrives. }
procedure RedrawKeptReady;
begin
  if KeptMode and (WizardForm.CurPageID = Pages[P_READY].ID) then
    RenderPage(P_READY);
end;

procedure PollBackground;
var
  Code, Name, OutFile: String;
begin
  if (not DataPrepared) or BgFailed or (BgIndex >= BgCount) then
    Exit;
  Name := BgStepName(BgIndex);
  if IsHelperStep(Name) then
  begin
    Code := ReadResultCode(BgOut);
    if (Code = '') and (Elapsed(BgStartedAt) > HELPER_LIMIT_MS) then
      Code := 'helper_timeout';
    if Code = '' then
      Exit;
    if Code <> HelperStepCode(Name) then
    begin
      BgFailed := True;
      BgCode := Code;
      { F3 at reinstall: a disk that is not the kept installation goes back to kept\ at once,
        unchanged (advisor item 1). }
      if (Name = 'kept-status') or (Name = 'restore-kept') then
      begin
        BgCode := 'kept_mismatch';
        if Name = 'kept-status' then
          NewOutRun('kept-return', '');
      end;
      UpdateBgStatus;
      RedrawKeptReady;
      Exit;
    end;
    if Name = 'service' then
    begin
      OutFile := NewOut('account');
      RunHelper('account-sid', RunId, OutFile, '');
      ServiceSid := JsonValue(ReadText(OutFile), 'sid');
    end;
  end
  else
  begin
    if JobPurpose <> 'bg' then
      Exit;
    if JobState <> JOB_DONE then
      Exit;
    JobState := JOB_IDLE;
    if JobExit <> 0 then
    begin
      BgFailed := True;
      BgCode := JobCode;
      UpdateBgStatus;
      RedrawKeptReady;
      Exit;
    end;
  end;
  BgIndex := BgIndex + 1;
  UpdateBgStatus;
  StartBgStep;
  if KeptMode and (WizardForm.CurPageID = Pages[P_READY].ID) then
    RenderPage(P_READY);
end;

{ Next on S08 to S10 after a background failure: the modal S13 form (spec S08). }
function CheckBackground: Boolean;
var
  Text: String;
begin
  Result := True;
  if not BgFailed then
    Exit;
  Text := CM('s07_start_failed');
  { Correction 5 (spec 7.5): a helper that never answered, or the account that cannot sign in. }
  if BgCode = 'helper_timeout' then
    Text := CM('av_blocked')
  else if BgCode = 'service_logon_failed' then
    Text := CM('service_logon_failed');
  if BgCode = 'kept_mismatch' then
  begin
    FailureForm(CM('s07_title'), CM('s07_kept_unreadable'), False);
    Result := False;
    Exit;
  end;
  if (BgCode = 'data_folder_parent_unsafe') or (BgCode = 'payload_part_missing') then
  begin
    { Parent decision: a folder above changed after the check; no Try again. }
    FailureForm(CM('s07_title'), FM1('s07_folder_changed', DataRoot), False);
    Result := False;
    Exit;
  end;
  if FailureForm(CM('s07_title'), Text, True) then
  begin
    BgFailed := False;
    UpdateBgStatus;
    StartBgStep;
  end;
  Result := False;
end;

{ ------------------------------------------------------------------------------------------- }
{ S08 Your organization                                                                         }
{ ------------------------------------------------------------------------------------------- }

function NewEditAt(Parent: TWinControl; Top: Integer): TNewEdit;
begin
  Result := TNewEdit.Create(WizardForm);
  Result.Parent := Parent;
  Result.SetBounds(0, Top, Parent.Width, ScaleY(21));
end;

function DefaultUser(Email: String): String;
var
  I: Integer;
  Local, C: String;
begin
  Local := Copy(Email, 1, Pos('@', Email) - 1);
  Result := '';
  for I := 1 to Length(Local) do
  begin
    C := Copy(Local, I, 1);
    if Pos(Lowercase(C), 'abcdefghijklmnopqrstuvwxyz0123456789_-') > 0 then
      Result := Result + C;
  end;
  while Length(Result) < 3 do
    Result := Result + '_';
  Result := Copy(Result, 1, 100);
end;

function DefaultSlug(Name: String): String;
var
  I: Integer;
  C: String;
begin
  Result := '';
  for I := 1 to Length(Name) do
  begin
    C := Lowercase(Copy(Name, I, 1));
    if Pos(C, 'abcdefghijklmnopqrstuvwxyz0123456789') > 0 then
      Result := Result + C
    else if (Result <> '') and (Copy(Result, Length(Result), 1) <> '-') then
      Result := Result + '-';
  end;
  while (Result <> '') and (Copy(Result, Length(Result), 1) = '-') do
    Result := Copy(Result, 1, Length(Result) - 1);
  if Result = '' then
    Result := 'organization';
  Result := Copy(Result, 1, 100);
end;

function ValidEmail(S: String): Boolean;
var
  At: Integer;
begin
  At := Pos('@', S);
  Result := (At > 1) and (Pos('.', Copy(S, At + 2, Length(S))) > 0) and (Pos(' ', S) = 0)
    and (Length(S) <= 254) and (Pos('@', Copy(S, At + 1, Length(S))) = 0);
end;

function ValidUser(S: String): Boolean;
var
  I: Integer;
begin
  Result := (Length(S) >= 3) and (Length(S) <= 100);
  for I := 1 to Length(S) do
    if Pos(Copy(S, I, 1), 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-') = 0 then
      Result := False;
end;

function ValidSlug(S: String): Boolean;
begin
  Result := (S <> '') and (DefaultSlug(S) = S);
end;

procedure OrgMoreClick(Sender: TObject; const Link: String; LinkType: TSysLinkType);
begin
  if OrgUser.Text = '' then OrgUser.Text := DefaultUser(OrgEmail.Text);
  if OrgSlug.Text = '' then OrgSlug.Text := DefaultSlug(OrgName.Text);
  OrgUserLabel.Visible := True;
  OrgUser.Visible := True;
  OrgSlugLabel.Visible := True;
  OrgSlug.Visible := True;
  OrgMoreHelp.Visible := True;
end;

procedure BuildOrgPage;
var
  Surface: TWinControl;
  Y: Integer;
  T: TNewStaticText;
begin
  Surface := Pages[P_ORG].Surface;
  Y := 0;
  T := AddTextTo(Surface, Y, CM('s08_name'), True); Y := Y + T.Height + ScaleY(2);
  T := AddTextTo(Surface, Y, CM('s08_name_help'), False); Y := Y + T.Height + ScaleY(2);
  OrgName := NewEditAt(Surface, Y); OrgName.MaxLength := 200; Y := Y + OrgName.Height + ScaleY(10);
  T := AddTextTo(Surface, Y, CM('s08_email'), True); Y := Y + T.Height + ScaleY(2);
  T := AddTextTo(Surface, Y, CM('s08_email_help'), False); Y := Y + T.Height + ScaleY(2);
  OrgEmail := NewEditAt(Surface, Y); OrgEmail.MaxLength := 254; Y := Y + OrgEmail.Height + ScaleY(10);
  OrgMoreLink := TNewLinkLabel.Create(WizardForm);
  OrgMoreLink.Parent := Surface;
  OrgMoreLink.Caption := '<a href="more">' + CM('s08_more') + '</a>';
  OrgMoreLink.Top := Y;
  OrgMoreLink.Width := Surface.Width;
  OrgMoreLink.AdjustHeight;
  OrgMoreLink.OnLinkClick := @OrgMoreClick;
  Y := Y + OrgMoreLink.Height + ScaleY(6);
  OrgUserLabel := AddTextTo(Surface, Y, CM('s08_username'), True); Y := Y + OrgUserLabel.Height + ScaleY(2);
  OrgUser := NewEditAt(Surface, Y); OrgUser.MaxLength := 100; Y := Y + OrgUser.Height + ScaleY(6);
  OrgSlugLabel := AddTextTo(Surface, Y, CM('s08_slug'), True); Y := Y + OrgSlugLabel.Height + ScaleY(2);
  OrgSlug := NewEditAt(Surface, Y); OrgSlug.MaxLength := 100; Y := Y + OrgSlug.Height + ScaleY(6);
  OrgMoreHelp := AddTextTo(Surface, Y, CM('s08_more_help'), False); Y := Y + OrgMoreHelp.Height + ScaleY(6);
  OrgError := AddTextTo(Surface, Y, '', True);
  OrgUserLabel.Visible := False; OrgUser.Visible := False;
  OrgSlugLabel.Visible := False; OrgSlug.Visible := False; OrgMoreHelp.Visible := False;
end;

function CheckOrg: Boolean;
begin
  Result := False;
  if OrgUser.Text = '' then OrgUser.Text := DefaultUser(OrgEmail.Text);
  if OrgSlug.Text = '' then OrgSlug.Text := DefaultSlug(OrgName.Text);
  if Trim(OrgName.Text) = '' then begin OrgError.Caption := CM('s08_err_name'); WizardForm.ActiveControl := OrgName; Exit; end;
  if Length(Trim(OrgName.Text)) > 100 then begin OrgError.Caption := CM('s08_err_name_long'); WizardForm.ActiveControl := OrgName; Exit; end;
  if not ValidEmail(OrgEmail.Text) then begin OrgError.Caption := CM('s08_err_email'); WizardForm.ActiveControl := OrgEmail; Exit; end;
  if not ValidUser(OrgUser.Text) then begin OrgMoreClick(nil, '', sltID); OrgError.Caption := CM('s08_err_username'); WizardForm.ActiveControl := OrgUser; Exit; end;
  if not ValidSlug(OrgSlug.Text) then begin OrgMoreClick(nil, '', sltID); OrgError.Caption := CM('s08_err_slug'); WizardForm.ActiveControl := OrgSlug; Exit; end;
  OrgError.Caption := '';
  Result := True;
end;

{ ------------------------------------------------------------------------------------------- }
{ S09 Email for Slate Operations                                                                }
{ ------------------------------------------------------------------------------------------- }

function MailDomain: String;
begin
  Result := Lowercase(Copy(MailFrom.Text, Pos('@', MailFrom.Text) + 1, Length(MailFrom.Text)));
end;

function IsOutlookDomain(Domain: String): Boolean;
begin
  Result := (Domain = 'outlook.com') or (Domain = 'hotmail.com') or (Domain = 'live.com') or (Domain = 'msn.com');
end;

{ Spec S09 and 12 item 7: known domains first, then the MX records (Windows side only). The
  answer only selects a provider; it fills no field. }
procedure DetectProvider;
var
  Domain, OutFile: String;
begin
  Domain := MailDomain;
  if (Domain = MailCheckedDomain) or not ValidEmail(MailFrom.Text) then
    Exit;
  MailCheckedDomain := Domain;
  MailDetected := '';
  MailOutlook := IsOutlookDomain(Domain);
  if MailOutlook then
  begin
    MailGmail.Checked := False;
    MailM365.Checked := False;
    MailOther.Checked := False;
  end
  else if (Domain = 'gmail.com') or (Domain = 'googlemail.com') then
    MailDetected := 'gmail'
  else
  begin
    OutFile := NewOut('provider');
    RunHelper('provider-detect', RunId, OutFile, '-Domain ' + Domain);
    MailDetected := ReadResultCode(OutFile);
  end;
  if MailDetected = 'gmail' then MailGmail.Checked := True
  else if MailDetected = 'm365' then MailM365.Checked := True
  else if not MailOutlook then MailOther.Checked := True;
end;

procedure LayoutMail; forward;

procedure MailChanged(Sender: TObject);
begin
  MailPassed := False;
  MailChangedAt := GetTickCount;
  if WizardForm.CurPageID = Pages[P_EMAIL].ID then
    WizardForm.NextButton.Caption := CM('s09_next_test');
end;

procedure MailProviderClick(Sender: TObject);
begin
  MailPassed := False;
  if Sender = MailOther then
    MailOutlook := False;
  MailChangedAt := GetTickCount;
  LayoutMail;
end;

procedure MailShowClick(Sender: TObject);
begin
  if MailShow.Checked then
    MailPassword.PasswordChar := #0
  else
    MailPassword.PasswordChar := '*';
end;

procedure HideShow;
begin
  { Spec S09: "Show" resets to hidden after each test send and when the page changes. }
  if MailShow <> nil then
  begin
    MailShow.Checked := False;
    MailPassword.PasswordChar := '*';
  end;
end;

procedure GmailHelpClick(Sender: TObject; const Link: String; LinkType: TSysLinkType);
begin
  if MailGmail.Checked then
  begin
    if ConfirmBox(CM('s09_gmail_title'), CM('s09_gmail_steps'), CM('s09_gmail_open'), CM('btn_close')) then
      OpenAsUser('https://myaccount.google.com/apppasswords', '');
  end
  else
    InfoForm(CM('s09_m365_title'), CM('s09_m365_steps'));
end;

procedure MailMoreClick(Sender: TObject; const Link: String; LinkType: TSysLinkType);
begin
  MailMore := True;
  if MailSender.Text = '' then
    MailSender.Text := Trim(OrgName.Text);
  LayoutMail;
end;

procedure ContinueLaterClick(Sender: TObject; const Link: String; LinkType: TSysLinkType); forward;

procedure Place(Control: TControl; var Y: Integer; Show: Boolean; Gap: Integer);
begin
  Control.Visible := Show;
  if Show then
  begin
    Control.Top := Y;
    Y := Y + Control.Height + Gap;
  end;
end;

procedure PlaceError(After: TControl; var Y: Integer);
begin
  if (MailErrorAfter = After) and (MailError.Caption <> '') then
  begin
    MailError.Visible := True;
    MailError.Top := Y;
    WizardForm.AdjustLabelHeight(MailError);
    Y := Y + MailError.Height + ScaleY(4);
  end;
end;

{ Shows the fields of the chosen provider in order (spec S09 "Fields, in order"). }
procedure LayoutMail;
var
  Y: Integer;
  Gmail, M365, Other: Boolean;
begin
  Gmail := MailGmail.Checked and not MailOutlook;
  M365 := MailM365.Checked and not MailOutlook;
  Other := MailOther.Checked;
  MailError.Visible := False;
  Y := 0;
  Place(MailFromLabel, Y, True, ScaleY(2));
  Place(MailFrom, Y, True, ScaleY(4));
  PlaceError(MailFrom, Y);
  Place(MailProviderLabel, Y, True, ScaleY(2));
  MailGmail.Top := Y; MailM365.Top := Y; MailOther.Top := Y;
  Y := Y + MailGmail.Height + ScaleY(6);
  PlaceError(MailGmail, Y);
  MailGmail.Caption := CM('s09_gmail');
  MailM365.Caption := CM('s09_m365');
  if MailDetected = 'gmail' then MailGmail.Caption := MailGmail.Caption + ' ' + CM('s09_detected');
  if MailDetected = 'm365' then MailM365.Caption := MailM365.Caption + ' ' + CM('s09_detected');
  if MailOutlook and not Other then
  begin
    MailNote.Caption := CM('s09_outlook');
    WizardForm.AdjustLabelHeight(MailNote);
    Place(MailNote, Y, True, ScaleY(6));
    Place(MailHelpLink, Y, False, 0);
    Place(MailPasswordLabel, Y, False, 0);
    Place(MailPassword, Y, False, 0);
    Place(MailShow, Y, False, 0);
  end
  else
  begin
    if Gmail then MailNote.Caption := CM('s09_gmail_help')
    else if M365 then MailNote.Caption := CM('s09_m365_note')
    else MailNote.Caption := '';
    WizardForm.AdjustLabelHeight(MailNote);
    Place(MailNote, Y, Gmail or M365, ScaleY(2));
    if Gmail then MailHelpLink.Caption := '<a href="help">' + CM('s09_gmail_link') + '</a>'
    else MailHelpLink.Caption := '<a href="help">' + CM('s09_m365_link') + '</a>';
    Place(MailHelpLink, Y, Gmail or M365, ScaleY(6));
    Place(MailServerLabel, Y, Other, ScaleY(2));
    Place(MailServer, Y, Other, ScaleY(4));
    PlaceError(MailServer, Y);
    Place(MailPortLabel, Y, Other, ScaleY(2));
    Place(MailPort, Y, Other, ScaleY(4));
    Place(MailSecurityLabel, Y, Other, ScaleY(2));
    MailSsl.Visible := Other; MailStartTls.Visible := Other;
    if Other then
    begin
      MailSsl.Top := Y; MailStartTls.Top := Y;
      Y := Y + MailSsl.Height + ScaleY(4);
      PlaceError(MailSsl, Y);
    end;
    Place(MailUserLabel, Y, Other, ScaleY(2));
    Place(MailUser, Y, Other, ScaleY(4));
    if Gmail then MailPasswordLabel.Caption := CM('s09_app_password') else MailPasswordLabel.Caption := CM('s09_password');
    Place(MailPasswordLabel, Y, True, ScaleY(2));
    Place(MailPassword, Y, True, ScaleY(2));
    Place(MailShow, Y, True, ScaleY(4));
    PlaceError(MailPassword, Y);
  end;
  Place(MailMoreLink, Y, not MailMore, ScaleY(4));
  Place(MailSenderLabel, Y, MailMore, ScaleY(2));
  Place(MailSender, Y, MailMore, ScaleY(6));
  MailStatus.Top := Y;
  WizardForm.AdjustLabelHeight(MailStatus);
end;

function NewRadioAt(Parent: TWinControl; Caption: String; Left, Width: Integer): TNewRadioButton;
begin
  Result := TNewRadioButton.Create(WizardForm);
  Result.Parent := Parent;
  Result.Caption := Caption;
  Result.SetBounds(Left, 0, Width, ScaleY(18));
  Result.OnClick := @MailProviderClick;
end;

procedure BuildMailPage;
var
  Surface: TWinControl;
  Third: Integer;
  Later: TNewLinkLabel;
begin
  Surface := Pages[P_EMAIL].Surface;
  Third := Surface.Width div 3;
  MailFromLabel := AddTextTo(Surface, 0, CM('s09_from'), True);
  MailFrom := NewEditAt(Surface, 0); MailFrom.MaxLength := 254; MailFrom.OnChange := @MailChanged;
  MailProviderLabel := AddTextTo(Surface, 0, CM('s09_provider'), True);
  MailGmail := NewRadioAt(Surface, CM('s09_gmail'), 0, Third);
  MailM365 := NewRadioAt(Surface, CM('s09_m365'), Third, Third);
  MailOther := NewRadioAt(Surface, CM('s09_other'), Third * 2, Third);
  MailNote := AddTextTo(Surface, 0, '', False);
  MailHelpLink := TNewLinkLabel.Create(WizardForm);
  MailHelpLink.Parent := Surface;
  MailHelpLink.Caption := '<a href="help">' + CM('s09_gmail_link') + '</a>';
  MailHelpLink.Width := Surface.Width;
  MailHelpLink.AdjustHeight;
  MailHelpLink.OnLinkClick := @GmailHelpClick;
  MailServerLabel := AddTextTo(Surface, 0, CM('s09_server'), True);
  MailServer := NewEditAt(Surface, 0); MailServer.OnChange := @MailChanged;
  MailPortLabel := AddTextTo(Surface, 0, CM('s09_port'), True);
  MailPort := NewEditAt(Surface, 0); MailPort.Width := ScaleX(80); MailPort.OnChange := @MailChanged;
  MailSecurityLabel := AddTextTo(Surface, 0, CM('s09_security'), True);
  MailSsl := TNewRadioButton.Create(WizardForm); MailSsl.Parent := Surface; MailSsl.Caption := CM('s09_ssl');
  MailSsl.SetBounds(0, 0, Surface.Width div 2, ScaleY(18)); MailSsl.OnClick := @MailChanged;
  MailStartTls := TNewRadioButton.Create(WizardForm); MailStartTls.Parent := Surface; MailStartTls.Caption := CM('s09_starttls');
  MailStartTls.SetBounds(Surface.Width div 2, 0, Surface.Width div 2, ScaleY(18)); MailStartTls.OnClick := @MailChanged;
  MailStartTls.Checked := True;
  MailUserLabel := AddTextTo(Surface, 0, CM('s09_user'), True);
  MailUser := NewEditAt(Surface, 0); MailUser.OnChange := @MailChanged;
  MailPasswordLabel := AddTextTo(Surface, 0, CM('s09_password'), True);
  MailPassword := NewEditAt(Surface, 0); MailPassword.PasswordChar := '*'; MailPassword.MaxLength := 1024; MailPassword.OnChange := @MailChanged;
  MailShow := TNewCheckBox.Create(WizardForm); MailShow.Parent := Surface; MailShow.Caption := CM('s09_show');
  MailShow.SetBounds(0, 0, ScaleX(120), ScaleY(18)); MailShow.OnClick := @MailShowClick;
  MailMoreLink := TNewLinkLabel.Create(WizardForm); MailMoreLink.Parent := Surface;
  MailMoreLink.Caption := '<a href="more">' + CM('s08_more') + '</a>'; MailMoreLink.OnLinkClick := @MailMoreClick;
  MailMoreLink.Width := Surface.Width; MailMoreLink.AdjustHeight;
  MailSenderLabel := AddTextTo(Surface, 0, CM('s09_sender_name'), True);
  MailSender := NewEditAt(Surface, 0); MailSender.MaxLength := 100; MailSender.OnChange := @MailChanged;
  MailError := AddTextTo(Surface, 0, '', True);
  MailStatus := AddTextTo(Surface, 0, '', False);
  { QA B7: Save report for an unknown result and for the R7 stop. }
  MailReportButton := TNewButton.Create(WizardForm);
  MailReportButton.Parent := Surface;
  MailReportButton.Caption := CM('btn_save_report');
  MailReportButton.SetBounds(0, 0, WizardForm.CalculateButtonWidth([CM('btn_save_report')]), WizardForm.NextButton.Height);
  MailReportButton.OnClick := @SaveReport;
  MailReportButton.Visible := False;
  Later := TNewLinkLabel.Create(WizardForm);
  Later.Parent := Surface;
  Later.Caption := '<a href="later">' + CM('s09_continue_later') + '</a>';
  Later.Width := Surface.Width;
  Later.AdjustHeight;
  Later.Top := Pages[P_EMAIL].SurfaceHeight - Later.Height;
  Later.OnLinkClick := @ContinueLaterClick;
  { W9 review item 7 (design W9-B1): M02 has no "Continue later". }
  Later.Visible := EntryScreen <> 'M01';
end;

function MailHost: String;
begin
  if MailGmail.Checked then Result := 'smtp.gmail.com'
  else if MailM365.Checked then Result := 'smtp.office365.com'
  else Result := Trim(MailServer.Text);
end;

function MailPortValue: Integer;
begin
  { Parent decision on D-4 (TASK-0083): Gmail 465 with implicit TLS, Microsoft 365 587 with
    STARTTLS. }
  if MailGmail.Checked then Result := 465
  else if MailM365.Checked then Result := 587
  else Result := StrToIntDef(Trim(MailPort.Text), 0);
end;

function MailUserValue: String;
begin
  if MailOther.Checked and (Trim(MailUser.Text) <> '') then Result := Trim(MailUser.Text)
  else Result := Trim(MailFrom.Text);
end;

function MailSenderValue: String;
begin
  Result := Trim(MailSender.Text);
  if Result = '' then
    Result := Trim(OrgName.Text);
end;

procedure SetMailError(Text: String; After: TControl);
begin
  MailError.Caption := Text;
  MailErrorAfter := After;
  LayoutMail;
end;

function MailFieldsReady: Boolean;
begin
  Result := ValidEmail(MailFrom.Text) and (MailPassword.Text <> '') and (MailGmail.Checked or MailM365.Checked or MailOther.Checked)
    and not (MailOutlook and not MailOther.Checked);
  if MailOther.Checked then
    Result := Result and (MailHost <> '') and (MailPortValue > 0) and (MailPortValue < 65536);
end;

procedure RenderMailStatus;
begin
  if MailPhase = 'waiting' then MailStatus.Caption := CM('s09_waiting')
  else if (MailPhase = 'selftest') or (MailPhase = 'sending') then MailStatus.Caption := FM1('s09_sending', Trim(OrgEmail.Text))
  else if MailPassed then MailStatus.Caption := FM1('s09_passed', Trim(OrgEmail.Text))
  else MailStatus.Caption := '';
  if MailShowReport and (ReportLine <> '') then
    MailStatus.Caption := ReportLine;
  WizardForm.AdjustLabelHeight(MailStatus);
  MailReportButton.Visible := MailShowReport and (MailPhase = '');
  MailReportButton.Top := MailStatus.Top + MailStatus.Height + ScaleY(4);
  if MailPassed and (EntryScreen = 'M01') then
    WizardForm.NextButton.Caption := CM('btn_done')
  else if MailPassed then
    WizardForm.NextButton.Caption := CM('btn_next')
  else
    WizardForm.NextButton.Caption := CM('s09_next_test');
  WizardForm.NextButton.Enabled := (MailPhase = '') and (MailFieldsReady or MailPassed);
end;

{ The channel self-test (plan F4d), then R7 again (spec 5.2), then smtp-test with the password
  through the pipe. }
procedure StartMailTest;
var
  Value, OutFile, Code: String;
begin
  MailError.Caption := '';
  MailShowReport := False;
  HideShow;
  if not BgDone then
  begin
    MailPhase := 'waiting';
    RenderMailStatus;
    Exit;
  end;
  OutFile := NewOut('r7');
  RunHelper('r7', RunId, OutFile, '');
  Code := ReadResultCode(OutFile);
  if Code <> 'clear' then
  begin
    MailPhase := '';
    MailShowReport := True;
    if Code = 'policy' then SetMailError(CM('c18_policy'), MailPassword)
    else SetMailError(CM('c18_unreadable'), MailPassword);
    RenderMailStatus;
    Exit;
  end;
  if not MailSelfTested then
  begin
    MailPhase := 'selftest';
    Value := RandomHex(32);
    StartJob('pipe-test', Value, 'selftest:' + GetSHA256OfString(AnsiString(Value)), True, True, 2);
    RenderMailStatus;
    Exit;
  end;
  MailPhase := 'sending';
  StartJob('smtp-test', '{"run_id":"' + RunId + '","mode":"test","host":' + JsonText(MailHost) + ',"port":' + IntToStr(MailPortValue) +
    ',"user":' + JsonText(MailUserValue) + ',"password":' + JsonText(MailPassword.Text) + ',"sender_email":' + JsonText(Trim(MailFrom.Text)) +
    ',"sender_name":' + JsonText(MailSenderValue) + ',"admin_email":' + JsonText(Trim(OrgEmail.Text)) + '}', 'smtp', True, False, 3);
  RenderMailStatus;
end;

procedure ShowMailFailure(Code: String);
begin
  if Code = 'smtp_auth_refused' then
  begin
    if MailGmail.Checked then SetMailError(CM('s09_err_auth_gmail'), MailPassword) else SetMailError(CM('s09_err_auth'), MailPassword);
  end
  else if Code = 'smtp_m365_auth_disabled' then SetMailError(CM('s09_err_m365'), MailPassword)
  else if Code = 'smtp_unreachable' then
  begin
    if MailGmail.Checked then SetMailError(FM1('s09_err_unreachable_known', CM('s09_gmail')), MailGmail)
    else if MailM365.Checked then SetMailError(FM1('s09_err_unreachable_known', CM('s09_m365')), MailGmail)
    else SetMailError(FM1('s09_err_unreachable', MailHost), MailServer);
  end
  else if Code = 'smtp_no_tls' then SetMailError(CM('s09_err_no_tls'), MailSsl)
  else if Code = 'smtp_tls_certificate' then SetMailError(FM1('s09_err_certificate', MailHost), MailServer)
  else if Code = 'smtp_sender_refused' then SetMailError(FM1('s09_err_sender', Trim(MailFrom.Text)), MailFrom)
  else if Code = 'smtp_recipient_refused' then SetMailError(FM1('s09_err_recipient', Trim(OrgEmail.Text)), MailFrom)
  else
  begin
    MailShowReport := True;
    if Code = 'service_logon_failed' then SetMailError(CM('service_logon_failed'), MailPassword)
    else if Code = 'helper_timeout' then SetMailError(CM('av_blocked'), MailPassword)
    else SetMailError(CM('s09_err_other'), MailPassword);
  end;
  if MailError.Visible and MailPassword.CanFocus then
    WizardForm.ActiveControl := MailPassword;
end;

procedure PollMail;
var
  Expected: String;
begin
  if MailPhase = 'waiting' then
  begin
    if BgDone then
      StartMailTest
    else if BgFailed then
    begin
      MailPhase := '';
      RenderMailStatus;
    end;
    Exit;
  end;
  if (MailPhase <> 'selftest') and (MailPhase <> 'sending') then
    Exit;
  if JobState <> JOB_DONE then
    Exit;
  JobState := JOB_IDLE;
  if MailPhase = 'selftest' then
  begin
    Expected := Copy(JobPurpose, Length('selftest:') + 1, 64);
    if (JobText <> '') and (Pos('"sha256":"' + Lowercase(Expected) + '"', Lowercase(JobText)) > 0) then
    begin
      MailSelfTested := True;
      StartMailTest;
    end
    else
    begin
      MailPhase := '';
      RenderMailStatus;
      FailureForm(CM('s09_title'), CM('s09_channel_failed'), False);
    end;
    Exit;
  end;
  MailPhase := '';
  HideShow;
  if JobCode = 'smtp_passed' then
  begin
    MailPassed := True;
    MailProviderName := CM('s09_other');
    if MailGmail.Checked then MailProviderName := CM('s09_gmail');
    if MailM365.Checked then MailProviderName := CM('s09_m365');
  end
  else if (JobCode = 'pipe_unavailable') or (JobCode = 'pipe_untrusted') or (JobCode = 'pipe_timeout') or (JobCode = 'pipe_closed') or (JobCode = 'pipe_failed') then
    FailureForm(CM('s09_title'), CM('s09_channel_failed'), False)
  else
    ShowMailFailure(JobCode);
  RenderMailStatus;
end;

{ ------------------------------------------------------------------------------------------- }
{ S10 Where to keep backups                                                                     }
{ ------------------------------------------------------------------------------------------- }

function OtherDrives: String;
var
  C: Integer;
  Root: String;
  Kind: Longword;
begin
  { A list like "E:2;F:3;" of the drives other than the data drive (2 removable, 3 fixed). }
  Result := '';
  for C := Ord('C') to Ord('Z') do
  begin
    Root := Chr(C) + ':\';
    Kind := GetDriveType(Root);
    if ((Kind = DRIVE_REMOVABLE) or (Kind = DRIVE_FIXED)) and (CompareText(Chr(C) + ':', Copy(DataRoot, 1, 2)) <> 0) and DirExists(Root) then
      Result := Result + Chr(C) + ':' + IntToStr(Kind) + ';';
  end;
end;

procedure BackupRadioClick(Sender: TObject);
begin
  BackupDrive := BackupLetters[TNewRadioButton(Sender).Tag];
  BackupError := '';
  RenderPage(P_BACKUP);
end;

procedure BackupConfirmClick(Sender: TObject);
begin
  WizardForm.NextButton.Enabled := BackupConfirm.Checked;
end;

procedure RenderBackup;
var
  List, Item, Letter, Caption: String;
  Count, Best, I: Integer;
  FreeBytes, BestFree, Ignored: Int64;
  Radio: TNewRadioButton;
  Removable, OnData, Found: Boolean;
begin
  BeginBody(P_BACKUP);
  AddStageLine(2);
  AddText(CM('s10_first'), False);
  List := OtherDrives;
  BackupSeen := List;
  SetArrayLength(BackupLetters, 0);
  Count := 0;
  Best := -1;
  BestFree := -1;
  while Pos(';', List) > 0 do
  begin
    Item := Copy(List, 1, Pos(';', List) - 1);
    List := Copy(List, Pos(';', List) + 1, Length(List));
    SetArrayLength(BackupLetters, Count + 1);
    BackupLetters[Count] := Copy(Item, 1, 2);
    if GetSpaceOnDisk64(Copy(Item, 1, 2) + '\', FreeBytes, Ignored) and (FreeBytes > BestFree) then
    begin
      BestFree := FreeBytes;
      Best := Count;
    end;
    Count := Count + 1;
  end;
  { The last entry: the data drive (spec S10). }
  SetArrayLength(BackupLetters, Count + 1);
  BackupLetters[Count] := Copy(DataRoot, 1, 2);
  Found := False;
  for I := 0 to Count do
    if CompareText(BackupLetters[I], BackupDrive) = 0 then
      Found := True;
  if (BackupDrive = '') or not Found then
  begin
    if Best >= 0 then BackupDrive := BackupLetters[Best] else BackupDrive := '';
  end;
  if Count = 0 then
  begin
    AddText(CM('s10_plug'), True);
    AddText(CM('s10_none'), False);
  end;
  SetArrayLength(BackupRadios, Count + 1);
  Removable := False;
  for I := 0 to Count do
  begin
    Letter := BackupLetters[I];
    if I = Count then
      Caption := FM1('s10_data_drive', Letter)
    else
    begin
      Caption := Letter;
      if GetDriveType(Letter + '\') = DRIVE_REMOVABLE then
        Caption := Caption + ' (' + CM('s10_usb_word') + ')';
      if GetSpaceOnDisk64(Letter + '\', FreeBytes, Ignored) then
        Caption := Caption + '   ' + FM1('s07_free', GB(FreeBytes));
    end;
    Radio := TNewRadioButton.Create(WizardForm);
    Radio.Parent := Cur;
    Radio.Caption := Caption;
    Radio.Tag := I;
    Radio.SetBounds(0, CurY, Cur.Width, ScaleY(18));
    Radio.Checked := CompareText(Letter, BackupDrive) = 0;
    if Radio.Checked and (I < Count) and (GetDriveType(Letter + '\') = DRIVE_REMOVABLE) then
      Removable := True;
    Radio.OnClick := @BackupRadioClick;
    BackupRadios[I] := Radio;
    CurY := CurY + Radio.Height + ScaleY(4);
  end;
  CurY := CurY + ScaleY(6);
  OnData := CompareText(BackupDrive, Copy(DataRoot, 1, 2)) = 0;
  if Removable then
    AddText(CM('s10_usb'), False);
  if BackupError <> '' then
    AddText(BackupError, True);
  WizardForm.NextButton.Caption := CM('btn_next');
  WizardForm.NextButton.Enabled := BackupDrive <> '';
  if OnData then
  begin
    BackupConfirm := TNewCheckBox.Create(WizardForm);
    BackupConfirm.Parent := Cur;
    BackupConfirm.Caption := FM1('s10_confirm', BackupDrive);
    BackupConfirm.SetBounds(0, CurY, Cur.Width, ScaleY(18));
    BackupConfirm.OnClick := @BackupConfirmClick;
    CurY := CurY + BackupConfirm.Height + ScaleY(6);
    WizardForm.NextButton.Enabled := False;
    AddText(CM('s10_later'), False);
  end;
end;

function CheckBackupDrive: Boolean;
var
  OutFile, Code, Text: String;
begin
  OutFile := NewOut('drive-check');
  RunHelper('drive-check', RunId, OutFile, '-Drive ' + Uppercase(BackupDrive));
  Text := ReadText(OutFile);
  Code := ReadResultCode(OutFile);
  Result := Code = 'ready';
  if Code = 'too_small' then
    BackupError := FM2('s10_too_small', BackupDrive, JsonLiteral(Text, 'free_gb'))
  else if not Result then
    BackupError := FM1('s10_not_writable', BackupDrive);
  if not Result then
    RenderPage(P_BACKUP);
end;

{ ------------------------------------------------------------------------------------------- }
{ S11 Ready to install                                                                          }
{ ------------------------------------------------------------------------------------------- }

procedure ChangeClick(Sender: TObject; const Link: String; LinkType: TSysLinkType);
begin
  JumpTarget := Pages[StrToIntDef(Link, P_ORG)].ID;
  WizardForm.BackButton.OnClick(WizardForm.BackButton);
end;

procedure WhatChangesClick(Sender: TObject; const Link: String; LinkType: TSysLinkType);
var
  Text: String;
begin
  Text := CM('s11_what_text');
  if LidChosen then
    Text := Text + ' ' + CM('s11_what_lid');
  InfoForm(CM('s11_what'), Text);
end;

procedure AddRow(Text: String; ChangePage: Integer);
var
  Row: TNewStaticText;
  Link: TNewLinkLabel;
begin
  Row := AddTextTo(Cur, CurY, Text, False);
  Row.Width := Cur.Width - ScaleX(70);
  WizardForm.AdjustLabelHeight(Row);
  if ChangePage >= 0 then
  begin
    Link := TNewLinkLabel.Create(WizardForm);
    Link.Parent := Cur;
    Link.Caption := '<a href="' + IntToStr(ChangePage) + '">' + CM('s11_change') + '</a>';
    Link.Left := Cur.Width - ScaleX(64);
    Link.Top := CurY;
    Link.OnLinkClick := @ChangeClick;
  end;
  CurY := CurY + Row.Height + ScaleY(6);
end;

procedure RenderReady;
var
  Link: TNewLinkLabel;
  Backups: String;
begin
  BeginBody(P_READY);
  AddStageLine(3);
  WizardForm.NextButton.Caption := CM('s11_next');
  if CheckRunning and (CheckFor = 'S11') then
  begin
    AddText(CM('s06_checking'), False);
    AddMarquee;
    WizardForm.NextButton.Enabled := False;
    Exit;
  end;
  if (CheckFor = 'S11') and CheckDone and (CountClass('fix') > 0) then
  begin
    AddCheckItems(True);
    WizardForm.NextButton.Enabled := False;
    Exit;
  end;
  if KeptMode then
  begin
    { Spec 4.3: the summary of the kept installation; the kept data holds the answers. }
    if KeptName <> '' then
      AddRow(FM1('s11_org', KeptName), -1);
    AddRow(FM1('s11_data', DataRoot), -1);
    AddRow(FM1('s11_address', AddressUrl), -1);
    AddRow(CM('s11_edition'), -1);
  end
  else
  begin
    AddRow(FM1('s11_org', Trim(OrgName.Text)), P_ORG);
    AddRow(FM1('s11_admin', Trim(OrgEmail.Text)), P_ORG);
    AddRow(FM2('s11_mail', Trim(MailFrom.Text), MailProviderName), P_EMAIL);
    AddRow(FM1('s11_data', DataRoot), -1);
    Backups := BackupDrive;
    if GetDriveType(BackupDrive + '\') = DRIVE_REMOVABLE then
      Backups := Backups + ' (' + CM('s10_usb_word') + ')';
    AddRow(FM1('s11_backups', Backups), P_BACKUP);
    AddRow(FM1('s11_address', AddressUrl), -1);
    AddRow(CM('s11_edition'), -1);
  end;
  CurY := CurY + ScaleY(6);
  AddText(CM('s11_time'), False);
  Link := AddLink(CM('s11_what'), 0);
  Link.OnLinkClick := @WhatChangesClick;
  { With kept data the install waits for the background steps (the F3 check among them). }
  { W9 review item 2: a background failure (F3 among them) opens with Next. }
  WizardForm.NextButton.Enabled := (not KeptMode) or BgDone or BgFailed;
end;

{ ------------------------------------------------------------------------------------------- }
{ S12 Installing                                                                                }
{ ------------------------------------------------------------------------------------------- }

{ The stage of an engine failure code, for "Setup could not <stage>" (spec 7.2). 0: the
  catalog's "Slate Operations did not start." }
{ A resumed install (spec 4.1): the engine uses its stored answers, and the backup folder exists. }
function ResumedInstall: Boolean;
begin
  Result := (EntryScreen = 'S06') and ((EntryNext = 'S12') or (EntryNext = 'S09'));
end;

function StageOfCode(Code: String): Integer;
begin
  Result := 0;
  if (Pos('pull', Code) > 0) or (Code = 'manifest_invalid') or (Code = 'image_missing') or (Pos('prefetch', Code) > 0) then Result := 1
  else if (Code = 'secrets_failed') or (Code = 'env_render_failed') or (Code = 'bundle_incomplete') or (Code = 'install_state_mismatch') or (Code = 'smtp_not_staged') then Result := 2
  else if Code = 'ca_failed' then Result := 3
  else if Code = 'provisioning_failed' then Result := 4
  else if (Code = 'https_not_ready') or (Pos('api', Code) > 0) then Result := 5
  else if Pos('bootstrap', Code) > 0 then Result := 6
  else if (Pos('backup', Code) > 0) or (Code = 'recovery_key_failed') or (Pos('restic', Code) > 0) then Result := 7;
end;

procedure InstallFail(Stage: Integer; Text: String);
begin
  InstallFailed := True;
  InstallNoRetry := False;
  InstallBackupFailed := Stage = 7;
  if Stage > 0 then
  begin
    InstallFailStage := CM('s12_stage' + IntToStr(Stage));
    if Text = '' then
      Text := FM1('s13_could_not', CM('s12_fail' + IntToStr(Stage)));
  end
  else
    InstallFailStage := CM('s12_stage5');
  if Text = '' then
    Text := CM('s12_not_ready');
  InstallFailText := Text;
  RenderPage(P_INSTALL);
end;

{ The disk limit that prepare-data recorded in the administrator-only state file. }
function VhdSizeGb: Integer;
begin
  Result := StrToIntDef(JsonLiteral(ReadText(ExpandConstant('{commonappdata}\SlateOps\state\install.json')), 'vhd_size_gb'), 0);
  if Result < 25 then
    Result := 25;
end;

procedure InstallNextStep;
var
  OutFile, Code, Answers, Lid, Extra: String;
begin
  InstallSlow := False;
  if InstallStep = 0 then
  begin
    { Plan 3.2 rule 4 and the engine's target rule (parent decision 3): <drive>:\SlateOps-backups. }
    if ResumedInstall or KeptMode then begin InstallStep := 1; InstallNextStep; Exit; end;
    InstallOut := NewOut('prepare-backup');
    InstallOutAt := GetTickCount;
    StartHelper('prepare-backup', RunId, InstallOut, '-Drive ' + Uppercase(BackupDrive));
  end
  else if InstallStep = 1 then
  begin
    OutFile := NewOut('save');
    Extra := '-Stage install_started';
    if KeptMode then
      Extra := Extra + ' -KeptMark';
    RunHelper('save-progress', RunId, OutFile, Extra);
    if ResumedInstall or KeptMode then
      Answers := '{"run_id":"' + RunId + '","version":"' + SetupVersion + '"}'
    else
    begin
      OutFile := NewOut('time-zone');
      RunHelper('time-zone', RunId, OutFile, '');
      Answers := '{"run_id":"' + RunId + '","version":"' + SetupVersion + '","answers":{' +
        '"business_name":' + JsonText(Trim(OrgName.Text)) + ',"slug":' + JsonText(OrgSlug.Text) +
        ',"admin_email":' + JsonText(Trim(OrgEmail.Text)) + ',"admin_username":' + JsonText(OrgUser.Text) +
        ',"public_host":' + JsonText(HostName + '.local') + ',"backup_target":' + JsonText(Uppercase(BackupDrive) + '\SlateOps-backups') +
        ',"data_vhd_max_gb":' + IntToStr(VhdSizeGb) + ',"time_zone":' + JsonText(JsonValue(ReadText(OutFile), 'iana')) + '}}';
    end;
    InstallStep := 2;
    { The answers go in and the result (with the recovery key) comes out through the pipe. }
    StartJob('install', Answers, 'install', True, True, 45);
    Answers := '';
  end
  else if InstallStep = 3 then
  begin
    Lid := '';
    if LidChosen then
      Lid := ' -Lid';
    SaveStringToFile(ExpandConstant('{tmp}\ca.pem'), AnsiString(PemText), False);
    InstallOut := NewOut('windows-steps');
    InstallOutAt := GetTickCount;
    StartHelper('windows-steps', RunId, InstallOut, '-PemFile ' + AddQuotes(ExpandConstant('{tmp}\ca.pem')) + Lid);
  end
  else if InstallStep = 4 then
  begin
    { Plan 10.3 F2 and W8-3: the HTTPS check from Windows runs before the finish. }
    InstallOut := NewOut('https-check');
    InstallOutAt := GetTickCount;
    StartHelper('https-check', RunId, InstallOut, '');
  end;
  RenderPage(P_INSTALL);
end;

procedure PollInstall;
var
  Code, Text: String;
begin
  if (not InstallStarted) or InstallDone or InstallFailed then
    Exit;
  if InstallStep = 2 then
  begin
    if JobSlow and not InstallSlow then
    begin
      InstallSlow := True;
      { Correction 5: at the limit, the task's last result once (spec 7.5). }
      if TaskTimeoutCode = 'service_logon_failed' then
      begin
        RunHelper('job-stop', RunId, NewOut('job-stop'), '');
        JobState := JOB_IDLE;
        ClosePipe;
        InstallFail(0, CM('service_logon_failed'));
        Exit;
      end;
      RenderPage(P_INSTALL);
    end;
    if (JobPurpose <> 'install') or (JobState <> JOB_DONE) then
      Exit;
    JobState := JOB_IDLE;
    Text := JobText;
    JobText := '';
    Code := JsonValue(Text, 'code');
    if Code = '' then
      Code := JobCode;
    if Code <> 'installed' then
    begin
      if Code = 'insufficient_space' then
      begin
        { D3: the server part's own disk; Try again does not help. }
        InstallFail(0, CM('s12_disk_full'));
        InstallNoRetry := True;
        RenderPage(P_INSTALL);
      end
      else if Code = 'service_logon_failed' then InstallFail(0, CM('service_logon_failed'))
      else if Code = 'helper_timeout' then InstallFail(0, CM('av_blocked'))
      else if StageOfCode(Code) = 7 then InstallFail(7, FM1('s12_backup_failed', BackupDrive))
      else InstallFail(StageOfCode(Code), '');
      Exit;
    end;
    { W8-5: the key stays in this process; a run that did not make it returns none, and S14
      then runs new-recovery-key (parent decision 2). }
    KeyText := JsonValue(Text, 'recovery_key');
    PemText := JsonValue(Text, 'ca_certificate_pem');
    SecurityCode := JsonValue(Text, 'ca_security_code');
    Text := '';
    InstallStep := 3;
    InstallNextStep;
    Exit;
  end;
  Code := ReadResultCode(InstallOut);
  if (Code = '') and (Elapsed(InstallOutAt) > HELPER_LIMIT_MS) then
  begin
    { Correction 5: a helper that never answered (spec 7.5 antivirus row). }
    if InstallStep = 0 then InstallFail(7, CM('av_blocked')) else InstallFail(8, CM('av_blocked'));
    Exit;
  end;
  if Code = '' then
    Exit;
  if InstallStep = 0 then
  begin
    if Code <> 'ready' then
    begin
      InstallFail(7, FM1('s12_backup_failed', BackupDrive));
      Exit;
    end;
    InstallStep := 1;
  end
  else if InstallStep = 3 then
  begin
    if Code <> 'done' then
    begin
      if Pos('firewall', Code) > 0 then InstallFail(8, CM('s12_firewall')) else InstallFail(8, '');
      Exit;
    end;
    if SecurityCode = '' then
      SecurityCode := JsonValue(ReadText(InstallOut), 'security_code');
    InstallStep := 4;
  end
  else if InstallStep = 4 then
  begin
    if Code = 'firewall_missing' then
    begin
      InstallFail(8, CM('s12_firewall'));
      Exit;
    end;
    if Code <> 'ok' then
    begin
      InstallFail(8, FM1('s12_https', AddressUrl));
      Exit;
    end;
    InstallDone := True;
    RenderPage(P_INSTALL);
    Exit;
  end;
  InstallNextStep;
end;

{ Correction 3 (spec F4b): Try again in the slow state stops the running job and repeats the
  install step; the engine's journal repeats only the step that did not finish. }
procedure SlowTryAgainClick(Sender: TObject);
begin
  RunHelper('job-stop', RunId, NewOut('job-stop'), '');
  JobState := JOB_IDLE;
  ClosePipe;
  InstallSlow := False;
  InstallStep := 1;
  InstallNextStep;
end;

{ Correction 6 (plan F5, design B10): "Choose another drive" after the backup step failed, with
  the S10 drive list; then drive-check, prepare-backup, set-backup-target, and Try again. }
procedure ChooseDriveClick(Sender: TObject);
var
  Form: TSetupForm;
  Radios: array of TNewRadioButton;
  Letters: array of String;
  List, Item, Chosen, Code: String;
  Count, I, Y: Integer;
  Go, Stop: TNewButton;
  Note: TNewStaticText;
begin
  List := OtherDrives;
  Count := 0;
  Form := CreateCustomForm(ScaleX(380), ScaleY(260), False, False);
  try
    Form.Caption := CM('s10_title');
    Y := ScaleY(12);
    while Pos(';', List) > 0 do
    begin
      Item := Copy(List, 1, 2);
      List := Copy(List, Pos(';', List) + 1, Length(List));
      if CompareText(Item, BackupDrive) <> 0 then
      begin
        SetArrayLength(Radios, Count + 1);
        SetArrayLength(Letters, Count + 1);
        Letters[Count] := Item;
        Radios[Count] := TNewRadioButton.Create(Form);
        Radios[Count].Parent := Form;
        Radios[Count].Caption := Item;
        Radios[Count].Checked := Count = 0;
        Radios[Count].SetBounds(ScaleX(16), Y, Form.ClientWidth - ScaleX(32), ScaleY(18));
        Y := Y + ScaleY(22);
        Count := Count + 1;
      end;
    end;
    if Count = 0 then
    begin
      Note := AddTextTo(Form, Y, CM('s10_plug'), False);
      Note.Left := ScaleX(16);
    end;
    Go := TNewButton.Create(Form);
    Go.Parent := Form;
    Go.Caption := CM('btn_next');
    Go.ModalResult := mrOk;
    Go.Default := True;
    Go.Enabled := Count > 0;
    Go.SetBounds(Form.ClientWidth - ScaleX(210), Form.ClientHeight - ScaleY(36), ScaleX(95), ScaleY(26));
    Stop := TNewButton.Create(Form);
    Stop.Parent := Form;
    Stop.Caption := CM('btn_cancel');
    Stop.ModalResult := mrCancel;
    Stop.Cancel := True;
    Stop.SetBounds(Form.ClientWidth - ScaleX(105), Form.ClientHeight - ScaleY(36), ScaleX(95), ScaleY(26));
    ModalOpen := True;
    if Form.ShowModal <> mrOk then
      Exit;
    Chosen := '';
    for I := 0 to Count - 1 do
      if Radios[I].Checked then
        Chosen := Letters[I];
  finally
    ModalOpen := False;
    Form.Free;
  end;
  if Chosen = '' then
    Exit;
  Code := ReadResultCode(NewOutRun('drive-check', '-Drive ' + Uppercase(Chosen)));
  if Code = 'ready' then
    Code := ReadResultCode(NewOutRun('prepare-backup', '-Drive ' + Uppercase(Chosen)));
  if (Code = 'ready') and (InstallStep >= 2) then
  begin
    { The engine keeps its target from step 12; set-backup-target changes it. }
    if RunJobBlocking('set-backup-target', '{"run_id":"' + RunId + '","backup_target":' + JsonText(Uppercase(Chosen) + '\SlateOps-backups') + '}', RunId, 300) = 'backup_target_set' then
      Code := 'ready'
    else
      Code := 'not_set';
  end;
  if Code <> 'ready' then
  begin
    MsgBox(FM1('s10_not_writable', Chosen), mbError, MB_OK);
    Exit;
  end;
  BackupDrive := Chosen;
  InstallFailed := False;
  if InstallStep >= 2 then
    InstallStep := 1;
  InstallNextStep;
end;

procedure WaitClick(Sender: TObject);
begin
  JobStartedAt := GetTickCount;
  InstallSlow := False;
  RenderPage(P_INSTALL);
end;

procedure RenderInstall;
var
  I, Running: Integer;
  StateWord: String;
  Button: TNewButton;
begin
  BeginBody(P_INSTALL);
  WizardForm.PageNameLabel.Caption := CM('s12_title');
  WizardForm.PageDescriptionLabel.Caption := CM('s12_subtitle');
  WizardForm.NextButton.Caption := CM('btn_next');
  AddStageLine(3);
  if InstallFailed then
  begin
    AddFailure(InstallFailStage, InstallFailText, not InstallNoRetry);
    if InstallBackupFailed then
    begin
      Button := AddButtonAt(CM('s12_choose_drive'), 0, 0);
      Button.OnClick := @ChooseDriveClick;
      CurY := CurY + Button.Height + ScaleY(6);
    end;
    Exit;
  end;
  { Stages 1 to 7 run inside one engine job: the engine reports no step while it runs (TASK-0094
    engine gap), so they show "Now" together; stage 8 is the Windows side. }
  if InstallDone then Running := 9
  else if InstallStep >= 3 then Running := 8
  else Running := 1;
  for I := 1 to 8 do
  begin
    StateWord := '';
    if (I < Running) and ((I = 8) or (Running >= 8)) then StateWord := CM('s12_done_word')
    else if (Running < 8) and (I <= 7) then StateWord := CM('s12_now_word')
    else if I = Running then StateWord := CM('s12_now_word');
    if StateWord <> '' then
      AddText(IntToStr(I) + '. ' + CM('s12_stage' + IntToStr(I)) + '   ' + StateWord, (I = Running) or ((Running < 8) and (I <= 7)))
    else
      AddText(IntToStr(I) + '. ' + CM('s12_stage' + IntToStr(I)), False);
  end;
  if not InstallDone then
    AddMarquee;
  if InstallSlow then
  begin
    AddText(CM('s12_slow'), True);
    Button := AddButtonAt(CM('s12_wait'), 0, 0);
    Button.OnClick := @WaitClick;
    Button := AddButtonAt(CM('btn_try_again'), Button.Width + ScaleX(8), 0);
    Button.OnClick := @SlowTryAgainClick;
    CurY := CurY + Button.Height + ScaleY(6);
    AddReportControls;
  end;
  CurY := CurY + ScaleY(6);
  AddText(CM('s12_box'), False);
  WizardForm.NextButton.Enabled := InstallDone;
end;

{ ------------------------------------------------------------------------------------------- }
{ S14 Save your recovery key                                                                    }
{ ------------------------------------------------------------------------------------------- }

function UsbDrives: String;
var
  C: Integer;
begin
  Result := '';
  for C := Ord('D') to Ord('Z') do
    if (GetDriveType(Chr(C) + ':\') = DRIVE_REMOVABLE) and DirExists(Chr(C) + ':\') then
      Result := Result + Chr(C) + ':;';
end;

{ W80-1: never the backup drive. On a resume the choice of S10 is not known on Windows, so a
  drive that holds a SlateOps-backups folder also counts as a backup drive. }
function IsBackupDrive(Letter: String): Boolean;
begin
  Result := (CompareText(Letter, BackupDrive) = 0) or DirExists(Letter + '\SlateOps-backups');
end;

procedure SaveKeyClick(Sender: TObject);
var
  Letter, Path: String;
  Attributes: Longword;
begin
  if (KeyUsb = nil) or (KeyUsb.ItemIndex < 0) then
    Exit;
  Letter := KeyUsb.Items[KeyUsb.ItemIndex];
  if IsBackupDrive(Letter) then
  begin
    KeyStateText := CM('s14_backup_drive');
    RefreshKeyState;
    Exit;
  end;
  Path := Letter + '\SlateOps-recovery-key.txt';
  Attributes := GetFileAttributes(Path);
  if (Attributes <> $FFFFFFFF) and ((Attributes and FILE_ATTRIBUTE_REPARSE) <> 0) then
    Exit;
  { The person's own save (plan 3.2 check 7); never logged. }
  if SaveStringToFile(Path, AnsiString(CM('s14_title') + #13#10#13#10 + KeyText + #13#10), False) then
    KeyStateText := FM1('s14_saved', Path);
  RefreshKeyState;
end;

{ Prints the key in this process with Windows printing calls: no file, no helper, no
  PowerShell; the fixed job name (W80-3). The spool file is the named exception (W8-5). }
function PrintKey(Printer: String): Boolean;
var
  DC, Font, Old, Name: Longword;
  Info: TDocInfo;
  Dpi, Y: Integer;
begin
  Result := False;
  DC := CreateDC('WINSPOOL', Printer, 0, 0);
  if DC = 0 then
    Exit;
  Name := GlobalAlloc($40, (Length(CM('s14_print_job')) + 1) * 2);
  try
    StrCopyTo(Name, CM('s14_print_job'));
    Info.cbSize := 20;
    Info.lpszDocName := Name;
    Info.lpszOutput := 0;
    Info.lpszDatatype := 0;
    Info.fwType := 0;
    if StartDoc(DC, Info) <= 0 then
      Exit;
    StartPage(DC);
    Dpi := GetDeviceCaps(DC, LOGPIXELSY);
    Y := Dpi;
    Font := CreateFont(-(Dpi * 14) div 72, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 0, 1, 'Segoe UI');
    Old := SelectObject(DC, Font);
    TextOut(DC, Dpi, Y, CM('s14_title'), Length(CM('s14_title')));
    SelectObject(DC, Old);
    DeleteObject(Font);
    Y := Y + (Dpi * 3) div 4;
    Font := CreateFont(-(Dpi * 20) div 72, 0, 0, 0, 700, 0, 0, 0, 1, 0, 0, 0, 1, 'Consolas');
    Old := SelectObject(DC, Font);
    TextOut(DC, Dpi, Y, KeyText, Length(KeyText));
    SelectObject(DC, Old);
    DeleteObject(Font);
    EndPage(DC);
    Result := EndDoc(DC) > 0;
  finally
    GlobalFree(Name);
    DeleteDC(DC);
  end;
end;

procedure PrintKeyClick(Sender: TObject);
var
  Form: TSetupForm;
  Combo: TNewComboBox;
  Go, Stop: TNewButton;
  OutFile, Text, Rest, Name: String;
  Files: array of Boolean;
  Count, Start, Answer: Integer;
begin
  OutFile := NewOut('printers');
  RunHelper('printers', RunId, OutFile, '');
  Text := ReadText(OutFile);
  Form := CreateCustomForm(ScaleX(380), ScaleY(110), False, False);
  try
    Form.Caption := CM('s14_print_title');
    Combo := TNewComboBox.Create(Form);
    Combo.Parent := Form;
    Combo.Style := csDropDownList;
    Combo.SetBounds(ScaleX(10), ScaleY(14), Form.ClientWidth - ScaleX(20), ScaleY(21));
    Count := 0;
    Rest := Text;
    Start := Pos('"name":"', Rest);
    while Start > 0 do
    begin
      Rest := Copy(Rest, Start, Length(Rest));
      Name := JsonValue(Rest, 'name');
      SetArrayLength(Files, Count + 1);
      Files[Count] := Pos('"writes_file":true', Copy(Rest, 1, Pos('}', Rest))) > 0;
      Combo.Items.Add(Name);
      if Pos('"default":true', Copy(Rest, 1, Pos('}', Rest))) > 0 then
        Combo.ItemIndex := Count;
      Count := Count + 1;
      Rest := Copy(Rest, 2, Length(Rest));
      Start := Pos('"name":"', Rest);
    end;
    if (Combo.ItemIndex < 0) and (Count > 0) then
      Combo.ItemIndex := 0;
    Go := TNewButton.Create(Form);
    Go.Parent := Form;
    Go.Caption := CM('s14_print');
    Go.ModalResult := mrOk;
    Go.Default := True;
    Go.SetBounds(Form.ClientWidth - ScaleX(210), Form.ClientHeight - ScaleY(36), ScaleX(95), ScaleY(26));
    Stop := TNewButton.Create(Form);
    Stop.Parent := Form;
    Stop.Caption := CM('btn_cancel');
    Stop.ModalResult := mrCancel;
    Stop.Cancel := True;
    Stop.SetBounds(Form.ClientWidth - ScaleX(105), Form.ClientHeight - ScaleY(36), ScaleX(95), ScaleY(26));
    ModalOpen := True;
    Answer := Form.ShowModal;
    ModalOpen := False;
    if (Answer = mrOk) and (Combo.ItemIndex >= 0) then
    begin
      if Files[Combo.ItemIndex] then
        KeyStateText := CM('s14_file_printer')
      else if PrintKey(Combo.Items[Combo.ItemIndex]) then
        KeyStateText := CM('s14_printed');
    end;
  finally
    ModalOpen := False;
    Form.Free;
  end;
  RefreshKeyState;
end;

procedure KeyCheckClick(Sender: TObject);
begin
  KeyChecked := KeyCheck.Checked;
  WizardForm.NextButton.Enabled := KeyChecked;
end;

function GroupedKey: String;
begin
  Result := KeyText;
  StringChangeEx(Result, '-', '  ', True);
end;

procedure RenderKey;
var
  Panel: TPanel;
  KeyLabel: TNewStaticText;
  Button: TNewButton;
  List, Item: String;
begin
  BeginBody(P_KEY);
  { Design B8: the header comes back after a failure and Try again. }
  WizardForm.PageNameLabel.Caption := CM('s14_title');
  WizardForm.PageDescriptionLabel.Caption := CM('s14_subtitle');
  WizardForm.NextButton.Caption := CM('btn_next');
  WizardForm.CancelButton.Visible := False;
  WizardForm.BackButton.Visible := False;
  if KeyState = 'making' then
  begin
    AddText(CM('s14_making'), True);
    AddMarquee;
    WizardForm.NextButton.Enabled := False;
    Exit;
  end;
  if KeyState = 'failed' then
  begin
    AddFailure(CM('s14_title'), CM('s14_key_failed'), True);
    Exit;
  end;
  { The key is static text that cannot be selected; no Copy button (spec S14). }
  Panel := TPanel.Create(WizardForm);
  Panel.Parent := Cur;
  Panel.BevelOuter := bvLowered;
  Panel.SetBounds(0, CurY, Cur.Width, ScaleY(46));
  KeyLabel := TNewStaticText.Create(WizardForm);
  KeyLabel.Parent := Panel;
  KeyLabel.Font.Name := 'Consolas';
  KeyLabel.Font.Size := 16;
  KeyLabel.Font.Style := [fsBold];
  KeyLabel.ShowAccelChar := False;
  KeyLabel.Caption := GroupedKey;
  KeyLabel.Left := ScaleX(10);
  KeyLabel.Top := ScaleY(10);
  CurY := CurY + Panel.Height + ScaleY(8);
  AddText(CM('s14_text'), False);
  Button := AddButtonAt(CM('s14_print'), 0, 0);
  Button.OnClick := @PrintKeyClick;
  CurY := CurY + Button.Height + ScaleY(8);
  List := UsbDrives;
  KeyUsb := nil;
  if List = '' then
    AddText(CM('s14_no_usb'), False)
  else
  begin
    KeyUsb := TNewComboBox.Create(WizardForm);
    KeyUsb.Parent := Cur;
    KeyUsb.Style := csDropDownList;
    KeyUsb.SetBounds(0, CurY, ScaleX(80), ScaleY(21));
    while Pos(';', List) > 0 do
    begin
      Item := Copy(List, 1, Pos(';', List) - 1);
      List := Copy(List, Pos(';', List) + 1, Length(List));
      KeyUsb.Items.Add(Item);
    end;
    KeyUsb.ItemIndex := 0;
    Button := AddButtonAt(CM('s14_usb'), ScaleX(90), 0);
    Button.OnClick := @SaveKeyClick;
    CurY := CurY + Button.Height + ScaleY(8);
  end;
  if KeyStateText <> '' then
    AddText(KeyStateText, True);
  KeyCheck := TNewCheckBox.Create(WizardForm);
  KeyCheck.Parent := Cur;
  KeyCheck.Caption := CM('s14_check');
  KeyCheck.SetBounds(0, CurY, Cur.Width, ScaleY(18));
  KeyCheck.Checked := KeyChecked;
  KeyCheck.OnClick := @KeyCheckClick;
  { W8-4: Next stays off until the box is checked. }
  WizardForm.NextButton.Enabled := KeyChecked;
end;

procedure StartNewKey;
begin
  KeyState := 'making';
  StartJob('new-recovery-key', '{"run_id":"' + RunId + '"}', 'key', False, True, 10);
end;

procedure PollKey;
begin
  if (KeyState <> 'making') or (JobPurpose <> 'key') or (JobState <> JOB_DONE) then
    Exit;
  JobState := JOB_IDLE;
  KeyText := JsonValue(JobText, 'recovery_key');
  JobText := '';
  if KeyText = '' then KeyState := 'failed' else KeyState := 'shown';
  RenderPage(P_KEY);
end;

{ ------------------------------------------------------------------------------------------- }
{ M01 Slate Operations on this PC (W8: "Send my invitation again" and Save report)              }
{ ------------------------------------------------------------------------------------------- }

procedure InviteClick(Sender: TObject);
var
  Code: String;
begin
  { Design B7: the wait says what happens. }
  MaintLine := CM('m01_sending');
  RenderPage(P_MAINT);
  WizardForm.Refresh;
  Code := RunJobBlocking('resend-invitation', '{"run_id":"' + RunId + '"}', RunId, 120);
  if Code = 'sent' then MaintLine := CM('m01_sent')
  else if Code = 'already_active' then MaintLine := CM('m01_already_active')
  else if Code = 'rate_limited' then MaintLine := CM('m01_rate_limited')
  else MaintLine := CM('m01_failed');
  RenderPage(P_MAINT);
end;


{ ------------------------------------------------------------------------------------------- }
{ Rendering and the timer                                                                       }
{ ------------------------------------------------------------------------------------------- }

{ Index -1: the current page. }
procedure RenderPage(Index: Integer);
var
  I: Integer;
begin
  { Design B2: the S01 Save report line. }
  if (Index < 0) and (WizardForm.CurPageID = wpWelcome) and StateUnsafe then
  begin
    WizardForm.WelcomeLabel2.Caption := CM('s01_state_unsafe') + #13#10#13#10 + ReportLine;
    Exit;
  end;
  { QA B7: the S09 Save report line. }
  if (Index < 0) and (Pages[P_EMAIL] <> nil) and (WizardForm.CurPageID = Pages[P_EMAIL].ID) then
  begin
    RenderMailStatus;
    Exit;
  end;
  if Index < 0 then
  begin
    for I := 0 to P_COUNT - 1 do
      if (Pages[I] <> nil) and (Pages[I].ID = WizardForm.CurPageID) then
        Index := I;
    if Index < 0 then
      Exit;
  end;
  if (Pages[Index] = nil) or (Pages[Index].ID <> WizardForm.CurPageID) then
    Exit;
  if Index = P_CHECK then RenderCheck
  else if Index = P_RESTART then RenderRestart
  else if Index = P_BACK then RenderWelcomeBack
  else if Index = P_DATA then RenderData
  else if Index = P_BACKUP then RenderBackup
  else if Index = P_READY then RenderReady
  else if Index = P_INSTALL then RenderInstall
  else if Index = P_KEY then RenderKey
  else if Index = P_MAINT then RenderMaint
  else if Index = P_UPDATE then RenderUpdate;
end;

procedure TimerTick(H, Msg, Id, Tick: Longword);
var
  Code: String;
begin
  { W9: while the key form is open, only its USB list follows the plugged drives. }
  if KeyFormOpen then
  begin
    if (KeyUsb <> nil) and (UsbDrives <> KeyFormUsbSeen) then
      FillKeyFormUsb;
    Exit;
  end;
  if Ticking or ModalOpen then
    Exit;
  Ticking := True;
  try
    PollJob;
    { Correction 5: the helper waits have time limits (a security program can block a helper). }
    if CheckRunning and (ReadResultCode(CheckOut) = '') and (Elapsed(CheckStartedAt) > CHECK_LIMIT_MS) then
    begin
      CheckRunning := False;
      CheckDone := False;
      CheckVerdict := 'helper_timeout';
      RenderPage(-1);
    end;
    if FixRunning and (ReadResultCode(FixOut) = '') and (Elapsed(FixStartedAt) > HELPER_LIMIT_MS) then
    begin
      FixRunning := False;
      CheckVerdict := 'helper_timeout';
      RenderPage(-1);
    end;
    if CheckRunning and (ReadResultCode(CheckOut) <> '') then
    begin
      CheckRunning := False;
      CheckDone := True;
      CheckText := ReadText(CheckOut);
      ParseCheck(CheckText);
      if (CheckFor = 'S11') and (CountClass('fix') = 0) then
      begin
        RecheckPassed := True;
        WizardForm.NextButton.OnClick(WizardForm.NextButton);
      end
      else
        RenderPage(-1);
    end;
    if FixRunning and (ReadResultCode(FixOut) <> '') then
      FixDone;
    if PrepState = 'working' then
    begin
      Code := ReadResultCode(PrepOut);
      if Code = 'prepared' then
      begin
        if Pos('"restart_needed":true', ReadText(PrepOut)) > 0 then
        begin
          PrepState := 'restart';
          { Spec 7.5 resume_other_user: the progress is saved when "ready to restart" opens. }
          PrepOut := NewOut('save');
          RunHelper('save-progress', RunId, PrepOut, '-Stage feature_restart -SetupPath ' + AddQuotes(ExpandConstant('{srcexe}')));
          ResumeCode := ReadResultCode(PrepOut);
        end
        else
          PrepState := 'done';
        RenderPage(P_RESTART);
      end
      else if Code <> '' then
      begin
        PrepState := 'failed';
        RenderPage(P_RESTART);
      end
      else if Elapsed(PrepStartedAt) > DATA_LIMIT_MS then
      begin
        PrepState := 'failed_av';
        RenderPage(P_RESTART);
      end;
    end;
    if DataStarted and not DataPrepared then
    begin
      Code := ReadResultCode(BgOut);
      if Code = 'ready' then
      begin
        DataPrepared := True;
        DataStarted := False;
        StartBackground;
        WizardForm.NextButton.OnClick(WizardForm.NextButton);
      end
      else if (Code <> '') or (Elapsed(DataStartedAt) > DATA_LIMIT_MS) then
      begin
        DataStarted := False;
        DataError := Code;
        if Code = '' then
          DataError := 'helper_timeout'
        else if (Code <> 'data_folder_parent_unsafe') and (Code <> 'not_empty') and (Code <> 'drive_not_fixed_ntfs') then
          DataError := 'start_failed';
        RenderPage(P_DATA);
      end;
    end;
    PollBackground;
    UpdateBgStatus;
    PollMail;
    PollInstall;
    PollKey;
    PollMaint;
    PollUpdate;
    if (Pages[P_EMAIL] <> nil) and (WizardForm.CurPageID = Pages[P_EMAIL].ID) and (MailChangedAt > 0) and (Elapsed(MailChangedAt) > 1500) then
    begin
      MailChangedAt := 0;
      DetectProvider;
      LayoutMail;
      RenderMailStatus;
    end;
    if (Pages[P_BACKUP] <> nil) and (WizardForm.CurPageID = Pages[P_BACKUP].ID) and (OtherDrives <> BackupSeen) then
      RenderPage(P_BACKUP);
    if (Pages[P_KEY] <> nil) and (WizardForm.CurPageID = Pages[P_KEY].ID) and (KeyState = 'shown') then
      if ((KeyUsb = nil) and (UsbDrives <> '')) or ((KeyUsb <> nil) and (UsbDrives = '')) then
        RenderPage(P_KEY);
  finally
    Ticking := False;
  end;
end;

{ ------------------------------------------------------------------------------------------- }
{ Cancel (spec 4.5)                                                                             }
{ ------------------------------------------------------------------------------------------- }

procedure KeepAndClose(EmailDiscarded: Boolean);
begin
  { Waits for the running step (spec 4.5), then the discard through the pipe and the stage. }
  SaveContinueLater;
end;

procedure ContinueLaterClick(Sender: TObject; const Link: String; LinkType: TSysLinkType);
begin
  KeepAndClose(False);
  ForceClose := True;
  WizardForm.Close;
end;

procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);
var
  OutFile: String;
begin
  Confirm := False;
  { W13b P2-4: M05 never removes anything. It closes when no step is in flight, after a result,
    and in the slow state of the engine job (UpdCanStop). }
  if EntryScreen = 'M05' then
  begin
    Cancel := UpdCanStop;
    Exit;
  end;
  { D-A (spec 4.5): S06 before S14 has no Cancel, as S14; closing keeps the saved stage. }
  if EntryNext = 'S14' then
  begin
    { Only S06 and S14 close; Inno's file copy on the way between them refuses. }
    Cancel := (CurPageID = Pages[P_BACK].ID) or (CurPageID = Pages[P_KEY].ID);
    Exit;
  end;
  if ForceClose or StateUnsafe or (EntryScreen = 'M01') or ((Pages[P_CHECK] <> nil) and (CurPageID = Pages[P_CHECK].ID) and (CheckVerdict = 'not_suitable')) then
  begin
    Cancel := True;
    Exit;
  end;
  if DataPrepared or DataStarted or (EntryNext = 'S08') or (EntryNext = 'S09') or (EntryNext = 'S12') then
  begin
    { Spec 4.5 (W9): "Remove everything setup added" (default) or "Keep it and continue later". }
    case AskCancelChoice of
      1: begin
           RemoveEverything;
           Cancel := True;
         end;
      2: begin
           KeepAndClose(False);
           Cancel := True;
         end;
    else
      Cancel := False;
    end;
    Exit;
  end;
  if (PrepState <> '') or (EntryNext = 'S07') then
  begin
    Cancel := ConfirmBox(CM('cancel_feature'), '', CM('btn_stop_setup'), CM('btn_go_back'));
    if Cancel then
    begin
      OutFile := NewOut('clear');
      RunHelper('clear-resume', RunId, OutFile, '-Cancel');
    end;
    Exit;
  end;
  Cancel := ConfirmBox(CM('cancel_nothing'), '', CM('btn_stop_setup'), CM('btn_go_back'));
  if Cancel and (EntryWelcomeBack or (StateCheckCode = 'safe')) then
  begin
    OutFile := NewOut('clear');
    RunHelper('clear-resume', RunId, OutFile, '-Cancel');
  end;
end;

{ ------------------------------------------------------------------------------------------- }
{ Inno Setup events                                                                             }
{ ------------------------------------------------------------------------------------------- }

function InitializeSetup(): Boolean;
var
  OutFile, Text, VersionText, StateText: String;
begin
#ifdef SelfTest
  { The self-test reads no PC state and starts no helper. }
  SetupVersion := '{#AppVersion}';
  HostName := DnsHostName('');
  RunId := NewRunId('install');
  EntryScreen := 'S01';
  Result := True;
  Exit;
#endif
  ExtractTemporaryFiles('{tmp}\scripts\*.ps1');
  ExtractTemporaryFiles('{tmp}\scripts\lib\*.ps1');
  try
    ExtractTemporaryFiles('{tmp}\scripts\version.json');
  except
    Log('version.json is not in this setup file.');
  end;
  HelperScript := ExpandConstant('{tmp}\scripts\setup-helper.ps1');
  HostName := DnsHostName('');
  VersionText := ReadText(ExpandConstant('{tmp}\scripts\version.json'));
  SetupVersion := JsonValue(VersionText, 'version');
  if SetupVersion = '' then
    SetupVersion := '{#AppVersion}';
  RunId := NewRunId('install');
  { Spec 4.1: before setup reads or writes C:\ProgramData\SlateOps, the folder passes the
    safety check; the first screen comes from Windows-side records only. }
  OutFile := ExpandConstant('{tmp}\state-check.json');
  StateCheckCode := '';
  if RunHelper('state-check', RunId, OutFile, '') then
    StateCheckCode := ReadResultCode(OutFile);
  Log('State folder check: ' + StateCheckCode);
  Text := ReadText(OutFile);
  StateUnsafe := (StateCheckCode = 'unsafe_owner') or (StateCheckCode = 'unsafe');
  EntryScreen := JsonValue(Text, 'screen');
  EntryNext := JsonValue(Text, 'next');
  EntryWelcomeBack := Pos('"welcome_back":true', Text) > 0;
  StateText := Text;
  if (EntryScreen = '') or StateUnsafe then
    EntryScreen := 'S01';
  { W13b P2-1: a newer setup file opens M05; the settings program never updates and opens M01. }
  InstalledVersion := JsonValue(Text, 'installed');
  if (EntryScreen = 'M05') and SETTINGS_BUILD then
    EntryScreen := 'M01';
  if EntryScreen = 'M01' then
    RunId := NewRunId('maintenance')
  else if EntryScreen = 'M05' then
    RunId := NewRunId('update');
  if (EntryNext = 'S08') or (EntryNext = 'S09') or (EntryNext = 'S12') or (EntryNext = 'S14') or (EntryScreen = 'M01') then
  begin
    OutFile := NewOut('account');
    RunHelper('account-sid', RunId, OutFile, '');
    ServiceSid := JsonValue(ReadText(OutFile), 'sid');
    Text := ReadText(ExpandConstant('{commonappdata}\SlateOps\state\install.json'));
    DataRoot := JsonValue(Text, 'data_root');
    DataPrepared := DataRoot <> '';
    { W9 review item 1 (QA W9-B1): a resumed kept reinstall stays kept; S07 does not run again, so
      the saved mark sets the mode. }
    if Pos('"kept":true', StateText) > 0 then
    begin
      KeptState := 'kept';
      KeptUse := True;
      KeptFor := DataRoot;
      { Design N-1: the organization name from kept.json through the helper, as RefreshKept
        reads it; after restore-kept the disk is back in distro (-Restored). }
      if FileExists(AddBackslash(DataRoot) + 'kept\ext4.vhdx') then
        Text := ReadText(NewOutRun('kept-read', '-DataRoot ' + AddQuotes(DataRoot)))
      else
        Text := ReadText(NewOutRun('kept-read', '-DataRoot ' + AddQuotes(DataRoot) + ' -Restored'));
      KeptName := JsonValue(Text, 'business_name');
    end;
    { Done background preparation: the count of this mode (8 kept steps, 7 otherwise). }
    BgIndex := BgCount;
    { Correction 4: a "continue later" saved before the background preparation finished runs it
      again from the step after the account (the server part steps repeat safely). }
    if (EntryNext = 'S08') and (Pos('"background_done":true', StateText) = 0) then
    begin
      BgResume := True;
      { W9 review item 1: no second restore; with the disk back in distro the kept steps go on
        from import-kept. }
      if KeptMode then
      begin
        if FileExists(AddBackslash(DataRoot) + 'kept\ext4.vhdx') then
          BgIndex := 1
        else
          BgIndex := 3;
      end
      else
        BgIndex := 1;
    end;
  end;
  if EntryNext = 'S07' then
    PrepState := 'done';
  { W9: the settings program opens only M01, or saves a report from the Start menu. }
  Result := SettingsEntry;
end;

procedure NoticesClick(Sender: TObject; const Link: String; LinkType: TSysLinkType);
var
  Text: String;
begin
  try
    ExtractTemporaryFiles('{tmp}\THIRD-PARTY-NOTICES.txt');
  except
    Log('The third-party notices are not in this setup file.');
  end;
  Text := ReadText(ExpandConstant('{tmp}\THIRD-PARTY-NOTICES.txt'));
  InfoForm(CM('s04_notices'), Text);
end;

procedure InitializeWizard;
begin
  SetArrayLength(Pages, P_COUNT);
  SetArrayLength(Bodies, P_COUNT);
  Pages[P_MAINT] := CreateCustomPage(wpWelcome, CM('m01_title'), '');
  Pages[P_UPDATE] := CreateCustomPage(Pages[P_MAINT].ID, CM('m05_title'), '');
  Pages[P_CHECK] := CreateCustomPage(Pages[P_MAINT].ID, CM('s02_title'), CM('s02_subtitle'));
  Pages[P_RESTART] := CreateCustomPage(wpLicense, CM('s05_title'), CM('s05_subtitle'));
  Pages[P_BACK] := CreateCustomPage(Pages[P_RESTART].ID, CM('s06_title'), CM('s06_continue'));
  Pages[P_DATA] := CreateCustomPage(Pages[P_BACK].ID, CM('s07_title'), CM('s07_subtitle'));
  Pages[P_ORG] := CreateCustomPage(Pages[P_DATA].ID, CM('s08_title'), CM('s08_subtitle'));
  Pages[P_EMAIL] := CreateCustomPage(Pages[P_ORG].ID, CM('s09_title'), CM('s09_subtitle'));
  Pages[P_BACKUP] := CreateCustomPage(Pages[P_EMAIL].ID, CM('s10_title'), CM('s10_subtitle'));
  Pages[P_READY] := CreateCustomPage(Pages[P_BACKUP].ID, CM('s11_title'), CM('s11_subtitle'));
  Pages[P_INSTALL] := CreateCustomPage(Pages[P_READY].ID, CM('s12_title'), CM('s12_subtitle'));
  Pages[P_KEY] := CreateCustomPage(wpInstalling, CM('s14_title'), CM('s14_subtitle'));
  BuildOrgPage;
  BuildMailPage;
  WizardForm.LicenseLabel1.Caption := CM('s04_subtitle');
  { Spec S04: a link-style button to the third-party notices, under the license text. }
  NoticesLink := TNewLinkLabel.Create(WizardForm);
  NoticesLink.Parent := WizardForm.LicensePage;
  NoticesLink.Caption := '<a href="notices">' + CM('s04_notices') + '</a>';
  NoticesLink.Left := WizardForm.LicenseMemo.Left;
  NoticesLink.Width := WizardForm.LicenseMemo.Width;
  NoticesLink.AdjustHeight;
  WizardForm.LicenseMemo.Height := WizardForm.LicenseMemo.Height - NoticesLink.Height - ScaleY(4);
  NoticesLink.Top := WizardForm.LicenseMemo.Top + WizardForm.LicenseMemo.Height + ScaleY(2);
  NoticesLink.OnLinkClick := @NoticesClick;
  ExtraButton := TNewButton.Create(WizardForm);
  ExtraButton.Parent := WizardForm;
  ExtraButton.Visible := False;
  ExtraButton.SetBounds(WizardForm.BackButton.Left - ScaleX(130), WizardForm.BackButton.Top, ScaleX(120), WizardForm.BackButton.Height);
  WizardReady := True;
#ifdef SelfTest
  RunSelfTest;
  Exit;
#endif
  SetTimer(0, 0, 1000, CreateCallback(@TimerTick));
  if BgResume then
    StartBgStep;
end;

procedure OpenAppClick(Sender: TObject);
begin
  OpenAsUser(AddressUrl, '');
end;

function ShouldSkipPage(PageID: Integer): Boolean;
var
  Resumed: Boolean;
begin
  Result := False;
  if SELF_TEST then
  begin
    Result := True;
    Exit;
  end;
  Resumed := EntryScreen = 'S06';
  { W13b: M05 shows its page, then Inno's file copy and the finished page; no key page. }
  if EntryScreen = 'M05' then
  begin
    Result := (PageID <> Pages[P_UPDATE].ID) and (PageID <> wpFinished);
    Exit;
  end;
  if PageID = Pages[P_UPDATE].ID then
  begin
    Result := True;
    Exit;
  end;
  if EntryScreen = 'M01' then
  begin
    Result := MaintSkip(PageID);
    Exit;
  end;
  { W9: with kept data the answers, the email account, the backup drive and the recovery key
    come from the kept installation (spec 4.3: no S08 to S10, no S14). }
  if KeptMode and ((PageID = Pages[P_ORG].ID) or (PageID = Pages[P_EMAIL].ID) or (PageID = Pages[P_BACKUP].ID) or (PageID = Pages[P_KEY].ID)) then
  begin
    Result := True;
    Exit;
  end;
  if PageID = Pages[P_MAINT].ID then Result := True
  else if PageID = wpWelcome then Result := Resumed or EntryWelcomeBack
  else if (PageID = Pages[P_CHECK].ID) or (PageID = wpLicense) then Result := Resumed
  else if PageID = Pages[P_RESTART].ID then Result := Resumed or not NeedPrepare
  else if PageID = Pages[P_BACK].ID then Result := not Resumed
  else if PageID = Pages[P_DATA].ID then Result := Resumed and (EntryNext <> 'S07')
  else if (PageID = Pages[P_ORG].ID) or (PageID = Pages[P_EMAIL].ID) then Result := Resumed and ((EntryNext = 'S12') or (EntryNext = 'S14'))
  else if (PageID = Pages[P_BACKUP].ID) or (PageID = Pages[P_READY].ID) then Result := Resumed and ((EntryNext = 'S12') or (EntryNext = 'S14') or (EntryNext = 'S09'))
  else if PageID = Pages[P_INSTALL].ID then Result := Resumed and (EntryNext = 'S14');
  { S11 "Change": pages between the target and S11 are passed over in both directions. }
  if (JumpTarget > 0) and (PageID > JumpTarget) and (PageID < Pages[P_READY].ID) then
    Result := True;
  if ReturnToReady and (PageID > WizardForm.CurPageID) and (PageID < Pages[P_READY].ID) then
    Result := True;
end;

{ S15 (spec S15); a procedure, so the W14 self-test draws it too. }
procedure RenderFinishedPage;
var
  Text: String;
begin
  WizardForm.FinishedHeadingLabel.Caption := CM('s15_title');
  { Design B9: after a resume the email address and the security code can be unknown. }
  if KeptMode then
    Text := ''
  else if Trim(OrgEmail.Text) = '' then
    Text := CM('s15_step1_no_address')
  else
    Text := FM1('s15_step1', Trim(OrgEmail.Text));
  if Text <> '' then
    Text := Text + #13#10#13#10;
  Text := Text + CM('s15_step2') + #13#10#13#10 + CM('s15_step3') + #13#10 + 'http://' + HostName + '.local/trust';
  if SecurityCode <> '' then
    Text := Text + #13#10 + FM1('s15_security', SecurityCode);
  WizardForm.FinishedLabel.Caption := Text + #13#10#13#10 + CM('s15_desk') + #13#10#13#10 + CM('s15_starts');
  WizardForm.AdjustLabelHeight(WizardForm.FinishedLabel);
  WizardForm.NextButton.Caption := CM('s15_finish');
  ExtraButton.Parent := WizardForm;
  ExtraButton.Caption := CM('s15_open');
  ExtraButton.Width := WizardForm.CalculateButtonWidth([CM('s15_open')]);
  ExtraButton.OnClick := @OpenAppClick;
  ExtraButton.Visible := True;
end;

procedure CurPageChanged(CurPageID: Integer);
var
  OutFile, Text: String;
begin
  if SELF_TEST then
    Exit;
  WizardForm.BeveledLabel.Caption := '';
  if ExtraButton <> nil then
    ExtraButton.Visible := False;
  WizardForm.NextButton.Visible := True;
  if (JumpTarget > 0) and (CurPageID = JumpTarget) then
  begin
    JumpTarget := 0;
    ReturnToReady := True;
  end;
  if CurPageID = Pages[P_READY].ID then
    ReturnToReady := False;
  if CurPageID = wpWelcome then
  begin
    WizardForm.WelcomeLabel1.Caption := CM('s01_title');
    WizardForm.WelcomeLabel2.Caption := CM('s01_text');
    WizardForm.NextButton.Caption := CM('s01_next');
    if StateUnsafe then
    begin
      WizardForm.WelcomeLabel2.Caption := CM('s01_state_unsafe');
      WizardForm.NextButton.Enabled := False;
      ExtraButton.Caption := CM('btn_save_report');
      ExtraButton.OnClick := @SaveReport;
      ExtraButton.Visible := True;
    end;
  end
  else if CurPageID = wpLicense then
    WizardForm.PageDescriptionLabel.Caption := CM('s04_subtitle')
  else if CurPageID = Pages[P_CHECK].ID then
  begin
    if not CheckDone and not CheckRunning then
      StartCheck('check', 'S02');
    RenderCheck;
  end
  else if CurPageID = Pages[P_RESTART].ID then
  begin
    if PrepState = '' then
      StartPrepare;
    RenderRestart;
  end
  else if CurPageID = Pages[P_BACK].ID then
  begin
    { D-A: no Cancel when S14 comes next. }
    WizardForm.CancelButton.Visible := EntryNext <> 'S14';
    if EntryNext = 'S12' then
      WizardForm.PageDescriptionLabel.Caption := CM('s06_stopped')
    else
      WizardForm.PageDescriptionLabel.Caption := CM('s06_continue');
    if not CheckDone and not CheckRunning then
      StartCheck('recheck', 'S06');
    RenderWelcomeBack;
  end
  else if CurPageID = Pages[P_DATA].ID then
  begin
    { Plan F4a: setup removes the shortcut when this page opens. }
    if not DataPrepared then
    begin
      OutFile := NewOut('clear');
      RunHelper('clear-resume', RunId, OutFile, '');
      if GetArrayLength(DriveLetters) = 0 then
        ReadDataDrives;
    end;
    RenderData;
  end
  else if CurPageID = Pages[P_ORG].ID then
  begin
    WizardForm.NextButton.Caption := CM('btn_next');
    UpdateBgStatus;
  end
  else if CurPageID = Pages[P_EMAIL].ID then
  begin
    { M02 is the S09 form with its own title (spec M02). }
    if EntryScreen = 'M01' then
    begin
      WizardForm.PageNameLabel.Caption := CM('m02_title');
      WizardForm.PageDescriptionLabel.Caption := CM('s09_subtitle');
    end;
    if MailFrom.Text = '' then
      MailFrom.Text := Trim(OrgEmail.Text);
    HideShow;
    DetectProvider;
    LayoutMail;
    RenderMailStatus;
    UpdateBgStatus;
  end
  else if CurPageID = Pages[P_BACKUP].ID then
  begin
    RenderBackup;
    UpdateBgStatus;
  end
  else if CurPageID = Pages[P_READY].ID then
  begin
    RecheckPassed := False;
    CheckFor := '';
    RenderReady;
  end
  else if CurPageID = Pages[P_INSTALL].ID then
  begin
    WizardForm.BackButton.Visible := False;
    if not InstallStarted then
    begin
      InstallStarted := True;
      InstallStep := 0;
      InstallStartedAt := GetTickCount;
      InstallNextStep;
    end;
    RenderInstall;
  end
  else if CurPageID = Pages[P_KEY].ID then
  begin
    if (KeyText = '') and (KeyState = '') then
      StartNewKey
    else if KeyState = '' then
      KeyState := 'shown';
    RenderKey;
  end
  else if CurPageID = Pages[P_MAINT].ID then
  begin
    if MaintPhase = '' then
      StartMaintStatus;
    RenderMaint;
  end
  else if CurPageID = Pages[P_UPDATE].ID then
    RenderUpdate
  else if (CurPageID = wpFinished) and (EntryScreen = 'M05') then
  begin
    WizardForm.FinishedHeadingLabel.Caption := CM('m05_title');
    WizardForm.FinishedLabel.Caption := FM1('m05_done', SetupVersion);
    WizardForm.AdjustLabelHeight(WizardForm.FinishedLabel);
    WizardForm.NextButton.Caption := CM('s15_finish');
  end
  else if CurPageID = wpFinished then
    RenderFinishedPage;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  OutFile: String;
begin
  Result := True;
  if SELF_TEST then
    Exit;
  { W13b: M05 runs on its page; Inno moves on (its file copy) only after the engine succeeded. }
  if (EntryScreen = 'M05') and (CurPageID = Pages[P_UPDATE].ID) then
  begin
    Result := UpdateNext;
    Exit;
  end;
  { W9: M02 and M03 run in maintenance; Inno never moves past them. }
  if (EntryScreen = 'M01') and ((CurPageID = Pages[P_EMAIL].ID) or (CurPageID = Pages[P_BACKUP].ID)) then
  begin
    Result := MaintNext(CurPageID);
    Exit;
  end;
  { W9: with kept data a background failure (the F3 check among them) shows on S11. }
  if (CurPageID = Pages[P_READY].ID) and BgFailed then
  begin
    Result := CheckBackground;
    Exit;
  end;
  if CurPageID = wpWelcome then
    Result := not StateUnsafe
  else if CurPageID = Pages[P_CHECK].ID then
  begin
    if CheckDrawFailed then
    begin
      CheckDrawFailed := False;
      StartCheck('check', 'S02');
      RenderCheck;
      Result := False;
    end
    else
      Result := CheckDone and (CheckVerdict = 'ready');
  end
  else if CurPageID = Pages[P_RESTART].ID then
  begin
    if PrepState = 'failed' then
    begin
      StartPrepare;
      RenderRestart;
      Result := False;
    end
    else if PrepState = 'restart' then
    begin
      OutFile := NewOut('restart');
      RunHelper('restart', RunId, OutFile, '');
      ForceClose := True;
      WizardForm.Close;
      Result := False;
    end
    else
      Result := PrepState = 'done';
  end
  else if CurPageID = Pages[P_BACK].ID then
    Result := CheckDone and (CountClass('fix') = 0)
  else if CurPageID = Pages[P_DATA].ID then
  begin
    { Spec 7.5: setup stays on S07 until the data folder step answers. }
    Result := DataPrepared;
    if not DataPrepared and not DataStarted then
      StartDataPrepare;
  end
  else if CurPageID = Pages[P_ORG].ID then
    Result := CheckOrg and CheckBackground
  else if CurPageID = Pages[P_EMAIL].ID then
  begin
    { Design B4: a background failure is reachable from S09 (the S13 form on Next). }
    if BgFailed then
    begin
      Result := CheckBackground;
      Exit;
    end;
    Result := MailPassed;
    if not MailPassed then
    begin
      if MailFieldsReady then
        StartMailTest;
    end
    else
      Result := CheckBackground;
  end
  else if CurPageID = Pages[P_BACKUP].ID then
    Result := CheckBackground and CheckBackupDrive
  else if CurPageID = Pages[P_READY].ID then
  begin
    { The quick recheck on Install (spec 5.2). }
    Result := RecheckPassed;
    if not RecheckPassed then
    begin
      StartCheck('recheck', 'S11');
      RenderReady;
    end;
  end
  else if CurPageID = Pages[P_INSTALL].ID then
  begin
    if InstallFailed then
    begin
      InstallFailed := False;
      if InstallStep = 2 then
        InstallStep := 1;
      InstallNextStep;
      Result := False;
    end
    else
      Result := InstallDone;
  end
  else if CurPageID = Pages[P_KEY].ID then
  begin
    if KeyState = 'failed' then
    begin
      StartNewKey;
      RenderKey;
      Result := False;
      Exit;
    end;
    Result := KeyChecked;
    if Result then
    begin
      OutFile := NewOut('save');
      RunHelper('save-progress', RunId, OutFile, '-Stage key_saved');
      KeyText := '';
    end;
  end
  else if CurPageID = wpFinished then
    ExtraButton.Visible := False;
end;

function BackButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = Pages[P_EMAIL].ID then
    HideShow;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  OutFile: String;
begin
  if CurStep = ssPostInstall then
  begin
    { W13b P2-4: an update keeps the saved stage; it makes no new recovery key. }
    if EntryScreen <> 'M05' then
    begin
      OutFile := NewOut('save');
      RunHelper('save-progress', RunId, OutFile, '-Stage install_finished');
    end;
    { A kept installation needs no new key (spec 4.3): the key of the first install still opens
      its backups; the kept folder goes once the disk runs again. }
    if KeptMode then
    begin
      NewOutRun('kept-done', '');
      RunHelper('save-progress', RunId, NewOut('save'), '-Stage key_saved');
    end;
    { W9-5 (plan 10.3 F4c): Modify in Settings, Apps opens the maintenance program. Inno writes
      its uninstall key in the 64-bit view before ssPostInstall. }
    if HAS_SETTINGS then
    begin
      RegWriteStringValue(HKLM64, UNINSTALL_KEY, 'ModifyPath', AddQuotes(ExpandConstant('{commonappdata}\SlateOps\settings\SlateOpsSettings.exe')));
      RegWriteDWordValue(HKLM64, UNINSTALL_KEY, 'NoModify', 0);
    end;
  end;
end;

procedure DeinitializeSetup;
begin
  ClosePipe;
end;
