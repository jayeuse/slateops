{ Maintenance.iss - the maintenance mode and the W9 parts of the wizard (plan 9.2, 9.3, 10.3 F4c;
  wizard spec M01 to M04, 4.5 "Remove everything"; W9). Included after Wizard.iss, which declares
  the routines below as forward. ASCII only.

  M02 and M03 reuse the S09 and S10 pages: the maintenance page moves to them with Next and back
  with Back, and every page in between is skipped (no install step runs in maintenance). M03 and
  M04 show the key in a modal form with the S14 content, because the S14 page lies after the
  install step. }

{ The variables of this file are declared in Wizard.iss, which reads some of them. }

{ ------------------------------------------------------------------------------------------- }
{ The key form (M03, M04)                                                                       }
{ ------------------------------------------------------------------------------------------- }

procedure RefreshKeyState;
begin
  if KeyFormOpen and (KeyFormStatus <> nil) then
    KeyFormStatus.Caption := KeyStateText
  else
    RenderPage(P_KEY);
end;

procedure KeyFormCheckClick(Sender: TObject);
begin
  KeyFormDone.Enabled := KeyFormCheck.Checked;
end;

procedure FillKeyFormUsb;
var
  List, Item: String;
begin
  List := UsbDrives;
  KeyFormUsbSeen := List;
  KeyUsb.Items.Clear;
  while Pos(';', List) > 0 do
  begin
    Item := Copy(List, 1, Pos(';', List) - 1);
    List := Copy(List, Pos(';', List) + 1, Length(List));
    KeyUsb.Items.Add(Item);
  end;
  if KeyUsb.Items.Count > 0 then
    KeyUsb.ItemIndex := 0;
end;

{ The S14 content as a modal form. It has no Cancel: the engine removes the old key when it makes
  the new one (W10b), so Cancel cannot keep the old key (spec M04; TASK-0096 Result). }
procedure KeyForm(FirstLine, FinalCaption: String);
var
  Form: TSetupForm;
  Text, KeyLabel: TNewStaticText;
  Panel: TPanel;
  Print, Save: TNewButton;
  Y: Integer;
begin
  Form := CreateCustomForm(ScaleX(540), ScaleY(400), False, False);
  try
    Form.Caption := CM('s14_title');
    Form.BorderIcons := [];
    Y := ScaleY(12);
    Text := AddTextTo(Form, Y, FirstLine, True);
    Text.Left := ScaleX(14);
    Text.Width := Form.ClientWidth - ScaleX(28);
    WizardForm.AdjustLabelHeight(Text);
    Y := Y + Text.Height + ScaleY(8);
    Text := AddTextTo(Form, Y, CM('s14_subtitle'), False);
    Text.Left := ScaleX(14);
    Text.Width := Form.ClientWidth - ScaleX(28);
    WizardForm.AdjustLabelHeight(Text);
    Y := Y + Text.Height + ScaleY(8);
    Panel := TPanel.Create(Form);
    Panel.Parent := Form;
    Panel.BevelOuter := bvLowered;
    Panel.SetBounds(ScaleX(14), Y, Form.ClientWidth - ScaleX(28), ScaleY(46));
    KeyLabel := TNewStaticText.Create(Form);
    KeyLabel.Parent := Panel;
    KeyLabel.Font.Name := 'Consolas';
    KeyLabel.Font.Size := 16;
    KeyLabel.Font.Style := [fsBold];
    KeyLabel.ShowAccelChar := False;
    KeyLabel.Caption := GroupedKey;
    KeyLabel.Left := ScaleX(10);
    KeyLabel.Top := ScaleY(10);
    Y := Y + Panel.Height + ScaleY(8);
    Text := AddTextTo(Form, Y, CM('s14_text'), False);
    Text.Left := ScaleX(14);
    Text.Width := Form.ClientWidth - ScaleX(28);
    WizardForm.AdjustLabelHeight(Text);
    Y := Y + Text.Height + ScaleY(10);
    Print := TNewButton.Create(Form);
    Print.Parent := Form;
    Print.Caption := CM('s14_print');
    Print.OnClick := @PrintKeyClick;
    Print.SetBounds(ScaleX(14), Y, ScaleX(130), ScaleY(26));
    KeyUsb := TNewComboBox.Create(Form);
    KeyUsb.Parent := Form;
    KeyUsb.Style := csDropDownList;
    KeyUsb.SetBounds(ScaleX(160), Y + ScaleY(2), ScaleX(70), ScaleY(21));
    FillKeyFormUsb;
    Save := TNewButton.Create(Form);
    Save.Parent := Form;
    Save.Caption := CM('s14_usb');
    Save.OnClick := @SaveKeyClick;
    Save.SetBounds(ScaleX(240), Y, ScaleX(170), ScaleY(26));
    Y := Y + ScaleY(34);
    KeyFormStatus := AddTextTo(Form, Y, '', True);
    KeyFormStatus.Left := ScaleX(14);
    KeyFormStatus.Width := Form.ClientWidth - ScaleX(28);
    Y := Y + ScaleY(36);
    KeyFormCheck := TNewCheckBox.Create(Form);
    KeyFormCheck.Parent := Form;
    KeyFormCheck.Caption := CM('s14_check');
    KeyFormCheck.OnClick := @KeyFormCheckClick;
    KeyFormCheck.SetBounds(ScaleX(14), Y, Form.ClientWidth - ScaleX(28), ScaleY(18));
    KeyFormDone := TNewButton.Create(Form);
    KeyFormDone.Parent := Form;
    KeyFormDone.Caption := FinalCaption;
    KeyFormDone.ModalResult := mrOk;
    KeyFormDone.Enabled := False;
    KeyFormDone.SetBounds(Form.ClientWidth - ScaleX(124), Form.ClientHeight - ScaleY(38), ScaleX(110), ScaleY(26));
    KeyStateText := '';
    KeyFormOpen := True;
    Form.ShowModal;
  finally
    KeyFormOpen := False;
    KeyUsb := nil;
    KeyFormStatus := nil;
    KeyText := '';
    KeyStateText := '';
    Form.Free;
  end;
end;

{ ------------------------------------------------------------------------------------------- }
{ M01                                                                                           }
{ ------------------------------------------------------------------------------------------- }

procedure StartMaintStatus;
begin
  MaintStatusOut := NewOut('engine-status');
  MaintStatusAt := GetTickCount;
  MaintStatus := 'checking';
  StartHelper('engine-status', RunId, MaintStatusOut, '');
end;

{ Spec M01: one status sentence first, from the engine status (plan 9.3), and a line under it. }
function MaintSentence(var Line: String): String;
begin
  Line := '';
  if MaintStatus = 'checking' then
    Result := CM('m01_checking')
  else if MaintStatus <> 'ok' then
    Result := CM('m01_not_ready')
  else if MaintState = 'needs_support' then
    Result := CM('m01_needs_support')
  else if MaintBackup = 'backup_target_missing' then
  begin
    Result := FM('m01_needs_backup', [Copy(MaintBackupFolder, 1, 2)]);
    Line := CM('m01_runs_line');
  end
  else
    Result := CM('m01_running');
end;

procedure GoToMaintPage(Action: String);
begin
  MaintAction := Action;
  WizardForm.NextButton.Visible := True;
  WizardForm.NextButton.Enabled := True;
  WizardForm.NextButton.OnClick(WizardForm.NextButton);
end;

procedure BackToMaint(Line: String);
begin
  MaintLine := Line;
  MaintAction := '';
  MaintPhase := '';
  WizardForm.BeveledLabel.Caption := '';
  WizardForm.BackButton.OnClick(WizardForm.BackButton);
end;

procedure StartMaintKey(Phase: String);
begin
  MaintPhase := Phase;
  KeyText := '';
  StartJob('new-recovery-key', '{"run_id":"' + RunId + '"}', 'maintkey', False, True, 10);
end;

procedure MaintActionClick(Sender: TObject);
var
  Text, Code: String;
begin
  if JobRunning or (MaintPhase <> '') then
    Exit;
  case TNewButton(Sender).Tag of
    0: OpenAsUser(AddressUrl, '');
    1: InviteClick(nil);
    2: begin
         Text := CM('s15_step3') + #13#10 + 'http://' + HostName + '.local/trust';
         Code := JsonValue(ReadText(NewOutRun('security-code', '')), 'security_code');
         if Code <> '' then
           Text := Text + #13#10#13#10 + FM('s15_security', [Code]);
         InfoForm(CM('m01_code'), Text);
       end;
    3: GoToMaintPage('email');
    4: GoToMaintPage('backup');
    5: begin
         StartMaintKey('key4');
         MaintLine := CM('s14_making');
         RenderPage(P_MAINT);
       end;
    6: begin
         { Repair: R7 is read again inside the helper right before the new password (11.1 W9). }
         MaintLine := CM('m01_repairing');
         RenderPage(P_MAINT);
         WizardForm.Refresh;
         Code := ReadResultCode(NewOutRun('repair', ''));
         if Code = 'repaired' then MaintLine := CM('m01_repaired')
         else if Code = 'logging_policy' then MaintLine := CM('c18_policy')
         else if Code = 'logging_policy_unreadable' then MaintLine := CM('c18_unreadable')
         else MaintLine := CM('m01_repair_failed');
         RenderPage(P_MAINT);
       end;
    7: SaveReport(nil);
  end;
end;

procedure AddMaintAction(Index, Column: Integer; Caption, Hint: String; var Bottom: Integer);
var
  Button: TNewButton;
  Half: Integer;
begin
  Half := (Cur.Width - ScaleX(8)) div 2;
  Button := TNewButton.Create(WizardForm);
  Button.Parent := Cur;
  Button.Style := bsCommandLink;
  Button.Caption := Caption;
  Button.CommandLinkHint := Hint;
  Button.Tag := Index;
  Button.SetBounds(Column * (Half + ScaleX(8)), CurY, Half, ScaleY(44));
  Button.AdjustHeightIfCommandLink;
  Button.OnClick := @MaintActionClick;
  if CurY + Button.Height > Bottom then
    Bottom := CurY + Button.Height;
end;

procedure RenderMaint;
var
  Sentence, Line: String;
  Verdict: TNewMemo;
  Bottom, I: Integer;
begin
  BeginBody(P_MAINT);
  WizardForm.PageNameLabel.Caption := CM('m01_title');
  WizardForm.PageDescriptionLabel.Caption := FM('m01_subtitle', [SetupVersion, AddressUrl]);
  WizardForm.NextButton.Visible := False;
  WizardForm.BackButton.Visible := False;
  WizardForm.CancelButton.Caption := CM('btn_close');
  Sentence := MaintSentence(Line);
  Verdict := AddVerdict(Sentence);
  if Line <> '' then
    AddText(Line, False);
  if MaintStatus = 'checking' then
    AddMarquee;
  CurY := CurY + ScaleY(4);
  for I := 0 to 3 do
  begin
    Bottom := CurY;
    if I = 0 then begin AddMaintAction(0, 0, CM('m01_open'), CM('m01_open_hint'), Bottom); AddMaintAction(1, 1, CM('m01_invite'), CM('m01_invite_hint'), Bottom); end;
    if I = 1 then begin AddMaintAction(2, 0, CM('m01_code'), CM('m01_code_hint'), Bottom); AddMaintAction(3, 1, CM('m01_email'), CM('m01_email_hint'), Bottom); end;
    if I = 2 then begin AddMaintAction(4, 0, CM('m01_backup'), CM('m01_backup_hint'), Bottom); AddMaintAction(5, 1, CM('m01_key'), CM('m01_key_hint'), Bottom); end;
    if I = 3 then begin AddMaintAction(6, 0, CM('m01_repair'), CM('m01_repair_hint'), Bottom); AddMaintAction(7, 1, CM('btn_save_report'), CM('m01_report_hint'), Bottom); end;
    CurY := Bottom + ScaleY(4);
  end;
  if MaintLine <> '' then
    AddText(MaintLine, True);
  if ReportLine <> '' then
    AddText(ReportLine, False);
  AddText(CM('m01_footer'), False);
  if (MaintStatus <> 'checking') and Verdict.CanFocus then
    WizardForm.ActiveControl := Verdict;
end;

{ M02 (S09 form) and M03 (S10 form) Next; True lets Inno move on (never in maintenance). }
function MaintNext(PageID: Integer): Boolean;
var
  Code: String;
begin
  Result := False;
  if PageID = Pages[P_EMAIL].ID then
  begin
    if MailPassed then
    begin
      { W9-4: set-email applies the staged values and recreates auth; through the pipe. }
      MaintPhase := 'setemail';
      WizardForm.NextButton.Enabled := False;
      StartJob('set-email', '{"run_id":"' + RunId + '"}', 'setemail', True, False, 5);
    end
    else
    begin
      { No administrator email on Windows: the test goes to the sending address itself. }
      OrgEmail.Text := Trim(MailFrom.Text);
      if Trim(OrgName.Text) = '' then
        OrgName.Text := 'Slate Operations';
      if MailFieldsReady then
        StartMailTest;
    end;
  end
  else if PageID = Pages[P_BACKUP].ID then
  begin
    WizardForm.BeveledLabel.Caption := ' ' + FM('m03_checking', [BackupDrive]);
    WizardForm.Refresh;
    if not CheckBackupDrive then
    begin
      WizardForm.BeveledLabel.Caption := '';
      Exit;
    end;
    Code := ReadResultCode(NewOutRun('prepare-backup', '-Drive ' + Uppercase(BackupDrive)));
    if Code <> 'ready' then
    begin
      WizardForm.BeveledLabel.Caption := '';
      BackupError := FM('s10_not_writable', [BackupDrive]);
      RenderPage(P_BACKUP);
      Exit;
    end;
    MaintTarget := Uppercase(BackupDrive);
    MaintPhase := 'target';
    WizardForm.NextButton.Enabled := False;
    StartJob('set-backup-target', '{"run_id":"' + RunId + '","backup_target":' + JsonText(MaintTarget + '\SlateOps-backups') + '}', 'target', False, False, 10);
  end;
end;

{ From the timer. }
procedure PollMaint;
var
  Text: String;
begin
  if EntryScreen <> 'M01' then
    Exit;
  if MaintStatus = 'checking' then
  begin
    Text := ReadText(MaintStatusOut);
    if (JsonValue(Text, 'code') <> '') or (Elapsed(MaintStatusAt) > HELPER_LIMIT_MS) then
    begin
      MaintStatus := JsonValue(Text, 'code');
      if MaintStatus = '' then
        MaintStatus := 'unreachable';
      MaintState := JsonValue(Text, 'state');
      MaintBackup := JsonValue(Text, 'backup');
      MaintBackupFolder := JsonValue(Text, 'backup_folder');
      RenderPage(P_MAINT);
    end;
  end;
  if (MaintPhase = '') or (JobState <> JOB_DONE) then
    Exit;
  JobState := JOB_IDLE;
  if MaintPhase = 'setemail' then
  begin
    if JobCode = 'email_set' then
      BackToMaint(FM('m02_done', [Trim(MailFrom.Text)]))
    else
      BackToMaint(CM('m02_failed'));
  end
  else if MaintPhase = 'target' then
  begin
    { TASK-0093 decision 4: a new backup store gets its own recovery key at once. }
    if JobCode = 'backup_target_set' then
      StartMaintKey('key3')
    else
    begin
      MaintPhase := '';
      WizardForm.BeveledLabel.Caption := '';
      BackupError := FM('s10_not_writable', [MaintTarget]);
      RenderPage(P_BACKUP);
    end;
  end
  else if (MaintPhase = 'key3') or (MaintPhase = 'key4') then
  begin
    KeyText := JsonValue(JobText, 'recovery_key');
    JobText := '';
    if KeyText = '' then
    begin
      if MaintPhase = 'key3' then BackToMaint(CM('s14_key_failed')) else begin MaintPhase := ''; MaintLine := CM('s14_key_failed'); RenderPage(P_MAINT); end;
      Exit;
    end;
    if MaintPhase = 'key3' then
    begin
      MaintPhase := 'keyform';
      KeyForm(CM('m03_first'), CM('btn_done'));
      BackToMaint(FM('m03_done', [MaintTarget]));
    end
    else
    begin
      MaintPhase := 'keyform';
      KeyForm(CM('m04_first'), CM('s15_finish'));
      MaintPhase := '';
      MaintLine := '';
      RenderPage(P_MAINT);
    end;
  end;
end;

{ Maintenance shows M01, and the S09 or S10 page only while its action runs. }
function MaintSkip(PageID: Integer): Boolean;
begin
  Result := True;
  if PageID = Pages[P_MAINT].ID then Result := False
  else if (PageID = Pages[P_EMAIL].ID) and (MaintAction = 'email') then Result := False
  else if (PageID = Pages[P_BACKUP].ID) and (MaintAction = 'backup') then Result := False;
end;

{ ------------------------------------------------------------------------------------------- }
{ Cancel at S08 to S11: "Remove everything" (default) or "Keep it and continue later" (spec 4.5) }
{ ------------------------------------------------------------------------------------------- }

{ 0 go back, 1 remove everything, 2 keep it and continue later. }
function AskCancelChoice: Integer;
var
  Form: TSetupForm;
  Text: TNewStaticText;
  Remove, Keep: TNewRadioButton;
  Stop, Back: TNewButton;
  Y: Integer;
begin
  Result := 0;
  Form := CreateCustomForm(ScaleX(460), ScaleY(230), False, False);
  try
    Form.Caption := CM('btn_stop_setup');
    Y := ScaleY(12);
    Text := AddTextTo(Form, Y, CM('cancel_server'), True);
    Text.Left := ScaleX(14);
    Text.Width := Form.ClientWidth - ScaleX(28);
    WizardForm.AdjustLabelHeight(Text);
    Y := Y + Text.Height + ScaleY(10);
    Remove := TNewRadioButton.Create(Form);
    Remove.Parent := Form;
    Remove.Caption := CM('cancel_remove');
    Remove.Checked := True;
    Remove.SetBounds(ScaleX(14), Y, Form.ClientWidth - ScaleX(28), ScaleY(18));
    Y := Y + ScaleY(24);
    Keep := TNewRadioButton.Create(Form);
    Keep.Parent := Form;
    Keep.Caption := CM('cancel_keep_option');
    Keep.SetBounds(ScaleX(14), Y, Form.ClientWidth - ScaleX(28), ScaleY(18));
    Y := Y + ScaleY(22);
    Text := AddTextTo(Form, Y, CM('cancel_keep'), False);
    Text.Left := ScaleX(32);
    Text.Width := Form.ClientWidth - ScaleX(46);
    WizardForm.AdjustLabelHeight(Text);
    Stop := TNewButton.Create(Form);
    Stop.Parent := Form;
    Stop.Caption := CM('btn_stop_setup');
    Stop.ModalResult := mrOk;
    Stop.SetBounds(Form.ClientWidth - ScaleX(250), Form.ClientHeight - ScaleY(38), ScaleX(115), ScaleY(26));
    Back := TNewButton.Create(Form);
    Back.Parent := Form;
    Back.Caption := CM('btn_go_back');
    Back.ModalResult := mrCancel;
    Back.Cancel := True;
    Back.Default := True;
    Back.SetBounds(Form.ClientWidth - ScaleX(128), Form.ClientHeight - ScaleY(38), ScaleX(115), ScaleY(26));
    ModalOpen := True;
    if Form.ShowModal = mrOk then
    begin
      if Remove.Checked then Result := 1 else Result := 2;
    end;
  finally
    ModalOpen := False;
    Form.Free;
  end;
end;

{ "Remove everything setup added" (spec 4.5): the uninstall steps with "Delete everything". With
  kept data the disk goes back to kept\ instead, never deleted (W9 kept-data branch). }
procedure RemoveEverything;
var
  Start: Cardinal;
begin
  Start := GetTickCount;
  while JobRunning and (Elapsed(Start) < 120000) do
  begin
    Sleep(1000);
    PollJob;
  end;
  WizardForm.BeveledLabel.Caption := ' ' + CM('u03_remove');
  WizardForm.Refresh;
  NewOutRun('uninstall-stop', '');
  if KeptMode then
    NewOutRun('kept-return', '')
  else
    NewOutRun('uninstall-data', '');
  NewOutRun('remove-windows', '');
end;

{ ------------------------------------------------------------------------------------------- }
{ The settings program (the small build, /DSettingsBuild)                                       }
{ ------------------------------------------------------------------------------------------- }

{ Returns True when the settings program goes on to M01. Save report from the Start menu runs
  here with no wizard (plan 10.6 item 1). }
function SettingsEntry: Boolean;
begin
  Result := True;
  if not SETTINGS_BUILD then
    Exit;
  if ExpandConstant('{param:SAVEREPORT|0}') = '1' then
  begin
    SaveReport(nil);
    if ReportLine <> '' then
      MsgBox(ReportLine, mbInformation, MB_OK);
    Result := False;
    Exit;
  end;
  if EntryScreen <> 'M01' then
  begin
    MsgBox(CM('m01_not_installed'), mbInformation, MB_OK);
    Result := False;
  end;
end;

{ The settings program never installs (W9); Inno would only get here past M01's pages. }
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if SETTINGS_BUILD then
    Result := CM('m01_not_installed');
end;
