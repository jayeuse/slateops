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
  { DEC-0041 (AC-W2): the limits of the S12 helper steps (the backup folder, the save, the time
    zone, R7, the Windows steps, the HTTPS check) and of the install job (minutes). }
  INSTALL_STEP_MS = 600000;
  INSTALL_JOB_MINUTES = 45;
  DATA_LIMIT_MS = 1800000;
  { DEC-0041 (AC-W1): the S07 folder check reads only; a security program that holds the helper
    shows the antivirus message after this time. }
  DATA_CHECK_MS = 60000;
  SUBMIT_LIMIT_MS = 120000;
  { W14-D8: the job-result helper answers in this time, and it is asked every 15 s while this
    process does not see the result itself. }
  JOB_ANSWER_MS = 120000;
  JOB_ASK_MS = 15000;
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
  { DEC-0041 (AC-W7): WM_UPDATEUISTATE with MAKEWPARAM(UIS_SET, UISF_HIDEFOCUS). }
  WM_UPDATEUISTATE = $0128;
  UIS_SET_HIDEFOCUS = $00010001;

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
{ W14-D3 (6.1 L1): the read-only verdict box shows no text cursor. }
function HideCaret(Wnd: HWND): Boolean;
  external 'HideCaret@user32.dll stdcall';
{ W14-D3 (6.1 L10): the drive name that Windows shows (the volume label). }
function GetVolumeInformation(Root, Name: String; NameSize: Longword; Serial, MaxLength, Flags: Longword; FsName: String; FsNameSize: Longword): Boolean;
  external 'GetVolumeInformationW@kernel32.dll stdcall';

var
  HelperScript, StateCheckCode, RunId, SetupVersion, ServiceSid, HostName: String;
  EntryScreen, EntryNext: String;
  EntryWelcomeBack, StateUnsafe, ForceClose, ModalOpen, Ticking, KeyTicking: Boolean;
  { DEC-0041 (AC-W4): the state-check found an earlier run that did not finish; setup removes
    it before S01. }
  EntryCleanup: Boolean;
  Pages: array of TWizardPage;
  Bodies: array of TPanel;
  Cur: TPanel;
  CurY, OutSeq: Integer;
  ExtraButton: TNewButton;
  NoticesLink: TNewLinkLabel;
  { W14-D3 (6.1 L6): the page buttons on Inno's own pages, built once (S01, S15). }
  S01Report, S15Open: TNewButton;
  S01Line: TNewStaticText;
  S15Steps: array of TNewStaticText;

  { S02, S06, S11: the check }
  CheckOut, CheckVerdict, CheckText, CheckFor: String;
  CheckRunning, CheckDone, NeedPrepare, RestartNeeded, LidChosen, FixRunning: Boolean;
  { W14-D1: S02 shows the draw failure; Next runs the check again. }
  CheckDrawFailed: Boolean;
  Items: array of TCheckItem;
  FixOut, FixAction: String;

  { S05 }
  PrepOut, PrepState, ResumeCode: String;
  { W14-D3 (rule 2.8): what the helper did: feature and WSL codes, and the failed step's key. }
  PrepFeature, PrepWsl, PrepFailKey: String;
  PrepDetails: Boolean;

  { S07 and the background preparation }
  DriveLetters: array of String;
  DriveFree: array of Int64;
  DriveRadios: array of TNewRadioButton;
  DataRoot, DataError, DataErrorValue: String;
  { DEC-0041 (AC-W1): the folder that the S07 check passed (with -UseKept when KeptChecked). }
  DataChecked: String;
  KeptChecked: Boolean;
  DataPrepared, DataStarted, BgFailed: Boolean;
  BgIndex: Integer;
  BgOut, BgCode: String;

  { S08 (DEC-0041 AC-W1): organization name, your name, email address, password and its second
    entry. The password exists only in these fields and in the pipe (AC-W5). }
  OrgName, OrgEmail, OrgYourName, OrgPassword, OrgConfirm: TNewEdit;
  OrgShow: TNewCheckBox;
  OrgError: TNewStaticText;
  { W14-D3 (6.1 L9): the S08 field blocks, laid out by LayoutOrg. }
  OrgNameLabel, OrgNameHelp, OrgEmailLabel, OrgEmailHelp, OrgYourNameLabel, OrgPasswordLabel, OrgPasswordHelp, OrgConfirmLabel: TNewStaticText;
  OrgErrorAfter: TControl;
  { W14-D3 (6.1): S08 and S09 sit on the page surface; their stage line is built once and the
    forms start under it. }
  OrgTop, MailTop: Integer;

  { S09 }
  MailFrom, MailPassword, MailServer, MailPort, MailUser, MailSender: TNewEdit;
  { DEC-0040, DEC-0041 (AC-W6): Gmail and Other only. }
  MailGmail, MailOther, MailSsl, MailStartTls: TNewRadioButton;
  MailShow: TNewCheckBox;
  MailNote, MailStatus, MailError, MailPasswordLabel, MailServerLabel, MailPortLabel, MailSecurityLabel, MailUserLabel, MailSenderLabel, MailFromLabel, MailProviderLabel: TNewStaticText;
  MailHelpLink, MailMoreLink: TNewLinkLabel;
  { W14-D3 (6.1 L9): MailMeasure measures the radio captions, so each radio is as wide as its
    text. }
  MailMeasure: TNewStaticText;
  MailPassed, MailSelfTested, MailOutlook, MailMore, MailSaved: Boolean;
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
  InstallStarted, InstallDone, InstallFailed: Boolean;
  InstallFailText, InstallFailStage, InstallOut, PemText, SecurityCode: String;
  InstallStartedAt: Cardinal;
  { DEC-0041 (AC-W2): the time zone for the install job while the channel self-test and R7 run
    first (AC-W5: the password crosses only a tested channel). }
  InstallTz: String;

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
  { W14-D8: when the job-result helper last started, and when it was asked. }
  JobPollAt, JobResultAt: Cardinal;
  PipeHandle: Longword;
  PipeFrame, PipeOutput: AnsiString;
  PipeConnected, PipeExpectOutput: Boolean;
  { W8 correction 1: the job's own flag; PollPipe clears PipeExpectOutput when the service closes. }
  JobPipeOut: Boolean;
  FailureStatus: TNewStaticText;
  CheckStartedAt, FixStartedAt, PrepStartedAt, BgStartedAt, InstallOutAt, DataStartedAt: Cardinal;
  MailShowReport: Boolean;
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
  { W14-D9: Save report runs from the timer: phase linux (the log-bundle job), collect, zip. }
  ReportPhase, ReportRun, ReportOut: String;
  ReportAt, ReportStepAt: Cardinal;
  ReportForm: TSetupForm;

  { W14-D5: the progress block of the page (spec 6.1). The body panel owns these labels, so
    BeginBody clears them; the timer changes only their captions. }
  WaitTime, WaitNow, StepLabel, ReportLabel: TNewStaticText;
  WaitSince: Cardinal;
  WaitLimit, WaitKind: String;
  WaitDrawn: Integer;
  { W14-D5: the last progress line of the running engine job (7.6), from its standard error. }
  JobStepJob, JobStepKey, JobRunId: String;
  JobStepNumber, JobStepTotal: Integer;
  { W14-D9: the last job-result answer named a sign-in failure of the account (spec 7.5). }
  JobLogonFailed: Boolean;
  { AC-W8: the job-result helper answered something other than "done" for this job. }
  JobAnswered: Boolean;
  { W14-D9: the step runner, one short helper action at a time from the timer. StepFor names
    what follows (StepFinished); StepLine is its one line. }
  StepAction, StepOut, StepFor, StepLine, StepLastCode: String;
  StepNumber, StepTotal: Integer;
  StepAt, StepLimitMs: Cardinal;
  { W14-D9: the setup file's parts, one file per timer tick. }
  ExtractList, ExtractFor: String;
  TimerStarted: Boolean;
  { W14-D9: waits that moved to the timer. }
  BgPending, BgPendingOut: String;
  BgPendingAt, BgBeganAt, KeyStartedAt, UpdStartedAt: Cardinal;
  BackupCheckedDrive, RestartExtra: String;
  KeySavedDone, RestartFirmware: Boolean;
  RestartIndex: Integer;
  { The start of a wait with several steps (7.6: the time counts from the start of the wait). }
  MailAt, MaintAt, CdAt: Cardinal;
  { W14-D3 (6.1 L5): the button row being built on the page. }
  RowX, RowHeight: Integer;
  { W14-D3 (6.1 L11): Inno's button row as Inno placed it: default width, right edge, gaps. }
  BtnDefaultW, BtnRight, BtnGapBN, BtnGapNC: Integer;
  { W14-D3: the buttons of the page body and of the forms, and the last verdict box, for the
    self-test's caption and color checks. }
  BodyButtons, FormButtons: array of TNewButton;
  LastVerdict: TNewMemo;
  { The pinned WSL version of this setup (version.json), for the 7.6 lines. }
  WslVersion: String;
  { DEC-0041 (AC-W3): the removal form; while it is open the timer runs only the removal. }
  RemoveForm: TSetupForm;
  RemovePanel: TPanel;
  RemoveTicking: Boolean;

  { W13b part 2: M05 Update (Maintenance.iss). JobRaw is the job-result text of the last job. }
  InstalledVersion, UpdPhase, UpdNext, UpdOut, UpdState, UpdNeedsGb, UpdFailText, UpdFailStage, JobRaw: String;
  UpdAt: Cardinal;
  UpdFailed, UpdRetry, UpdWaiting, UpdSlowShown, UpdEngineDone: Boolean;

procedure RenderPage(Index: Integer); forward;
procedure SaveReport(Sender: TObject); forward;
{ W14-D5 and W14-D9, in Maintenance.iss: what follows a step, and the page's current wait. }
procedure StepFinished(ForTag, Code: String); forward;
function WaitStage(Kind: String): Integer; forward;
function WaitActionText(Kind: String): String; forward;
function PageLineText: String; forward;
procedure StartBackground; forward;
{ DEC-0041, in Maintenance.iss: the stage names, M02's set-email, the removal. }
function StageName(Stages: String; Index: Integer): String; forward;
procedure StartSetEmail; forward;
function RunRemoval(Why: String): Boolean; forward;
function BgDone: Boolean; forward;
{ W9, in Maintenance.iss. }
procedure RefreshKeyState; forward;
procedure FillKeyFormUsb; forward;
procedure RenderMaint; forward;
procedure StartMaintStatus; forward;
procedure PollMaint; forward;
function MaintNext(PageID: Integer): Boolean; forward;
function MaintSkip(PageID: Integer): Boolean; forward;
{ W14-D9, in Maintenance.iss. }
procedure StartCloseFlow(Flow, After: String); forward;
procedure PollCloseFlow; forward;
function CloseFlowRunning: Boolean; forward;
function SettingsEntry: Boolean; forward;
#ifdef SelfTest
procedure RunSelfTest; forward;
#endif
{ S07 and S12 read the kept mode. }
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
  DeleteFile(OutFile + '.progress');
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

function FM4(Key, A, B, C, D: String): String;
begin
  Result := FmtMessage(CM(Key), [A, B, C, D]);
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
  { W14-D3 (6.1 L1): the grey bands were the panel's own color (clBtnFace), which every text
    control on it takes. The panel now has the page surface's color, so its texts and the
    verdict box paint the page color; S08 and S09, built on the surface, never showed grey. }
  Bodies[Index].ParentBackground := False;
  Bodies[Index].Color := Pages[Index].SurfaceColor;
  Bodies[Index].SetBounds(0, 0, Pages[Index].SurfaceWidth, Pages[Index].SurfaceHeight);
  Cur := Bodies[Index];
  CurY := 0;
  RowX := 0;
  SetArrayLength(BodyButtons, 0);
  LastVerdict := nil;
  { W14-D5: the old panel took its labels with it. }
  WaitTime := nil;
  WaitNow := nil;
  StepLabel := nil;
  ReportLabel := nil;
  WaitKind := '';
  WaitDrawn := 0;
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

{ W14-D3 (6.1 L4): every element ends with the 4 px of a block; ItemGap and BlockGap add the
  rest to 12 px between items and 16 px between blocks. }
function AddText(S: String; Bold: Boolean): TNewStaticText;
begin
  Result := AddTextTo(Cur, CurY, S, Bold);
  CurY := CurY + Result.Height + ScaleY(4);
end;

procedure ItemGap;
begin
  CurY := CurY + ScaleY(8);
end;

procedure BlockGap;
begin
  CurY := CurY + ScaleY(12);
end;

{ W14-D3 (6.1 L1): the verdict box keeps the focus for a screen reader but shows no cursor. }
procedure VerdictCaretOff(Sender: TObject);
begin
  HideCaret(TNewMemo(Sender).Handle);
end;

procedure VerdictKeyUp(Sender: TObject; var Key: Word; Shift: TShiftState);
begin
  HideCaret(TNewMemo(Sender).Handle);
end;

procedure FocusVerdict(Verdict: TNewMemo);
begin
  if (Verdict = nil) or not Verdict.CanFocus then
    Exit;
  WizardForm.ActiveControl := Verdict;
  HideCaret(Verdict.Handle);
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
  { W14-D3 (6.1 L1): the page color, not the window's grey. }
  Result.Color := Cur.Color;
  Result.Font.Style := [fsBold];
  Result.SetBounds(0, CurY, Cur.Width, Height);
  Result.Text := S;
  Result.OnClick := @VerdictCaretOff;
  Result.OnKeyUp := @VerdictKeyUp;
  LastVerdict := Result;
  CurY := CurY + Result.Height + ScaleY(4);
end;

function AddButtonAt(Caption: String; Left, Tag: Integer): TNewButton;
begin
  Result := TNewButton.Create(WizardForm);
  Result.Parent := Cur;
  Result.Caption := Caption;
  Result.Tag := Tag;
  Result.SetBounds(Left, CurY, WizardForm.CalculateButtonWidth([Caption]), WizardForm.NextButton.Height);
  SetArrayLength(BodyButtons, GetArrayLength(BodyButtons) + 1);
  BodyButtons[GetArrayLength(BodyButtons) - 1] := Result;
end;

{ W14-D3 (6.1 L5): the buttons of one item or block in one row, left to right, 8 px apart. }
function AddRowButton(Caption: String; Tag: Integer): TNewButton;
begin
  Result := AddButtonAt(Caption, RowX, Tag);
  RowX := RowX + Result.Width + ScaleX(8);
  RowHeight := Result.Height;
end;

procedure EndRow;
begin
  if RowX > 0 then
    CurY := CurY + RowHeight + ScaleY(4);
  RowX := 0;
end;

{ DEC-0041 (AC-W7): a link label never draws the dotted focus box. It takes no keyboard focus
  from Tab, and its own UI state hides the focus box (WM_UPDATEUISTATE, UIS_SET with
  UISF_HIDEFOCUS) for the focus that a click gives it. Every TNewLinkLabel goes through here
  once it has its parent. }
procedure NoFocusBox(Link: TNewLinkLabel);
begin
  Link.TabStop := False;
  SendMessage(Link.Handle, WM_UPDATEUISTATE, UIS_SET_HIDEFOCUS, 0);
end;

function AddLink(Caption: String; Tag: Integer): TNewLinkLabel;
begin
  Result := TNewLinkLabel.Create(WizardForm);
  Result.Parent := Cur;
  NoFocusBox(Result);
  Result.Caption := '<a href="' + IntToStr(Tag) + '">' + Caption + '</a>';
  Result.Tag := Tag;
  Result.Left := 0;
  Result.Top := CurY;
  Result.Width := Cur.Width;
  Result.AdjustHeight;
  CurY := CurY + Result.Height + ScaleY(4);
end;

{ W14-D3 (6.1 L7): a line that ends with its link ("23 checks passed. Show all checks"). The
  text is plain; only Caption is the link. }
function AddLinkLine(Text, Caption: String; Tag: Integer): TNewLinkLabel;
var
  Plain: String;
begin
  Plain := Text;
  StringChangeEx(Plain, '<', '(', True);
  StringChangeEx(Plain, '>', ')', True);
  Result := TNewLinkLabel.Create(WizardForm);
  Result.Parent := Cur;
  NoFocusBox(Result);
  Result.Caption := Plain + ' <a href="' + IntToStr(Tag) + '">' + Caption + '</a>';
  Result.Tag := Tag;
  Result.Left := 0;
  Result.Top := CurY;
  Result.Width := Cur.Width;
  Result.AdjustHeight;
  CurY := CurY + Result.Height + ScaleY(4);
end;

{ ------------------------------------------------------------------------------------------- }
{ W14-D5: the progress block (spec 2.4, 6.1, 7.6): stages, the current action, the time so far  }
{ ------------------------------------------------------------------------------------------- }

{ Minutes and seconds since Since: "4:12". }
function TimeText(Since: Cardinal): String;
var
  Seconds: Cardinal;
begin
  Seconds := (GetTickCount - Since) div 1000;
  Result := IntToStr(Seconds div 60) + ':' + Copy(IntToStr(100 + (Seconds mod 60)), 2, 2);
end;

function TimeLine: String;
begin
  if WaitLimit <> '' then
    Result := FM2('wait_time_limit', TimeText(WaitSince), WaitLimit)
  else
    Result := FM1('wait_time', TimeText(WaitSince));
end;

{ TASK-0097 AC-8 (Designer 4): an action inside a one-line text loses its own full stop, so the
  line reads "... to drive D:" and then the time, not "D:." and then the time. }
function NoStop(Text: String): String;
begin
  Result := Text;
  if (Length(Result) > 0) and (Copy(Result, Length(Result), 1) = '.') then
    Result := Copy(Result, 1, Length(Result) - 1);
end;

{ The one-line form: "3 of 7: <action>, then the time"; with one stage only the action and the
  time (copy wait_line, wait_line_one). }
function OneLine(Number, Total: Integer; Action: String; Since: Cardinal): String;
begin
  if (Total > 1) and (Number > 0) then
    Result := FM4('wait_line', IntToStr(Number), IntToStr(Total), NoStop(Action), TimeText(Since))
  else
    Result := FM2('wait_line_one', NoStop(Action), TimeText(Since));
end;

{ The full form. Stages: names split by "|" ('' for a wait with one stage, which shows no list);
  Current: the stage that runs now (1-based). Action: the current action, shown as given; ''
  shows none. Since: the start of the wait. Limit: the "This can take ..." sentence, or ''.
  Kind names the wait for WaitStage and WaitActionText (Maintenance.iss). }
procedure AddProgress(Kind, Stages: String; Current: Integer; Action: String; Since: Cardinal; Limit: String);
var
  Rest, Name, StateWord: String;
  I, Cut: Integer;
  Row: TNewStaticText;
begin
  Rest := Stages;
  I := 0;
  while Rest <> '' do
  begin
    I := I + 1;
    Cut := Pos('|', Rest);
    if Cut = 0 then
    begin
      Name := Rest;
      Rest := '';
    end
    else
    begin
      Name := Copy(Rest, 1, Cut - 1);
      Rest := Copy(Rest, Cut + 1, Length(Rest));
    end;
    if I < Current then StateWord := CM('s12_done_word')
    else if I = Current then StateWord := CM('s12_now_word')
    else StateWord := CM('wait_next_word');
    Row := AddTextTo(Cur, CurY, StateWord, I = Current);
    Row.Width := ScaleX(52);
    Row := AddTextTo(Cur, CurY, Name, I = Current);
    Row.Left := ScaleX(60);
    Row.Width := Cur.Width - ScaleX(60);
    WizardForm.AdjustLabelHeight(Row);
    CurY := CurY + Row.Height + ScaleY(2);
  end;
  if I > 0 then
    CurY := CurY + ScaleY(4);
  WaitKind := Kind;
  WaitDrawn := Current;
  WaitNow := nil;
  if Action <> '' then
    WaitNow := AddText(Action, False);
  WaitSince := Since;
  WaitLimit := Limit;
  WaitTime := nil;
  { Since 0: the wait is over (all stages done), so no time line. }
  if Since <> 0 then
    WaitTime := AddText(TimeLine, False);
end;

{ W14-D3 (6.1 L12): the bottom band of the page in page coordinates (the place of the old status
  line, DEC-0041 removed it). Content on S08 to S11 ends 12 px above it. }
function StatusBandTop: Integer;
begin
  Result := WizardForm.Bevel.Top - ScaleY(22) - WizardForm.InnerNotebook.Top;
end;

{ The page's one line for a short wait (7.6 one-line form); the timer keeps it current. }
procedure AddStepLine;
var
  Text: String;
begin
  Text := PageLineText;
  if Text = '' then
    Exit;
  StepLabel := AddText(Text, False);
end;

{ The stage line under the header on S02 to S12 (spec 6.1) on Parent at Top; returns the top of
  the content under it (16 px under the line). }
function StageLineAt(Parent: TWinControl; Top, Stage: Integer): Integer;
var
  Labels: array of TNewStaticText;
  I, Left: Integer;
begin
  SetArrayLength(Labels, 3);
  Left := 0;
  for I := 1 to 3 do
  begin
    Labels[I - 1] := TNewStaticText.Create(WizardForm);
    Labels[I - 1].Parent := Parent;
    Labels[I - 1].ShowAccelChar := False;
    Labels[I - 1].Caption := CM('stage_' + IntToStr(I));
    if I < 3 then
      Labels[I - 1].Caption := Labels[I - 1].Caption + '  ' + CM('stage_sep') + '  ';
    if I = Stage then
      Labels[I - 1].Font.Style := [fsBold];
    Labels[I - 1].Left := Left;
    Labels[I - 1].Top := Top;
    Left := Left + Labels[I - 1].Width;
  end;
  { 6.1 L4: the stage line is a block (16 px under it). }
  Result := Top + Labels[0].Height + ScaleY(16);
end;

procedure AddStageLine(Stage: Integer);
begin
  CurY := StageLineAt(Cur, CurY, Stage);
end;

{ ------------------------------------------------------------------------------------------- }
{ W14-D3 (6.1 L11): Inno's button row. Each button is as wide as its caption needs, never        }
{ narrower than Inno's default; the row stays right aligned with Inno's gaps. Every caption      }
{ change goes through a setter below, so no caption is cut ("end test ema", screenshot 10).      }
{ ------------------------------------------------------------------------------------------- }

function RowButtonWidth(Caption: String): Integer;
begin
  Result := WizardForm.CalculateButtonWidth([Caption]);
  if Result < BtnDefaultW then
    Result := BtnDefaultW;
end;

procedure PlaceRowButton(Button: TNewButton; Right: Integer);
var
  Width: Integer;
begin
  Width := RowButtonWidth(Button.Caption);
  if (Button.Width <> Width) or (Button.Left <> Right - Width) then
    Button.SetBounds(Right - Width, Button.Top, Width, Button.Height);
end;

procedure LayoutButtonRow;
var
  Right: Integer;
begin
  if (BtnDefaultW = 0) or not WizardReady then
    Exit;
  { Cancel keeps its slot when it is hidden, as Inno keeps it. }
  PlaceRowButton(WizardForm.CancelButton, BtnRight);
  Right := WizardForm.CancelButton.Left - BtnGapNC;
  PlaceRowButton(WizardForm.NextButton, Right);
  Right := WizardForm.NextButton.Left - BtnGapBN;
  PlaceRowButton(WizardForm.BackButton, Right);
  { S05 "Restart later" sits left of Back (6.1 L6 exception). }
  if (ExtraButton <> nil) and ExtraButton.Visible then
    PlaceRowButton(ExtraButton, WizardForm.BackButton.Left - BtnGapNC);
end;

procedure SetNextCaption(Caption: String);
begin
  WizardForm.NextButton.Caption := Caption;
  LayoutButtonRow;
end;

procedure SetCancelCaption(Caption: String);
begin
  WizardForm.CancelButton.Caption := Caption;
  LayoutButtonRow;
end;

procedure SetExtraCaption(Caption: String);
begin
  ExtraButton.Caption := Caption;
  LayoutButtonRow;
end;

{ W14-D3 (6.1 L11): a form's right-aligned buttons (Left may be nil) as wide as their captions
  need, never narrower than they were, 8 px apart, with the form's right margin kept. }
procedure FitFormRow(Form: TSetupForm; Left, Right: TNewButton);
var
  Margin, Width: Integer;
begin
  Margin := Form.ClientWidth - (Right.Left + Right.Width);
  Width := Form.CalculateButtonWidth([Right.Caption]);
  if Width < Right.Width then
    Width := Right.Width;
  Right.SetBounds(Form.ClientWidth - Margin - Width, Right.Top, Width, Right.Height);
  if Left = nil then
    Exit;
  Width := Form.CalculateButtonWidth([Left.Caption]);
  if Width < Left.Width then
    Width := Left.Width;
  Left.SetBounds(Right.Left - ScaleX(8) - Width, Left.Top, Width, Left.Height);
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
    FitFormRow(Form, nil, Button);
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

{ W14-D5: Exec copies the engine's standard error to this file while the job runs. }
function JobErrFile: String;
begin
  Result := '';
  if JobRequestId <> '' then
    Result := ExpandConstant('{commonappdata}\SlateOps\svc-out\') + Lowercase(JobRequestId) + '.stderr.txt';
end;

{ W14-D5: the helper writes its progress lines beside its result file. }
function ProgressFileOf(OutFile: String): String;
begin
  Result := OutFile + '.progress';
end;

{ True when S is not empty and every character of S is in Allowed. }
function AllChars(S, Allowed: String): Boolean;
var
  I: Integer;
begin
  Result := S <> '';
  for I := 1 to Length(S) do
    if Pos(Copy(S, I, 1), Allowed) = 0 then
      Result := False;
end;

{ One progress line (7.6): "progress <job> <number>/<total> <key> <state>", fields split by one
  space. The engine's lines match ^progress [a-z-]+ [0-9]+/[0-9]+ [a-z_]+ (start|done)$ (TASK-0097
  W14-D5 engine part); the helper's keys may hold digits too (c12). Any other line is ignored. }
function ParseProgressLine(Line: String; Helper: Boolean; var Job, Key, State: String; var Number, Total: Integer): Boolean;
var
  Parts: array of String;
  Rest, Letters, Digits, KeyChars, Count: String;
  Cut, Slash: Integer;
begin
  Result := False;
  Letters := 'abcdefghijklmnopqrstuvwxyz';
  Digits := '0123456789';
  SetArrayLength(Parts, 0);
  Rest := Line;
  while GetArrayLength(Parts) < 6 do
  begin
    SetArrayLength(Parts, GetArrayLength(Parts) + 1);
    Cut := Pos(' ', Rest);
    if Cut = 0 then
    begin
      Parts[GetArrayLength(Parts) - 1] := Rest;
      Break;
    end;
    Parts[GetArrayLength(Parts) - 1] := Copy(Rest, 1, Cut - 1);
    Rest := Copy(Rest, Cut + 1, Length(Rest));
  end;
  if (GetArrayLength(Parts) <> 5) or (Parts[0] <> 'progress') then
    Exit;
  if not AllChars(Parts[1], Letters + '-') then
    Exit;
  Count := Parts[2];
  Slash := Pos('/', Count);
  if (Slash = 0) or not AllChars(Copy(Count, 1, Slash - 1), Digits) or not AllChars(Copy(Count, Slash + 1, Length(Count)), Digits) then
    Exit;
  KeyChars := Letters + '_';
  if Helper then
    KeyChars := KeyChars + Digits;
  if not AllChars(Parts[3], KeyChars) then
    Exit;
  if (Parts[4] <> 'start') and (Parts[4] <> 'done') then
    Exit;
  Job := Parts[1];
  Number := StrToIntDef(Copy(Count, 1, Slash - 1), 0);
  Total := StrToIntDef(Copy(Count, Slash + 1, Length(Count)), 0);
  Key := Parts[3];
  State := Parts[4];
  Result := True;
end;

{ The last complete progress line of FileName (only lines that end with a line break count, so a
  line that is still being written is not read). The file can be open for writing in the other
  process (W14-D5), so it is read with LoadStringFromLockedFile; the last 8 KB are enough. Job,
  Key, Number and Total keep their values when no line matches. }
procedure ReadProgressFile(FileName: String; Helper: Boolean; var Job, Key: String; var Number, Total: Integer);
var
  Raw: AnsiString;
  Text, Line, J, K, S: String;
  N, T, Stop: Integer;
begin
  if (FileName = '') or not FileExists(FileName) then
    Exit;
  if not LoadStringFromLockedFile(FileName, Raw) then
    Exit;
  Text := String(Raw);
  if Length(Text) > 8192 then
    Text := Copy(Text, Length(Text) - 8191, 8192);
  Stop := Pos(#10, Text);
  while Stop > 0 do
  begin
    Line := Copy(Text, 1, Stop - 1);
    Text := Copy(Text, Stop + 1, Length(Text));
    if Copy(Line, Length(Line), 1) = #13 then
      Line := Copy(Line, 1, Length(Line) - 1);
    if ParseProgressLine(Line, Helper, J, K, S, N, T) then
    begin
      Job := J;
      Key := K;
      Number := N;
      Total := T;
    end;
    Stop := Pos(#10, Text);
  end;
end;

{ The step that the running engine job reports (7.6 engine keys). }
procedure ReadJobProgress;
begin
  ReadProgressFile(JobErrFile, False, JobStepJob, JobStepKey, JobStepNumber, JobStepTotal);
end;

{ The action line of one step (7.6): copy step_<job>_<key> with the values A, B and C; '' when
  the copy has no line for it (the caller then shows the stage name, never the key). }
function StepText(Job, Key, A, B, C: String): String;
var
  Name: String;
begin
  Result := '';
  if (Job = '') or (Key = '') then
    Exit;
  Name := 'step_' + Job + '_' + Key;
  StringChangeEx(Name, '-', '_', True);
  if HasMessage(Name) then
    Result := FM3(Name, A, B, C);
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
  JobStepJob := '';
  JobStepKey := '';
  JobStepNumber := 0;
  JobStepTotal := 0;
  JobLogonFailed := False;
  JobAnswered := False;
  { Save report's log-bundle job keeps the report's run ID (its bundle file is named by it). }
  JobRunId := RunId;
  if Purpose = 'report' then
    JobRunId := ReportRun;
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
  Result := StartHelper('job', JobRunId, JobOut, Extra);
  if not Result then
  begin
    JobState := JOB_DONE;
    JobCode := 'helper_failed';
    ClosePipe;
  end;
end;

{ The code of a job that gave no result in its time limit: the task's last result, from the
  job-result answers that the poll asks for every 15 s (W14-D9: no blocking helper call); a
  sign-in failure of the account is service_logon_failed (plan 10.7, spec 7.5). }
function JobTimeoutCode: String;
begin
  if JobLogonFailed then
    Result := 'service_logon_failed'
  else
    Result := 'job_timeout';
end;

{ One step of the runner, from the timer. Done when JobState = JOB_DONE. }
procedure PollJob;
var
  Code, Text: String;
  Found: Boolean;
begin
  if (JobState = JOB_IDLE) or (JobState = JOB_DONE) then
    Exit;
  if JobRunId = '' then
    JobRunId := RunId;
  PollPipe;
  ReadJobProgress;
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
    JobPollAt := GetTickCount;
    Log('Job ' + JobName + ' ' + JobRequestId + ': submitted.');
  end;
  if JobState = JOB_WAIT then
  begin
    if JobResultOut = '' then
    begin
      { Cheap check first: the result file names this request (it holds no secret). }
      Text := Lowercase(ReadText(ExecResultFile));
      Found := Pos('"request_id":"' + Lowercase(JobRequestId) + '"', Text) > 0;
      { AC-W8 (W14-D8, CI engineer): the limit holds whether or not this process sees the
        result, so a handover that the job-result helper never confirms ends at the limit with
        its message instead of asking forever. DEC-0041 (AC-W2): the install job has its limit
        too. W13b P2-5: a running update has no verdict at a limit; the engine has its own (M05,
        Preserved). }
      if (JobPurpose <> 'update') and (Elapsed(JobStartedAt) > JobLimitMs) then
      begin
        { W8 correction 5: at the limit, the task's last result once (spec 7.5). }
        Log('Job ' + JobName + ': no result in its time.');
        JobCode := JobTimeoutCode;
        JobState := JOB_DONE;
        ClosePipe;
        Exit;
      end;
      { W14-D8: the job-result helper reads the result itself every 15 s too, so a result that
        this process does not see (W14-D8 on the owner's PC) is still collected. }
      if ((not Found) or JobAnswered) and (Elapsed(JobPollAt) < JOB_ASK_MS) then
        Exit;
      if (not Found) and FileExists(ExecResultFile) and (Text = '') then
        Log('Job ' + JobName + ': the result file exists but this process cannot read it.');
      JobPollAt := GetTickCount;
      JobResultAt := GetTickCount;
      JobResultOut := NewOut('job-result');
      if not StartHelper('job-result', JobRunId, JobResultOut, '-RequestId ' + JobRequestId) then
      begin
        Log('Job ' + JobName + ': the job-result helper did not start.');
        JobCode := 'helper_failed';
        JobState := JOB_DONE;
        ClosePipe;
      end;
      Exit;
    end;
    Code := ReadResultCode(JobResultOut);
    if (Code = '') and (Elapsed(JobResultAt) > JOB_ANSWER_MS) then
    begin
      Log('Job ' + JobName + ': the job-result helper gave no answer in its time.');
      JobCode := 'helper_timeout';
      JobState := JOB_DONE;
      ClosePipe;
      Exit;
    end;
    if Code = '' then
      Exit;
    if Code <> 'done' then
    begin
      { AC-W8: every answer other than "done" is logged with its code; the next ask waits
        JOB_ASK_MS, and the job limit above ends the wait. }
      Log('Job ' + JobName + ': the job-result helper answered ' + Code + '.');
      JobAnswered := True;
      { W14-D9: the answer "waiting" names a sign-in failure of the account (spec 7.5). }
      JobLogonFailed := Pos('"logon_failed":true', ReadText(JobResultOut)) > 0;
      JobResultOut := '';
      Exit;
    end;
    Log('Job ' + JobName + ': result collected.');
    ReadJobProgress;
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

{ ------------------------------------------------------------------------------------------- }
{ W14-D9: the step runner. One short helper action at a time runs from the timer; StepFinished  }
{ (Maintenance.iss) takes its code. A step past its limit ends as helper_timeout, so every      }
{ continuation shows a message instead of waiting on.                                           }
{ ------------------------------------------------------------------------------------------- }

function StepRunning: Boolean;
begin
  Result := StepFor <> '';
end;

{ Starts Action; False when another step runs (the caller's button stays as it is). Line,
  Number and Total make the one line (7.6); Line '' shows none. }
function RunStep(Action, Extra, ForTag, Line: String; Number, Total: Integer; LimitMs: Cardinal): Boolean;
begin
  Result := False;
  if StepFor <> '' then
  begin
    Log('Step ' + ForTag + ' not started: ' + StepFor + ' runs.');
    Exit;
  end;
  StepAction := Action;
  StepFor := ForTag;
  StepLine := Line;
  StepNumber := Number;
  StepTotal := Total;
  StepLimitMs := LimitMs;
  StepAt := GetTickCount;
  StepOut := NewOut(Action);
  if not StartHelper(Action, RunId, StepOut, Extra) then
    StepOut := '';
  Log('Step ' + ForTag + ': ' + Action + ' started.');
  Result := True;
end;

{ From the timer. }
procedure PollStep;
var
  Code, ForTag: String;
begin
  if StepFor = '' then
    Exit;
  if StepOut = '' then
    Code := 'helper_failed'
  else
    Code := ReadResultCode(StepOut);
  if (Code = '') and (Elapsed(StepAt) > StepLimitMs) then
  begin
    Log('Step ' + StepFor + ': no result in its time.');
    Code := 'helper_timeout';
  end;
  if Code = '' then
    Exit;
  ForTag := StepFor;
  StepFor := '';
  StepLastCode := Code;
  Log('Step ' + ForTag + ': ' + Code + '.');
  StepFinished(ForTag, Code);
end;

{ ------------------------------------------------------------------------------------------- }
{ W14-D9: the setup file's parts, one file per timer tick. ExtractTemporaryFiles holds the      }
{ window while it unpacks, so each file gets its own tick and the page shows the stage first.   }
{ ------------------------------------------------------------------------------------------- }

{ Patterns: file patterns in the payload folder of the temporary folder, split by "|". }
procedure QueueExtract(Patterns, ForTag: String);
begin
  ExtractList := Patterns;
  ExtractFor := ForTag;
end;

function ExtractRunning: Boolean;
begin
  Result := ExtractFor <> '';
end;

{ Unpacks the first file of the list. }
procedure ExtractNextPart;
var
  Name: String;
  Cut: Integer;
begin
  Cut := Pos('|', ExtractList);
  if Cut = 0 then
  begin
    Name := ExtractList;
    ExtractList := '';
  end
  else
  begin
    Name := Copy(ExtractList, 1, Cut - 1);
    ExtractList := Copy(ExtractList, Cut + 1, Length(ExtractList));
  end;
  if Name = '' then
    Exit;
  try
    ExtractTemporaryFiles('{tmp}\payload\' + Name);
  except
    Log('The setup file has no part ' + Name + '.');
  end;
end;

{ From the timer: one file, or the end of the list. The first tick only shows the stage. }
procedure PollExtract;
var
  ForTag: String;
begin
  if ExtractFor = '' then
    Exit;
  { Cancel: nothing more is unpacked, and no step follows. }
  if CloseFlowRunning then
  begin
    ExtractList := '';
    ExtractFor := '';
    Exit;
  end;
  if ExtractList <> '' then
  begin
    ExtractNextPart;
    Exit;
  end;
  ForTag := ExtractFor;
  ExtractFor := '';
  StepFinished(ForTag, 'extracted');
end;


{ ------------------------------------------------------------------------------------------- }
{ Save report (plan 10.6; DEC-0033)                                                             }
{ ------------------------------------------------------------------------------------------- }

{ Plan 10.6 item 3: the wizard removes from the staged files every file that holds a password it
  holds: the email password (M02) and the administrator's password (S08, DEC-0041). }
procedure DropFilesHolding(Staging, Password: String);
var
  Find: TFindRec;
  Content: AnsiString;
begin
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

procedure DropFilesWithPassword(Staging: String);
begin
  if MailPassword <> nil then
    DropFilesHolding(Staging, MailPassword.Text);
  if OrgPassword <> nil then
    DropFilesHolding(Staging, OrgPassword.Text);
end;

{ W14-D9: Save report runs from the timer (7.6 "Save report", one line beside its button):
  2 of 4 the server part's logs (the log-bundle job, when the server part answers and no other
  job runs; W8 correction 3), 3 of 4 the setup logs with passwords and personal details removed
  (report-collect and the wizard's own password check), 4 of 4 the file on the desktop
  (report-zip). Stage 1, the copy of the setup log, takes no time. Each helper step has its
  limit; a report that could not be saved says so. }
procedure ReportCollect;
var
  InnoCopy: String;
begin
  InnoCopy := ExpandConstant('{tmp}\setup-program.log');
  if ExpandConstant('{log}') <> '' then
    CopyFile(ExpandConstant('{log}'), InnoCopy, False);
  ReportPhase := 'collect';
  ReportStepAt := GetTickCount;
  ReportOut := NewOut('report');
  StartHelper('report-collect', ReportRun, ReportOut, '-InputFile ' + AddQuotes(InnoCopy));
end;

function ReportProgressText: String;
var
  Action: String;
begin
  if ReportPhase = 'linux' then
  begin
    Action := '';
    if JobPurpose = 'report' then
      Action := StepText(JobStepJob, JobStepKey, '', '', '');
    if Action = '' then
      Action := CM('report_stage2');
    Result := OneLine(2, 4, Action, ReportAt);
  end
  else if ReportPhase = 'collect' then
    Result := OneLine(3, 4, CM('report_stage3'), ReportAt)
  else
    Result := OneLine(4, 4, CM('report_stage4'), ReportAt);
end;

{ The line goes to the label that the page or form gave (ReportLabel), the S13 form, S01 and the
  settings program's report form. }
procedure ShowReportLine;
var
  Text: String;
begin
  if ReportPhase <> '' then
    Text := ReportProgressText
  else
    Text := ReportLine;
  if ReportLabel <> nil then
    ReportLabel.Caption := Text;
  if FailureStatus <> nil then
  begin
    FailureStatus.Caption := Text;
    FailureStatus.AdjustHeight;
  end;
  if WizardReady and (WizardForm.CurPageID = wpWelcome) and StateUnsafe and (S01Line <> nil) then
  begin
    S01Line.Caption := Text;
    WizardForm.AdjustLabelHeight(S01Line);
  end;
end;

{ W14-D9: the server part's logs need the one Exec job. They are left out (report.txt says so)
  while a job runs or a flow can start one soon, so the report never takes the job of a page. }
function ReportJobAllowed: Boolean;
begin
  Result := (StepFor = '') and (MaintPhase = '') and (MailPhase = '') and not CloseFlowRunning
    and not (DataPrepared and not BgDone and not BgFailed)
    and not (InstallStarted and not InstallDone and not InstallFailed)
    and not ((EntryScreen = 'M05') and (UpdPhase <> '') and not UpdFailed);
end;

procedure SaveReport(Sender: TObject);
begin
  if ReportPhase <> '' then
    Exit;
  ReportRun := NewRunId('report');
  ReportAt := GetTickCount;
  ReportPath := '';
  { The Linux part, when the server part answers (plan 10.6 item 1). }
  if (ServiceSid <> '') and not JobRunning and ReportJobAllowed then
  begin
    ReportPhase := 'linux';
    StartJob('log-bundle', '{"run_id":"' + ReportRun + '"}', 'report', False, False, 2);
  end
  else
    ReportCollect;
  ShowReportLine;
  { The page draws the line beside its Save report button. }
  if WizardReady and not ModalOpen then
    RenderPage(-1);
end;

{ The end of Save report: the result line, saved or not. }
procedure EndReport;
begin
  ReportPhase := '';
  if ReportPath <> '' then
    ReportLine := FM1('report_saved', ExtractFileName(ReportPath))
  else
    ReportLine := CM('report_failed');
  ShowReportLine;
  { The settings program's report form closes by itself (TForm.Close ends its modal loop; the
    script classes give a form no ModalResult). }
  if ReportForm <> nil then
    ReportForm.Close;
  { Design B2: the page draws the result line with "Show in folder". }
  if WizardReady and not ModalOpen then
    RenderPage(-1);
end;

{ From the timer, also while a modal form is open (the S13 form). }
procedure PollReport;
var
  Code: String;
begin
  if ReportPhase = '' then
    Exit;
  if ReportPhase = 'linux' then
  begin
    if (JobPurpose = 'report') and (JobState <> JOB_DONE) and (JobState <> JOB_IDLE) then
    begin
      ShowReportLine;
      Exit;
    end;
    if JobPurpose = 'report' then
    begin
      JobState := JOB_IDLE;
      JobPurpose := '';
    end;
    ReportCollect;
    ShowReportLine;
    Exit;
  end;
  Code := ReadResultCode(ReportOut);
  if (Code = '') and (Elapsed(ReportStepAt) < HELPER_LIMIT_MS) then
  begin
    ShowReportLine;
    Exit;
  end;
  if ReportPhase = 'collect' then
  begin
    { TASK-0097 AC-9 (Security S97-1): only a finished collect goes on. After the time limit, or
      with any other code, report-collect may still write its staging folder, so no password
      check and no zip run; the report is not saved. }
    if Code <> 'collected' then
    begin
      if Code = '' then
        Code := 'helper_timeout';
      Log('Save report: the collect step ended with ' + Code + '; no report is saved.');
      ReportPath := '';
      EndReport;
      Exit;
    end;
    DropFilesWithPassword(ExpandConstant('{tmp}\report-') + ReportRun);
    ReportPhase := 'zip';
    ReportStepAt := GetTickCount;
    ReportOut := NewOut('report');
    StartHelper('report-zip', ReportRun, ReportOut, '');
    ShowReportLine;
    Exit;
  end;
  ReportPath := JsonValue(ReadText(ReportOut), 'path');
  EndReport;
end;

procedure ShowReportClick(Sender: TObject; const Link: String; LinkType: TSysLinkType);
begin
  if ReportPath <> '' then
    OpenAsUser(ExpandConstant('{win}\explorer.exe'), '/select,' + AddQuotes(ReportPath));
end;

{ W14-D3 (6.1 L5): Save report in the row being built; the caller ends the row. }
procedure AddReportButton;
var
  Button: TNewButton;
begin
  Button := AddRowButton(CM('btn_save_report'), 0);
  Button.OnClick := @SaveReport;
end;

{ W14-D9: the line while the report is saved; W14-D3 (6.1 L7): its result ends with "Show in
  folder". }
procedure AddReportLine;
var
  Link: TNewLinkLabel;
begin
  if (ReportPhase = '') and (ReportPath <> '') and (ReportLine <> '') then
  begin
    Link := AddLinkLine(ReportLine, CM('btn_show_in_folder'), 0);
    Link.OnLinkClick := @ShowReportClick;
  end
  else if (ReportLine <> '') or (ReportPhase <> '') then
  begin
    ReportLabel := AddText(ReportLine, False);
    ShowReportLine;
  end;
end;

{ The Save report button in its own row and, once saved, the result line. }
procedure AddReportControls;
begin
  AddReportButton;
  EndRow;
  AddReportLine;
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
  { W14-D3 (6.1 L4, L5): the actions 12 px under the text, in one row: Save report. }
  ItemGap;
  AddReportButton;
  EndRow;
  AddReportLine;
  if TryAgain then
  begin
    SetNextCaption(CM('btn_try_again'));
    WizardForm.NextButton.Enabled := True;
  end
  else
    WizardForm.NextButton.Enabled := False;
  FocusVerdict(Verdict);
end;

{ W14-D3 (6.1 L11): a form button as wide as its caption needs, never narrower than Width. }
function FormButton(Form: TSetupForm; Caption: String; Width, ModalCode: Integer): TNewButton;
begin
  Result := TNewButton.Create(Form);
  Result.Parent := Form;
  Result.Caption := Caption;
  { ModalCode 0: the button does not close the form. }
  Result.ModalResult := ModalCode;
  if Form.CalculateButtonWidth([Caption]) > Width then
    Width := Form.CalculateButtonWidth([Caption]);
  Result.Width := Width;
  Result.Height := ScaleY(26);
  SetArrayLength(FormButtons, GetArrayLength(FormButtons) + 1);
  FormButtons[GetArrayLength(FormButtons) - 1] := Result;
end;

function FormText(Form: TSetupForm; Y: Integer; S: String; Bold: Boolean): TNewStaticText;
begin
  Result := AddTextTo(Form, Y, S, Bold);
  Result.Left := ScaleX(14);
  Result.Width := Form.ClientWidth - ScaleX(28);
  WizardForm.AdjustLabelHeight(Result);
end;

{ A failure of background work, in a modal form with the S13 layout (spec 4.1). W14-D3 (6.1 L4,
  L5, L11): the texts flow with the rhythm, the report line takes the height of its text, and
  the buttons sit in one row at their caption widths: [Try again] [Save report] ... [Close]. }
function BuildFailureForm(Stage, WhatHappened: String; TryAgain: Boolean): TSetupForm;
var
  Form: TSetupForm;
  Text: TNewStaticText;
  Again, Report, CloseButton: TNewButton;
  Y: Integer;
begin
  Form := CreateCustomForm(ScaleX(440), ScaleY(220), False, False);
  Form.Caption := CM('s13_title');
  Y := ScaleY(14);
  Text := FormText(Form, Y, Stage, True);
  Y := Y + Text.Height + ScaleY(4);
  Text := FormText(Form, Y, WhatHappened, False);
  Y := Y + Text.Height + ScaleY(4);
  if TryAgain then
  begin
    Text := FormText(Form, Y, CM('s13_what'), False);
    Y := Y + Text.Height + ScaleY(4);
  end;
  { Design B2: SaveReport writes its result line here. }
  FailureStatus := FormText(Form, Y + ScaleY(8), '', False);
  Y := Y + ScaleY(8) + ScaleY(36);
  Again := FormButton(Form, CM('btn_try_again'), ScaleX(90), mrRetry);
  Again.Enabled := TryAgain;
  Again.Default := TryAgain;
  Report := FormButton(Form, CM('btn_save_report'), ScaleX(90), 0);
  Report.OnClick := @SaveReport;
  CloseButton := FormButton(Form, CM('btn_close'), ScaleX(90), mrCancel);
  CloseButton.Cancel := True;
  Form.ClientHeight := Y + ScaleY(16) + Again.Height + ScaleY(14);
  Again.SetBounds(ScaleX(14), Form.ClientHeight - ScaleY(14) - Again.Height, Again.Width, Again.Height);
  Report.SetBounds(Again.Left + Again.Width + ScaleX(8), Again.Top, Report.Width, Report.Height);
  CloseButton.SetBounds(Form.ClientWidth - ScaleX(14) - CloseButton.Width, Again.Top, CloseButton.Width, CloseButton.Height);
  Result := Form;
end;

{ Returns True for Try again. }
function FailureForm(Stage, WhatHappened: String; TryAgain: Boolean): Boolean;
var
  Form: TSetupForm;
begin
  Form := BuildFailureForm(Stage, WhatHappened, TryAgain);
  try
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
  { DEC-0037 (TASK-0097 AC-7): setup never suggests BitLocker, so C24 "off" has no message and
    no key is looked up for it (older check results gave it as Advice). }
  if (Item.Id = 'C24') and (Item.Code = 'off') then
  begin
    Result := '';
    Exit;
  end;
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
  { W14-D5: the item list shows the fix's one line. }
  RenderPage(-1);
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
  entries), then restart (spec 5.3, F4a). W14-D9: the save and the restart run from the timer
  (7.6 "S02 and S06 restart": "Saving your progress...", then "Restarting this PC..."). }
procedure CheckRestartConfirm(Code: String);
var
  Firmware: Boolean;
  Index: Integer;
  Text, Extra, Title: String;
begin
  Firmware := RestartFirmware;
  Index := RestartIndex;
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
  { DEC-0041: the check restart comes before Install, so no server work is on this PC yet; the
    next start removes what an earlier step added (AC-W4) and starts at S01. }
  Extra := '';
  if Firmware then
    Extra := '-Firmware';
  if RunStep('restart', Extra, 'cr-restart', CM('later_restarting'), 0, 0, HELPER_LIMIT_MS) then
    RenderPage(-1);
end;

{ The check restart (S02, the S11 recheck, the C04 firmware restart): the progress and the
  resume entries first. AC-W9: after S05 (in this run, or after its restart) the mark prepared
  lets the resume go on after S05, so nothing that S05 turned on is removed. }
procedure CheckRestart(Firmware: Boolean; Index: Integer);
var
  Extra: String;
begin
  RestartFirmware := Firmware;
  RestartIndex := Index;
  Extra := '-Stage check_restart -SetupPath ' + AddQuotes(ExpandConstant('{srcexe}'));
  if (PrepState <> '') or (EntryNext = 'S07') then
    Extra := Extra + ' -Prepared';
  if RunStep('save-progress', Extra, 'cr-save', CM('later_saving'), 0, 0, HELPER_LIMIT_MS) then
    RenderPage(-1);
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
    FitFormRow(Form, Go, Stop);
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
  Button := AddRowButton(Caption, Index * 16);
  Button.OnClick := @ItemButtonClick;
  Button.Enabled := not FixRunning and not StepRunning;
  if Caption2 <> '' then
  begin
    Button := AddRowButton(Caption2, Index * 16 + 1);
    Button.OnClick := @ItemButtonClick;
    Button.Enabled := not FixRunning and not StepRunning;
  end;
  EndRow;
end;

{ The check item that a fix action belongs to. }
function FixItemId: String;
begin
  if FixAction = 'fix-network-private' then Result := 'C10'
  else if FixAction = 'fix-mdns' then Result := 'C17'
  else Result := 'C29';
end;

{ W14-D3 (6.1 L2, L3): one bold heading "<result word>: <check name>", its text directly under
  it, then its buttons in one row. }
procedure AddItem(Index: Integer);
begin
  AddText(ItemWord(Items[Index]) + ': ' + ItemName(Items[Index]), True);
  if (Items[Index].Id = 'C22') and LidChosen then
    AddText(CM('c22_chosen'), False)
  else
    AddText(ItemMessage(Items[Index]), False);
  { W14-D5 (7.6 "S02 fixes"): the running fix's one line in its item, in place of its buttons. }
  if FixRunning and (Items[Index].Id = FixItemId) then
    StepLabel := AddText(PageLineText, False)
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
{ W14-D3 (6.1 L8): an item is drawn only while it can still fit above the bottom block. }
function ItemFits: Boolean;
begin
  Result := CurY + ScaleY(200) <= Cur.Height;
end;

procedure AddOneItem(Index: Integer; var Shown, More: Integer);
begin
  if (Shown < 4) and ItemFits then
  begin
    if Shown > 0 then
      ItemGap;
    AddItem(Index);
    Shown := Shown + 1;
  end
  else
    More := More + 1;
end;

{ W14-D3 (6.1 L2 to L8, target layouts): the items (Fix first, then Recommended, no group line,
  12 px apart), then the bottom block 16 px under them: "23 checks passed. Show all checks" and
  the row [Check again] [Save report]. }
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
      AddOneItem(I, Shown, More);
  if not OnlyFix then
    for I := 0 to GetArrayLength(Items) - 1 do
      if Items[I].Cls = 'advice' then
        AddOneItem(I, Shown, More);
  if Shown > 0 then
    BlockGap;
  if More > 0 then
  begin
    Link := AddLink(FM1('s02_show_more', IntToStr(More)), 0);
    Link.OnLinkClick := @ShowAllChecks;
  end;
  Link := AddLinkLine(FM1('s02_passed', IntToStr(Passed)), CM('s02_show_all'), 0);
  Link.OnLinkClick := @ShowAllChecks;
  Button := AddRowButton(CM('btn_check_again'), 0);
  Button.OnClick := @CheckAgainClick;
  Button.Enabled := not FixRunning and not StepRunning;
  { W14-D1: Save report on S02 whatever the result. }
  AddReportButton;
  EndRow;
  AddReportLine;
  { W14-D5 (7.6 "S02 and S06 restart"): the one line of the save and the restart. }
  if StepRunning then
    AddStepLine;
end;

function StopTodo(Item: TCheckItem): String;
begin
  Result := '';
  if (Item.Id = 'C02') and (Item.Code = 'home') then Result := CM('s03_home_todo')
  else if (Item.Id = 'C02') and (Item.Code = 'edition_not_supported') then Result := CM('s03_edition_todo')
  else if Item.Id = 'C05' then Result := CM('s03_memory_todo')
  else if (Item.Id = 'C01') and (Item.Code = 'windows_10') then Result := CM('s03_win10_todo');
end;

{ W14-D3 (rule 2.8, spec 5.2 item 3, C26): the ready verdict's second line names only the
  components that are missing. }
{ The C26 values: what S05 has to do (also S05's subtitle before the work, TASK-0097 AC-6). }
procedure C26Needs(var Vmp, Wsl: Boolean);
var
  I: Integer;
begin
  Vmp := False;
  Wsl := False;
  for I := 0 to GetArrayLength(Items) - 1 do
    if (Items[I].Id = 'C26') and (Items[I].Cls = 'auto') then
    begin
      Vmp := JsonValue(Items[I].Raw, 'vmp_state') <> 'Enabled';
      Wsl := JsonLiteral(Items[I].Raw, 'wsl_install_needed') = 'true';
    end;
end;

{ The WSL version that C26 read on this PC ('' when none is installed). }
function C26WslVersion: String;
var
  I: Integer;
begin
  Result := '';
  for I := 0 to GetArrayLength(Items) - 1 do
    if Items[I].Id = 'C26' then
      Result := JsonValue(Items[I].Raw, 'wsl_version');
end;

function PrepLine: String;
var
  Vmp, Wsl: Boolean;
begin
  Result := '';
  C26Needs(Vmp, Wsl);
  if Vmp and Wsl then Result := CM('s02_ready_prep_both')
  else if Vmp then Result := CM('s02_ready_prep_vmp')
  else if Wsl then Result := CM('s02_ready_prep_wsl');
end;

procedure RenderCheckBody;
var
  Verdict: TNewMemo;
  I, Stops: Integer;
begin
  BeginBody(P_CHECK);
  WizardForm.PageNameLabel.Caption := CM('s02_title');
  WizardForm.PageDescriptionLabel.Caption := CM('s02_subtitle');
  WizardForm.NextButton.Visible := True;
  SetNextCaption(CM('btn_next'));
  SetCancelCaption(SetupMessage(msgButtonCancel));
  AddStageLine(1);
  { AC-W9: a check restart that setup asked for before S05 goes on here. }
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
    { W14-D5 (7.6 "S02 PC check"): four stages, the check that runs (N of 30), the time. }
    AddProgress('check', CM('s02_stages'), WaitStage('check'), WaitActionText('check'), CheckStartedAt, CM('wait_about_1'));
    WizardForm.NextButton.Enabled := False;
    Exit;
  end;
  if CheckVerdict = 'not_suitable' then
  begin
    { S03: the same page in its "not suitable" state (spec S03). W14-D3 (6.1 L3, L4): each Stop
      item is one block (name, message, what you can do), 12 px apart, 16 px around the list. }
    WizardForm.PageNameLabel.Caption := CM('s03_title');
    WizardForm.PageDescriptionLabel.Caption := CM('s03_subtitle');
    Verdict := AddVerdict(CM('s03_verdict'));
    BlockGap;
    Stops := 0;
    for I := 0 to GetArrayLength(Items) - 1 do
      if Items[I].Cls = 'stop' then
      begin
        if Stops > 0 then
          ItemGap;
        Stops := Stops + 1;
        AddText(ItemName(Items[I]), True);
        AddText(ItemMessage(Items[I]), False);
        if StopTodo(Items[I]) <> '' then
          AddText(CM('s03_what') + ' ' + StopTodo(Items[I]), False);
      end;
    BlockGap;
    AddText(CM('s03_suitable'), False);
    AddText(CM('s03_wrong'), False);
    AddReportControls;
    WizardForm.NextButton.Visible := False;
    SetCancelCaption(CM('btn_close'));
  end
  else if CheckVerdict = 'needs_fixes' then
  begin
    if CountClass('fix') = 1 then
      Verdict := AddVerdict(CM('s02_needs_one'))
    else
      Verdict := AddVerdict(FM1('s02_needs', IntToStr(CountClass('fix'))));
    BlockGap;
    AddCheckItems(False);
    WizardForm.NextButton.Enabled := False;
  end
  else
  begin
    Verdict := AddVerdict(CM('s02_ready'));
    if PrepLine <> '' then
      AddText(PrepLine, False);
    BlockGap;
    AddCheckItems(False);
    WizardForm.NextButton.Enabled := not FixRunning;
  end;
  FocusVerdict(Verdict);
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
      ItemGap;
      Button := AddRowButton(CM('btn_save_report'), 0);
      Button.OnClick := @SaveReport;
      EndRow;
      if (ReportLine <> '') or (ReportPhase <> '') then
      begin
        ReportLabel := AddText(ReportLine, False);
        ShowReportLine;
      end;
    except
      Log('S02 Save report button failed: ' + GetExceptionMessage);
    end;
    WizardForm.NextButton.Visible := True;
    SetNextCaption(CM('btn_try_again'));
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

{ W14-D9: the WSL package comes out of the setup file from the timer (pc.unpack), then the
  helper runs (StepFinished 'prep-unpack'). }
procedure StartPrepare;
begin
  PrepState := 'unpack';
  PrepOut := '';
  PrepStartedAt := GetTickCount;
  QueueExtract('wsl.*.msi', 'prep-unpack');
end;

{ W14-D3 (rule 2.8, spec S05): the stage list that stays after the work, with "(already on this
  PC)" for a component that was there. }
function S05ComponentStages: String;
var
  Vmp, Wsl: String;
begin
  Vmp := CM('s05_stage_vmp');
  if PrepFeature = 'enabled' then
    Vmp := Vmp + ' ' + CM('s05_already');
  Wsl := CM('s05_stage_wsl');
  if PrepWsl = 'present' then
    Wsl := Wsl + ' ' + CM('s05_already');
  Result := Vmp + '|' + Wsl;
end;

function S05DoneStages: String;
begin
  Result := S05ComponentStages + '|' + CM('s05_stage_restart') + '|' + CM('s05_stage_details') + '|' + CM('s05_stage_install');
end;

{ TASK-0097 AC-6 (Designer 2): no restart happened, so no restart stage; Your details is next. }
function S05NoRestartStages: String;
begin
  Result := S05ComponentStages + '|' + CM('s05_stage_details') + '|' + CM('s05_stage_install');
end;

{ TASK-0097 AC-6 (Designer 1): the verdict says what setup did, from the helper's codes
  (Virtual Machine Platform: enabled, pending or enabled_now; WSL: present or installed). }
function S05VerdictKey(Feature, Wsl: String): String;
begin
  if (Feature = 'enabled_now') and (Wsl = 'installed') then Result := 's05_done'
  else if Feature = 'enabled_now' then Result := 's05_done_vmp'
  else if Wsl = 'installed' then Result := 's05_done_wsl'
  else if Feature = 'pending' then Result := 's05_done_pending'
  else Result := 's05_done_no_restart';
end;

{ The subtitle names what Windows finishes at the restart: from the helper's codes after the
  work, from the C26 values that PrepLine reads before it. }
function S05SubtitleKey: String;
var
  Vmp, Wsl: Boolean;
begin
  if PrepFeature <> '' then
  begin
    Vmp := (PrepFeature = 'enabled_now') or (PrepFeature = 'pending');
    Wsl := PrepWsl = 'installed';
  end
  else
    C26Needs(Vmp, Wsl);
  if Vmp and not Wsl then Result := 's05_subtitle_vmp'
  else if Wsl and not Vmp then Result := 's05_subtitle_wsl'
  else if not Vmp and not Wsl then Result := 's05_subtitle_ready'
  else Result := 's05_subtitle';
end;

{ TASK-0097 AC-6 (Designer 3): a WSL that is already on this PC shows its own version (C26) in
  Details and on the "Now:" line; otherwise the version in this setup file. }
function S05WslVersion: String;
var
  Vmp, Wsl: Boolean;
begin
  Result := WslVersion;
  C26Needs(Vmp, Wsl);
  if ((PrepWsl = 'present') or ((PrepWsl = '') and not Wsl)) and (C26WslVersion <> '') then
    Result := C26WslVersion;
end;

procedure RenderRestart;
var
  Steps: String;
  Link: TNewLinkLabel;
begin
  BeginBody(P_RESTART);
  { Design B8: the header comes back after a failure and Try again. }
  WizardForm.PageNameLabel.Caption := CM('s05_title');
  WizardForm.PageDescriptionLabel.Caption := CM(S05SubtitleKey);
  AddStageLine(1);
  SetNextCaption(CM('btn_next'));
  if ExtraButton <> nil then
    ExtraButton.Visible := False;
  if (PrepState = 'unpack') or (PrepState = 'working') or (PrepState = 'saving') then
  begin
    { W14-D5 (7.6 "S05 prepare"): the stages, the current action and the time so far. }
    AddProgress('prep', CM('s05_stages'), WaitStage('prep'), WaitActionText('prep'), PrepStartedAt, CM('wait_about_2'));
    WizardForm.NextButton.Enabled := False;
  end
  else if PrepState = 'failed' then
  begin
    { 7.5: the component by its name. }
    if Pos('prepare.wsl', PrepFailKey) = 1 then
      AddFailure(CM('s05_title'), CM('s05_failed_wsl'), True)
    else
      AddFailure(CM('s05_title'), CM('s05_failed'), True);
  end
  else if PrepState = 'failed_av' then
    AddFailure(CM('s05_title'), CM('av_blocked'), True)
  else if PrepState = 'restart' then
  begin
    { W14-D3 (rule 2.8, spec S05): the stage list stays; the verdict names both components,
      one line of why for each; the steps; Details holds only the version and the codes. }
    AddProgress('', S05DoneStages, 3, '', 0, '');
    BlockGap;
    AddVerdict(CM(S05VerdictKey(PrepFeature, PrepWsl)));
    AddText(CM('s05_why_vmp'), False);
    AddText(CM('s05_why_wsl'), False);
    BlockGap;
    Steps := RestartResumeText(ResumeCode, 's05_steps');
    if Steps = '' then
      Steps := CM('s05_steps');
    AddText(Steps, False);
    Link := AddLink(CM('btn_details'), 0);
    Link.OnLinkClick := @PrepDetailsClick;
    if PrepDetails then
      AddText(FM3('s05_details', S05WslVersion, PrepFeature, PrepWsl), False);
    SetNextCaption(CM('s05_next'));
    WizardForm.NextButton.Enabled := not StepRunning;
    { 7.6: "Restarting this PC..." after Restart now. }
    AddStepLine;
    if ExtraButton <> nil then
    begin
      ExtraButton.OnClick := @RestartLaterClick;
      ExtraButton.Visible := True;
      SetExtraCaption(CM('s05_later'));
    end;
  end
  else
  begin
    { No restart happened, so the subtitle says so, also when setup installed WSL just now (spec S05). }
    WizardForm.PageDescriptionLabel.Caption := CM('s05_subtitle_ready');
    AddProgress('', S05NoRestartStages, 3, '', 0, '');
    BlockGap;
    AddVerdict(CM('s05_done_no_restart'));
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
  SetNextCaption(CM('btn_continue'));
  { W14-D3: the subtitle already says where setup continues; a body line only when it adds to
    it (screenshot 6 showed the same sentence twice, both bold). }
  if EntryNext = 'S14' then
  begin
    AddText(CM('s06_stopped_key'), False);
    BlockGap;
  end;
  if CheckVerdict = 'helper_timeout' then
  begin
    AddFailure(CM('s06_title'), CM('av_blocked'), True);
    Exit;
  end;
  if CheckRunning or not CheckDone then
  begin
    { W14-D5 (7.6 "S06 and S11 recheck"): full on S06, one stage. }
    AddProgress('recheck', '', 1, WaitActionText('recheck'), CheckStartedAt, '');
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

{ The S07 drive list from the helper's "drives" result, largest first. The first (largest) drive
  is the default only while no folder is chosen, so the person's own choice stays after Back and
  Next (W14-D7, closed: the part-1 reset is reverted). }
procedure LoadDataDrives(Text: String);
var
  Rest, Letter, DriveType, FileSystem: String;
  Start, Count, I, J: Integer;
  FreeBytes: Int64;
  SwapS: String;
  SwapF: Int64;
begin
  SetArrayLength(DriveLetters, 0);
  SetArrayLength(DriveFree, 0);
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

{ W14-D9: from the timer (7.6 "S07 drives": "Looking for drives..."); StepFinished 'drives'
  loads the list and draws S07. }
procedure ReadDataDrives;
begin
  RunStep('drives', '', 'drives', CM('s07_looking'), 0, 0, HELPER_LIMIT_MS);
end;

function GB(Bytes: Int64): String;
begin
  Result := IntToStr(Integer(Bytes div 1073741824));
end;

{ W14-D3 (6.1 L10): the name that Windows shows for a drive (its volume label), "Local Disk"
  when it has none. }
function DriveName(Letter: String): String;
var
  Buffer, FsName: String;
  I: Integer;
begin
  Result := '';
  Buffer := StringOfChar(#0, 261);
  FsName := '';
  if GetVolumeInformation(AddBackslash(Copy(Letter, 1, 2)), Buffer, 261, 0, 0, 0, FsName, 0) then
  begin
    I := 1;
    while (I <= Length(Buffer)) and (Copy(Buffer, I, 1) <> #0) do
      I := I + 1;
    Result := Trim(Copy(Buffer, 1, I - 1));
  end;
  if Result = '' then
    Result := CM('drive_local_disk');
end;

{ The drive row of 6.1 L10 (copy drive_row): the name, the letter and the free space, with
  "Most space" on the largest drive and "(USB drive)" after the name of a removable drive. }
function DriveRow(Letter: String; FreeBytes: Int64; Most: Boolean): String;
var
  Name: String;
begin
  Name := DriveName(Letter);
  if GetDriveType(Copy(Letter, 1, 2) + '\') = DRIVE_REMOVABLE then
    Name := FM1('drive_usb_name', Name);
  if Most then
    Result := FM3('drive_row_most', Name, Copy(Letter, 1, 2), GB(FreeBytes))
  else
    Result := FM3('drive_row', Name, Copy(Letter, 1, 2), GB(FreeBytes));
end;

{ W9: the S07 card uses the kept data (plan 9.2) when the folder holds it and the person keeps
  the default "Use the kept data". }
function KeptMode: Boolean;
begin
  Result := (KeptState = 'kept') and KeptUse;
end;

{ The stages of the background preparation (7.6), one per step, split by "|". }
function BgStageNames: String;
begin
  if KeptMode then
    Result := CM('bg_stages_kept')
  else
    Result := FM1('bg_stages', Copy(DataRoot, 1, 2));
end;

{ Reads kept.json through the helper, after its folder checks (never a Pascal read, which
  would follow a link). W14-D9: from the timer (7.6 "S07 drives, kept data"); KeptState is
  'reading' until StepFinished 'kept' fills it and draws S07 again. }
procedure RefreshKept;
begin
  if (KeptFor = DataRoot) or StepRunning then
    Exit;
  KeptState := '';
  KeptUse := True;
  if (DataRoot = '') or not DirExists(AddBackslash(DataRoot) + 'kept') then
  begin
    KeptFor := DataRoot;
    Exit;
  end;
  if RunStep('kept-read', '-DataRoot ' + AddQuotes(DataRoot), 'kept', FM1('s07_reading_kept', AddBackslash(DataRoot) + 'kept'), 0, 0, HELPER_LIMIT_MS) then
  begin
    KeptFor := DataRoot;
    KeptState := 'reading';
  end;
end;

procedure KeptRead(Text: String);
begin
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
  Radio: TNewRadioButton;
  Link: TNewLinkLabel;
  Button: TNewButton;
begin
  BeginBody(P_DATA);
  AddStageLine(2);
  SetNextCaption(CM('btn_next'));
  AddText(CM('s07_first'), False);
  { 7.6 "S07 drives, kept data": the one line while the list, the kept data or the chosen folder
    is read (DEC-0041 AC-W1: Next only checks the folder). }
  AddStepLine;
  ItemGap;
  { W14-D3 (6.1 L10): one radio button per drive, 4 px apart. }
  SetArrayLength(DriveRadios, GetArrayLength(DriveLetters));
  for I := 0 to GetArrayLength(DriveLetters) - 1 do
  begin
    Radio := TNewRadioButton.Create(WizardForm);
    Radio.Parent := Cur;
    Radio.Caption := DriveRow(DriveLetters[I], DriveFree[I], I = 0);
    Radio.Tag := I;
    Radio.SetBounds(0, CurY, Cur.Width, ScaleY(18));
    Radio.Checked := CompareText(Copy(DataRoot, 1, 2), DriveLetters[I]) = 0;
    Radio.OnClick := @DriveRadioClick;
    DriveRadios[I] := Radio;
    CurY := CurY + Radio.Height + ScaleY(4);
  end;
  ItemGap;
  { 6.1 L7: the Folder line ends with "Change folder". }
  Link := AddLinkLine(FM1('s07_folder', DataRoot), CM('s07_change_folder'), 0);
  Link.OnLinkClick := @ChangeFolderClick;
  { The messages of the folder sit under the Folder line, in regular text (6.1 L2). }
  if DataError = 'data_folder_parent_unsafe' then
  begin
    AddText(FM2('s07_parent_unsafe', DataRoot, DefaultFolderFor(DataRoot)), False);
    Button := AddRowButton(FM1('s07_use_default', DefaultFolderFor(DataRoot)), 0);
    Button.OnClick := @UseDefaultClick;
    EndRow;
  end
  else if DataError = 'not_empty' then
    AddText(CM('s07_not_empty'), False)
  else if DataError = 'too_small' then
    AddText(FM1('s07_too_small', DataErrorValue), False)
  else if DataError = 'drive_not_fixed_ntfs' then
    AddText(CM('s07_usb_note'), False)
  else if (DataError = 'start_failed') or (DataError = 'helper_timeout') then
  begin
    { In place, never from the timer as a dialog (spec 12 item 1). }
    if DataError = 'helper_timeout' then AddText(CM('av_blocked'), False) else AddText(CM('s07_start_failed'), False);
    AddReportControls;
  end;
  RefreshKept;
  if KeptState = 'kept' then
  begin
    { Spec S07 kept-data card: its heading, then the two choices 4 px apart. }
    ItemGap;
    AddText(FM3('s07_kept', KeptName, KeptVersion, KeptOn), True);
    Radio := TNewRadioButton.Create(WizardForm);
    Radio.Parent := Cur;
    Radio.Caption := CM('s07_use_kept');
    Radio.Tag := 1;
    Radio.Checked := KeptUse;
    Radio.OnClick := @KeptChoiceClick;
    Radio.SetBounds(0, CurY, Cur.Width, ScaleY(18));
    CurY := CurY + Radio.Height + ScaleY(4);
    Radio := TNewRadioButton.Create(WizardForm);
    Radio.Parent := Cur;
    Radio.Caption := CM('s07_start_new');
    Radio.Tag := 0;
    Radio.Checked := not KeptUse;
    Radio.OnClick := @KeptChoiceClick;
    Radio.SetBounds(0, CurY, Cur.Width, ScaleY(18));
    CurY := CurY + Radio.Height + ScaleY(4);
  end
  else if KeptState = 'kept_newer' then
    AddText(FM1('s07_kept_newer', KeptVersion), False)
  else if KeptState = 'kept_older' then
    AddText(FM1('s07_kept_older', KeptVersion), False)
  else if KeptState = 'kept_unreadable' then
  begin
    AddText(CM('s07_kept_unreadable'), False);
    AddReportControls;
  end;
  ItemGap;
  if DataError <> 'drive_not_fixed_ntfs' then
    AddText(CM('s07_usb_note'), False);
  Link := AddLink(CM('s07_change_program'), 0);
  Link.OnLinkClick := @ChangeProgramClick;
  { W9-3: newer, older (W13b) or unreadable kept data, and "Start new" in a kept folder, keep
    Next off until the folder changes; the kept data is read first (W14-D9). }
  WizardForm.NextButton.Enabled := (DataRoot <> '') and not StepRunning and ((KeptState = '') or KeptMode);
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

{ DEC-0041 (AC-W1): S07 Next checks the chosen folder and writes nothing (data-check, from the
  timer, 7.6 one-line form); StepFinished 'data-check' selects Next again once it is ready. The
  data folder is made on S12, after Install. }
procedure StartDataCheck;
var
  FreeBytes: Int64;
  Ignored: Int64;
  Extra: String;
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
  DataError := '';
  Extra := '-DataRoot ' + AddQuotes(DataRoot);
  if KeptMode then
    Extra := Extra + ' -UseKept';
  if RunStep('data-check', Extra, 'data-check', FM1('s07_checking', DataRoot), 0, 0, DATA_CHECK_MS) then
    RenderPage(P_DATA);
end;

{ S12 stage 1 (DEC-0041 AC-W2): the parts come out of the setup file one per timer tick
  (data.unpack, StepFinished 'data-unpack'), then the data folder step makes the folder. }
procedure StartServerPrep;
begin
  InstallStep := -1;
  DataPrepared := False;
  DataStarted := True;
  BgOut := '';
  BgIndex := 0;
  BgFailed := False;
  BgCode := '';
  DataStartedAt := GetTickCount;
  QueueExtract('slateops-linux-*|slateops-engine-*|slateops-server-*|slateops-caddy-*|release-manifest.json|release-manifest.json.sigstore.json', 'data-unpack');
end;

procedure StartDataFolder;
begin
  BgOut := NewOut('prepare-data');
  DataStartedAt := GetTickCount;
  if KeptMode then
    StartHelper('prepare-data', RunId, BgOut, '-DataRoot ' + AddQuotes(DataRoot) + ' -UseKept')
  else
    StartHelper('prepare-data', RunId, BgOut, '-DataRoot ' + AddQuotes(DataRoot));
  RenderPage(P_INSTALL);
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

{ W14-D5: the current action of the background preparation (7.6 background row): the helper
  step's line, or the engine job's step from its standard error, else the stage name. }
function BgAction: String;
var
  Name, Drive: String;
begin
  Result := '';
  Name := BgStepName(BgIndex);
  Drive := Copy(DataRoot, 1, 2);
  if (BgPending = 'return') or (Name = 'kept-status') then
    Result := StepText('bg', 'kept_status', '', '', '')
  else if Name = 'service' then Result := StepText('bg', 'service', '', '', '')
  else if Name = 'wslconfig' then Result := StepText('bg', 'wslconfig', '', '', '')
  else if Name = 'import-distro' then Result := StepText('bg', 'import', Drive, '', '')
  else if Name = 'restore-kept' then Result := StepText('bg', 'restore_kept', DataRoot, '', '')
  else if Name = 'import-kept' then Result := StepText('bg', 'import_kept', '', '', '')
  else if Name = 'start-boot' then Result := StepText('bg', 'start', '', '', '')
  else if (JobPurpose = 'bg') and (JobStepJob = Name) then
    Result := StepText(JobStepJob, JobStepKey, '', '', '');
  if Result = '' then
  begin
    StringChangeEx(Name, '-', '_', True);
    Result := CM('bg_stage_' + Name);
  end;
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
  BgBeganAt := GetTickCount;
  StartBgStep;
end;

{ The step after a done background step. }
procedure NextBgStep;
begin
  BgIndex := BgIndex + 1;
  StartBgStep;
  { DEC-0041 (AC-W2): S12 shows the next stage. }
  RenderPage(P_INSTALL);
end;

{ W14-D9: the helper calls inside the background run from the timer too: the account's SID
  after the service step ('sid'), and the kept data back to kept\ after a mismatch ('return'). }
function PollBgPending: Boolean;
var
  Code: String;
begin
  Result := BgPending <> '';
  if not Result then
    Exit;
  Code := ReadResultCode(BgPendingOut);
  if (Code = '') and (Elapsed(BgPendingAt) < HELPER_LIMIT_MS) then
    Exit;
  if BgPending = 'sid' then
  begin
    BgPending := '';
    ServiceSid := JsonValue(ReadText(BgPendingOut), 'sid');
    NextBgStep;
    Exit;
  end;
  { F3 at reinstall: the disk that is not the kept installation is back in kept\ (advisor
    item 1); only now the failure shows (S12, PollServerPrep). }
  BgPending := '';
  BgFailed := True;
end;

procedure StartBgPending(Kind, Action: String);
begin
  BgPending := Kind;
  BgPendingAt := GetTickCount;
  BgPendingOut := NewOut(Action);
  StartHelper(Action, RunId, BgPendingOut, '');
end;

{ The server part's steps on S12 (DEC-0041 AC-W2), from PollServerPrep. No step starts or ends
  while the removal runs (TASK-0097 AC-3). }
procedure PollBackground;
var
  Code, Name: String;
begin
  if CloseFlowRunning then
    Exit;
  if PollBgPending then
    Exit;
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
        begin
          BgFailed := False;
          StartBgPending('return', 'kept-return');
          Exit;
        end;
      end;
      Exit;
    end;
    if Name = 'service' then
    begin
      StartBgPending('sid', 'account-sid');
      Exit;
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
      Exit;
    end;
  end;
  NextBgStep;
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

{ DEC-0041 (AC-W1): the format check of the email address, the engine's shape (packaging/engine
  answers.py _EMAIL): 1 to 64 characters with no space before the "@", then a domain of letter,
  number and hyphen labels with at least one dot, no label that starts or ends with a hyphen. }
function ValidEmail(S: String): Boolean;
var
  At, I, LabelLen, Dots: Integer;
  Local, Domain, C: String;
begin
  Result := False;
  At := Pos('@', S);
  if (At < 2) or (At > 65) or (Length(S) > 254) then
    Exit;
  Local := Copy(S, 1, At - 1);
  Domain := Copy(S, At + 1, Length(S));
  if (Domain = '') or (Length(Domain) > 253) then
    Exit;
  for I := 1 to Length(Local) do
    if Ord(Local[I]) <= 32 then
      Exit;
  Dots := 0;
  LabelLen := 0;
  for I := 1 to Length(Domain) do
  begin
    C := Copy(Domain, I, 1);
    if C = '.' then
    begin
      if (LabelLen = 0) or (Copy(Domain, I - 1, 1) = '-') then
        Exit;
      Dots := Dots + 1;
      LabelLen := 0;
    end
    else if Pos(Lowercase(C), 'abcdefghijklmnopqrstuvwxyz0123456789') > 0 then
      LabelLen := LabelLen + 1
    else if (C = '-') and (LabelLen > 0) then
      LabelLen := LabelLen + 1
    else
      Exit;
    if LabelLen > 63 then
      Exit;
  end;
  Result := (Dots > 0) and (LabelLen > 0) and (Copy(Domain, Length(Domain), 1) <> '-');
end;

{ DEC-0041 (AC-W5): the administrator's user name from the name on S08: letters and numbers in
  lower case, every other run of characters one hyphen; the email address gives it when the name
  has no letter or number. The engine's rule: 3 to 100 of a-z, 0-9, - and _. }
function UserFromName(Name, Email: String): String;
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
    Result := DefaultUser(Email);
  while Length(Result) < 3 do
    Result := Result + '_';
  Result := Copy(Result, 1, 100);
end;

{ DEC-0041 (AC-W1): the length rule of the app's password policy (backend validate_password:
  at least 12 characters, at most 128). }
function PasswordLengthOk(S: String): Boolean;
begin
  Result := (Length(S) >= 12) and (Length(S) <= 128);
end;

{ The width of a radio button or check box that shows S: its text and the box. The measuring
  label is built at the first use (S08 is built before S09). }
function RadioWidth(S: String): Integer;
begin
  if MailMeasure = nil then
  begin
    MailMeasure := TNewStaticText.Create(WizardForm);
    MailMeasure.Parent := WizardForm;
    MailMeasure.AutoSize := True;
    MailMeasure.WordWrap := False;
    MailMeasure.ShowAccelChar := False;
    MailMeasure.Visible := False;
  end;
  MailMeasure.Caption := S;
  Result := MailMeasure.Width + ScaleX(24);
end;

procedure LayoutOrg; forward;

procedure OrgShowClick(Sender: TObject);
begin
  if OrgShow.Checked then
  begin
    OrgPassword.PasswordChar := #0;
    OrgConfirm.PasswordChar := #0;
  end
  else
  begin
    OrgPassword.PasswordChar := '*';
    OrgConfirm.PasswordChar := '*';
  end;
end;

{ "Show" resets to hidden when the page changes. }
procedure HideOrgShow;
begin
  if OrgShow <> nil then
  begin
    OrgShow.Checked := False;
    OrgShowClick(nil);
  end;
end;

procedure BuildOrgPage;
var
  Surface: TWinControl;
begin
  Surface := Pages[P_ORG].Surface;
  OrgTop := StageLineAt(Surface, 0, 2);
  OrgNameLabel := AddTextTo(Surface, 0, CM('s08_name'), True);
  OrgNameHelp := AddTextTo(Surface, 0, CM('s08_name_help'), False);
  OrgName := NewEditAt(Surface, 0); OrgName.MaxLength := 200;
  OrgYourNameLabel := AddTextTo(Surface, 0, CM('s08_your_name'), True);
  OrgYourName := NewEditAt(Surface, 0); OrgYourName.MaxLength := 200;
  OrgEmailLabel := AddTextTo(Surface, 0, CM('s08_email'), True);
  OrgEmailHelp := AddTextTo(Surface, 0, CM('s08_email_help'), False);
  OrgEmail := NewEditAt(Surface, 0); OrgEmail.MaxLength := 254;
  OrgPasswordLabel := AddTextTo(Surface, 0, CM('s08_password'), True);
  OrgPasswordHelp := AddTextTo(Surface, 0, CM('s08_password_help'), False);
  OrgPassword := NewEditAt(Surface, 0); OrgPassword.MaxLength := 128; OrgPassword.PasswordChar := '*';
  OrgConfirmLabel := AddTextTo(Surface, 0, CM('s08_confirm'), True);
  OrgConfirm := NewEditAt(Surface, 0); OrgConfirm.MaxLength := 128; OrgConfirm.PasswordChar := '*';
  OrgShow := TNewCheckBox.Create(WizardForm);
  OrgShow.Parent := Surface;
  OrgShow.Caption := CM('s08_show');
  OrgShow.SetBounds(0, 0, ScaleX(120), ScaleY(18));
  OrgShow.OnClick := @OrgShowClick;
  { 6.1 L2: a field error is regular text, under its field. }
  OrgError := AddTextTo(Surface, 0, '', False);
  LayoutOrg;
end;

procedure OrgFail(Key: String; Field: TNewEdit);
begin
  OrgError.Caption := CM(Key);
  OrgErrorAfter := Field;
  LayoutOrg;
  WizardForm.ActiveControl := Field;
end;

{ DEC-0041 (AC-W1): the email address gets a format check only (no email is sent); the
  password gets the length rule and must match its second entry. }
function CheckOrg: Boolean;
begin
  Result := False;
  if Trim(OrgName.Text) = '' then begin OrgFail('s08_err_name', OrgName); Exit; end;
  if Length(Trim(OrgName.Text)) > 100 then begin OrgFail('s08_err_name_long', OrgName); Exit; end;
  if Trim(OrgYourName.Text) = '' then begin OrgFail('s08_err_your_name', OrgYourName); Exit; end;
  if not ValidEmail(Trim(OrgEmail.Text)) then begin OrgFail('s08_err_email', OrgEmail); Exit; end;
  if not PasswordLengthOk(OrgPassword.Text) then begin OrgFail('s08_err_password', OrgPassword); Exit; end;
  if OrgConfirm.Text <> OrgPassword.Text then begin OrgFail('s08_err_confirm', OrgConfirm); Exit; end;
  OrgError.Caption := '';
  OrgErrorAfter := nil;
  LayoutOrg;
  HideOrgShow;
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
procedure ApplyProvider;
begin
  { DEC-0040: a Microsoft 365 domain is set up with Other. }
  if MailDetected = 'gmail' then MailGmail.Checked := True
  else if not MailOutlook then MailOther.Checked := True;
end;

procedure DetectProvider;
var
  Domain: String;
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
    MailOther.Checked := False;
  end
  else if (Domain = 'gmail.com') or (Domain = 'googlemail.com') then
    MailDetected := 'gmail'
  else
  begin
    { W14-D9: from the timer (7.6 "S09 provider lookup"); StepFinished 'provider' sets the
      radio. Another step running: the lookup runs at the next change. }
    if not RunStep('provider-detect', '-Domain ' + Domain, 'provider', FM1('s09_looking_up', Domain), 0, 0, HELPER_LIMIT_MS) then
      MailCheckedDomain := '';
    Exit;
  end;
  ApplyProvider;
end;

procedure LayoutMail; forward;

procedure MailChanged(Sender: TObject);
begin
  MailPassed := False;
  MailSaved := False;
  MailChangedAt := GetTickCount;
  if WizardForm.CurPageID = Pages[P_EMAIL].ID then
    SetNextCaption(CM('s09_next_test'));
end;

procedure MailProviderClick(Sender: TObject);
begin
  MailPassed := False;
  MailSaved := False;
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
  if ConfirmBox(CM('s09_gmail_title'), CM('s09_gmail_steps'), CM('s09_gmail_open'), CM('btn_close')) then
    OpenAsUser('https://myaccount.google.com/apppasswords', '');
end;

procedure MailMoreClick(Sender: TObject; const Link: String; LinkType: TSysLinkType);
begin
  MailMore := True;
  if MailSender.Text = '' then
    MailSender.Text := Trim(OrgName.Text);
  LayoutMail;
end;

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

{ W14-D3 (6.1 L9): S08 field blocks: label, 4 px, help, 4 px, field, 4 px, its error; 12 px to
  the next block; "More options" 12 px under the last field, hidden once open. }
procedure PlaceOrgError(After: TControl; var Y: Integer);
begin
  if (OrgErrorAfter = After) and (OrgError.Caption <> '') then
  begin
    OrgError.Top := Y;
    WizardForm.AdjustLabelHeight(OrgError);
    Y := Y + OrgError.Height + ScaleY(4);
  end;
end;

procedure LayoutOrg;
var
  Y, ShowWidth: Integer;
begin
  Y := OrgTop;
  OrgError.Visible := (OrgErrorAfter <> nil) and (OrgError.Caption <> '');
  Place(OrgNameLabel, Y, True, ScaleY(4));
  Place(OrgNameHelp, Y, True, ScaleY(4));
  Place(OrgName, Y, True, ScaleY(4));
  PlaceOrgError(OrgName, Y);
  Y := Y + ScaleY(8);
  Place(OrgYourNameLabel, Y, True, ScaleY(4));
  Place(OrgYourName, Y, True, ScaleY(4));
  PlaceOrgError(OrgYourName, Y);
  Y := Y + ScaleY(8);
  Place(OrgEmailLabel, Y, True, ScaleY(4));
  Place(OrgEmailHelp, Y, True, ScaleY(4));
  Place(OrgEmail, Y, True, ScaleY(4));
  PlaceOrgError(OrgEmail, Y);
  Y := Y + ScaleY(8);
  { "Show" at the right end of the Password label's line (as on M02 Other), for both fields. }
  OrgShow.Width := RadioWidth(OrgShow.Caption);
  ShowWidth := OrgShow.Width;
  OrgPasswordLabel.Width := OrgName.Width - ShowWidth - ScaleX(8);
  OrgShow.SetBounds(OrgName.Width - ShowWidth, Y, ShowWidth, OrgShow.Height);
  OrgShow.Visible := True;
  Place(OrgPasswordLabel, Y, True, ScaleY(4));
  Place(OrgPasswordHelp, Y, True, ScaleY(4));
  Place(OrgPassword, Y, True, ScaleY(4));
  PlaceOrgError(OrgPassword, Y);
  Y := Y + ScaleY(8);
  Place(OrgConfirmLabel, Y, True, ScaleY(4));
  Place(OrgConfirm, Y, True, ScaleY(4));
  PlaceOrgError(OrgConfirm, Y);
end;

{ The status line and Save report under the form; RenderMailStatus calls it again when the
  status line changes. }
procedure PlaceMailTail;
var
  Y: Integer;
begin
  WizardForm.AdjustLabelHeight(MailStatus);
  Y := MailStatus.Top;
  if MailStatus.Caption <> '' then
    Y := Y + MailStatus.Height + ScaleY(4);
  MailReportButton.Top := Y;
end;

{ 6.1 L9: a radio group is one row at the radios' own widths, 16 px apart. }
procedure PlaceRadioRow(First, Second, Third: TNewRadioButton; Y: Integer);
begin
  First.SetBounds(0, Y, RadioWidth(First.Caption), First.Height);
  Second.SetBounds(First.Left + First.Width + ScaleX(16), Y, RadioWidth(Second.Caption), Second.Height);
  if Third <> nil then
    Third.SetBounds(Second.Left + Second.Width + ScaleX(16), Y, RadioWidth(Third.Caption), Third.Height);
end;

{ W14-D10 (owner, rc.24): the Other fields are built at the top of the page. A state that does
  not show them hides them all, so none stays at its build position over the form. }
procedure HideMailOtherFields;
begin
  MailServerLabel.Visible := False;
  MailServer.Visible := False;
  MailPortLabel.Visible := False;
  MailPort.Visible := False;
  MailSecurityLabel.Visible := False;
  MailSsl.Visible := False;
  MailStartTls.Visible := False;
  MailUserLabel.Visible := False;
  MailUser.Visible := False;
end;

{ Shows the fields of the chosen provider in order (spec S09 "Fields, in order"). W14-D3 (6.1
  L9): the field blocks with the 4 / 12 px rhythm; the help link ends its help line; "Continue
  later" is the last line of the form, 16 px under the last block. }
procedure LayoutMail;
var
  Y, Full, Half, PortWidth, ShowWidth: Integer;
  Gmail, Other: Boolean;
begin
  Gmail := MailGmail.Checked and not MailOutlook;
  Other := MailOther.Checked;
  MailError.Visible := False;
  { The error is full width except under the password of the Other rows. }
  MailError.SetBounds(0, MailError.Top, MailFrom.Width, MailError.Height);
  Y := MailTop;
  Place(MailFromLabel, Y, True, ScaleY(4));
  Place(MailFrom, Y, True, ScaleY(4));
  PlaceError(MailFrom, Y);
  Y := Y + ScaleY(8);
  Place(MailProviderLabel, Y, True, ScaleY(4));
  MailGmail.Caption := CM('s09_gmail');
  if MailDetected = 'gmail' then MailGmail.Caption := MailGmail.Caption + ' ' + CM('s09_detected');
  PlaceRadioRow(MailGmail, MailOther, nil, Y);
  Y := Y + MailGmail.Height + ScaleY(4);
  PlaceError(MailGmail, Y);
  Y := Y + ScaleY(8);
  if MailOutlook and not Other then
  begin
    MailNote.Caption := CM('s09_outlook');
    WizardForm.AdjustLabelHeight(MailNote);
    Place(MailNote, Y, True, ScaleY(4));
    Place(MailHelpLink, Y, False, 0);
    Place(MailPasswordLabel, Y, False, 0);
    Place(MailPassword, Y, False, 0);
    Place(MailShow, Y, False, 0);
    HideMailOtherFields;
    Y := Y + ScaleY(8);
  end
  else
  begin
    MailNote.Visible := False;
    if Other then
    begin
      { 6.1 rule 9, its only exception (parent decision, 2026-11-18): with Other, Server and
        Port share one row and User name and Password share one row, so every field fits
        above the status line. Each field keeps its block: label, 4 px, field, 4 px. }
      Full := MailFrom.Width;
      Half := (Full - ScaleX(16)) div 2;
      PortWidth := ScaleX(80);
      MailServerLabel.SetBounds(0, Y, Full - PortWidth - ScaleX(16), MailServerLabel.Height);
      MailPortLabel.SetBounds(Full - PortWidth, Y, PortWidth, MailPortLabel.Height);
      MailServerLabel.Visible := True;
      MailPortLabel.Visible := True;
      Y := Y + MailServerLabel.Height + ScaleY(4);
      MailServer.SetBounds(0, Y, Full - PortWidth - ScaleX(16), MailServer.Height);
      MailPort.SetBounds(Full - PortWidth, Y, PortWidth, MailPort.Height);
      MailServer.Visible := True;
      MailPort.Visible := True;
      Y := Y + MailServer.Height + ScaleY(4);
      PlaceError(MailServer, Y);
      Y := Y + ScaleY(8);
      Place(MailSecurityLabel, Y, True, ScaleY(4));
      MailSsl.Visible := True;
      MailStartTls.Visible := True;
      PlaceRadioRow(MailSsl, MailStartTls, nil, Y);
      Y := Y + MailSsl.Height + ScaleY(4);
      PlaceError(MailSsl, Y);
      Y := Y + ScaleY(8);
      { "Show" sits at the right end of the Password label's line (parent decision,
        2026-11-18), so the row needs no line under the fields for it. }
      MailPasswordLabel.Caption := CM('s09_password');
      ShowWidth := RadioWidth(MailShow.Caption);
      MailUserLabel.SetBounds(0, Y, Half, MailUserLabel.Height);
      MailPasswordLabel.SetBounds(Half + ScaleX(16), Y, Half - ShowWidth - ScaleX(8), MailPasswordLabel.Height);
      MailShow.SetBounds(Full - ShowWidth, Y, ShowWidth, MailShow.Height);
      MailUserLabel.Visible := True;
      MailPasswordLabel.Visible := True;
      MailShow.Visible := True;
      if MailShow.Height > MailUserLabel.Height then
        Y := Y + MailShow.Height + ScaleY(4)
      else
        Y := Y + MailUserLabel.Height + ScaleY(4);
      MailUser.SetBounds(0, Y, Half, MailUser.Height);
      MailPassword.SetBounds(Half + ScaleX(16), Y, Half, MailPassword.Height);
      MailUser.Visible := True;
      MailPassword.Visible := True;
      Y := Y + MailPassword.Height + ScaleY(4);
      { The password's error in the password column; every other error stays under its own
        field at full width (TASK-0097 AC-4, Designer B1). }
      if MailErrorAfter = MailPassword then
        MailError.SetBounds(Half + ScaleX(16), MailError.Top, Half, MailError.Height);
      PlaceError(MailPassword, Y);
      MailHelpLink.Visible := False;
      Y := Y + ScaleY(8);
    end
    else
    begin
      Place(MailServerLabel, Y, False, 0);
      Place(MailServer, Y, False, 0);
      Place(MailPortLabel, Y, False, 0);
      Place(MailPort, Y, False, 0);
      Place(MailSecurityLabel, Y, False, 0);
      MailSsl.Visible := False;
      MailStartTls.Visible := False;
      Place(MailUserLabel, Y, False, 0);
      Place(MailUser, Y, False, 0);
      { Gmail: the password block at full width. }
      MailPasswordLabel.SetBounds(0, MailPasswordLabel.Top, MailFrom.Width, MailPasswordLabel.Height);
      MailPassword.SetBounds(0, MailPassword.Top, MailFrom.Width, MailPassword.Height);
      MailShow.SetBounds(0, MailShow.Top, ScaleX(120), MailShow.Height);
      if Gmail then MailPasswordLabel.Caption := CM('s09_app_password') else MailPasswordLabel.Caption := CM('s09_password');
      Place(MailPasswordLabel, Y, True, ScaleY(4));
      { The help line ends with its link (Gmail: app password). }
      MailHelpLink.Caption := CM('s09_gmail_help') + ' <a href="help">' + CM('s09_gmail_link') + '</a>';
      MailHelpLink.AdjustHeight;
      Place(MailHelpLink, Y, Gmail, ScaleY(4));
      Place(MailPassword, Y, True, ScaleY(4));
      Place(MailShow, Y, True, ScaleY(4));
      PlaceError(MailPassword, Y);
      Y := Y + ScaleY(8);
    end;
  end;
  Place(MailMoreLink, Y, not MailMore, ScaleY(4));
  Place(MailSenderLabel, Y, MailMore, ScaleY(4));
  Place(MailSender, Y, MailMore, ScaleY(4));
  MailStatus.Top := Y;
  PlaceMailTail;
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
begin
  Surface := Pages[P_EMAIL].Surface;
  Third := Surface.Width div 3;
  MailTop := StageLineAt(Surface, 0, 2);
  MailFromLabel := AddTextTo(Surface, 0, CM('s09_from'), True);
  MailFrom := NewEditAt(Surface, 0); MailFrom.MaxLength := 254; MailFrom.OnChange := @MailChanged;
  MailProviderLabel := AddTextTo(Surface, 0, CM('s09_provider'), True);
  MailGmail := NewRadioAt(Surface, CM('s09_gmail'), 0, Third);
  MailOther := NewRadioAt(Surface, CM('s09_other'), Third, Third);
  MailNote := AddTextTo(Surface, 0, '', False);
  MailHelpLink := TNewLinkLabel.Create(WizardForm);
  MailHelpLink.Parent := Surface;
  NoFocusBox(MailHelpLink);
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
  MailMoreLink := TNewLinkLabel.Create(WizardForm); MailMoreLink.Parent := Surface; NoFocusBox(MailMoreLink);
  MailMoreLink.Caption := '<a href="more">' + CM('s08_more') + '</a>'; MailMoreLink.OnLinkClick := @MailMoreClick;
  MailMoreLink.Width := Surface.Width; MailMoreLink.AdjustHeight;
  MailSenderLabel := AddTextTo(Surface, 0, CM('s09_sender_name'), True);
  MailSender := NewEditAt(Surface, 0); MailSender.MaxLength := 100; MailSender.OnChange := @MailChanged;
  { 6.1 L2: a field error is regular text. }
  MailError := AddTextTo(Surface, 0, '', False);
  MailStatus := AddTextTo(Surface, 0, '', False);
  { QA B7: Save report for an unknown result and for the R7 stop. }
  MailReportButton := TNewButton.Create(WizardForm);
  MailReportButton.Parent := Surface;
  MailReportButton.Caption := CM('btn_save_report');
  MailReportButton.SetBounds(0, 0, WizardForm.CalculateButtonWidth([CM('btn_save_report')]), WizardForm.NextButton.Height);
  MailReportButton.OnClick := @SaveReport;
  MailReportButton.Visible := False;
end;

function MailHost: String;
begin
  if MailGmail.Checked then Result := 'smtp.gmail.com'
  else Result := Trim(MailServer.Text);
end;

function MailPortValue: Integer;
begin
  { Parent decision on D-4 (TASK-0083): Gmail 465 with implicit TLS. }
  if MailGmail.Checked then Result := 465
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
  Result := ValidEmail(MailFrom.Text) and (MailPassword.Text <> '') and (MailGmail.Checked or MailOther.Checked)
    and not (MailOutlook and not MailOther.Checked);
  if MailOther.Checked then
    Result := Result and (MailHost <> '') and (MailPortValue > 0) and (MailPortValue < 65536);
end;

procedure RenderMailStatus;
var
  Line: String;
begin
  { W14-D5 (7.6 "S09 Send test email", "M02 save", "S09 provider lookup"): the one line of the
    running wait; the timer keeps it current. }
  Line := PageLineText;
  StepLabel := nil;
  if Line <> '' then
  begin
    MailStatus.Caption := Line;
    StepLabel := MailStatus;
  end
  { DEC-0041 (AC-W6): after set-email, the test email's address and where to look. }
  else if MailSaved then MailStatus.Caption := FM1('m02_test_sent', Trim(OrgEmail.Text))
  else MailStatus.Caption := '';
  if MailShowReport and ((ReportLine <> '') or (ReportPhase <> '')) then
  begin
    ReportLabel := MailStatus;
    ShowReportLine;
  end;
  MailReportButton.Visible := MailShowReport and (MailPhase = '');
  PlaceMailTail;
  if MailSaved then
    SetNextCaption(CM('btn_done'))
  else
    SetNextCaption(CM('s09_next_test'));
  WizardForm.NextButton.Enabled := (MailPhase = '') and (MaintPhase = '') and (MailFieldsReady or MailSaved);
end;

{ M02 (DEC-0041 AC-W6): the channel self-test (plan F4d), then R7 again (spec 5.2), then
  smtp-test with the password through the pipe, then set-email (PollMail). The password goes only
  with the test email, after both checks. }
procedure StartMailTest;
var
  Value: String;
begin
  MailError.Caption := '';
  MailShowReport := False;
  HideShow;
  if MailPhase = '' then
    MailAt := GetTickCount;
  if not MailSelfTested then
  begin
    MailPhase := 'selftest';
    Value := RandomHex(32);
    StartJob('pipe-test', Value, 'selftest:' + GetSHA256OfString(AnsiString(Value)), True, True, 2);
    RenderMailStatus;
    Exit;
  end;
  if MailPhase <> 'r7done' then
  begin
    MailPhase := 'r7';
    if not RunStep('r7', '', 'r7', CM('s09_policy'), 3, 4, HELPER_LIMIT_MS) then
      MailPhase := '';
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
  else if Code = 'smtp_unreachable' then
  begin
    if MailGmail.Checked then SetMailError(FM1('s09_err_unreachable_known', CM('s09_gmail')), MailGmail)
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
  if (MailPhase <> 'selftest') and (MailPhase <> 'sending') then
    Exit;
  if JobState <> JOB_DONE then
    Exit;
  { W14-D9: only this page's job (Save report can run a job too). }
  if (JobPurpose <> 'smtp') and (Copy(JobPurpose, 1, 9) <> 'selftest:') then
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
    { DEC-0041 (AC-W6): set-email follows at once (Maintenance.iss, StartSetEmail). }
    MailPassed := True;
    StartSetEmail;
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
  ItemGap;
  if Count = 0 then
  begin
    AddText(CM('s10_plug'), True);
    AddText(CM('s10_none'), False);
    ItemGap;
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
      { W14-D3 (6.1 L10): the drive row with its name, "(USB drive)" for a removable one. }
      if not GetSpaceOnDisk64(Letter + '\', FreeBytes, Ignored) then
        FreeBytes := 0;
      Caption := DriveRow(Letter, FreeBytes, False);
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
  ItemGap;
  OnData := CompareText(BackupDrive, Copy(DataRoot, 1, 2)) = 0;
  if Removable then
    AddText(CM('s10_usb'), False);
  { 6.1 L2: a message under the list is regular text. }
  if BackupError <> '' then
    AddText(BackupError, False);
  { 7.6 "S10 Next" and M03: the one line under the list. }
  AddStepLine;
  SetNextCaption(CM('btn_next'));
  WizardForm.NextButton.Enabled := (BackupDrive <> '') and not StepRunning and (MaintPhase = '');
  if OnData then
  begin
    BackupConfirm := TNewCheckBox.Create(WizardForm);
    BackupConfirm.Parent := Cur;
    BackupConfirm.Caption := FM1('s10_confirm', BackupDrive);
    BackupConfirm.SetBounds(0, CurY, Cur.Width, ScaleY(18));
    BackupConfirm.OnClick := @BackupConfirmClick;
    CurY := CurY + BackupConfirm.Height + ScaleY(4);
    WizardForm.NextButton.Enabled := False;
    AddText(CM('s10_later'), False);
  end;
end;

{ The drive-check result (W14-D9: the helper ran from the timer, 7.6 "S10 Next"). }
function BackupResult(Text: String): Boolean;
var
  Code: String;
begin
  Code := JsonValue(Text, 'code');
  Result := Code = 'ready';
  if Code = 'too_small' then
    BackupError := FM2('s10_too_small', BackupDrive, JsonLiteral(Text, 'free_gb'))
  else if not Result then
    BackupError := FM1('s10_not_writable', BackupDrive);
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
    NoFocusBox(Link);
    Link.Caption := '<a href="' + IntToStr(ChangePage) + '">' + CM('s11_change') + '</a>';
    Link.Left := Cur.Width - ScaleX(64);
    Link.Top := CurY;
    Link.OnLinkClick := @ChangeClick;
  end;
  { W14-D3 (6.1 L4): rows 4 px apart. }
  CurY := CurY + Row.Height + ScaleY(4);
end;

procedure RenderReady;
var
  Link: TNewLinkLabel;
  Backups: String;
begin
  BeginBody(P_READY);
  AddStageLine(3);
  SetNextCaption(CM('s11_next'));
  if CheckRunning and (CheckFor = 'S11') then
  begin
    { W14-D5 (7.6 "S06 and S11 recheck"): one line on S11. }
    StepLabel := AddText(PageLineText, False);
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
    { DEC-0041 (AC-W1): the address the administrator signs in with; no email page. }
    AddRow(FM1('s11_admin', Trim(OrgEmail.Text)), P_ORG);
    AddRow(FM1('s11_data', DataRoot), -1);
    Backups := BackupDrive;
    if GetDriveType(BackupDrive + '\') = DRIVE_REMOVABLE then
      Backups := Backups + ' (' + CM('s10_usb_word') + ')';
    AddRow(FM1('s11_backups', Backups), P_BACKUP);
    AddRow(FM1('s11_address', AddressUrl), -1);
    AddRow(CM('s11_edition'), -1);
  end;
  BlockGap;
  AddText(CM('s11_time'), False);
  Link := AddLink(CM('s11_what'), 0);
  Link.OnLinkClick := @WhatChangesClick;
  { DEC-0041 (AC-W2): the server work starts after Install, on S12. }
  WizardForm.NextButton.Enabled := True;
end;

{ ------------------------------------------------------------------------------------------- }
{ S12 Installing                                                                                }
{ ------------------------------------------------------------------------------------------- }

{ DEC-0041 (AC-W2): every server step runs on S12, after Install, in this order: the data folder
  (stage 1), the server part (the steps of BgStepName, one stage each), then the backup folder,
  the saved progress and the time zone, the channel self-test and R7 (AC-W5: the password crosses
  only a tested channel), the install job (its own stages), the Windows steps and the HTTPS
  check. Every step has a time limit; a step past it, or any failed step, stops the install with
  its message (S13 in place). Its page offers Save report; Next removes everything setup added
  and closes setup (AC-W3). }

{ The stage of an engine failure code, for "Setup could not <stage>" (spec 7.2). 0: the
  catalog's "Slate Operations did not start." }
function StageOfCode(Code: String): Integer;
begin
  Result := 0;
  if (Pos('pull', Code) > 0) or (Code = 'manifest_invalid') or (Code = 'image_missing') or (Pos('prefetch', Code) > 0) then Result := 1
  else if (Code = 'secrets_failed') or (Code = 'env_render_failed') or (Code = 'bundle_incomplete') or (Code = 'install_state_mismatch') then Result := 2
  else if Code = 'ca_failed' then Result := 3
  else if Code = 'provisioning_failed' then Result := 4
  else if (Code = 'https_not_ready') or (Pos('api', Code) > 0) then Result := 5
  else if Pos('bootstrap', Code) > 0 then Result := 6
  else if (Pos('backup', Code) > 0) or (Code = 'recovery_key_failed') or (Pos('restic', Code) > 0) then Result := 7;
end;

{ The stages before the install job's own eight: the data folder and the server part. }
function PrepStageCount: Integer;
begin
  Result := 1 + BgCount;
end;

{ Every S12 stage, split by "|": the data folder, the server part's steps, the install's. }
function S12Stages: String;
var
  I: Integer;
begin
  Result := CM('s12_stage_data') + '|' + BgStageNames;
  for I := 1 to 8 do
    Result := Result + '|' + CM('s12_stage' + IntToStr(I));
end;

procedure InstallFailAt(StageName, Text: String);
begin
  InstallFailed := True;
  InstallFailStage := StageName;
  if Text = '' then
    Text := CM('s12_not_ready');
  InstallFailText := Text;
  Log('Install stopped at "' + StageName + '".');
  RenderPage(P_INSTALL);
end;

{ Stage: one of the install job's eight stages (1 to 8), or 0 for "Start Slate Operations". }
procedure InstallFail(Stage: Integer; Text: String);
begin
  if Stage > 0 then
  begin
    if Text = '' then
      Text := FM1('s13_could_not', CM('s12_fail' + IntToStr(Stage)));
    InstallFailAt(CM('s12_stage' + IntToStr(Stage)), Text);
  end
  else
    InstallFailAt(CM('s12_stage5'), Text);
end;

{ The message of a failed data folder or server part step. }
function PrepFailText(Code: String): String;
begin
  if Code = 'helper_timeout' then Result := CM('s12_av_blocked')
  else if Code = 'job_timeout' then Result := CM('s12_step_limit')
  else if Code = 'service_logon_failed' then Result := CM('s12_logon_failed')
  else if Code = 'kept_mismatch' then Result := CM('s07_kept_unreadable')
  else if Code = 'not_empty' then Result := CM('s07_not_empty')
  else if Code = 'drive_not_fixed_ntfs' then Result := CM('s07_usb_note')
  else if (Code = 'data_folder_parent_unsafe') or (Code = 'payload_part_missing') then Result := FM1('s12_folder_changed', DataRoot)
  else Result := CM('s07_start_failed');
end;

{ The disk limit that prepare-data recorded in the administrator-only state file. }
function VhdSizeGb: Integer;
begin
  Result := StrToIntDef(JsonLiteral(ReadText(ExpandConstant('{commonappdata}\SlateOps\state\install.json')), 'vhd_size_gb'), 0);
  if Result < 25 then
    Result := 25;
end;

{ The install job with the answers (AC-W5): the existing install keys with the administrator's
  email address and user name, no email server keys, and admin_password beside "answers" (the
  engine holds it in memory only and never stores it with the answers, packaging/engine
  install.py). The input goes through the pipe only (plan 3.2 rule 3), so the password never
  reaches a file; TimeZone is the IANA name of this PC's zone. A kept reinstall sends no
  answers: the kept data holds them. }
procedure InstallStartJob(TimeZone: String);
var
  Answers: String;
begin
  if KeptMode then
    Answers := '{"run_id":"' + RunId + '","version":"' + SetupVersion + '"}'
  else
    Answers := '{"run_id":"' + RunId + '","version":"' + SetupVersion + '","answers":{' +
      '"business_name":' + JsonText(Trim(OrgName.Text)) + ',"slug":' + JsonText(DefaultSlug(Trim(OrgName.Text))) +
      ',"admin_email":' + JsonText(Trim(OrgEmail.Text)) + ',"admin_username":' + JsonText(UserFromName(Trim(OrgYourName.Text), Trim(OrgEmail.Text))) +
      ',"public_host":' + JsonText(HostName + '.local') + ',"backup_target":' + JsonText(Uppercase(BackupDrive) + '\SlateOps-backups') +
      ',"data_vhd_max_gb":' + IntToStr(VhdSizeGb) + ',"time_zone":' + JsonText(TimeZone) + '},' +
      '"admin_password":' + JsonText(OrgPassword.Text) + '}';
  InstallStep := 2;
  { The answers go in and the result (with the recovery key) comes out through the pipe. }
  StartJob('install', Answers, 'install', True, True, INSTALL_JOB_MINUTES);
  Answers := '';
  RenderPage(P_INSTALL);
end;

{ AC-W5: before the install job, the channel self-test (plan F4d) and R7 (spec 5.2), as M02 runs
  them before the email password. }
procedure InstallChannelCheck(TimeZone: String);
var
  Value: String;
begin
  InstallTz := TimeZone;
  if KeptMode then
  begin
    InstallStartJob(TimeZone);
    Exit;
  end;
  Value := RandomHex(32);
  StartJob('pipe-test', Value, 'selftest:' + GetSHA256OfString(AnsiString(Value)), True, True, 2);
  RenderPage(P_INSTALL);
end;

procedure InstallNextStep;
var
  Lid, Extra: String;
begin
  if InstallStep = 0 then
  begin
    { Plan 3.2 rule 4 and the engine's target rule (parent decision 3): <drive>:\SlateOps-backups. }
    if KeptMode then begin InstallStep := 1; InstallNextStep; Exit; end;
    InstallOut := NewOut('prepare-backup');
    InstallOutAt := GetTickCount;
    StartHelper('prepare-backup', RunId, InstallOut, '-Drive ' + Uppercase(BackupDrive));
  end
  else if InstallStep = 1 then
  begin
    { W14-D9: the save and the time zone run from the timer (StepFinished 'inst-save',
      'inst-tz'), then InstallChannelCheck. }
    Extra := '-Stage install_started';
    if KeptMode then
      Extra := Extra + ' -KeptMark';
    RunStep('save-progress', Extra, 'inst-save', '', 0, 0, INSTALL_STEP_MS);
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

{ Stage 1 and the server part (InstallStep -1). }
procedure PollServerPrep;
var
  Code: String;
begin
  if DataStarted and not DataPrepared then
  begin
    if ExtractRunning or (BgOut = '') then
      Exit;
    Code := ReadResultCode(BgOut);
    if (Code = '') and (Elapsed(DataStartedAt) > DATA_LIMIT_MS) then
      Code := 'helper_timeout';
    if Code = '' then
      Exit;
    DataStarted := False;
    if Code <> 'ready' then
    begin
      InstallFailAt(CM('s12_stage_data'), PrepFailText(Code));
      Exit;
    end;
    DataPrepared := True;
    StartBackground;
    RenderPage(P_INSTALL);
    Exit;
  end;
  PollBackground;
  if BgFailed then
  begin
    InstallFailAt(StageName(BgStageNames, BgIndex + 1), PrepFailText(BgCode));
    Exit;
  end;
  if BgDone then
  begin
    InstallStep := 0;
    InstallNextStep;
  end;
end;

procedure PollInstall;
var
  Code, Text, Expected: String;
begin
  if (not InstallStarted) or InstallDone or InstallFailed then
    Exit;
  if InstallStep = -1 then
  begin
    PollServerPrep;
    Exit;
  end;
  { AC-W5: the channel self-test before the install job; R7 follows (StepFinished 'inst-r7'). }
  if (InstallStep = 1) and (Copy(JobPurpose, 1, 9) = 'selftest:') and (JobState = JOB_DONE) then
  begin
    JobState := JOB_IDLE;
    Expected := Copy(JobPurpose, Length('selftest:') + 1, 64);
    JobPurpose := '';
    if (JobText <> '') and (Pos('"sha256":"' + Lowercase(Expected) + '"', Lowercase(JobText)) > 0) then
      RunStep('r7', '', 'inst-r7', '', 0, 0, INSTALL_STEP_MS)
    else
      InstallFail(6, CM('s09_channel_failed'));
    JobText := '';
    Exit;
  end;
  if InstallStep = 2 then
  begin
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
      if Code = 'insufficient_space' then InstallFail(0, CM('s12_disk_full'))
      else if Code = 'service_logon_failed' then InstallFail(0, CM('s12_logon_failed'))
      else if Code = 'job_timeout' then InstallFail(0, CM('s12_step_limit'))
      else if Code = 'helper_timeout' then InstallFail(0, CM('s12_av_blocked'))
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
  { W14-D9: step 1 (the save, the time zone, R7) runs in the step runner. }
  if InstallStep = 1 then
    Exit;
  Code := ReadResultCode(InstallOut);
  if (Code = '') and (Elapsed(InstallOutAt) > INSTALL_STEP_MS) then
  begin
    { Correction 5: a helper that never answered (spec 7.5 antivirus row). }
    if InstallStep = 0 then InstallFail(7, CM('s12_av_blocked')) else InstallFail(8, CM('s12_av_blocked'));
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

procedure RenderInstall;
begin
  BeginBody(P_INSTALL);
  WizardForm.PageNameLabel.Caption := CM('s12_title');
  WizardForm.PageDescriptionLabel.Caption := CM('s12_subtitle');
  SetNextCaption(CM('btn_next'));
  AddStageLine(3);
  if InstallFailed then
  begin
    { AC-W3: Save report first (in the row), then Next removes everything and closes setup. }
    AddFailure(InstallFailStage, InstallFailText, False);
    AddText(CM('s13_remove_what'), False);
    SetNextCaption(CM('s13_remove'));
    WizardForm.NextButton.Enabled := True;
    Exit;
  end;
  { W14-D5 (7.6 "S12 install"): every stage, the action that runs now, the time so far. }
  if InstallDone then
    AddProgress('install', S12Stages, PrepStageCount + 9, '', 0, '')
  else
    AddProgress('install', S12Stages, WaitStage('install'), WaitActionText('install'), InstallStartedAt, CM('wait_up_to_30'));
  BlockGap;
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

{ W14-D9: the printer list comes from the helper on the timer (StepFinished 'printers'). }
procedure PrintKeyClick(Sender: TObject);
begin
  if StepRunning then
    Exit;
  if RunStep('printers', '', 'printers', '', 0, 0, HELPER_LIMIT_MS) then
  begin
    KeyStateText := CM('s14_finding_printers');
    RefreshKeyState;
  end;
end;

procedure ShowPrinterForm(Text: String);
var
  Form: TSetupForm;
  Combo: TNewComboBox;
  Go, Stop: TNewButton;
  Rest, Name: String;
  Files: array of Boolean;
  Count, Start, Answer: Integer;
begin
  KeyStateText := '';
  { The key form closed (or the key went) while the list was read: nothing to print. }
  if KeyText = '' then
    Exit;
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
    FitFormRow(Form, Go, Stop);
    ModalOpen := True;
    Answer := Form.ShowModal;
    ModalOpen := False;
    if (Answer = mrOk) and (Combo.ItemIndex >= 0) then
    begin
      if Files[Combo.ItemIndex] then
        KeyStateText := CM('s14_file_printer')
      else
      begin
        { 7.6 "S14 key": the line before the spool call (in this process, no async point). }
        KeyStateText := FM1('s14_sending', Combo.Items[Combo.ItemIndex]);
        RefreshKeyState;
        if PrintKey(Combo.Items[Combo.ItemIndex]) then
          KeyStateText := CM('s14_printed')
        else
          KeyStateText := '';
      end;
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
  SetNextCaption(CM('btn_next'));
  WizardForm.CancelButton.Visible := False;
  WizardForm.BackButton.Visible := False;
  if KeyState = 'making' then
  begin
    { W14-D5 (7.6 "S14 key"): full form, one stage. }
    AddProgress('key', '', 1, WaitActionText('key'), KeyStartedAt, '');
    WizardForm.NextButton.Enabled := False;
    Exit;
  end;
  if KeyState = 'failed' then
  begin
    AddFailure(CM('s14_title'), CM('s14_key_failed'), True);
    Exit;
  end;
  { The key is static text that cannot be selected; no Copy button (spec S14). }
  { W14-D3: one flat border round the key, on the page color. }
  Panel := TPanel.Create(WizardForm);
  Panel.Parent := Cur;
  Panel.BevelOuter := bvNone;
  Panel.BorderStyle := bsSingle;
  Panel.ParentBackground := False;
  Panel.Color := Cur.Color;
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
  CurY := CurY + Panel.Height + ScaleY(4);
  AddText(CM('s14_text'), False);
  ItemGap;
  { W14-D3 (6.1 L5): [Print the key] [E:] [Save to a USB drive] in one row. }
  Button := AddRowButton(CM('s14_print'), 0);
  Button.OnClick := @PrintKeyClick;
  List := UsbDrives;
  KeyUsb := nil;
  if List <> '' then
  begin
    KeyUsb := TNewComboBox.Create(WizardForm);
    KeyUsb.Parent := Cur;
    KeyUsb.Style := csDropDownList;
    KeyUsb.SetBounds(RowX, CurY + (Button.Height - ScaleY(21)) div 2, ScaleX(80), ScaleY(21));
    RowX := RowX + KeyUsb.Width + ScaleX(8);
    while Pos(';', List) > 0 do
    begin
      Item := Copy(List, 1, Pos(';', List) - 1);
      List := Copy(List, Pos(';', List) + 1, Length(List));
      KeyUsb.Items.Add(Item);
    end;
    KeyUsb.ItemIndex := 0;
    Button := AddRowButton(CM('s14_usb'), 0);
    Button.OnClick := @SaveKeyClick;
  end;
  EndRow;
  if List = '' then
    AddText(CM('s14_no_usb'), False);
  { 6.1 L2: result lines are regular. }
  if KeyStateText <> '' then
    AddText(KeyStateText, False);
  ItemGap;
  KeyCheck := TNewCheckBox.Create(WizardForm);
  KeyCheck.Parent := Cur;
  KeyCheck.Caption := CM('s14_check');
  KeyCheck.SetBounds(0, CurY, Cur.Width, ScaleY(18));
  KeyCheck.Checked := KeyChecked;
  KeyCheck.OnClick := @KeyCheckClick;
  { The one line of "Saving your progress..." after Next (W14-D9). }
  AddStepLine;
  { W8-4: Next stays off until the box is checked. }
  WizardForm.NextButton.Enabled := KeyChecked and not StepRunning;
end;

procedure StartNewKey;
begin
  KeyState := 'making';
  KeyStartedAt := GetTickCount;
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

{ Design B7: the wait says what happens. W14-D9 (7.6 "M01 Send my invitation again"): the job
  runs from the timer (PollMaint, phase invite) with its one line under the actions. }
procedure InviteClick(Sender: TObject);
begin
  if JobRunning or StepRunning or (MaintPhase <> '') then
    Exit;
  MaintLine := '';
  MaintPhase := 'invite';
  MaintAt := GetTickCount;
  StartJob('resend-invitation', '{"run_id":"' + RunId + '"}', 'invite', False, False, 2);
  RenderPage(P_MAINT);
end;

procedure InviteDone(Code: String);
begin
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
    ShowReportLine;
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

{ W14-D5: the labels of the running waits; captions only, the page is not drawn again (6.1). }
procedure RefreshWaitLabels;
var
  Line: String;
begin
  if WaitTime <> nil then
    WaitTime.Caption := TimeLine;
  if (WaitNow <> nil) and (WaitKind <> '') then
  begin
    Line := WaitActionText(WaitKind);
    if (Line <> '') and (WaitNow.Caption <> Line) then
      WaitNow.Caption := Line;
  end;
  if StepLabel <> nil then
  begin
    Line := PageLineText;
    if Line <> '' then
      StepLabel.Caption := Line;
  end;
  if ReportPhase <> '' then
    ShowReportLine;
end;

procedure TimerTick(H, Msg, Id, Tick: Longword);
var
  Code: String;
begin
  { W14-D9: Save report moves in every state: inside a modal form (the S13 form) and in the
    settings program's Start menu report, before the wizard exists. }
  if ReportPhase <> '' then
  begin
    if ReportPhase = 'linux' then
      PollJob;
    PollReport;
  end;
  { DEC-0041 (AC-W3, AC-W4): while the removal form is open, the timer runs only the removal;
    the form is modal, so this comes before the gates below (as Save report does). }
  if RemoveForm <> nil then
  begin
    if not RemoveTicking then
    begin
      RemoveTicking := True;
      try
        PollCloseFlow;
        RefreshWaitLabels;
      finally
        RemoveTicking := False;
      end;
    end;
    Exit;
  end;
  if not WizardReady then
    Exit;
  { W9: while the key form is open, only its USB list follows the plugged drives, and its
    printer list step runs (W14-D9). }
  if KeyFormOpen then
  begin
    if (KeyUsb <> nil) and (UsbDrives <> KeyFormUsbSeen) then
      FillKeyFormUsb;
    { The key form opens from PollMaint, inside a tick (Ticking is set), so this branch has its
      own guard. }
    if not KeyTicking then
    begin
      KeyTicking := True;
      try
        PollStep;
      finally
        KeyTicking := False;
      end;
    end;
    Exit;
  end;
  if Ticking or ModalOpen then
  begin
    RefreshWaitLabels;
    Exit;
  end;
  Ticking := True;
  try
    PollJob;
    PollStep;
    PollExtract;
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
        PrepFeature := JsonValue(ReadText(PrepOut), 'feature');
        PrepWsl := JsonValue(ReadText(PrepOut), 'wsl');
        if Pos('"restart_needed":true', ReadText(PrepOut)) > 0 then
        begin
          { Spec 7.5 resume_other_user: the progress is saved when "ready to restart" opens.
            W14-D9: from the timer; StepFinished 'prep-save' opens "ready to restart". }
          PrepState := 'saving';
          RunStep('save-progress', '-Stage feature_restart -SetupPath ' + AddQuotes(ExpandConstant('{srcexe}')), 'prep-save', '', 0, 0, HELPER_LIMIT_MS);
        end
        else
          PrepState := 'done';
        RenderPage(P_RESTART);
      end
      else if Code <> '' then
      begin
        PrepState := 'failed';
        PrepFailKey := JsonValue(ReadText(PrepOut), 'message_key');
        RenderPage(P_RESTART);
      end
      else if Elapsed(PrepStartedAt) > DATA_LIMIT_MS then
      begin
        PrepState := 'failed_av';
        RenderPage(P_RESTART);
      end;
    end;
    PollMail;
    PollInstall;
    PollKey;
    PollMaint;
    PollUpdate;
    RefreshWaitLabels;
    LayoutButtonRow;
    { W14-D5: the page draws again only when its wait moves to another stage. }
    if (WaitKind <> '') and (WaitDrawn > 0) and (WaitStage(WaitKind) <> WaitDrawn) then
      RenderPage(-1);
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

{ One timer for the wizard and the settings program's Start menu report (W14-D9). }
procedure StartTimer;
begin
  if TimerStarted then
    Exit;
  TimerStarted := True;
  SetTimer(0, 0, 1000, CreateCallback(@TimerTick));
end;

{ DEC-0041 (AC-W3): setup changed this PC once S05 ran its helper, after a restart that setup
  asked for (AC-W9: its progress and resume entries go too), and once Install was selected. }
function SetupChangedPc: Boolean;
begin
  Result := (PrepState <> '') or (EntryNext <> '') or EntryWelcomeBack or InstallStarted;
end;

procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);
begin
  Confirm := False;
  { The removal form is modal; nothing else closes setup while it runs. }
  if CloseFlowRunning then
  begin
    Cancel := False;
    Exit;
  end;
  { W13b P2-4: M05 never removes anything. It closes when no step is in flight, after a result,
    and in the slow state of the engine job (UpdCanStop). }
  if EntryScreen = 'M05' then
  begin
    Cancel := UpdCanStop;
    Exit;
  end;
  { D-A (spec 4.5): a finished install (S06 before S14) has no Cancel, as S14. }
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
  if not SetupChangedPc then
  begin
    Cancel := ConfirmBox(CM('cancel_nothing'), '', CM('btn_stop_setup'), CM('btn_go_back'));
    Exit;
  end;
  { DEC-0041 (AC-W3): Cancel and closing the window remove everything setup added (a complete
    installation or nothing), then setup closes. A failed install asks nothing more. }
  if (not InstallFailed) and not ConfirmBox(CM('cancel_remove_all'), '', CM('btn_stop_setup'), CM('btn_go_back')) then
  begin
    Cancel := False;
    Exit;
  end;
  RunRemoval('close');
  Cancel := True;
end;

{ ------------------------------------------------------------------------------------------- }
{ Inno Setup events                                                                             }
{ ------------------------------------------------------------------------------------------- }

function InitializeSetup(): Boolean;
var
  OutFile, Text, VersionText: String;
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
  WslVersion := JsonValue(VersionText, 'wsl_version');
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
  { AC-W9: a check restart that setup asked for before S05 goes on at S02. }
  EntryWelcomeBack := Pos('"welcome_back":true', Text) > 0;
  { DEC-0041 (AC-W4): an earlier run that did not finish; CurPageChanged removes it before S01. }
  EntryCleanup := (Pos('"cleanup":true', Text) > 0) and not StateUnsafe and not SETTINGS_BUILD;
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
  { The pipe's access list (S14 new key, M01 jobs) and the data folder of the installation. }
  if (EntryNext = 'S14') or (EntryScreen = 'M01') then
  begin
    OutFile := NewOut('account');
    RunHelper('account-sid', RunId, OutFile, '');
    ServiceSid := JsonValue(ReadText(OutFile), 'sid');
    Text := ReadText(ExpandConstant('{commonappdata}\SlateOps\state\install.json'));
    DataRoot := JsonValue(Text, 'data_root');
    DataPrepared := DataRoot <> '';
  end;
  { DEC-0041: the only continuation, after the restart that S05 asked for. }
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
  { W14-D3 (parent decision, 2026-11-18): the wizard is 165% high, so S09 with Other and every
    field ends above the status line (6.1 L8, L12). Inno 6.7.4 accepts WizardSizePercent only
    up to 150 (Compiler.SetupCompiler.pas, StrToPercentages 100..150), so the [Code] adds the
    rest the way Inno applies the percentage: a taller client area, with the anchored controls
    following. Before any page is built, so every surface has the new height. }
  WizardForm.ClientHeight := (WizardForm.ClientHeight * 165) div 150;
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
  { W14-D3: the license page's own line repeated the subtitle; the license text takes its place. }
  WizardForm.LicenseLabel1.Visible := False;
  WizardForm.LicenseMemo.Height := WizardForm.LicenseMemo.Height + (WizardForm.LicenseMemo.Top - WizardForm.LicenseLabel1.Top);
  WizardForm.LicenseMemo.Top := WizardForm.LicenseLabel1.Top;
  { Spec S04: a link-style button to the third-party notices, under the license text. }
  NoticesLink := TNewLinkLabel.Create(WizardForm);
  NoticesLink.Parent := WizardForm.LicensePage;
  NoFocusBox(NoticesLink);
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
  { W14-D3 (6.1 L11): Inno's row as Inno placed it. }
  BtnDefaultW := WizardForm.NextButton.Width;
  BtnRight := WizardForm.CancelButton.Left + WizardForm.CancelButton.Width;
  BtnGapBN := WizardForm.NextButton.Left - (WizardForm.BackButton.Left + WizardForm.BackButton.Width);
  BtnGapNC := WizardForm.CancelButton.Left - (WizardForm.NextButton.Left + WizardForm.NextButton.Width);
  WizardReady := True;
#ifdef SelfTest
  RunSelfTest;
  Exit;
#endif
  StartTimer;
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
  { W9: with kept data the answers, the backup drive and the recovery key come from the kept
    installation (spec 4.3: no S08, no S10, no S14). }
  if KeptMode and ((PageID = Pages[P_ORG].ID) or (PageID = Pages[P_BACKUP].ID) or (PageID = Pages[P_KEY].ID)) then
  begin
    Result := True;
    Exit;
  end;
  { DEC-0041 (AC-W1): setup has no email page; the S09 form is M02 of the settings program only
    (MaintSkip above). Only the S05 restart (S06, then S07) and a finished install (S06, then
    S14) start past S01. }
  if (PageID = Pages[P_MAINT].ID) or (PageID = Pages[P_EMAIL].ID) then Result := True
  else if PageID = wpWelcome then Result := Resumed or EntryWelcomeBack
  else if (PageID = Pages[P_CHECK].ID) or (PageID = wpLicense) then Result := Resumed
  else if PageID = Pages[P_RESTART].ID then Result := Resumed or not NeedPrepare
  else if PageID = Pages[P_BACK].ID then Result := not Resumed
  else if (PageID = Pages[P_DATA].ID) or (PageID = Pages[P_ORG].ID) or (PageID = Pages[P_BACKUP].ID) or (PageID = Pages[P_READY].ID) or (PageID = Pages[P_INSTALL].ID) then
    Result := Resumed and (EntryNext = 'S14');
  { S11 "Change": pages between the target and S11 are passed over in both directions. }
  if (JumpTarget > 0) and (PageID > JumpTarget) and (PageID < Pages[P_READY].ID) then
    Result := True;
  if ReturnToReady and (PageID > WizardForm.CurPageID) and (PageID < Pages[P_READY].ID) then
    Result := True;
end;

{ S15 (spec S15); a procedure, so the W14 self-test draws it too. W14-D3 (6.1 L4, L6): one label
  per step, 12 px apart, and "Open Slate Operations" on the page under step 2; built once,
  because Inno's page stays and CurPageChanged can run again. }
procedure PlaceFinishedText(Index: Integer; Text: String; var Y: Integer);
begin
  if S15Steps[Index] = nil then
  begin
    S15Steps[Index] := TNewStaticText.Create(WizardForm);
    S15Steps[Index].Parent := WizardForm.FinishedPage;
    S15Steps[Index].AutoSize := False;
    S15Steps[Index].WordWrap := True;
    S15Steps[Index].ShowAccelChar := False;
  end;
  S15Steps[Index].Visible := Text <> '';
  if Text = '' then
    Exit;
  S15Steps[Index].SetBounds(WizardForm.FinishedLabel.Left, Y, WizardForm.FinishedLabel.Width, ScaleY(15));
  S15Steps[Index].Caption := Text;
  WizardForm.AdjustLabelHeight(S15Steps[Index]);
  Y := Y + S15Steps[Index].Height + ScaleY(12);
end;

procedure RenderFinishedPage;
var
  Step1, Step3: String;
  Y: Integer;
begin
  WizardForm.FinishedHeadingLabel.Caption := CM('s15_title');
  { Design B9: after a resume the email address and the security code can be unknown. }
  if KeptMode then
    Step1 := ''
  else if Trim(OrgEmail.Text) = '' then
    Step1 := CM('s15_step1_no_address')
  else
    Step1 := FM1('s15_step1', Trim(OrgEmail.Text));
  Step3 := CM('s15_step3') + #13#10 + 'http://' + HostName + '.local/trust';
  if SecurityCode <> '' then
    Step3 := Step3 + #13#10 + FM1('s15_security', SecurityCode);
  WizardForm.FinishedLabel.Caption := '';
  WizardForm.FinishedLabel.Visible := False;
  if GetArrayLength(S15Steps) = 0 then
    SetArrayLength(S15Steps, 5);
  Y := WizardForm.FinishedLabel.Top;
  PlaceFinishedText(0, Step1, Y);
  PlaceFinishedText(1, CM('s15_step2'), Y);
  if S15Open = nil then
  begin
    S15Open := TNewButton.Create(WizardForm);
    S15Open.Parent := WizardForm.FinishedPage;
    S15Open.OnClick := @OpenAppClick;
  end;
  S15Open.Caption := CM('s15_open');
  S15Open.SetBounds(WizardForm.FinishedLabel.Left, Y - ScaleY(8), WizardForm.CalculateButtonWidth([CM('s15_open')]), WizardForm.NextButton.Height);
  Y := S15Open.Top + S15Open.Height + ScaleY(12);
  PlaceFinishedText(2, Step3, Y);
  PlaceFinishedText(3, CM('s15_desk'), Y);
  PlaceFinishedText(4, CM('s15_starts'), Y);
  SetNextCaption(CM('s15_finish'));
end;

procedure CurPageChanged(CurPageID: Integer);
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
    { DEC-0041 (AC-W4): an earlier run that did not finish is removed first, with its stages;
      then setup starts here. When the removal stops at a limit or is closed, setup closes and
      the next start removes the rest. }
    if EntryCleanup then
    begin
      EntryCleanup := False;
      if not RunRemoval('start') then
      begin
        ForceClose := True;
        WizardForm.Close;
        Exit;
      end;
    end;
    WizardForm.WelcomeLabel1.Caption := CM('s01_title');
    WizardForm.WelcomeLabel2.Caption := CM('s01_text');
    SetNextCaption(CM('s01_next'));
    if StateUnsafe then
    begin
      WizardForm.WelcomeLabel2.Caption := CM('s01_state_unsafe');
      WizardForm.NextButton.Enabled := False;
      { W14-D3 (6.1 L6): Save report sits on the page under the message, not in the row. }
      WizardForm.AdjustLabelHeight(WizardForm.WelcomeLabel2);
      if S01Report = nil then
      begin
        S01Report := TNewButton.Create(WizardForm);
        S01Report.Parent := WizardForm.WelcomePage;
        S01Report.Caption := CM('btn_save_report');
        S01Report.OnClick := @SaveReport;
      end;
      S01Report.SetBounds(WizardForm.WelcomeLabel2.Left, WizardForm.WelcomeLabel2.Top + WizardForm.WelcomeLabel2.Height + ScaleY(12),
        WizardForm.CalculateButtonWidth([CM('btn_save_report')]), WizardForm.NextButton.Height);
      if S01Line = nil then
      begin
        S01Line := TNewStaticText.Create(WizardForm);
        S01Line.Parent := WizardForm.WelcomePage;
        S01Line.AutoSize := False;
        S01Line.WordWrap := True;
        S01Line.ShowAccelChar := False;
      end;
      S01Line.SetBounds(S01Report.Left, S01Report.Top + S01Report.Height + ScaleY(4), WizardForm.WelcomeLabel2.Width, ScaleY(15));
      S01Line.Caption := ReportLine;
      WizardForm.AdjustLabelHeight(S01Line);
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
      { W14-D9: nothing waits for the shortcut's removal. }
      StartHelper('clear-resume', RunId, NewOut('clear'), '');
      if GetArrayLength(DriveLetters) = 0 then
        ReadDataDrives;
    end;
    RenderData;
  end
  else if CurPageID = Pages[P_ORG].ID then
    SetNextCaption(CM('btn_next'))
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
  end
  else if CurPageID = Pages[P_BACKUP].ID then
    RenderBackup
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
      { DEC-0041 (AC-W2): the server work starts here, after Install. }
      InstallStarted := True;
      InstallStartedAt := GetTickCount;
      StartServerPrep;
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
    SetNextCaption(CM('s15_finish'));
  end
  else if CurPageID = wpFinished then
    RenderFinishedPage;
  { W14-D3 (6.1 L11): Inno sets its own captions at each page change. }
  LayoutButtonRow;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if SELF_TEST then
    Exit;
  if CloseFlowRunning then
  begin
    Result := False;
    Exit;
  end;
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
      { W14-D9: from the timer; StepFinished 'restart-now' closes setup. }
      if RunStep('restart', '', 'restart-now', CM('later_restarting'), 0, 0, HELPER_LIMIT_MS) then
        RenderPage(P_RESTART);
      Result := False;
    end
    else
      Result := PrepState = 'done';
  end
  else if CurPageID = Pages[P_BACK].ID then
    Result := CheckDone and (CountClass('fix') = 0)
  else if CurPageID = Pages[P_DATA].ID then
  begin
    { DEC-0041 (AC-W1): Next checks the folder and writes nothing (StepFinished 'data-check'
      selects Next again); the data folder is made on S12. }
    Result := (DataChecked <> '') and (DataChecked = DataRoot) and (KeptChecked = KeptMode);
    if not Result and not StepRunning then
      StartDataCheck;
  end
  else if CurPageID = Pages[P_ORG].ID then
    Result := CheckOrg
  else if CurPageID = Pages[P_BACKUP].ID then
  begin
    { W14-D9 (7.6 "S10 Next"): drive-check runs from the timer; StepFinished 's10-check' selects
      Next again once the drive is ready. }
    Result := False;
    if (BackupCheckedDrive <> '') and (BackupCheckedDrive = BackupDrive) then
    begin
      BackupCheckedDrive := '';
      Result := True;
      Exit;
    end;
    BackupError := '';
    if RunStep('drive-check', '-Drive ' + Uppercase(BackupDrive), 's10-check', FM1('m03_checking', BackupDrive), 0, 0, HELPER_LIMIT_MS) then
      RenderPage(P_BACKUP);
  end
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
      { DEC-0041 (AC-W3): after Save report, Next removes everything setup added and closes
        setup. Save report finishes first (it can run the server part's log job). }
      Result := False;
      if ReportPhase <> '' then
        Exit;
      RunRemoval('close');
      ForceClose := True;
      WizardForm.Close;
    end
    else
      Result := InstallDone;
  end
  else if CurPageID = Pages[P_KEY].ID then
  begin
    if KeyState = 'failed' then
    begin
      Result := False;
      if JobRunning then
        Exit;
      StartNewKey;
      RenderKey;
      Exit;
    end;
    { W14-D9: the save runs from the timer; StepFinished 'key-saved' selects Next again. }
    Result := KeySavedDone;
    if Result or not KeyChecked then
      Exit;
    if RunStep('save-progress', '-Stage key_saved', 'key-saved', CM('later_saving'), 0, 0, HELPER_LIMIT_MS) then
      RenderPage(P_KEY);
  end
  else if CurPageID = wpFinished then
    ExtraButton.Visible := False;
end;

function BackButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = Pages[P_EMAIL].ID then
    HideShow;
  if CurPageID = Pages[P_ORG].ID then
    HideOrgShow;
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
