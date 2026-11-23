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
  the new one (W10b), so Cancel cannot keep the old key (spec M04; TASK-0096 Result). W14-D3: the
  S14 layout with the rhythm (4 px in a block, 12 px between blocks), the flat key border, the
  row [Print the key] [E:] [Save to a USB drive], regular result text and buttons sized to their
  captions. Built apart from showing it, so the self-test can check it. }
function BuildKeyForm(FirstLine, FinalCaption: String): TSetupForm;
var
  Form: TSetupForm;
  Text, KeyLabel: TNewStaticText;
  Panel: TPanel;
  Print, Save: TNewButton;
  Y, X: Integer;
begin
  Form := CreateCustomForm(ScaleX(540), ScaleY(400), False, False);
  Form.Caption := CM('s14_title');
  Form.BorderIcons := [];
  Y := ScaleY(14);
  Text := FormText(Form, Y, FirstLine, True);
  Y := Y + Text.Height + ScaleY(4);
  Text := FormText(Form, Y, CM('s14_subtitle'), False);
  Y := Y + Text.Height + ScaleY(12);
  Panel := TPanel.Create(Form);
  Panel.Parent := Form;
  Panel.BevelOuter := bvNone;
  Panel.BorderStyle := bsSingle;
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
  Y := Y + Panel.Height + ScaleY(4);
  Text := FormText(Form, Y, CM('s14_text'), False);
  Y := Y + Text.Height + ScaleY(12);
  Print := FormButton(Form, CM('s14_print'), 0, 0);
  Print.OnClick := @PrintKeyClick;
  Print.SetBounds(ScaleX(14), Y, Print.Width, Print.Height);
  X := Print.Left + Print.Width + ScaleX(8);
  KeyUsb := TNewComboBox.Create(Form);
  KeyUsb.Parent := Form;
  KeyUsb.Style := csDropDownList;
  KeyUsb.SetBounds(X, Y + (Print.Height - ScaleY(21)) div 2, ScaleX(70), ScaleY(21));
  FillKeyFormUsb;
  X := X + KeyUsb.Width + ScaleX(8);
  Save := FormButton(Form, CM('s14_usb'), 0, 0);
  Save.OnClick := @SaveKeyClick;
  Save.SetBounds(X, Y, Save.Width, Save.Height);
  Y := Y + Print.Height + ScaleY(4);
  KeyFormStatus := FormText(Form, Y, '', False);
  Y := Y + ScaleY(36);
  KeyFormCheck := TNewCheckBox.Create(Form);
  KeyFormCheck.Parent := Form;
  KeyFormCheck.Caption := CM('s14_check');
  KeyFormCheck.OnClick := @KeyFormCheckClick;
  KeyFormCheck.SetBounds(ScaleX(14), Y, Form.ClientWidth - ScaleX(28), ScaleY(18));
  KeyFormDone := FormButton(Form, FinalCaption, ScaleX(110), mrOk);
  KeyFormDone.Enabled := False;
  KeyFormDone.SetBounds(Form.ClientWidth - ScaleX(14) - KeyFormDone.Width, Form.ClientHeight - ScaleY(38), KeyFormDone.Width, KeyFormDone.Height);
  KeyStateText := '';
  Result := Form;
end;

procedure KeyForm(FirstLine, FinalCaption: String);
var
  Form: TSetupForm;
begin
  Form := BuildKeyForm(FirstLine, FinalCaption);
  try
    KeyFormOpen := True;
    Form.ShowModal;
  finally
    KeyFormOpen := False;
    { A printer list still being read belongs to this form (W14-D9): it is dropped. }
    if StepFor = 'printers' then
      StepFor := '';
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
  { W9 review item 5 (plan 10.7): the network differs from the range of the firewall rules. }
  else if MaintNetwork then
  begin
    Result := CM('m01_needs_network');
    Line := CM('m01_runs_line');
  end
  else if MaintBackup = 'backup_target_missing' then
  begin
    { Option b: when the drive is back and backups still fail, Repair sets the rights again. }
    Result := FM1('m01_needs_backup_repair', Copy(MaintBackupFolder, 1, 2));
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
  WizardForm.BackButton.OnClick(WizardForm.BackButton);
end;

procedure StartMaintKey(Phase: String);
begin
  MaintPhase := Phase;
  KeyText := '';
  StartJob('new-recovery-key', '{"run_id":"' + RunId + '"}', 'maintkey', False, True, 10);
end;

{ D-B (spec M04): the engine removes the old key when it makes the new one, so the person
  confirms first; "Go back" is the default. }
function ConfirmNewKey: Boolean;
var
  Form: TSetupForm;
  Text: TNewStaticText;
  Go, Back: TNewButton;
  Y: Integer;
begin
  Form := CreateCustomForm(ScaleX(440), ScaleY(170), False, False);
  try
    Form.Caption := CM('m04_confirm_title');
    Y := ScaleY(12);
    Text := AddTextTo(Form, Y, CM('m04_confirm_title'), True);
    Text.Left := ScaleX(14);
    Text.Width := Form.ClientWidth - ScaleX(28);
    WizardForm.AdjustLabelHeight(Text);
    Y := Y + Text.Height + ScaleY(8);
    Text := AddTextTo(Form, Y, CM('m04_confirm_text'), False);
    Text.Left := ScaleX(14);
    Text.Width := Form.ClientWidth - ScaleX(28);
    WizardForm.AdjustLabelHeight(Text);
    Go := TNewButton.Create(Form);
    Go.Parent := Form;
    Go.Caption := CM('m04_confirm_go');
    Go.ModalResult := mrOk;
    Go.SetBounds(Form.ClientWidth - ScaleX(250), Form.ClientHeight - ScaleY(38), ScaleX(115), ScaleY(26));
    Back := TNewButton.Create(Form);
    Back.Parent := Form;
    Back.Caption := CM('btn_go_back');
    Back.ModalResult := mrCancel;
    Back.Cancel := True;
    Back.Default := True;
    Back.SetBounds(Form.ClientWidth - ScaleX(128), Form.ClientHeight - ScaleY(38), ScaleX(115), ScaleY(26));
    FitFormRow(Form, Go, Back);
    ModalOpen := True;
    Result := Form.ShowModal = mrOk;
  finally
    ModalOpen := False;
    Form.Free;
  end;
end;

{ M01 "Show the phone code" after its helper (W14-D9: StepFinished 'code'). }
procedure ShowPhoneCode(Code: String);
var
  Text: String;
begin
  Text := CM('s15_step3') + #13#10 + 'http://' + HostName + '.local/trust';
  if Code <> '' then
    Text := Text + #13#10#13#10 + FM1('s15_security', Code);
  InfoForm(CM('m01_code'), Text);
end;

procedure MaintActionClick(Sender: TObject);
begin
  if JobRunning or StepRunning or (MaintPhase <> '') then
    Exit;
  case TNewButton(Sender).Tag of
    0: OpenAsUser(AddressUrl, '');
    2: begin
         { 7.6 "M01 phone code": "Reading the security code..." from the timer. }
         if RunStep('security-code', '', 'code', CM('m01_reading_code'), 0, 0, HELPER_LIMIT_MS) then
           RenderPage(P_MAINT);
       end;
    3: GoToMaintPage('email');
    4: GoToMaintPage('backup');
    5: begin
         if not ConfirmNewKey then
           Exit;
         StartMaintKey('key4');
         MaintAt := GetTickCount;
         MaintLine := '';
         RenderPage(P_MAINT);
       end;
    6: begin
         { Repair: R7 is read again inside the helper right before the new password (11.1 W9).
           W14-D9 (7.6 "M01 Repair"): from the timer, with its stages from the helper's
           progress lines (repair.*); StepFinished 'repair' writes the result line. }
         MaintLine := '';
         if RunStep('repair', '', 'repair', '', 0, 0, HELPER_LIMIT_MS) then
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
  WizardForm.PageDescriptionLabel.Caption := FM2('m01_subtitle', SetupVersion, AddressUrl);
  WizardForm.NextButton.Visible := False;
  WizardForm.BackButton.Visible := False;
  SetCancelCaption(CM('btn_close'));
  Sentence := MaintSentence(Line);
  Verdict := AddVerdict(Sentence);
  if Line <> '' then
    AddText(Line, False);
  { AC-W6 (DEC-0041): email is set up after install, in M02. }
  if (MaintStatus = 'ok') and MaintEmailMissing then
    AddText(CM('m01_email_not_set'), False);
  { W14-D5 (7.6 "M01 status"): full form, one stage; the sentence above names the action. }
  if MaintStatus = 'checking' then
    AddProgress('maint', '', 1, '', MaintStatusAt, '');
  { 7.6 "M01 Repair" (TASK-0097 AC-5, Designer B2 option a): while Repair runs, its full form
    takes the place of the actions, so the page ends inside its frame; the actions come back
    with the result. The other M01 waits: one line under the actions. }
  if StepFor = 'repair' then
    AddProgress('repair', CM('repair_stages'), WaitStage('repair'), WaitActionText('repair'), StepAt, '')
  else
  begin
    CurY := CurY + ScaleY(4);
    for I := 0 to 3 do
    begin
      Bottom := CurY;
      { DEC-0041 (QA N1): no "Send my invitation again": the administrator has a password from
        setup. The tags stay (MaintActionClick); seven actions in four rows. }
      if I = 0 then begin AddMaintAction(0, 0, CM('m01_open'), CM('m01_open_hint'), Bottom); AddMaintAction(2, 1, CM('m01_code'), CM('m01_code_hint'), Bottom); end;
      if I = 1 then begin AddMaintAction(3, 0, CM('m01_email'), CM('m01_email_hint'), Bottom); AddMaintAction(4, 1, CM('m01_backup'), CM('m01_backup_hint'), Bottom); end;
      if I = 2 then begin AddMaintAction(5, 0, CM('m01_key'), CM('m01_key_hint'), Bottom); AddMaintAction(6, 1, CM('m01_repair'), CM('m01_repair_hint'), Bottom); end;
      if I = 3 then AddMaintAction(7, 0, CM('btn_save_report'), CM('m01_report_hint'), Bottom);
      CurY := Bottom + ScaleY(4);
    end;
    AddStepLine;
  end;
  if MaintLine <> '' then
    AddText(MaintLine, False);
  if (ReportLine <> '') or (ReportPhase <> '') then
  begin
    ReportLabel := AddText(ReportLine, False);
    ShowReportLine;
  end;
  AddText(CM('m01_footer'), False);
  if MaintStatus <> 'checking' then
    FocusVerdict(Verdict);
end;

{ W9-4: set-email applies the staged values and recreates auth; through the pipe. }
procedure StartSetEmail;
begin
  MaintPhase := 'setemail';
  MaintAt := GetTickCount;
  WizardForm.NextButton.Enabled := False;
  StartJob('set-email', '{"run_id":"' + RunId + '"}', 'setemail', True, False, 5);
  RenderMailStatus;
end;

{ M02 (S09 form) and M03 (S10 form) Next; True lets Inno move on (never in maintenance). }
function MaintNext(PageID: Integer): Boolean;
begin
  Result := False;
  if PageID = Pages[P_EMAIL].ID then
  begin
    { DEC-0041 (AC-W6): one Next sends the test email and saves the settings (StartSetEmail);
      Done returns to M01. }
    if MailSaved then
    begin
      BackToMaint(FM1('m02_done', Trim(MailFrom.Text)));
      Exit;
    end;
    { No administrator email on Windows: the test goes to the sending address itself. }
    OrgEmail.Text := Trim(MailFrom.Text);
    if Trim(OrgName.Text) = '' then
      OrgName.Text := 'Slate Operations';
    if MailFieldsReady then
      StartMailTest;
  end
  else if PageID = Pages[P_BACKUP].ID then
  begin
    { W14-D9 (7.6 "M03"): 1 drive-check and 2 prepare-backup from the timer (StepFinished
      'm03-check', 'm03-prepare'), 3 set-backup-target and 4 the new key (PollMaint). }
    if StepRunning or (MaintPhase <> '') then
      Exit;
    BackupError := '';
    MaintAt := GetTickCount;
    if RunStep('drive-check', '-Drive ' + Uppercase(BackupDrive), 'm03-check', FM1('m03_checking', BackupDrive), 1, 4, HELPER_LIMIT_MS) then
      RenderPage(P_BACKUP);
  end;
end;

procedure M03Target;
begin
  MaintTarget := Uppercase(BackupDrive);
  MaintPhase := 'target';
  WizardForm.NextButton.Enabled := False;
  StartJob('set-backup-target', '{"run_id":"' + RunId + '","backup_target":' + JsonText(MaintTarget + '\SlateOps-backups') + '}', 'target', False, False, 10);
  RenderPage(P_BACKUP);
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
      MaintNetwork := JsonLiteral(Text, 'network_changed') = 'true';
      { AC-W6: only the flag; the administrator's address never reaches Windows here. }
      MaintEmailMissing := JsonLiteral(Text, 'email_configured') = 'false';
      RenderPage(P_MAINT);
    end;
  end;
  if (MaintPhase = '') or (JobState <> JOB_DONE) then
    Exit;
  { W14-D9: only this phase's job (Save report can run a job too). }
  if not ((JobPurpose = MaintPhase) or ((JobPurpose = 'maintkey') and ((MaintPhase = 'key3') or (MaintPhase = 'key4')))) then
    Exit;
  JobState := JOB_IDLE;
  if MaintPhase = 'setemail' then
  begin
    { The page says where the test email went (m02_test_sent) and Next becomes Done. }
    MaintPhase := '';
    if JobCode = 'email_set' then
    begin
      MailSaved := True;
      RenderMailStatus;
    end
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
      BackupError := FM1('s10_not_writable', MaintTarget);
      RenderPage(P_BACKUP);
    end;
  end
  else if (MaintPhase = 'key3') or (MaintPhase = 'key4') then
  begin
    KeyText := JsonValue(JobText, 'recovery_key');
    JobText := '';
    if KeyText = '' then
    begin
      { W9 review item 9: the drive changed, but its key was not made. }
      if MaintPhase = 'key3' then BackToMaint(FM1('m03_key_failed', MaintTarget)) else begin MaintPhase := ''; MaintLine := CM('s14_key_failed'); RenderPage(P_MAINT); end;
      Exit;
    end;
    if MaintPhase = 'key3' then
    begin
      MaintPhase := 'keyform';
      KeyForm(CM('m03_first'), CM('btn_done'));
      BackToMaint(FM1('m03_done', MaintTarget));
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
{ M05 Update (plan 7.4 setup-program path, 7.3, 10.3 F10; wizard spec M05; W13b part 2)          }
{ ------------------------------------------------------------------------------------------- }

{ Phases: idle (engine status until engine_idle), copy (the receive parts into the data folder),
  receive, wsl (W13b-5), update (the engine job), scripts (the state-tree scripts, only after the
  engine succeeded), done (Inno copies the program folder, then the finished page). pause waits
  UPDATE_WAIT_MS before idle or wsl again. A failure shows in place in the S13 layout. }

function UpdStageName(Index: Integer): String;
begin
  case Index of
    1: Result := CM('m05_stage1');
    2: Result := CM('m05_stage2');
    3: Result := CM('m05_stage3');
  else
    Result := CM('m05_stage4');
  end;
end;

{ P2-4: Cancel closes when no step is in flight, after a result, and in the slow state of the
  engine job, which goes on without setup (a later run of this setup waits for it, then finds
  version_not_newer). }
function UpdCanStop: Boolean;
begin
  Result := UpdFailed or (UpdPhase = '') or (UpdPhase = 'idle') or (UpdPhase = 'pause') or ((UpdPhase = 'update') and UpdSlowShown);
end;

procedure UpdStep(Phase, Action, Extra: String);
begin
  UpdPhase := Phase;
  UpdAt := GetTickCount;
  UpdOut := '';
  if Action <> '' then
  begin
    UpdOut := NewOut(Action);
    StartHelper(Action, RunId, UpdOut, Extra);
  end;
end;

procedure UpdPause(NextPhase: String);
begin
  UpdWaiting := True;
  UpdNext := NextPhase;
  UpdStep('pause', '', '');
  RenderPage(P_UPDATE);
end;

procedure UpdFail(Stage: Integer; Text: String; Retry: Boolean);
begin
  UpdFailed := True;
  UpdRetry := Retry;
  UpdWaiting := False;
  UpdPhase := '';
  UpdFailStage := UpdStageName(Stage);
  UpdFailText := Text;
  WizardForm.CancelButton.Enabled := True;
  RenderPage(P_UPDATE);
end;

{ A step that did not reach the engine's update changed nothing (spec 7.5 for the helper codes). }
function UpdStepText(Code: String): String;
begin
  if Code = 'helper_timeout' then
    Result := CM('av_blocked')
  else if Code = 'service_logon_failed' then
    Result := CM('service_logon_failed')
  else
    Result := FM1('m05_not_changed', InstalledVersion);
end;

{ P2-3: the sentence follows the engine's journal state (job-result update_state), because only
  a rollback restores and revokes the sessions. }
procedure UpdateFailed;
begin
  UpdState := JsonValue(JobRaw, 'update_state');
  UpdNeedsGb := JsonLiteral(JobRaw, 'needs_gb');
  if UpdState = 'rolled_back' then
    UpdFail(4, FM1('m05_rolled_back', InstalledVersion), True)
  else if UpdState = 'needs_support' then
    UpdFail(4, CM('m05_support'), False)
  else if JobCode = 'insufficient_space' then
    UpdFail(2, FM1('m05_space', UpdNeedsGb), False)
  else
    UpdFail(3, UpdStepText(JobCode), True);
end;

{ The receive parts and the WSL package of this setup; not the Linux image. W14-D9: one file
  per timer tick (upd.unpack); StepFinished 'upd-unpack' copies them (update-prepare). }
procedure ExtractUpdateParts;
begin
  QueueExtract('slateops-engine-*|slateops-server-*|slateops-caddy-*|release-manifest.json|release-manifest.json.sigstore.json|wsl.*', 'upd-unpack');
end;

procedure StartUpdate;
begin
  UpdStartedAt := GetTickCount;
  UpdFailed := False;
  UpdWaiting := False;
  UpdSlowShown := False;
  UpdState := '';
  UpdStep('idle', 'engine-status', '');
  RenderPage(P_UPDATE);
end;

{ The four M05 stages, and the fifth when the update goes back (7.6). }
function UpdStages: String;
begin
  Result := UpdStageName(1) + '|' + UpdStageName(2) + '|' + UpdStageName(3) + '|' + UpdStageName(4);
  if (JobPurpose = 'update') and ((JobStepJob = 'rollback') or (JobStepJob = 'recover')) then
    Result := Result + '|' + FM1('m05_stage_back', InstalledVersion);
end;

procedure RenderUpdate;
begin
  BeginBody(P_UPDATE);
  WizardForm.PageNameLabel.Caption := CM('m05_title');
  WizardForm.PageDescriptionLabel.Caption := FM2('m05_subtitle', InstalledVersion, SetupVersion);
  WizardForm.BackButton.Visible := False;
  if UpdFailed then
  begin
    AddFailure(UpdFailStage, UpdFailText, UpdRetry);
    Exit;
  end;
  if UpdPhase = '' then
  begin
    AddText(FM1('m05_backup', InstalledVersion), False);
    AddText(CM('m05_people'), False);
    SetNextCaption(CM('m05_next'));
    WizardForm.NextButton.Enabled := True;
    Exit;
  end;
  WizardForm.NextButton.Enabled := False;
  WizardForm.CancelButton.Enabled := UpdCanStop;
  { W14-D5 (7.6 "M05 update"): stage 1 on Windows (the idle check, the parts, the WSL step) and
    the engine's receive; stages 2 to 4 from the update job's standard error; the stage "Go back
    to version ..." when the engine reports a rollback or a recover. }
  if UpdWaiting then
    AddText(CM('m05_waiting'), False);
  if UpdPhase = 'done' then
    AddProgress('update', UpdStages, 5, '', 0, '')
  else
    AddProgress('update', UpdStages, WaitStage('update'), WaitActionText('update'), UpdStartedAt, CM('wait_up_to_60'));
  { P2-5: no verdict at a time limit; the slow line and Save report, and no Try again while the
    engine still works. }
  if (UpdPhase = 'update') and UpdSlowShown then
  begin
    BlockGap;
    AddText(CM('s12_slow'), True);
    AddText(CM('m05_slow_close'), False);
    AddReportControls;
  end;
  { W14-D3 (designer's M05 item): "People cannot use ... This can take up to 1 hour. Tell your
    people before you start." shows before the start only; while it runs, the time line already
    says the hour. }
end;

{ From the timer. }
procedure PollUpdate;
var
  Code: String;
begin
  if (EntryScreen <> 'M05') or (UpdPhase = '') or (UpdPhase = 'done') or (UpdPhase = 'unpack') then
    Exit;
  if UpdPhase = 'pause' then
  begin
    if Elapsed(UpdAt) < UPDATE_WAIT_MS then
      Exit;
    if UpdNext = 'idle' then
      UpdStep('idle', 'engine-status', '')
    else
      UpdStep('wsl', 'update-wsl', '');
    Exit;
  end;
  if (UpdPhase = 'receive') or (UpdPhase = 'update') then
  begin
    if JobState <> JOB_DONE then
    begin
      if (UpdPhase = 'update') and JobSlow and not UpdSlowShown then
      begin
        UpdSlowShown := True;
        { As S12 (correction 5): the task's last result; an account that cannot sign in never
          runs the job. W14-D9: the poll's job-result answer; the stop runs from the timer
          (StepFinished 'upd-logon'). }
        if JobLogonFailed then
        begin
          JobState := JOB_IDLE;
          RunStep('job-stop', '', 'upd-logon', '', 0, 0, HELPER_LIMIT_MS);
          Exit;
        end;
        RenderPage(P_UPDATE);
      end;
      Exit;
    end;
    JobState := JOB_IDLE;
    if UpdPhase = 'receive' then
    begin
      if JobExit = 0 then
        UpdStep('wsl', 'update-wsl', '')
      else
        UpdFail(1, UpdStepText(JobCode), True);
    end
    { P2-2: "version_not_newer" is an update that the tick finished (section 12). }
    else if (JobExit = 0) or (JobCode = 'version_not_newer') then
    begin
      UpdEngineDone := True;
      UpdStep('scripts', 'update-done', '');
      RenderPage(P_UPDATE);
    end
    else if (JobCode = 'runner_busy') or (JobCode = 'engine_busy') then
      UpdPause('idle')
    else
      UpdateFailed;
    Exit;
  end;
  Code := ReadResultCode(UpdOut);
  if (Code = '') and (UpdPhase = 'wsl') and (Elapsed(UpdAt) > WSL_LIMIT_MS) then
    Code := 'helper_timeout';
  if (Code = '') and (UpdPhase <> 'wsl') and (Elapsed(UpdAt) > HELPER_LIMIT_MS) then
    Code := 'helper_timeout';
  if Code = '' then
    Exit;
  if UpdPhase = 'idle' then
  begin
    if Code <> 'ok' then
      UpdFail(1, CM('m05_unreachable'), True)
    else if JsonLiteral(ReadText(UpdOut), 'engine_idle') <> 'true' then
      UpdPause('idle')
    else
    begin
      UpdWaiting := False;
      UpdStep('unpack', '', '');
      ExtractUpdateParts;
      RenderPage(P_UPDATE);
    end;
  end
  else if UpdPhase = 'copy' then
  begin
    if Code = 'copied' then
    begin
      { Its own purpose: receive keeps the job runner's time limit (only the update job has none). }
      UpdPhase := 'receive';
      StartJob('receive', '{"run_id":"' + RunId + '","setup_version":"' + SetupVersion + '"}', 'updreceive', False, False, 15);
    end
    else
      UpdFail(1, UpdStepText(Code), True);
  end
  else if UpdPhase = 'wsl' then
  begin
    if (Code = 'present') or (Code = 'wsl_updated') then
    begin
      UpdWaiting := False;
      UpdPhase := 'update';
      StartJob('update', '{"run_id":"' + RunId + '","version":"' + SetupVersion + '"}', 'update', False, False, UPDATE_SLOW_MINUTES);
      RenderPage(P_UPDATE);
    end
    else if Code = 'engine_busy' then
      UpdPause('wsl')
    else if Code = 'wsl_not_back' then
      UpdFail(1, CM('f10'), True)
    else if Code = 'engine_unreachable' then
      UpdFail(1, CM('m05_unreachable'), True)
    else if Code = 'helper_timeout' then
      UpdFail(1, CM('av_blocked'), True)
    else
      UpdFail(1, CM('s05_failed'), Code <> 'hash_mismatch');
  end
  else if UpdPhase = 'scripts' then
  begin
    if Code = 'copied' then
    begin
      UpdPhase := 'done';
      WizardForm.NextButton.Enabled := True;
      WizardForm.NextButton.OnClick(WizardForm.NextButton);
    end
    else if Code = 'helper_timeout' then
      UpdFail(4, CM('av_blocked'), True)
    else
      { The engine runs the new version; Try again reaches here again through version_not_newer. }
      UpdFail(4, FM1('m05_finish_failed', SetupVersion), True);
  end;
end;

{ Next on M05: "Update now", then Try again; True (Inno's file copy) only after success. }
function UpdateNext: Boolean;
begin
  Result := UpdPhase = 'done';
  if Result then
    Exit;
  { W14-D9: Save report's server part runs; one job at a time. }
  if JobRunning then
    Exit;
  if UpdFailed and not UpdRetry then
    Exit;
  if UpdFailed then
    RunId := NewRunId('update');
  { The engine already runs this version: only the Windows part is left. }
  if UpdFailed and UpdEngineDone then
  begin
    UpdFailed := False;
    UpdStep('scripts', 'update-done', '');
    RenderPage(P_UPDATE);
    Exit;
  end;
  if UpdFailed or (UpdPhase = '') then
    StartUpdate;
end;

{ ------------------------------------------------------------------------------------------- }
{ DEC-0041 (AC-W3, AC-W4): Remove everything setup added                                       }
{ ------------------------------------------------------------------------------------------- }

{ Setup is a complete installation or nothing. Cancel, closing the window, a failed install
  (after Save report) and an earlier run found at start run this one removal, in a modal form
  with its stages and the time so far: 1 the running step stops, 2 Slate Operations stops, 3 the
  data of this run goes (kept data is never deleted: setup-remove-data returns it to kept\), 4
  WSL and Virtual Machine Platform go only when setup turned them on and no other distribution
  is registered, 5 the Windows settings and the state folder go, last, so a removal that stops
  early leaves the records for the next start (AC-W4). Every step has a limit; a step past it
  stops the removal, is logged, and setup closes. The form's Close button works at any time.
  The steps run from the wizard's timer (TimerTick), never inside a tick of their own. }
const
  REMOVE_STEP_MS = 20000;
  { Unregistering the server part (the helper waits up to 60 s for each Exec job) and deleting
    the data folder. }
  REMOVE_DATA_MS = 150000;
  { "wsl --uninstall" and DISM, up to 90 s each inside the helper. }
  REMOVE_FEATURES_MS = 200000;
  { The tasks, the hidden account and its profile, the firewall, the state folder. }
  REMOVE_WINDOWS_MS = 90000;

var
  CloseFlow, CloseAfter, ClosePhase, CloseOut, CloseLine, CloseEnd, RemoveFeaturesCode, RemoveDataCode, RemoveWindowsCode: String;
  CloseAt, CloseStartedAt, CloseLimitMs: Cardinal;
  CloseNumber: Integer;
  RemoveClose: TNewButton;

function CloseFlowRunning: Boolean;
begin
  Result := ClosePhase <> '';
end;

{ The removal's page in its form: what happens, the stages, the step that runs and the time;
  at the end the last line (Windows finishes at the next restart, or why it stopped). }
{ AC-O8 (owner, rc.28): the removal runs from its first step until it ends or a step passes its
  limit; every step has a hard limit, so it always ends. Until then the window cannot close. }
function RemovalRunning: Boolean;
begin
  Result := (ClosePhase <> '') or RemoveStartPending;
end;

{ The window's X, Alt+F4 and Escape: refused while the removal runs. }
procedure RemoveCloseQuery(Sender: TObject; var CanClose: Boolean);
begin
  CanClose := not RemovalRunning;
end;

procedure RenderRemove;
begin
  if RemoveForm = nil then
    Exit;
  RemoveClose.Enabled := not RemovalRunning;
  if RemovePanel <> nil then
    RemovePanel.Free;
  RemovePanel := TPanel.Create(RemoveForm);
  RemovePanel.Parent := RemoveForm;
  RemovePanel.BevelOuter := bvNone;
  RemovePanel.ParentBackground := False;
  RemovePanel.Color := RemoveForm.Color;
  RemovePanel.SetBounds(ScaleX(14), ScaleY(14), RemoveForm.ClientWidth - ScaleX(28), RemoveClose.Top - ScaleY(26));
  Cur := RemovePanel;
  CurY := 0;
  RowX := 0;
  WaitTime := nil;
  WaitNow := nil;
  if CloseAfter = 'start' then
    AddText(CM('remove_start'), False)
  else
    AddText(CM('remove_text'), False);
  BlockGap;
  if ClosePhase <> '' then
    AddProgress('remove', CM('remove_stages'), CloseNumber, FM1('wait_now', CloseLine), CloseStartedAt, '')
  else
  begin
    if CloseEnd = 'done' then
      AddProgress('remove', CM('remove_stages'), 6, '', 0, '')
    else
      AddProgress('remove', CM('remove_stages'), CloseNumber, '', 0, '');
    if CloseEnd = 'limit' then AddText(CM('remove_limit'), False)
    else if CloseEnd = 'kept' then AddText(CM('remove_kept_failed'), False)
    else if CloseEnd = 'data' then AddText(CM('remove_data_failed'), False)
    else
    begin
      if RemoveFeaturesCode = 'removed' then AddText(CM('remove_restart_line'), False);
      if RemoveWindowsCode = 'removed_at_restart' then AddText(CM('remove_account_restart'), False);
    end;
  end;
end;

procedure CloseStep(Number: Integer; Phase, Line, Action, Extra: String; LimitMs: Cardinal);
begin
  ClosePhase := Phase;
  CloseNumber := Number;
  CloseAt := GetTickCount;
  CloseLimitMs := LimitMs;
  CloseLine := Line;
  CloseOut := '';
  if Action <> '' then
  begin
    CloseOut := NewOut(Action);
    if not StartHelper(Action, RunId, CloseOut, Extra) then
      CloseOut := '';
  end;
  Log('Removal ' + IntToStr(Number) + ' of 5: ' + Phase + ' (limit ' + IntToStr(LimitMs div 1000) + ' s).');
  RenderRemove;
end;

{ Flow: 'remove'. After: 'close' (Cancel, closing the window, a failed install), 'start' (an
  earlier run, AC-W4), 'none' (the self-test: no form, no end action). }
procedure StartCloseFlow(Flow, After: String);
begin
  if ClosePhase <> '' then
    Exit;
  CloseFlow := Flow;
  CloseAfter := After;
  CloseEnd := '';
  RemoveFeaturesCode := '';
  RemoveDataCode := '';
  RemoveWindowsCode := '';
  CloseStartedAt := GetTickCount;
  { Nothing of the install goes on: no step, no unpacking, no job result is awaited. }
  StepFor := '';
  ExtractList := '';
  ExtractFor := '';
  JobState := JOB_IDLE;
  ClosePipe;
  { R-4 (Architect N-5): while S05 turns features on, the removal waits for that step, within
    S05's own limit; the step records what setup turned on before it does it, so the removal then
    reads a complete record. }
  if PrepState = 'working' then
  begin
    ClosePhase := 'prep';
    CloseNumber := 1;
    CloseAt := GetTickCount;
    CloseOut := PrepOut;
    CloseLine := CM('remove_wait_prep');
    if Elapsed(PrepStartedAt) < DATA_LIMIT_MS then
      CloseLimitMs := DATA_LIMIT_MS - Elapsed(PrepStartedAt)
    else
      CloseLimitMs := REMOVE_STEP_MS;
    Log('Removal 1 of 5: waiting for the S05 step (limit ' + IntToStr(CloseLimitMs div 1000) + ' s).');
    RenderRemove;
    Exit;
  end;
  CloseStep(1, 'job', CM('remove_job'), 'job-stop', '', REMOVE_STEP_MS);
end;

{ The end of the removal: the form closes by itself when there is nothing more to read, else it
  shows the last line and its Close button. }
procedure EndCloseFlow(EndKey: String);
begin
  ClosePhase := '';
  CloseEnd := EndKey;
  Log('Removal ended: ' + EndKey + '.');
  if RemoveForm = nil then
    Exit;
  { Inno's Pascal Script gives a form no ModalResult (only buttons have one): Close ends
    ShowModal, and RunRemoval reads CloseEnd, not the modal result. }
  { A restart line (features or the account, R-10) stays on the form until Close. }
  if (EndKey = 'done') and (RemoveFeaturesCode <> 'removed') and (RemoveWindowsCode <> 'removed_at_restart') then
    RemoveForm.Close
  else
    RenderRemove;
end;

{ From the timer. }
procedure PollCloseFlow;
var
  Code, Extra: String;
begin
  if ClosePhase = '' then
    Exit;
  if CloseOut = '' then
    Code := 'helper_failed'
  else
    Code := ReadResultCode(CloseOut);
  if (Code = '') and (Elapsed(CloseAt) < CloseLimitMs) then
    Exit;
  if Code = '' then
  begin
    { AC-W3: past its limit the removal stops and setup closes; the records stay, so the next
      start removes the rest (AC-W4). }
    Log('Removal: ' + ClosePhase + ' gave no result in ' + IntToStr(CloseLimitMs div 1000) + ' s; setup closes, and the next setup run removes the rest.');
    EndCloseFlow('limit');
    Exit;
  end;
  Log('Removal: ' + ClosePhase + ': ' + Code + '.');
  if ClosePhase = 'prep' then
  begin
    PrepState := 'done';
    CloseStep(1, 'job', CM('remove_job'), 'job-stop', '', REMOVE_STEP_MS);
  end
  else if ClosePhase = 'job' then
    CloseStep(2, 'stop', CM('remove_stopping'), 'uninstall-stop', '', REMOVE_STEP_MS)
  else if ClosePhase = 'stop' then
    CloseStep(3, 'data', CM('remove_data_line'), 'setup-remove-data', '', REMOVE_DATA_MS)
  else if ClosePhase = 'data' then
  begin
    { Kept data that could not go back to kept\ stops the removal: nothing else goes, so the next
      start tries again; the data is never deleted. }
    if Code = 'keep_failed' then
    begin
      EndCloseFlow('kept');
      Exit;
    end;
    { R-5 (Architect N-6, Security S97-8): any other data step that did not finish stops the
      removal before the Windows settings and the state record go, so the next start finds the
      records and finishes it. }
    if (Code <> 'removed') and (Code <> 'returned') and (Code <> 'nothing') then
    begin
      EndCloseFlow('data');
      Exit;
    end;
    RemoveDataCode := Code;
    CloseStep(4, 'features', CM('remove_features'), 'remove-features', '', REMOVE_FEATURES_MS);
  end
  else if ClosePhase = 'features' then
  begin
    RemoveFeaturesCode := Code;
    { W9 review item 4: with the data folder left over, the scripts stay for Save report. }
    Extra := '';
    if (RemoveDataCode <> 'removed') and (RemoveDataCode <> 'returned') and (RemoveDataCode <> 'nothing') then
      Extra := '-DataLeft';
    CloseStep(5, 'windows', CM('remove_windows'), 'remove-windows', Extra, REMOVE_WINDOWS_MS);
  end
  else
  begin
    { R-10: removed_at_restart: a startup task removes the account's profile at the restart. }
    RemoveWindowsCode := Code;
    EndCloseFlow('done');
  end;
end;

{ The form, built without being shown (the self-test builds it too). }
function BuildRemoveForm(After: String): TSetupForm;
begin
  Result := CreateCustomForm(ScaleX(480), ScaleY(330), False, False);
  Result.Caption := CM('remove_title');
  RemoveForm := Result;
  CloseAfter := After;
  SetArrayLength(FormButtons, 0);
  RemoveClose := FormButton(Result, CM('btn_close'), ScaleX(90), mrCancel);
  RemoveClose.Cancel := True;
  RemoveClose.SetBounds(Result.ClientWidth - ScaleX(14) - RemoveClose.Width, Result.ClientHeight - ScaleY(14) - RemoveClose.Height,
    RemoveClose.Width, RemoveClose.Height);
  Result.OnCloseQuery := @RemoveCloseQuery;
  RenderRemove;
end;

{ The labels of the form go with it; nothing that the timer reads may point at them. }
procedure FreeRemoveForm;
begin
  if RemoveForm <> nil then
    RemoveForm.Free;
  RemoveForm := nil;
  RemovePanel := nil;
  RemoveClose := nil;
  Cur := nil;
  WaitKind := '';
  WaitTime := nil;
  WaitNow := nil;
  WaitDrawn := 0;
end;

{ Runs the removal in its modal form. True when every step ended; False when a step passed its
  limit, kept data stayed in distro, or the person closed the form first (logged; the next
  start removes the rest). Never call it from inside a timer tick. }
function RunRemoval(Why: String): Boolean;
begin
  Result := False;
  { R-6 (Architect N-8): the window shows first; the first timer tick starts the work. AC-O8:
    pending before the form is built, so its Close starts off. }
  RemoveWhy := Why;
  RemoveStartPending := True;
  BuildRemoveForm(Why);
  try
    RemoveForm.ShowModal;
    if ClosePhase <> '' then
    begin
      Log('The removal was closed during ' + ClosePhase + '; the next setup run removes the rest.');
      ClosePhase := '';
    end;
    Result := CloseEnd = 'done';
  finally
    RemoveStartPending := False;
    FreeRemoveForm;
  end;
end;

{ ------------------------------------------------------------------------------------------- }
{ W14-D9: what follows each step of the step runner and the unpacking (Wizard.iss)               }
{ ------------------------------------------------------------------------------------------- }

procedure StepFinished(ForTag, Code: String);
var
  Text: String;
begin
  Text := '';
  if StepOut <> '' then
    Text := ReadText(StepOut);
  if ForTag = 'cr-save' then
  begin
    RenderPage(-1);
    CheckRestartConfirm(Code);
  end
  else if ForTag = 'cr-restart' then
  begin
    if Code = 'restarting' then
    begin
      ForceClose := True;
      WizardForm.Close;
    end
    else
      RenderPage(-1);
  end
  else if ForTag = 'restart-now' then
  begin
    ForceClose := True;
    WizardForm.Close;
  end
  else if ForTag = 'prep-unpack' then
  begin
    PrepOut := NewOut('prepare-pc');
    PrepState := 'working';
    StartHelper('prepare-pc', RunId, PrepOut, '');
    RenderPage(P_RESTART);
  end
  else if ForTag = 'prep-save' then
  begin
    PrepState := 'restart';
    ResumeCode := Code;
    RenderPage(P_RESTART);
  end
  else if ForTag = 'drives' then
  begin
    LoadDataDrives(Text);
    if Code = 'helper_timeout' then
      DataError := 'helper_timeout';
    RenderPage(P_DATA);
  end
  else if ForTag = 'kept' then
  begin
    KeptRead(Text);
    { A kept folder that the helper could not read never counts as an empty one. }
    if KeptState = '' then
      KeptState := 'kept_unreadable';
    RenderPage(P_DATA);
  end
  else if ForTag = 'data-unpack' then
    StartDataFolder
  else if ForTag = 'org-name' then
  begin
    { DEC-0039 (P-3 a): another device answers for the address: the person chooses another
      short name. A probe that cannot run does not stop setup (it is logged). }
    OrgStatus.Caption := '';
    StepLabel := nil;
    WizardForm.NextButton.Enabled := True;
    if Code = 'in_use' then
    begin
      OrgMoreOpen := True;
      UpdateOrgAddress;
      OrgError.Caption := FM1('s08_err_label_in_use', OrgSlug.Text + '.local');
      OrgErrorAfter := OrgSlug;
      LayoutOrg;
      if OrgSlug.CanFocus then
        WizardForm.ActiveControl := OrgSlug;
    end
    else if Code = 'label_invalid' then
    begin
      OrgMoreOpen := True;
      UpdateOrgAddress;
      OrgFail('s08_err_label', OrgSlug);
    end
    else
    begin
      if Code <> 'free' then
        Log('S08 name check: ' + Code + '; setup goes on.');
      OrgNameChecked := OrgSlug.Text;
      LayoutOrg;
      WizardForm.NextButton.OnClick(WizardForm.NextButton);
    end;
  end
  else if ForTag = 'data-check' then
  begin
    { DEC-0041 (AC-W1): the S07 folder check; Next goes on only with "ready". }
    if Code = 'ready' then
    begin
      DataChecked := DataRoot;
      KeptChecked := KeptMode;
      WizardForm.NextButton.Enabled := True;
      WizardForm.NextButton.OnClick(WizardForm.NextButton);
    end
    else
    begin
      DataChecked := '';
      DataError := Code;
      { The three folder messages of S07; a helper that never answered gets the antivirus
        message; any other answer the start failure. }
      if (Code <> 'data_folder_parent_unsafe') and (Code <> 'not_empty') and (Code <> 'drive_not_fixed_ntfs') and (Code <> 'helper_timeout') then
        DataError := 'start_failed';
      RenderPage(P_DATA);
    end;
  end
  else if ForTag = 'provider' then
  begin
    MailDetected := Code;
    ApplyProvider;
    LayoutMail;
    RenderMailStatus;
  end
  else if ForTag = 'r7' then
  begin
    if Code <> 'clear' then
    begin
      MailPhase := '';
      MailShowReport := True;
      if Code = 'policy' then SetMailError(CM('c18_policy'), MailPassword)
      else SetMailError(CM('c18_unreadable'), MailPassword);
      RenderMailStatus;
    end
    else
    begin
      MailPhase := 'r7done';
      StartMailTest;
    end;
  end
  else if ForTag = 's10-check' then
  begin
    if BackupResult(Text) then
    begin
      BackupCheckedDrive := BackupDrive;
      WizardForm.NextButton.Enabled := True;
      WizardForm.NextButton.OnClick(WizardForm.NextButton);
    end
    else
      RenderPage(P_BACKUP);
  end
  else if ForTag = 'inst-save' then
  begin
    { DEC-0041 (AC-W2): a step past its limit stops the install with its message. }
    if Code = 'helper_timeout' then
      InstallFail(0, CM('s12_av_blocked'))
    else if KeptMode then
      InstallChannelCheck('')
    else
      RunStep('time-zone', '', 'inst-tz', '', 0, 0, INSTALL_STEP_MS);
  end
  else if ForTag = 'inst-tz' then
  begin
    if Code = 'helper_timeout' then
      InstallFail(0, CM('s12_av_blocked'))
    else
      InstallChannelCheck(JsonValue(Text, 'iana'));
  end
  else if ForTag = 'inst-r7' then
  begin
    { AC-W5: R7 again right before the password goes to the install job (spec 5.2). }
    if Code = 'clear' then InstallStartJob(InstallTz)
    else if Code = 'policy' then InstallFail(6, CM('c18_policy'))
    else if Code = 'helper_timeout' then InstallFail(6, CM('s12_av_blocked'))
    else InstallFail(6, CM('c18_unreadable'));
  end
  else if ForTag = 'printers' then
    ShowPrinterForm(Text)
  else if ForTag = 'key-saved' then
  begin
    KeySavedDone := True;
    KeyText := '';
    WizardForm.NextButton.Enabled := True;
    WizardForm.NextButton.OnClick(WizardForm.NextButton);
  end
  else if ForTag = 'code' then
  begin
    RenderPage(P_MAINT);
    ShowPhoneCode(JsonValue(Text, 'security_code'));
  end
  else if ForTag = 'repair' then
  begin
    if Code = 'repaired' then MaintLine := CM('m01_repaired')
    else if Code = 'logging_policy' then MaintLine := CM('c18_policy')
    else if Code = 'logging_policy_unreadable' then MaintLine := CM('c18_unreadable')
    else if Code = 'helper_timeout' then MaintLine := CM('av_blocked')
    else MaintLine := CM('m01_repair_failed');
    RenderPage(P_MAINT);
  end
  else if ForTag = 'm03-check' then
  begin
    if not BackupResult(Text) then
      RenderPage(P_BACKUP)
    else
    begin
      RunStep('prepare-backup', '-Drive ' + Uppercase(BackupDrive), 'm03-prepare', FM1('cd_preparing', BackupDrive), 2, 4, HELPER_LIMIT_MS);
      RenderPage(P_BACKUP);
    end;
  end
  else if ForTag = 'm03-prepare' then
  begin
    if Code <> 'ready' then
    begin
      BackupError := FM1('s10_not_writable', BackupDrive);
      RenderPage(P_BACKUP);
    end
    else
      M03Target;
  end
  else if ForTag = 'upd-logon' then
    UpdFail(3, CM('service_logon_failed'), True)
  else if ForTag = 'upd-unpack' then
  begin
    UpdStep('copy', 'update-prepare', '');
    RenderPage(P_UPDATE);
  end;
end;

{ ------------------------------------------------------------------------------------------- }
{ W14-D5: the stage and the action of each wait (spec 7.6)                                      }
{ ------------------------------------------------------------------------------------------- }

{ The last helper progress line of OutFile (beside its result file). }
procedure HelperStep(OutFile: String; var Job, Key: String; var Number, Total: Integer);
begin
  Job := '';
  Key := '';
  Number := 0;
  Total := 0;
  if OutFile <> '' then
    ReadProgressFile(ProgressFileOf(OutFile), True, Job, Key, Number, Total);
end;

{ The stage of one of the eight S12 stages that an install step key belongs to (7.6). }
function InstallKeyStage(Key: String): Integer;
begin
  if (Key = 'folders') or (Key = 'secrets') or (Key = 'env') then Result := 2
  else if Key = 'tls' then Result := 3
  else if (Key = 'providers') or (Key = 'provision') then Result := 4
  else if (Key = 'api') or (Key = 'caddy') then Result := 5
  else if Key = 'admin' then Result := 6
  else if (Key = 'backup') or (Key = 'finish') then Result := 7
  else Result := 1;
end;

function UpdateKeyStage(Key: String): Integer;
begin
  if Key = 'backup' then Result := 2
  else if (Key = 'env') or (Key = 'providers') or (Key = 'health') or (Key = 'provision') then Result := 3
  else if (Key = 'api') or (Key = 'caddy') or (Key = 'switch') then Result := 4
  else Result := 1;
end;

function CheckStage(Number: Integer): Integer;
begin
  { DEC-0039: 27 checks (no C15, C16, C30): C17 is check 15. }
  if Number <= 6 then Result := 1
  else if Number <= 8 then Result := 2
  else if Number <= 15 then Result := 3
  else Result := 4;
end;

function StageName(Stages: String; Index: Integer): String;
var
  I, Cut: Integer;
begin
  Result := Stages;
  for I := 2 to Index do
  begin
    Cut := Pos('|', Result);
    if Cut = 0 then
      Exit;
    Result := Copy(Result, Cut + 1, Length(Result));
  end;
  Cut := Pos('|', Result);
  if Cut > 0 then
    Result := Copy(Result, 1, Cut - 1);
end;

function WaitStage(Kind: String): Integer;
var
  Job, Key: String;
  Number, Total: Integer;
begin
  Result := 1;
  if Kind = 'check' then
  begin
    HelperStep(CheckOut, Job, Key, Number, Total);
    Result := CheckStage(Number);
  end
  else if Kind = 'prep' then
  begin
    if PrepState = 'saving' then Result := 3
    else if PrepState = 'working' then
    begin
      HelperStep(PrepOut, Job, Key, Number, Total);
      if (Key = 'wsl') or (Key = 'busy') then Result := 2
      else if Key = 'check' then Result := 3;
    end;
  end
  else if Kind = 'install' then
  begin
    { DEC-0041 (AC-W2): 1 the data folder, then one stage per server part step, then the eight
      stages of the install. }
    if InstallStep = -1 then
    begin
      if DataPrepared then Result := 2 + BgIndex;
    end
    else if InstallDone then Result := PrepStageCount + 9
    else if InstallStep >= 3 then Result := PrepStageCount + 8
    else if (InstallStep = 2) and (JobPurpose = 'install') and (JobStepJob = 'install') then Result := PrepStageCount + InstallKeyStage(JobStepKey)
    else if InstallStep = 1 then Result := PrepStageCount + 6
    else Result := PrepStageCount + 1;
  end
  else if Kind = 'repair' then
  begin
    HelperStep(StepOut, Job, Key, Number, Total);
    if Number > 0 then Result := Number;
  end
  else if Kind = 'update' then
  begin
    if UpdPhase = 'done' then Result := 5
    else if UpdPhase = 'scripts' then Result := 4
    else if (UpdPhase = 'update') and (JobPurpose = 'update') then
    begin
      if (JobStepJob = 'rollback') or (JobStepJob = 'recover') then Result := 5
      else if JobStepJob = 'update' then Result := UpdateKeyStage(JobStepKey);
    end;
  end;
end;

{ The action line of the new recovery key's steps (7.6 S14, M03, M04). }
function KeyAction(Context, Drive: String): String;
begin
  Result := '';
  if (JobPurpose <> 'key') and (JobPurpose <> 'maintkey') then
    Exit;
  if JobStepKey = 'mount' then
  begin
    if Context = 'm03' then Result := FM1('m03_mount_line', Drive)
    else Result := StepText('new-recovery-key', 'mount', Drive, '', '');
  end
  else if JobStepKey = 'key' then
  begin
    if Context = 'm03' then Result := FM1('m03_key_line', Drive)
    else if Context = 'm04' then Result := CM('m04_key_line')
    else Result := StepText('new-recovery-key', 'key', Drive, '', '');
  end;
end;

{ The check that runs: "Checking: Internet (12 of 30)." (7.6), from the helper's line. }
function CheckActionText(CopyKey, Stages: String): String;
var
  Job, Key, Name: String;
  Number, Total: Integer;
begin
  HelperStep(CheckOut, Job, Key, Number, Total);
  Result := '';
  if (Key = '') or (Number = 0) then
    Exit;
  Name := CM(Key + '_name');
  if (Name = '') and (Stages <> '') then
    Name := StageName(Stages, CheckStage(Number));
  if Name <> '' then
    Result := FM3(CopyKey, Name, IntToStr(Number), IntToStr(Total));
end;

function WaitActionText(Kind: String): String;
var
  Job, Key, Drive: String;
  Number, Total: Integer;
begin
  Result := '';
  Drive := Copy(DataRoot, 1, 2);
  if Kind = 'check' then
  begin
    Result := CheckActionText('check_action', CM('s02_stages'));
    if Result = '' then
      Result := StageName(CM('s02_stages'), 1);
  end
  else if Kind = 'recheck' then
  begin
    Result := CheckActionText('recheck_action', '');
    if Result = '' then
      Result := CM('s06_checking');
  end
  else if Kind = 'prep' then
  begin
    if PrepState = 'unpack' then Result := StepText('pc', 'unpack', '', '', '')
    else if PrepState = 'saving' then Result := CM('later_saving')
    else
    begin
      HelperStep(PrepOut, Job, Key, Number, Total);
      if Key = 'busy' then Result := StepText('pc', 'busy', IntToStr(Number), IntToStr(Total), '')
      else if Key <> '' then Result := StepText('pc', Key, S05WslVersion, '', '')
      else Result := StepText('pc', 'vmp', '', '', '');
    end;
  end
  else if Kind = 'install' then
  begin
    if InstallDone then
      Exit;
    if InstallStep = -1 then
    begin
      if DataPrepared then Result := BgAction
      else if ExtractRunning or (BgOut = '') then Result := StepText('data', 'unpack', '', '', '')
      else Result := StepText('data', 'folder', DataRoot, '', '');
    end
    else if (InstallStep = 1) and (Copy(JobPurpose, 1, 9) = 'selftest:') then
      Result := CM('s09_channel')
    else if (InstallStep = 1) and (StepFor = 'inst-r7') then
      Result := CM('s09_policy')
    else if InstallStep = 0 then
      Result := StepText('backup', 'check', BackupDrive, '', '')
    else if (InstallStep = 2) and (JobPurpose = 'install') and (JobStepJob = 'install') then
      Result := StepText('install', JobStepKey, HostName + '.local', Trim(OrgEmail.Text), BackupDrive)
    else if InstallStep = 3 then
    begin
      HelperStep(InstallOut, Job, Key, Number, Total);
      Result := StepText('win', Key, HostName + '.local', '', '');
    end
    else if InstallStep = 4 then
      Result := StepText('win', 'https', HostName + '.local', '', '');
    if Result = '' then
      Result := StageName(S12Stages, WaitStage('install'));
  end
  else if Kind = 'key' then
  begin
    Result := KeyAction('s14', BackupDrive);
    if Result = '' then
      Result := CM('s14_making');
  end
  else if Kind = 'repair' then
  begin
    HelperStep(StepOut, Job, Key, Number, Total);
    Result := StepText('repair', Key, HostName + '.local', Copy(MaintBackupFolder, 1, 2), '');
    if Result = '' then
      Result := CM('m01_repairing');
  end
  else if Kind = 'update' then
  begin
    if (UpdPhase = 'idle') or (UpdPhase = 'pause') then Result := StepText('upd', 'idle', '', '', '')
    else if UpdPhase = 'unpack' then Result := StepText('upd', 'unpack', SetupVersion, '', '')
    else if UpdPhase = 'copy' then Result := StepText('upd', 'copy', SetupVersion, Drive, '')
    else if UpdPhase = 'wsl' then Result := StepText('upd', 'wsl', WslVersion, '', '')
    else if UpdPhase = 'scripts' then Result := StepText('upd', 'scripts', '', '', '')
    else if ((UpdPhase = 'receive') and (JobPurpose = 'updreceive')) or ((UpdPhase = 'update') and (JobPurpose = 'update')) then
      Result := StepText(JobStepJob, JobStepKey, SetupVersion, InstalledVersion, '');
    if (Result = '') and (UpdPhase <> 'done') then
      Result := StageName(UpdStages, WaitStage('update'));
  end;
  if (Result <> '') and (Kind <> 'check') and (Kind <> 'recheck') then
    Result := FM1('wait_now', Result);
end;

{ The one line of the page's short wait (7.6 one-line form), or '' when none runs. }
function PageLineText: String;
var
  Job, Key, Action: String;
  Number, Total: Integer;
begin
  Result := '';
  if (StepFor <> '') and (StepFor <> 'repair') and (StepLine <> '') then
  begin
    if (StepFor = 'm03-check') or (StepFor = 'm03-prepare') then
      Result := OneLine(StepNumber, StepTotal, StepLine, MaintAt)
    else if StepFor = 'r7' then
      Result := OneLine(2, 4, StepLine, MailAt)
    else
      Result := OneLine(StepNumber, StepTotal, StepLine, StepAt);
    Exit;
  end;
  if FixRunning then
  begin
    if FixAction = 'fix-network-private' then Action := CM('c10_fixing')
    else if FixAction = 'fix-mdns' then Action := CM('c17_fixing')
    else if FixAction = 'remove-windows' then Action := CM('c29_removing_leftovers')
    else
    begin
      HelperStep(FixOut, Job, Key, Number, Total);
      Action := StepText('kit', Key, '', '', '');
      if Action = '' then
      begin
        Action := StepText('kit', 'stop', '', '', '');
        Number := 1;
      end;
      Result := OneLine(Number, 3, Action, FixStartedAt);
      Exit;
    end;
    Result := OneLine(0, 0, Action, FixStartedAt);
    Exit;
  end;
  if CheckRunning and (CheckFor = 'S11') then
  begin
    Action := CheckActionText('recheck_action', '');
    if Action = '' then
      Action := CM('s06_checking');
    Result := OneLine(0, 0, Action, CheckStartedAt);
    Exit;
  end;
  { M02 (DEC-0041 AC-W6): 1 the channel self-test, 2 the security policy, 3 the test email,
    4 set-email (MaintPhase 'setemail' below). }
  if MailPhase = 'selftest' then
    Result := OneLine(1, 4, CM('s09_channel'), MailAt)
  else if MailPhase = 'sending' then
  begin
    { AC-W6: the engine sends to the administrator's stored address, which Windows learns only
      from the answer (sent_to). }
    Result := OneLine(3, 4, CM('m02_sending'), MailAt);
  end
  else if MaintPhase = 'setemail' then
  begin
    Action := '';
    if JobPurpose = 'setemail' then
      Action := StepText(JobStepJob, JobStepKey, '', '', '');
    if Action = '' then
      Action := StepText('set-email', 'write', '', '', '');
    Result := OneLine(4, 4, Action, MailAt);
  end
  else if MaintPhase = 'target' then
  begin
    Action := '';
    if JobPurpose = 'target' then
      Action := StepText(JobStepJob, JobStepKey, Copy(MaintBackupFolder, 1, 2), MaintTarget, '');
    if Action = '' then
      Action := FM1('m03_setting', MaintTarget);
    Result := OneLine(3, 4, Action, MaintAt);
  end
  else if MaintPhase = 'key3' then
  begin
    Action := KeyAction('m03', MaintTarget);
    if Action = '' then
      Action := FM1('m03_key_line', MaintTarget);
    Result := OneLine(4, 4, Action, MaintAt);
  end
  else if MaintPhase = 'key4' then
  begin
    Action := KeyAction('m04', Copy(MaintBackupFolder, 1, 2));
    if Action = '' then
      Action := CM('m04_key_line');
    Result := OneLine(0, 0, Action, MaintAt);
  end;
end;

{ ------------------------------------------------------------------------------------------- }
{ The settings program (the small build, /DSettingsBuild)                                       }
{ ------------------------------------------------------------------------------------------- }

{ Returns True when the settings program goes on to M01. Save report from the Start menu runs
  here with no wizard (plan 10.6 item 1). }
function SettingsEntry: Boolean;
var
  CloseButton: TNewButton;
begin
  Result := True;
  if not SETTINGS_BUILD then
    Exit;
  if ExpandConstant('{param:SAVEREPORT|0}') = '1' then
  begin
    { W9 review item 8 (design W9-B5): say what happens first, then the result. W14-D9 (7.6
      "Save report", settings program): a small form with the one line while the timer saves
      the report; it closes by itself at the end. }
    MsgBox(CM('report_start'), mbInformation, MB_OK);
    ReportForm := CreateCustomForm(ScaleX(440), ScaleY(110), False, False);
    try
      ReportForm.Caption := CM('btn_save_report');
      ReportLabel := TNewStaticText.Create(ReportForm);
      ReportLabel.Parent := ReportForm;
      ReportLabel.AutoSize := False;
      ReportLabel.WordWrap := True;
      ReportLabel.ShowAccelChar := False;
      ReportLabel.SetBounds(ScaleX(14), ScaleY(14), ReportForm.ClientWidth - ScaleX(28), ScaleY(40));
      CloseButton := TNewButton.Create(ReportForm);
      CloseButton.Parent := ReportForm;
      CloseButton.Caption := CM('btn_close');
      CloseButton.ModalResult := mrCancel;
      CloseButton.Cancel := True;
      CloseButton.SetBounds(ReportForm.ClientWidth - ScaleX(104), ReportForm.ClientHeight - ScaleY(38), ScaleX(90), ScaleY(26));
      FitFormRow(ReportForm, nil, CloseButton);
      StartTimer;
      SaveReport(nil);
      ModalOpen := True;
      ReportForm.ShowModal;
    finally
      ModalOpen := False;
      ReportLabel := nil;
      ReportForm.Free;
      ReportForm := nil;
    end;
    if (ReportPhase = '') and (ReportLine <> '') then
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
  { W14-D1: the self-test build stops here; its result file is written. }
  if SELF_TEST then
    Result := 'Self-test finished.';
end;
