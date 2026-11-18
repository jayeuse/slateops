{ Uninstall.iss - the uninstaller's [Code] (plan 9.1, 10.3 F3 and F4c, 10.7; wizard spec U01 to
  U04; W9). Included after Wizard.iss, so it uses CM, FM, ReadText, JsonValue and NewRunId from
  there. At uninstall time there is no WizardForm, no ExtractTemporaryFiles and no *AsOriginalUser
  call (Inno Setup help), so these forms and calls stand alone. The helper runs from
  C:\ProgramData\SlateOps\scripts (TASK-0091 carry) after the state folder passes its check, and
  its result files lie in that folder (the helper's own root).

  Order (Inno 6.7.4 Setup.Uninstall.pas): InitializeUninstall shows U01 and U02 and removes
  nothing; Inno's confirmation; the progress form; usUninstall does the work (an exception there
  stops the uninstall before Inno removes a file); Inno removes its files; usPostUninstall shows
  U04. ASCII only. }

const
  { DEC-0041 (AC-W7): the limits of the uninstaller's helper steps, each above the waits inside
    the helper: the checks (60 s); the stop, whose "Keep my data" runs prepare-uninstall (up to
    600 s) and, when it fails, the restart of the server part (720 s); the data step (terminate
    120 s, unregister 300 s, the restart of a failed keep 120 s, then the delete: 660 s); the
    Windows parts (180 s); Save report's collect and zip (300 s each). }
  U_SHORT_SEC = 60;
  U_STOP_SEC = 720;
  U_DATA_SEC = 660;
  U_WINDOWS_SEC = 180;
  U_REPORT_SEC = 300;

var
  UHelper, URoot, URunId, UDataRoot, UBackupFolder, ULeft: String;
  UKeep, UDeleteBackups: Boolean;
  UDiskGb, USeq: Integer;
  URadioKeep, URadioDelete: TNewRadioButton;
  UBackupsCheck, UConfirmCheck: TNewCheckBox;
  UConfirmButton: TNewButton;
  { W14-D5 and W14-D9 (spec 7.6 "U03 uninstall", "Save report" U04): the uninstaller has no
    page timer and waits in Exec. Inno's Exec keeps processing messages while it waits (Inno 6.7
    Setup.InstFunc HandleProcessWait) but disables the windows (Setup.ScriptFunc
    TWindowDisabler), so the window repaints and a timer runs; U03 has no button to press. The
    stage line is set before each step, and the timer keeps its time current. }
  UStageLine: String;
  UStageNumber, UStageTotal: Integer;
  UStageAt: Cardinal;
  UTimerOn: Boolean;
  UReportForm: TSetupForm;
  UReportLabel: TNewStaticText;

{ DEC-0041 (AC-W7): every helper step has a limit. The helper starts without a wait, and the
  uninstaller waits for its result file in one-second waits on ping.exe (Exec keeps the window
  painting while it waits, as noted above). Past LimitSec the step gives no result (''), which
  each caller treats as a failed step; the helper is left to end by itself, and this is logged.
  The helper writes its result file with a rename, so the file is complete once it exists. }
function URun(Action, ARunId, Extra: String; LimitSec: Integer): String;
var
  OutFile: String;
  Code: Integer;
  Started: Cardinal;
begin
  USeq := USeq + 1;
  OutFile := URoot + '\uninstall-' + IntToStr(USeq) + '.json';
  DeleteFile(OutFile);
  Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ' + AddQuotes(UHelper) + ' -Action ' + Action +
    ' -RunId ' + ARunId + ' -OutFile ' + AddQuotes(OutFile) + ' ' + Extra, '', SW_HIDE, ewNoWait, Code);
  Started := GetTickCount;
  while (not FileExists(OutFile)) and ((GetTickCount - Started) < Cardinal(LimitSec * 1000)) do
    Exec(ExpandConstant('{sys}\ping.exe'), '-n 2 127.0.0.1', '', SW_HIDE, ewWaitUntilTerminated, Code);
  if not FileExists(OutFile) then
    Log('Uninstall step ' + Action + ': no result in ' + IntToStr(LimitSec) + ' s; the uninstaller goes on.');
  Result := ReadText(OutFile);
  DeleteFile(OutFile);
  DeleteFile(OutFile + '.progress');
end;

function UText(Parent: TWinControl; Top: Integer; S: String; Bold: Boolean): TNewStaticText;
begin
  Result := TNewStaticText.Create(Parent);
  Result.Parent := Parent;
  Result.AutoSize := False;
  Result.WordWrap := True;
  Result.ShowAccelChar := False;
  Result.SetBounds(ScaleX(16), Top, Parent.ClientWidth - ScaleX(32), ScaleY(15));
  Result.Caption := S;
  if Bold then
    Result.Font.Style := [fsBold];
  Result.AdjustHeight;
end;

function UButton(Parent: TSetupForm; Caption: String; Left: Integer; ModalCode: Integer): TNewButton;
begin
  Result := TNewButton.Create(Parent);
  Result.Parent := Parent;
  Result.Caption := Caption;
  Result.ModalResult := ModalCode;
  Result.SetBounds(Left, Parent.ClientHeight - ScaleY(40), ScaleX(130), ScaleY(26));
end;

{ The one line (7.6: "2 of 3: <stage>" and the time) in the report form or in Inno's uninstall
  form. }
procedure UShow;
var
  Text: String;
begin
  if UStageLine = '' then
    Exit;
  Text := OneLine(UStageNumber, UStageTotal, UStageLine, UStageAt);
  if UReportLabel <> nil then
    UReportLabel.Caption := Text
  else
  begin
    UninstallProgressForm.StatusLabel.Caption := Text;
    UninstallProgressForm.Update;
  end;
end;

procedure UTick(H, Msg, Id, Tick: Longword);
begin
  UShow;
end;

procedure UStartTimer;
begin
  if UTimerOn then
    Exit;
  UTimerOn := True;
  SetTimer(0, 0, 1000, CreateCallback(@UTick));
end;

{ U03: the stage before each step (7.6: 1 of 3 to 3 of 3). }
procedure UStage(Number: Integer; Line: String);
begin
  UStageNumber := Number;
  UStageTotal := 3;
  UStageLine := Line;
  UShow;
end;

procedure UReportSaved(Path: String);
begin
  if Path <> '' then
    MsgBox(FM1('report_saved', ExtractFileName(Path)), mbInformation, MB_OK);
end;

{ Save report from the uninstaller (plan 10.6), while the helper is still there. }
procedure USaveReport;
var
  ReportRun, Path, OldLine: String;
  OldNumber, OldTotal: Integer;
  OldAt: Cardinal;
begin
  ReportRun := NewRunId('report');
  OldLine := UStageLine;
  OldNumber := UStageNumber;
  OldTotal := UStageTotal;
  OldAt := UStageAt;
  Path := '';
  UReportForm := CreateCustomForm(ScaleX(440), ScaleY(90), False, False);
  try
    UReportForm.Caption := CM('btn_save_report');
    UReportLabel := UText(UReportForm, ScaleY(16), '', False);
    UReportForm.Show;
    UStartTimer;
    UStageAt := GetTickCount;
    UStageTotal := 4;
    UStageNumber := 3;
    UStageLine := CM('report_stage3');
    UShow;
    URun('report-collect', ReportRun, '', U_REPORT_SEC);
    UStageNumber := 4;
    UStageLine := CM('report_stage4');
    UShow;
    Path := JsonValue(URun('report-zip', ReportRun, '', U_REPORT_SEC), 'path');
  finally
    UReportLabel := nil;
    UReportForm.Free;
    UReportForm := nil;
    UStageLine := OldLine;
    UStageNumber := OldNumber;
    UStageTotal := OldTotal;
    UStageAt := OldAt;
  end;
  UReportSaved(Path);
end;

{ F4c and F3: a stop with its sentence and, while the helper can run, Save report (W9 review
  item 4). With an unsafe folder nothing more runs from it, so no Save report then. }
procedure UStopped(Text: String; CanReport: Boolean);
begin
  if CanReport then
  begin
    if TaskDialogMsgBox(Text, '', mbError, MB_YESNO, [CM('btn_save_report'), CM('btn_close')], 0) = IDYES then
      USaveReport;
  end
  else
    MsgBox(Text, mbError, MB_OK);
end;

procedure URadioClick(Sender: TObject);
begin
  if UBackupsCheck <> nil then
  begin
    UBackupsCheck.Enabled := URadioDelete.Checked;
    if not URadioDelete.Checked then
      UBackupsCheck.Checked := False;
  end;
end;

{ U01 "Keep your data?" (spec U01): Keep is the default; closing the form cancels (F4c).
  Returns 0 to cancel, 1 to keep, 2 to delete. }
function AskKeepData: Integer;
var
  Form: TSetupForm;
  Text: TNewStaticText;
  Go, Stop: TNewButton;
  Y: Integer;
begin
  Result := 0;
  UBackupsCheck := nil;
  Form := CreateCustomForm(ScaleX(500), ScaleY(300), False, False);
  try
    Form.Caption := CM('u01_title');
    Y := ScaleY(14);
    URadioKeep := TNewRadioButton.Create(Form);
    URadioKeep.Parent := Form;
    URadioKeep.Caption := CM('u01_keep');
    URadioKeep.Checked := True;
    URadioKeep.OnClick := @URadioClick;
    URadioKeep.SetBounds(ScaleX(16), Y, Form.ClientWidth - ScaleX(32), ScaleY(18));
    { W14-D3 (6.1 L4): the option, 4 px, its text, 12 px to the next option. }
    Y := Y + URadioKeep.Height + ScaleY(4);
    Text := UText(Form, Y, FM2('u01_keep_text', UDataRoot + '\kept', IntToStr(UDiskGb)), False);
    Text.Left := ScaleX(34);
    Text.Width := Form.ClientWidth - ScaleX(50);
    Text.AdjustHeight;
    Y := Y + Text.Height + ScaleY(12);
    URadioDelete := TNewRadioButton.Create(Form);
    URadioDelete.Parent := Form;
    URadioDelete.Caption := CM('u01_delete');
    URadioDelete.OnClick := @URadioClick;
    URadioDelete.SetBounds(ScaleX(16), Y, Form.ClientWidth - ScaleX(32), ScaleY(18));
    Y := Y + URadioDelete.Height + ScaleY(4);
    Text := UText(Form, Y, CM('u01_delete_text'), False);
    Text.Left := ScaleX(34);
    Text.Width := Form.ClientWidth - ScaleX(50);
    Text.AdjustHeight;
    Y := Y + Text.Height + ScaleY(4);
    { Offered only when the record names a backup folder (advisor item 6). }
    if UBackupFolder <> '' then
    begin
      UBackupsCheck := TNewCheckBox.Create(Form);
      UBackupsCheck.Parent := Form;
      UBackupsCheck.Caption := FM1('u01_backups', Copy(UBackupFolder, 1, 2));
      UBackupsCheck.Enabled := False;
      UBackupsCheck.SetBounds(ScaleX(34), Y, Form.ClientWidth - ScaleX(50), ScaleY(18));
    end;
    Go := UButton(Form, CM('u01_uninstall'), Form.ClientWidth - ScaleX(290), mrOk);
    Go.Default := True;
    Stop := UButton(Form, CM('btn_cancel'), Form.ClientWidth - ScaleX(150), mrCancel);
    Stop.Cancel := True;
    if Form.ShowModal = mrOk then
    begin
      if URadioDelete.Checked then Result := 2 else Result := 1;
      UDeleteBackups := (UBackupsCheck <> nil) and UBackupsCheck.Checked;
    end;
  finally
    Form.Free;
    UBackupsCheck := nil;
  end;
end;

procedure UConfirmClick(Sender: TObject);
begin
  UConfirmButton.Enabled := UConfirmCheck.Checked;
end;

{ U02 "Delete all Slate Operations data?": "Go back" is the default. }
function ConfirmDelete: Boolean;
var
  Form: TSetupForm;
  Text: TNewStaticText;
  Back: TNewButton;
  Line: String;
begin
  Form := CreateCustomForm(ScaleX(460), ScaleY(200), False, False);
  try
    Form.Caption := CM('u02_title');
    if UDeleteBackups then Line := FM1('u02_backups_deleted', Copy(UBackupFolder, 1, 2))
    else if UBackupFolder <> '' then Line := FM1('u02_backups_kept', Copy(UBackupFolder, 1, 2))
    else Line := '';
    Text := UText(Form, ScaleY(14), CM('u02_text') + ' ' + Line, False);
    UConfirmCheck := TNewCheckBox.Create(Form);
    UConfirmCheck.Parent := Form;
    UConfirmCheck.Caption := CM('u02_check');
    UConfirmCheck.OnClick := @UConfirmClick;
    UConfirmCheck.SetBounds(ScaleX(16), Text.Top + Text.Height + ScaleY(14), Form.ClientWidth - ScaleX(32), ScaleY(18));
    UConfirmButton := UButton(Form, CM('u02_delete'), Form.ClientWidth - ScaleX(290), mrOk);
    UConfirmButton.Enabled := False;
    Back := UButton(Form, CM('btn_go_back'), Form.ClientWidth - ScaleX(150), mrCancel);
    Back.Cancel := True;
    Back.Default := True;
    Result := Form.ShowModal = mrOk;
  finally
    Form.Free;
  end;
end;

function InitializeUninstall(): Boolean;
var
  Text: String;
  Answer: Integer;
begin
  Result := False;
  URoot := ExpandConstant('{commonappdata}\SlateOps');
  UHelper := URoot + '\scripts\setup-helper.ps1';
  URunId := NewRunId('uninstall');
  if not FileExists(UHelper) then
  begin
    { Nothing of the server part is left (an install that stopped before S07); Inno removes its
      own files. }
    UHelper := '';
    Result := True;
    Exit;
  end;
  try
    Text := URun('state-check', URunId, '', U_SHORT_SEC);
    if JsonValue(Text, 'code') <> 'safe' then
    begin
      UStopped(CM('f4c_stopped'), False);
      Exit;
    end;
    Text := URun('uninstall-info', URunId, '', U_SHORT_SEC);
    UDataRoot := JsonValue(Text, 'data_root');
    UBackupFolder := JsonValue(Text, 'backup_folder');
    UDiskGb := StrToIntDef(JsonLiteral(Text, 'disk_gb'), 0);
    repeat
      UDeleteBackups := False;
      Answer := AskKeepData;
      if Answer = 0 then
        Exit;
      if (Answer = 2) and not ConfirmDelete then
        Answer := -1;
    until Answer > 0;
    UKeep := Answer = 1;
    Result := True;
  except
    UStopped(CM('f4c_stopped'), True);
    Result := False;
  end;
end;


procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Text, Code, Extra: String;
begin
  if (CurUninstallStep = usUninstall) and (UHelper <> '') then
  begin
    UStageAt := GetTickCount;
    UStartTimer;
    { U03 stage 1. }
    UStage(1, CM('u03_stopping'));
    Extra := '';
    if UKeep then
      Extra := '-Keep';
    Code := JsonValue(URun('uninstall-stop', URunId, Extra, U_STOP_SEC), 'code');
    if Code <> 'stopped' then
    begin
      UStageLine := '';
      { F3 (uninstall) or F4c: nothing was removed; Inno removes nothing either. }
      if UKeep then
        UStopped(CM('u04_keep_failed'), True)
      else
        UStopped(CM('f4c_stopped'), True);
      Abort;
    end;
    { U03 stage 2. }
    if UKeep then
      UStage(2, FM1('u03_moving_line', UDataRoot + '\kept'))
    else
      UStage(2, FM1('u03_deleting', UDataRoot));
    Extra := '';
    if UKeep then
      Extra := '-Keep'
    else if UDeleteBackups then
      Extra := '-DeleteBackups';
    Code := JsonValue(URun('uninstall-data', URunId, Extra, U_DATA_SEC), 'code');
    if UKeep and (Code <> 'kept') then
    begin
      UStageLine := '';
      UStopped(CM('u04_keep_failed'), True);
      Abort;
    end;
    if (not UKeep) and (Code <> 'removed') then
      ULeft := 'data';
    { U03 stage 3: the Windows parts; each leftover is logged (W9-6). }
    UStage(3, CM('u03_removing'));
    { W9 review item 4: with the data folder left over, the scripts stay for the U04 report. }
    Extra := '';
    if ULeft = 'data' then
      Extra := '-DataLeft';
    Text := URun('remove-windows', URunId, Extra, U_WINDOWS_SEC);
    if JsonValue(Text, 'code') = 'leftovers' then
      ULeft := ULeft + ' windows';
    { Inno's own lines follow (its files). }
    UStageLine := '';
  end;
  if (CurUninstallStep = usPostUninstall) and (UHelper <> '') then
  begin
    { U04. }
    if UKeep then
      Text := FM1('u04_kept', UDataRoot + '\kept')
    else
      Text := CM('u04_deleted');
    Text := Text + #13#10#13#10 + CM('u04_feature');
    if ULeft <> '' then
    begin
      if TaskDialogMsgBox(CM('u04_leftovers'), Text, mbInformation, MB_YESNO, [CM('btn_save_report'), CM('btn_close')], 0) = IDYES then
        USaveReport;
    end
    else
      MsgBox(Text, mbInformation, MB_OK);
  end;
end;
