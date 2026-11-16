; p1-f4-test.iss - spike F4 of the Windows installer plan (section 10). A throwaway test installer.
; It installs no part of Slate Operations. It checks four things on the owner's PC:
;   1. RunOnce resume: the first run writes an HKLM RunOnce entry and asks for a restart
;      (PrepareToInstall, NeedsRestart). After the restart and the sign-in, Windows starts it again
;      with /RESUME=1. It records whether the resumed run is elevated (IsAdmin).
;   2. Long action with progress: on the resumed run, after "Ready to Install", a progress page runs
;      a 40-second action (a hidden PowerShell sleep) and polls for its end, as the real wizard
;      will poll the Exec job.
;   3. Named pipe: the wizard itself creates \\.\pipe\slateops-p1-f4-<request id> with Pascal Script
;      DLL calls (first instance, no remote clients, no-wait mode, access for Administrators and
;      slateops-svc only, owner Administrators), starts the boot-test Exec job "f4-pipe" through the
;      kit's request file, sends a random test value and checks the SHA-256 that the job returns.
;      No hidden helper process is used: the wizard polls the pipe in no-wait mode.
;   4. Uninstall and Modify: a custom form "Keep your data?" in the uninstaller, and a ModifyPath
;      entry, so that Settings > Apps > Modify opens a maintenance window.
; Results: C:\ProgramData\SlateOpsBootTest\logs\f4-results.txt (key=value lines, no secrets).
; Build (no Windows needed): docker run --rm -v "$PWD:/work" amake/innosetup:innosetup6 p1-f4-test.iss
; Output: output\SlateOpsP1F4Test.exe (unsigned).

#define AppName "Slate Operations P1 installer test"

[Setup]
AppId={{5E0F1C2A-7B3D-4A61-9C8E-2F4D6B1A0C93}
AppName={#AppName}
AppVersion=0.0.1
AppPublisher=Slate Operations (P1 test)
DefaultDirName={autopf}\SlateOps P1 installer test
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
OutputDir=output
OutputBaseFilename=SlateOpsP1F4Test
Compression=lzma2
SolidCompression=yes
SetupLogging=yes
CloseApplications=no
Uninstallable=yes

[Files]
Source: "p1-f4-readme.txt"; DestDir: "{app}"; Flags: ignoreversion

[UninstallDelete]
Type: files; Name: "{app}\maintenance.exe"
Type: files; Name: "{app}\setup-resume.exe"

[Code]
const
  RunOnceKey = 'Software\Microsoft\Windows\CurrentVersion\RunOnce';
  RunOnceName = 'SlateOpsP1F4Resume';
  UninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{5E0F1C2A-7B3D-4A61-9C8E-2F4D6B1A0C93}_is1';
  PIPE_ACCESS_DUPLEX = $00000003;
  FILE_FLAG_FIRST_PIPE_INSTANCE = $00080000;
  PIPE_TYPE_BYTE = $00000000;
  PIPE_NOWAIT = $00000001;
  PIPE_REJECT_REMOTE_CLIENTS = $00000008;
  ERROR_PIPE_CONNECTED = 535;
  ERROR_PIPE_LISTENING = 536;
  ERROR_NO_DATA = 232;
  SDDL_REVISION_1 = 1;

type
  TSecurityAttributes = record
    nLength: DWORD;
    lpSecurityDescriptor: Longint;
    bInheritHandle: Longint;
  end;

function CreateNamedPipe(lpName: String; dwOpenMode, dwPipeMode, nMaxInstances, nOutBufferSize, nInBufferSize, nDefaultTimeOut: DWORD;
  var lpSecurityAttributes: TSecurityAttributes): Longint;
  external 'CreateNamedPipeW@kernel32.dll stdcall';
function ConnectNamedPipe(hNamedPipe: Longint; lpOverlapped: Longint): Boolean;
  external 'ConnectNamedPipe@kernel32.dll stdcall';
function DisconnectNamedPipe(hNamedPipe: Longint): Boolean;
  external 'DisconnectNamedPipe@kernel32.dll stdcall';
function WriteFile(hFile: Longint; lpBuffer: AnsiString; nNumberOfBytesToWrite: DWORD; var lpNumberOfBytesWritten: DWORD; lpOverlapped: Longint): Boolean;
  external 'WriteFile@kernel32.dll stdcall';
function ReadFile(hFile: Longint; lpBuffer: AnsiString; nNumberOfBytesToRead: DWORD; var lpNumberOfBytesRead: DWORD; lpOverlapped: Longint): Boolean;
  external 'ReadFile@kernel32.dll stdcall';
function CloseHandle(hObject: Longint): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';
function ConvertStringSecurityDescriptorToSecurityDescriptor(StringSecurityDescriptor: String; StringSDRevision: DWORD;
  var SecurityDescriptor: Longint; SecurityDescriptorSize: Longint): Boolean;
  external 'ConvertStringSecurityDescriptorToSecurityDescriptorW@advapi32.dll stdcall';
function LocalFree(hMem: Longint): Longint;
  external 'LocalFree@kernel32.dll stdcall';

var
  Resumed: Boolean;

function KitPath(const Relative: String): String;
begin
  Result := ExpandConstant('{commonappdata}\SlateOpsBootTest\') + Relative;
end;

procedure AddResult(const Line: String);
begin
  if DirExists(KitPath('logs')) then
    SaveStringToFile(KitPath('logs\f4-results.txt'), Line + #13#10, True);
end;

function RandomHex(Count: Integer): String;
var
  I: Integer;
begin
  Result := '';
  for I := 1 to Count do
    Result := Result + Copy('0123456789abcdef', Random(16) + 1, 1);
end;

function ServiceSid(): String;
var
  Text: AnsiString;
  P, Q: Integer;
begin
  { state.json is written by the kit (administrators only); the value is a SID, not a secret. }
  Result := '';
  if not LoadStringFromFile(KitPath('state\state.json'), Text) then Exit;
  P := Pos('"account_sid"', Text);
  if P = 0 then Exit;
  Text := Copy(Text, P + 13, 200);
  P := Pos('"S-1-', Text);
  if P = 0 then Exit;
  Text := Copy(Text, P + 1, 200);
  Q := Pos('"', Text);
  if Q > 0 then Result := Copy(Text, 1, Q - 1);
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if ExpandConstant('{param:MODIFY|0}') = '1' then begin
    AddResult('modify_opened=1');
    MsgBox('Maintenance mode works.' + #13#10#13#10 + 'P1 test: "Modify" in Settings > Apps opened this window. Select OK to close it.', mbInformation, MB_OK);
    Result := False;
    Exit;
  end;
  Resumed := ExpandConstant('{param:RESUME|0}') = '1';
  if Resumed then begin
    AddResult('resume_started=1');
    if IsAdmin then AddResult('resume_is_admin=1') else AddResult('resume_is_admin=0');
  end else
    AddResult('first_run_started=1');
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  { After the restart, go straight on: the folder is already chosen. }
  Result := Resumed and (PageID = wpSelectDir);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not Resumed then begin
    { RunOnce starts a copy in the program folder: every user can read it, only administrators can
      change it. The kit folder would hide an ACL failure behind the elevation question. }
    ForceDirectories(WizardDirValue);
    CopyFile(ExpandConstant('{srcexe}'), AddBackslash(WizardDirValue) + 'setup-resume.exe', False);
    RegWriteStringValue(HKLM, RunOnceKey, RunOnceName, '"' + AddBackslash(WizardDirValue) + 'setup-resume.exe" /RESUME=1');
    AddResult('runonce_written=1');
    NeedsRestart := True;
    Result := 'P1 test: Windows must restart once.' + #13#10#13#10 +
      'Select "No, I will restart my computer later", then Finish. The P1 script restarts the PC.' + #13#10 +
      'After the restart and your sign-in, this test installer opens again by itself.';
  end;
end;

procedure RunLongAction();
var
  Page: TOutputProgressWizardPage;
  Done: String;
  Code, Ticks: Integer;
begin
  Page := CreateOutputProgressPage('Long action', 'P1 test: a long action with a progress bar (about 40 seconds).');
  Done := ExpandConstant('{tmp}\long-action-done.txt');
  Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -NonInteractive -WindowStyle Hidden -Command "Start-Sleep -Seconds 40; Set-Content -LiteralPath ''' + Done + ''' -Value ok"',
    '', SW_HIDE, ewNoWait, Code);
  Page.Show;
  try
    Ticks := 0;
    while (not FileExists(Done)) and (Ticks < 480) do begin
      if Ticks < 160 then Page.SetProgress(Ticks, 160) else Page.SetProgress(160, 160);
      Page.SetText('Working on a long action...', IntToStr(Ticks div 4) + ' s');
      Sleep(250);
      Ticks := Ticks + 1;
    end;
  finally
    Page.Hide;
  end;
  if FileExists(Done) then begin
    AddResult('long_action=ok');
    AddResult('long_action_seconds=' + IntToStr(Ticks div 4));
  end else
    AddResult('long_action=timeout');
end;

procedure RunPipeTest();
var
  Page: TOutputProgressWizardPage;
  Sa: TSecurityAttributes;
  Sd, Pipe, Code, Ticks: Longint;
  RequestId, Name, Value, Expected, Sid: String;
  Buffer, Answer: AnsiString;
  Written, Got: DWORD;
  Connected: Boolean;
  Err: Longint;
begin
  Sid := ServiceSid();
  if Sid = '' then begin AddResult('pipe=no_service_sid'); Exit; end;
  { The first group comes from the clock (digits only, valid hex), so two runs never share a pipe name. }
  RequestId := Copy(GetDateTimeString('ddhhnnss', #0, #0), 1, 8) + '-' + RandomHex(4) + '-4' + RandomHex(3) + '-a' + RandomHex(3) + '-' + RandomHex(12);
  Name := '\\.\pipe\slateops-p1-f4-' + RequestId;
  Value := RandomHex(32);
  Expected := GetSHA256OfString(Value);
  Sd := 0;
  if not ConvertStringSecurityDescriptorToSecurityDescriptor('O:BAD:P(A;;GA;;;BA)(A;;GA;;;' + Sid + ')', SDDL_REVISION_1, Sd, 0) then begin
    AddResult('pipe=sd_failed;error=' + IntToStr(DLLGetLastError())); Exit;
  end;
  Sa.nLength := 12;
  Sa.lpSecurityDescriptor := Sd;
  Sa.bInheritHandle := 0;
  Pipe := CreateNamedPipe(Name, PIPE_ACCESS_DUPLEX or FILE_FLAG_FIRST_PIPE_INSTANCE,
    PIPE_TYPE_BYTE or PIPE_NOWAIT or PIPE_REJECT_REMOTE_CLIENTS, 1, 4096, 4096, 0, Sa);
  Err := DLLGetLastError();
  LocalFree(Sd);
  if Pipe = -1 then begin AddResult('pipe=create_failed;error=' + IntToStr(Err)); Exit; end;
  Page := CreateOutputProgressPage('Named pipe', 'P1 test: send a value to the Exec job through a named pipe.');
  Page.Show;
  try
    SaveStringToFile(KitPath('state\request.txt'), 'f4-pipe ' + RequestId, False);
    Exec(ExpandConstant('{sys}\schtasks.exe'), '/Run /TN "\SlateOpsBootTest\Exec"', '', SW_HIDE, ewWaitUntilTerminated, Code);
    AddResult('pipe_task_start_exit=' + IntToStr(Code));
    Connected := False;
    Ticks := 0;
    while (not Connected) and (Ticks < 240) do begin
      ConnectNamedPipe(Pipe, 0);
      Err := DLLGetLastError();
      if Err = ERROR_PIPE_CONNECTED then Connected := True
      else if (Err <> ERROR_PIPE_LISTENING) and (Err <> 0) then Ticks := 240
      else begin
        Page.SetText('Waiting for the Exec job to connect...', IntToStr(Ticks div 4) + ' s');
        Page.SetProgress(Ticks, 240);
        Sleep(250);
        Ticks := Ticks + 1;
      end;
    end;
    if not Connected then begin AddResult('pipe=not_connected;error=' + IntToStr(Err)); Exit; end;
    Buffer := Value + #10;
    if not WriteFile(Pipe, Buffer, Length(Buffer), Written, 0) then begin AddResult('pipe=write_failed;error=' + IntToStr(DLLGetLastError())); Exit; end;
    Answer := '';
    Ticks := 0;
    while (Pos(#10, Answer) = 0) and (Ticks < 120) do begin
      Buffer := StringOfChar(' ', 128);
      Got := 0;
      if ReadFile(Pipe, Buffer, 128, Got, 0) and (Got > 0) then
        Answer := Answer + Copy(Buffer, 1, Got)
      else begin
        Page.SetText('Waiting for the answer...', IntToStr(Ticks div 4) + ' s');
        Sleep(250);
        Ticks := Ticks + 1;
      end;
    end;
    if Pos(#10, Answer) > 0 then Answer := Copy(Answer, 1, Pos(#10, Answer) - 1);
    if Answer = Expected then AddResult('pipe=ok') else if Answer = '' then AddResult('pipe=no_answer') else AddResult('pipe=mismatch');
  finally
    Page.Hide;
    DisconnectNamedPipe(Pipe);
    CloseHandle(Pipe);
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if Resumed and (CurPageID = wpReady) then begin
    RunLongAction();
    RunPipeTest();
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssDone then begin
    if CopyFile(ExpandConstant('{srcexe}'), ExpandConstant('{app}\maintenance.exe'), False) then begin
      RegWriteStringValue(HKLM, UninstallKey, 'ModifyPath', '"' + ExpandConstant('{app}\maintenance.exe') + '" /MODIFY=1');
      RegWriteDWordValue(HKLM, UninstallKey, 'NoModify', 0);
      AddResult('modify_path_written=1');
    end;
  end;
end;

function InitializeUninstall(): Boolean;
var
  Form: TSetupForm;
  Info: TNewStaticText;
  Keep, Delete: TNewRadioButton;
  OKButton, CancelButton: TNewButton;
begin
  Result := True;
  if UninstallSilent then begin AddResult('uninstall_choice=silent'); Exit; end;
  Form := CreateCustomForm(ScaleX(380), ScaleY(170), False, True);
  try
    Form.Caption := 'Keep your data?';
    Info := TNewStaticText.Create(Form);
    Info.Parent := Form;
    Info.Left := ScaleX(12);
    Info.Top := ScaleY(12);
    Info.Width := Form.ClientWidth - ScaleX(24);
    Info.WordWrap := True;
    Info.Caption := 'P1 test of the uninstall page. Nothing of Slate Operations is deleted by this test.';
    Keep := TNewRadioButton.Create(Form);
    Keep.Parent := Form;
    Keep.Left := ScaleX(12);
    Keep.Top := ScaleY(52);
    Keep.Width := Form.ClientWidth - ScaleX(24);
    Keep.Caption := 'Keep my data';
    Keep.Checked := True;
    Delete := TNewRadioButton.Create(Form);
    Delete.Parent := Form;
    Delete.Left := ScaleX(12);
    Delete.Top := ScaleY(78);
    Delete.Width := Form.ClientWidth - ScaleX(24);
    Delete.Caption := 'Delete everything';
    OKButton := TNewButton.Create(Form);
    OKButton.Parent := Form;
    OKButton.Caption := 'OK';
    OKButton.Left := Form.ClientWidth - ScaleX(75 + 6 + 75 + 12);
    OKButton.Top := Form.ClientHeight - ScaleY(23 + 12);
    OKButton.Width := ScaleX(75);
    OKButton.Height := ScaleY(23);
    OKButton.ModalResult := mrOk;
    OKButton.Default := True;
    CancelButton := TNewButton.Create(Form);
    CancelButton.Parent := Form;
    CancelButton.Caption := 'Cancel';
    CancelButton.Left := Form.ClientWidth - ScaleX(75 + 12);
    CancelButton.Top := Form.ClientHeight - ScaleY(23 + 12);
    CancelButton.Width := ScaleX(75);
    CancelButton.Height := ScaleY(23);
    CancelButton.ModalResult := mrCancel;
    CancelButton.Cancel := True;
    if Form.ShowModal() = mrOk then begin
      if Keep.Checked then AddResult('uninstall_choice=keep') else AddResult('uninstall_choice=delete');
    end else begin
      AddResult('uninstall_choice=cancel');
      Result := False;
    end;
  finally
    Form.Free();
  end;
end;
