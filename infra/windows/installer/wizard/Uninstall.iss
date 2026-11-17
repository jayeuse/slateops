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

var
  UHelper, URoot, URunId, UDataRoot, UBackupFolder, ULeft: String;
  UKeep, UDeleteBackups: Boolean;
  UDiskGb, USeq: Integer;
  URadioKeep, URadioDelete: TNewRadioButton;
  UBackupsCheck, UConfirmCheck: TNewCheckBox;
  UConfirmButton: TNewButton;

function URun(Action, ARunId, Extra: String): String;
var
  OutFile: String;
  Code: Integer;
begin
  USeq := USeq + 1;
  OutFile := URoot + '\uninstall-' + IntToStr(USeq) + '.json';
  DeleteFile(OutFile);
  Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ' + AddQuotes(UHelper) + ' -Action ' + Action +
    ' -RunId ' + ARunId + ' -OutFile ' + AddQuotes(OutFile) + ' ' + Extra, '', SW_HIDE, ewWaitUntilTerminated, Code);
  Result := ReadText(OutFile);
  DeleteFile(OutFile);
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

procedure UReportSaved(Path: String);
begin
  if Path <> '' then
    MsgBox(FM('report_saved', [ExtractFileName(Path)]), mbInformation, MB_OK);
end;

{ Save report from the uninstaller (plan 10.6), while the helper is still there. }
procedure USaveReport;
var
  ReportRun: String;
begin
  ReportRun := NewRunId('report');
  URun('report-collect', ReportRun, '');
  UReportSaved(JsonValue(URun('report-zip', ReportRun, ''), 'path'));
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
    Y := Y + ScaleY(22);
    Text := UText(Form, Y, FM('u01_keep_text', [UDataRoot + '\kept', IntToStr(UDiskGb)]), False);
    Text.Left := ScaleX(34);
    Text.Width := Form.ClientWidth - ScaleX(50);
    Text.AdjustHeight;
    Y := Y + Text.Height + ScaleY(14);
    URadioDelete := TNewRadioButton.Create(Form);
    URadioDelete.Parent := Form;
    URadioDelete.Caption := CM('u01_delete');
    URadioDelete.OnClick := @URadioClick;
    URadioDelete.SetBounds(ScaleX(16), Y, Form.ClientWidth - ScaleX(32), ScaleY(18));
    Y := Y + ScaleY(22);
    Text := UText(Form, Y, CM('u01_delete_text'), False);
    Text.Left := ScaleX(34);
    Text.Width := Form.ClientWidth - ScaleX(50);
    Text.AdjustHeight;
    Y := Y + Text.Height + ScaleY(8);
    { Offered only when the record names a backup folder (advisor item 6). }
    if UBackupFolder <> '' then
    begin
      UBackupsCheck := TNewCheckBox.Create(Form);
      UBackupsCheck.Parent := Form;
      UBackupsCheck.Caption := FM('u01_backups', [Copy(UBackupFolder, 1, 2)]);
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
    if UDeleteBackups then Line := FM('u02_backups_deleted', [Copy(UBackupFolder, 1, 2)])
    else if UBackupFolder <> '' then Line := FM('u02_backups_kept', [Copy(UBackupFolder, 1, 2)])
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
    Text := URun('state-check', URunId, '');
    if JsonValue(Text, 'code') <> 'safe' then
    begin
      UStopped(CM('f4c_stopped'), False);
      Exit;
    end;
    Text := URun('uninstall-info', URunId, '');
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

procedure UStatus(S: String);
begin
  UninstallProgressForm.StatusLabel.Caption := S;
  UninstallProgressForm.Update;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Text, Code, Extra: String;
begin
  if (CurUninstallStep = usUninstall) and (UHelper <> '') then
  begin
    { U03 stage 1. }
    UStatus(CM('u03_stop'));
    Extra := '';
    if UKeep then
      Extra := '-Keep';
    Code := JsonValue(URun('uninstall-stop', URunId, Extra), 'code');
    if Code <> 'stopped' then
    begin
      { F3 (uninstall) or F4c: nothing was removed; Inno removes nothing either. }
      if UKeep then
        UStopped(CM('u04_keep_failed'), True)
      else
        UStopped(CM('f4c_stopped'), True);
      Abort;
    end;
    { U03 stage 2. }
    if UKeep then
      UStatus(FM('u03_moving', [UDataRoot + '\kept']))
    else
      UStatus(CM('u03_remove'));
    Extra := '';
    if UKeep then
      Extra := '-Keep'
    else if UDeleteBackups then
      Extra := '-DeleteBackups';
    Code := JsonValue(URun('uninstall-data', URunId, Extra), 'code');
    if UKeep and (Code <> 'kept') then
    begin
      UStopped(CM('u04_keep_failed'), True);
      Abort;
    end;
    if (not UKeep) and (Code <> 'removed') then
      ULeft := 'data';
    { U03 stage 3: the Windows parts; each leftover is logged (W9-6). }
    UStatus(CM('u03_remove'));
    { W9 review item 4: with the data folder left over, the scripts stay for the U04 report. }
    Extra := '';
    if ULeft = 'data' then
      Extra := '-DataLeft';
    Text := URun('remove-windows', URunId, Extra);
    if JsonValue(Text, 'code') = 'leftovers' then
      ULeft := ULeft + ' windows';
  end;
  if (CurUninstallStep = usPostUninstall) and (UHelper <> '') then
  begin
    { U04. }
    if UKeep then
      Text := FM('u04_kept', [UDataRoot + '\kept'])
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
