{ SelfTest.iss - the [Code] self-test (W14-D1, TASK-0097). Compiled only with /DSelfTest; the
  windows-installer workflow runs the result with /VERYSILENT /SELFTESTOUT=<file>. It runs the
  message helpers, the check reader and the S02 draw on the owner's check result (fixture), and
  the draw routines of S07, S09, S11, S12, S14, S15, M01 and M05 with sample state, so that a runtime
  fault (Type Mismatch, nil access) shows on the CI runner before the owner's next pass. Every
  step writes PASS or FAIL with the fault text; the last line is DONE. The pages stay hidden.
  With /DSelfTestRed one more step calls a routine that hands an "array of String" parameter on
  to FmtMessage, the W14-D1 pattern; the workflow expects it to FAIL. ASCII only. }

var
  SelfLog: String;

procedure SelfRecord(Name: String; Ok: Boolean; Message: String);
begin
  if Ok then
    SelfLog := SelfLog + 'PASS ' + Name + #13#10
  else
    SelfLog := SelfLog + 'FAIL ' + Name + ': ' + Message + #13#10;
end;

{ A measurement for a decision that is open (the workflow fails only on FAIL lines). }
procedure SelfInfo(Name, Message: String);
begin
  SelfLog := SelfLog + 'INFO ' + Name + ': ' + Message + #13#10;
end;

#ifdef SelfTestRed
function OpenArrayFM(Key: String; Args: array of String): String;
begin
  Result := FmtMessage(CM(Key), Args);
end;
#endif

{ The check reader and the S02 draw on one fixture; RenderCheckBody runs without its guard. }
procedure SelfCheck(Name, Fixture, Verdict: String; Fixes: Integer);
var
  Text, Messages: String;
  I: Integer;
begin
  try
    ExtractTemporaryFile(Fixture);
    Text := ReadText(ExpandConstant('{tmp}\' + Fixture));
    ParseCheck(Text);
    SelfRecord(Name + ' read', (CheckVerdict = Verdict) and (GetArrayLength(Items) = 30) and (CountClass('fix') = Fixes),
      'verdict ' + CheckVerdict + ', ' + IntToStr(GetArrayLength(Items)) + ' rows, ' + IntToStr(CountClass('fix')) + ' fix');
  except
    SelfRecord(Name + ' read', False, GetExceptionMessage);
  end;
  try
    Messages := '';
    for I := 0 to GetArrayLength(Items) - 1 do
      Messages := Messages + ItemWord(Items[I]) + ItemName(Items[I]) + ItemMessage(Items[I]);
    SelfRecord(Name + ' item messages', Messages <> '', 'empty');
  except
    SelfRecord(Name + ' item messages', False, GetExceptionMessage);
  end;
  try
    CheckDone := True;
    CheckRunning := False;
    CheckFor := 'S02';
    RenderCheckBody;
    SelfRecord(Name + ' S02 draw', True, '');
  except
    SelfRecord(Name + ' S02 draw', False, GetExceptionMessage);
  end;
end;

{ W14-D3: the checks after each page draw: the body panel and the verdict box have the page
  color (6.1 L1), the content ends above the page bottom (6.1 L8, no scrolling), and no button
  caption is wider than its button (6.1 L11). }
function SelfButtonsFit(var Bad: String): Boolean;
var
  I: Integer;
begin
  Result := True;
  for I := 0 to GetArrayLength(BodyButtons) - 1 do
    if WizardForm.CalculateButtonWidth([BodyButtons[I].Caption]) > BodyButtons[I].Width then
    begin
      Result := False;
      Bad := Bad + ' "' + BodyButtons[I].Caption + '"';
    end;
end;

procedure SelfFits(Name: String; Index: Integer);
var
  Bad: String;
  Ok: Boolean;
  Limit: Integer;
begin
  try
    { 6.1 L12: on S10 and S11 the status line takes the bottom of the page. }
    Limit := Bodies[Index].Height;
    if (Index = P_BACKUP) or (Index = P_READY) then
      Limit := StatusBandTop - ScaleY(12);
    Bad := '';
    Ok := SelfButtonsFit(Bad);
    if Bodies[Index].Color <> Pages[Index].SurfaceColor then
    begin
      Ok := False;
      Bad := Bad + ' panel color';
    end;
    if (LastVerdict <> nil) and (LastVerdict.Color <> Pages[Index].SurfaceColor) then
    begin
      Ok := False;
      Bad := Bad + ' verdict color';
    end;
    if CurY > Limit then
    begin
      Ok := False;
      Bad := Bad + ' content ' + IntToStr(CurY) + ' > ' + IntToStr(Limit);
    end;
    SelfRecord(Name + ' layout', Ok, Bad);
    SelfInfo(Name + ' height', 'content ends at ' + IntToStr(CurY) + ', limit ' + IntToStr(Limit));
  except
    SelfRecord(Name + ' layout', False, GetExceptionMessage);
  end;
end;

procedure SelfDraw(Name: String; Index: Integer);
begin
  try
    if Index = P_EMAIL then
    begin
      HideShow;
      LayoutMail;
      RenderMailStatus;
      ShowMailFailure('smtp_auth_refused');
      ShowMailFailure('smtp_unreachable');
      ShowMailFailure('smtp_recipient_refused');
    end
    else if Index = P_READY then RenderReady
    else if Index = P_INSTALL then RenderInstall
    else if Index = P_KEY then RenderKey
    else if Index = P_MAINT then RenderMaint
    else if Index = P_UPDATE then RenderUpdate
    else RenderFinishedPage;
    SelfRecord(Name, True, '');
    if (Index >= 0) and (Index <> P_EMAIL) then
      SelfFits(Name, Index);
  except
    SelfRecord(Name, False, GetExceptionMessage);
  end;
end;

{ W14-D3 (6.1 L11): Inno's button row with every caption the code sets: each button as wide as
  its caption, the row in order with no overlap. }
procedure SelfButtonRow;
var
  Captions: array of String;
  I: Integer;
  Ok: Boolean;
  Bad: String;
begin
  try
    SetArrayLength(Captions, 11);
    Captions[0] := CM('s09_next_test'); Captions[1] := CM('s05_next'); Captions[2] := CM('m05_next');
    Captions[3] := CM('btn_try_again'); Captions[4] := CM('s11_next'); Captions[5] := CM('s15_finish');
    Captions[6] := CM('btn_continue'); Captions[7] := CM('btn_done'); Captions[8] := CM('s01_next');
    Captions[9] := CM('btn_next'); Captions[10] := CM('btn_close');
    Ok := True;
    Bad := '';
    ExtraButton.Visible := True;
    SetExtraCaption(CM('s05_later'));
    for I := 0 to GetArrayLength(Captions) - 1 do
    begin
      SetNextCaption(Captions[I]);
      SetCancelCaption(CM('btn_close'));
      if (WizardForm.CalculateButtonWidth([Captions[I]]) > WizardForm.NextButton.Width)
        or (WizardForm.BackButton.Left + WizardForm.BackButton.Width > WizardForm.NextButton.Left)
        or (WizardForm.NextButton.Left + WizardForm.NextButton.Width > WizardForm.CancelButton.Left)
        or (ExtraButton.Left + ExtraButton.Width > WizardForm.BackButton.Left)
        or (WizardForm.CalculateButtonWidth([CM('s05_later')]) > ExtraButton.Width) then
      begin
        Ok := False;
        Bad := Bad + ' "' + Captions[I] + '"';
      end;
    end;
    ExtraButton.Visible := False;
    SetNextCaption(CM('btn_next'));
    SetCancelCaption(SetupMessage(msgButtonCancel));
    SelfRecord('W14-D3 the button row fits every caption', Ok, Bad);
  except
    SelfRecord('W14-D3 the button row fits every caption', False, GetExceptionMessage);
  end;
end;

{ W14-D3: the S13 form and the M03/M04 key form are built (not shown, the build is silent) and
  their buttons checked. }
procedure SelfForms;
var
  Form: TSetupForm;
  I: Integer;
  Ok: Boolean;
  Bad: String;
begin
  try
    Ok := True;
    Bad := '';
    SetArrayLength(FormButtons, 0);
    Form := BuildFailureForm(CM('s12_stage4'), FM1('s13_could_not', CM('s12_fail4')), True);
    try
      for I := 0 to GetArrayLength(FormButtons) - 1 do
        if Form.CalculateButtonWidth([FormButtons[I].Caption]) > FormButtons[I].Width then
        begin
          Ok := False;
          Bad := Bad + ' "' + FormButtons[I].Caption + '"';
        end;
    finally
      FailureStatus := nil;
      Form.Free;
    end;
    SetArrayLength(FormButtons, 0);
    KeyText := 'ABCD-EFGH-IJKL-MNOP-QRST-UVWX';
    Form := BuildKeyForm(CM('m04_first'), CM('s15_finish'));
    try
      for I := 0 to GetArrayLength(FormButtons) - 1 do
        if Form.CalculateButtonWidth([FormButtons[I].Caption]) > FormButtons[I].Width then
        begin
          Ok := False;
          Bad := Bad + ' "' + FormButtons[I].Caption + '"';
        end;
    finally
      KeyUsb := nil;
      KeyFormStatus := nil;
      Form.Free;
    end;
    SetArrayLength(FormButtons, 0);
    SelfRecord('W14-D3 the S13 form and the key form draw, buttons fit', Ok, Bad);
  except
    SelfRecord('W14-D3 the S13 form and the key form draw, buttons fit', False, GetExceptionMessage);
  end;
end;

{ W14-D3 (6.1 L9): S08 with More options open and an error under its field; S09 with "Continue
  later" under the form, inside the page. }
procedure SelfFormPages;
var
  Ok: Boolean;
  ErrorHeight: Integer;
begin
  try
    OrgMoreClick(nil, '', sltID);
    OrgError.Caption := CM('s08_err_email');
    OrgErrorAfter := OrgEmail;
    LayoutOrg;
    Ok := (not OrgMoreLink.Visible) and OrgUser.Visible and OrgError.Visible
      and (OrgError.Top > OrgEmail.Top) and (OrgError.Top < OrgUserLabel.Top)
      and (OrgNameLabel.Top >= OrgTop)
      and (OrgMoreHelp.Top + OrgMoreHelp.Height <= StatusBandTop - ScaleY(12));
    SelfRecord('W14-D3 S08 More options and the error under its field', Ok,
      'error at ' + IntToStr(OrgError.Top) + ', email at ' + IntToStr(OrgEmail.Top) + ', ends at '
      + IntToStr(OrgMoreHelp.Top + OrgMoreHelp.Height) + ', limit ' + IntToStr(StatusBandTop - ScaleY(12)));
    SelfInfo('S08 height', 'content ends at ' + IntToStr(OrgMoreHelp.Top + OrgMoreHelp.Height) + ', limit '
      + IntToStr(StatusBandTop - ScaleY(12)) + ', page ' + IntToStr(Pages[P_ORG].SurfaceHeight));
    OrgError.Caption := '';
    OrgErrorAfter := nil;
    LayoutOrg;
    { S09 as the owner fills it: Gmail, More options open, an error under the password, a
      status line. }
    MailGmail.Checked := True;
    MailMore := True;
    MailError.Caption := CM('s09_err_auth_gmail');
    MailErrorAfter := MailPassword;
    MailStatus.Caption := CM('s09_policy');
    LayoutMail;
    Ok := (MailLater.Top > MailSender.Top) and (MailLater.Top + MailLater.Height <= StatusBandTop - ScaleY(12))
      and (MailM365.Left >= MailGmail.Left + MailGmail.Width + ScaleX(16)) and (MailFromLabel.Top >= MailTop);
    SelfRecord('W14-D3 S09 rhythm, radios and Continue later', Ok,
      'later ends at ' + IntToStr(MailLater.Top + MailLater.Height) + ', limit ' + IntToStr(StatusBandTop - ScaleY(12)));
    SelfInfo('S09 Gmail height', 'content ends at ' + IntToStr(MailLater.Top + MailLater.Height) + ', limit '
      + IntToStr(StatusBandTop - ScaleY(12)) + ', page ' + IntToStr(Pages[P_EMAIL].SurfaceHeight));
    { The tallest state (parent decision, 2026-11-18): Other with every field, More options, an
      error under the password and the status line. Server and Port share a row, User name and
      Password share a row (6.1 rule 9, its only exception); it must end inside the page. }
    MailOther.Checked := True;
    MailError.Caption := CM('s09_err_auth');
    MailStatus.Caption := '';
    ShowStatusLine(FM4('bg_line', '3', '7', CM('step_bg_import'), '2:10'));
    LayoutMail;
    Ok := (MailLater.Top + MailLater.Height <= StatusBandTop - ScaleY(12))
      and (MailPort.Top = MailServer.Top) and (MailPassword.Top = MailUser.Top)
      and (MailPort.Left >= MailServer.Left + MailServer.Width + ScaleX(16))
      and (MailPassword.Left >= MailUser.Left + MailUser.Width + ScaleX(16))
      and MailSender.Visible and MailUser.Visible and MailPort.Visible and MailError.Visible
      and (MailError.Left = MailPassword.Left)
      and (MailShow.Top < MailPassword.Top) and (MailShow.Left + MailShow.Width <= MailPassword.Left + MailPassword.Width)
      and (MailPasswordLabel.Left + MailPasswordLabel.Width <= MailShow.Left);
    SelfRecord('W14-D3 S09 Other with every field fits above the status line', Ok,
      'Continue later ends at ' + IntToStr(MailLater.Top + MailLater.Height) + ', limit ' + IntToStr(StatusBandTop - ScaleY(12))
      + ', page ' + IntToStr(Pages[P_EMAIL].SurfaceHeight));
    SelfInfo('S09 Other height', 'content ends at ' + IntToStr(MailLater.Top + MailLater.Height) + ', limit '
      + IntToStr(StatusBandTop - ScaleY(12)) + ', page ' + IntToStr(Pages[P_EMAIL].SurfaceHeight));
    { TASK-0097 AC-4 (Designer B1): Other with the server error. Only the password's error goes
      to the password column; this one starts at the left edge under Server and Port, full
      width, and is as tall as its text needs at that width. }
    MailError.Caption := FM1('s09_err_unreachable', 'smtp.example.com');
    MailErrorAfter := MailServer;
    LayoutMail;
    ErrorHeight := MailError.Height;
    WizardForm.AdjustLabelHeight(MailError);
    Ok := MailError.Visible and (MailError.Left = 0) and (MailError.Width = MailFrom.Width)
      and (MailError.Top > MailServer.Top) and (MailError.Top < MailSecurityLabel.Top)
      and (MailError.Height = ErrorHeight) and (MailError.Top + MailError.Height <= MailSecurityLabel.Top)
      and (MailLater.Top + MailLater.Height <= StatusBandTop - ScaleY(12));
    SelfRecord('AC-4 S09 Other: the server error is under its field, full width', Ok,
      'left ' + IntToStr(MailError.Left) + ', width ' + IntToStr(MailError.Width) + ' of ' + IntToStr(MailFrom.Width)
      + ', height ' + IntToStr(ErrorHeight) + ' needs ' + IntToStr(MailError.Height) + ', top ' + IntToStr(MailError.Top)
      + ', next label ' + IntToStr(MailSecurityLabel.Top));
    MailErrorAfter := MailPassword;
    ShowStatusLine('');
    MailGmail.Checked := True;
    MailError.Caption := '';
    MailErrorAfter := nil;
    MailStatus.Caption := '';
    LayoutMail;
    { 6.1 L1: the status line takes the page color. }
    ShowStatusLine('x');
    SelfRecord('W14-D3 the status line has the page color', StatusLine.Color = Pages[P_ORG].SurfaceColor, 'color');
    ShowStatusLine('');
  except
    SelfRecord('W14-D3 S08 and S09 forms', False, GetExceptionMessage);
  end;
end;

{ W14-D3: the states of the pages that part 3 changed, each drawn and checked. }
procedure SelfPageStates;
begin
  { S03 }
  try
    CheckVerdict := 'not_suitable';
    Items[0].Cls := 'stop';
    RenderCheckBody;
    SelfRecord('S03', True, '');
    SelfFits('S03', P_CHECK);
  except
    SelfRecord('S03', False, GetExceptionMessage);
  end;
  { S05: working, ready to restart, failed (WSL), done without a restart }
  try
    PrepStartedAt := GetTickCount;
    PrepState := 'working';
    RenderRestart;
    SelfFits('S05 working', P_RESTART);
    PrepState := 'restart';
    PrepFeature := 'enabled_now';
    PrepWsl := 'present';
    PrepDetails := True;
    RenderRestart;
    SelfFits('S05 ready to restart', P_RESTART);
    { The longest step text (another administrator account). }
    ResumeCode := 'resume_other_user';
    RenderRestart;
    SelfFits('S05 ready to restart, other user', P_RESTART);
    ResumeCode := '';
    PrepState := 'failed';
    PrepFailKey := 'prepare.wsl.failed';
    RenderRestart;
    SelfFits('S05 failed', P_RESTART);
    PrepState := 'done';
    RenderRestart;
    SelfFits('S05 done', P_RESTART);
    PrepState := '';
    SelfRecord('S05 states', True, '');
  except
    SelfRecord('S05 states', False, GetExceptionMessage);
  end;
  { S06 }
  try
    CheckVerdict := 'ready';
    CheckRunning := False;
    CheckDone := True;
    SetArrayLength(Items, 0);
    EntryNext := 'S14';
    RenderWelcomeBack;
    SelfFits('S06', P_BACK);
    EntryNext := '';
    SelfRecord('S06', True, '');
  except
    SelfRecord('S06', False, GetExceptionMessage);
  end;
  { S10 }
  try
    DataRoot := 'C:\SlateOps';
    BackupError := FM1('s10_not_writable', 'E:');
    RenderBackup;
    SelfFits('S10', P_BACKUP);
    BackupError := '';
    SelfRecord('S10', True, '');
  except
    SelfRecord('S10', False, GetExceptionMessage);
  end;
  { S12 slow, and S13 in place with Choose another drive }
  try
    InstallStarted := True;
    InstallStep := 2;
    InstallStartedAt := GetTickCount;
    InstallSlow := True;
    RenderInstall;
    SelfFits('S12 slow', P_INSTALL);
    InstallSlow := False;
    InstallFailed := True;
    InstallBackupFailed := True;
    InstallFailStage := CM('s12_stage7');
    InstallFailText := FM1('s12_backup_failed', 'E:');
    RenderInstall;
    SelfFits('S13 with Choose another drive', P_INSTALL);
    InstallFailed := False;
    InstallBackupFailed := False;
    InstallStarted := False;
    SelfRecord('S12 slow and S13', True, '');
  except
    SelfRecord('S12 slow and S13', False, GetExceptionMessage);
  end;
end;



{ TASK-0097 AC-8 (Designer 9): every text that the status line shows fits on its one line (18 px
  high, so a second line is cut off): the background line with each step, the close flows and
  their notices. Each text is measured at the status line's own font with no wrapping; the time
  gets one more digit (10:00). One INFO line per text gives its width and the limit. }
procedure SelfLineFits(Key: String; Measure: TNewStaticText; Limit: Integer; var Ok: Boolean; var Bad: String);
var
  Text: String;
begin
  if Copy(Key, 1, 5) = 'step_' then
    Text := BgLineText(FM1(Key, 'D:\SlateOps'))
  else if (Key = 'later_save_failed') or (Key = 'later_restart_failed') or (Copy(Key, 1, 4) = 's07_') then
    Text := CM(Key)
  else
    Text := OneLine(4, 4, FM1(Key, 'D:\SlateOps\kept'), GetTickCount);
  Measure.Caption := Text + '0';
  SelfInfo('AC-8 status line ' + Key, 'width ' + IntToStr(Measure.Width) + ', limit ' + IntToStr(Limit));
  if Measure.Width > Limit then
  begin
    Ok := False;
    Bad := Bad + ' ' + Key + ' (' + IntToStr(Measure.Width) + ')';
  end;
end;

procedure SelfStatusLine;
var
  Measure: TNewStaticText;
  Bad: String;
  L: Integer;
  Ok: Boolean;
begin
  try
    ShowStatusLine('x');
    L := StatusLine.Width;
    ShowStatusLine('');
    Measure := TNewStaticText.Create(WizardForm);
    Measure.Parent := WizardForm;
    Measure.Visible := False;
    Measure.AutoSize := True;
    Measure.WordWrap := False;
    Measure.ShowAccelChar := False;
    BgIndex := 7;
    BgBeganAt := GetTickCount;
    Ok := True;
    Bad := '';
    SelfLineFits('step_data_unpack', Measure, L, Ok, Bad);
    SelfLineFits('step_data_folder', Measure, L, Ok, Bad);
    SelfLineFits('step_bg_service', Measure, L, Ok, Bad);
    SelfLineFits('step_bg_wslconfig', Measure, L, Ok, Bad);
    SelfLineFits('step_bg_import', Measure, L, Ok, Bad);
    SelfLineFits('step_bg_restore_kept', Measure, L, Ok, Bad);
    SelfLineFits('step_bg_import_kept', Measure, L, Ok, Bad);
    SelfLineFits('step_bg_start', Measure, L, Ok, Bad);
    SelfLineFits('step_bg_kept_status', Measure, L, Ok, Bad);
    SelfLineFits('step_receive_space', Measure, L, Ok, Bad);
    SelfLineFits('step_receive_stage', Measure, L, Ok, Bad);
    SelfLineFits('step_receive_signature', Measure, L, Ok, Bad);
    SelfLineFits('step_receive_check', Measure, L, Ok, Bad);
    SelfLineFits('step_receive_load', Measure, L, Ok, Bad);
    SelfLineFits('step_receive_keep', Measure, L, Ok, Bad);
    SelfLineFits('step_prepare_systemd', Measure, L, Ok, Bad);
    SelfLineFits('step_prepare_docker', Measure, L, Ok, Bad);
    SelfLineFits('step_prepare_container', Measure, L, Ok, Bad);
    SelfLineFits('step_prepare_networking', Measure, L, Ok, Bad);
    SelfLineFits('step_prepare_time', Measure, L, Ok, Bad);
    SelfLineFits('step_prepare_listeners', Measure, L, Ok, Bad);
    SelfLineFits('step_prepare_interop', Measure, L, Ok, Bad);
    SelfLineFits('step_prepare_mounts', Measure, L, Ok, Bad);
    SelfLineFits('step_prepare_shells', Measure, L, Ok, Bad);
    SelfLineFits('step_prepare_bundle', Measure, L, Ok, Bad);
    SelfLineFits('step_prefetch_start_pull', Measure, L, Ok, Bad);
    SelfLineFits('later_waiting', Measure, L, Ok, Bad);
    SelfLineFits('later_discarding', Measure, L, Ok, Bad);
    SelfLineFits('later_saving', Measure, L, Ok, Bad);
    SelfLineFits('later_restarting', Measure, L, Ok, Bad);
    SelfLineFits('cancel_closing', Measure, L, Ok, Bad);
    SelfLineFits('remove_stopping', Measure, L, Ok, Bad);
    SelfLineFits('remove_data', Measure, L, Ok, Bad);
    SelfLineFits('remove_moving_kept', Measure, L, Ok, Bad);
    SelfLineFits('remove_windows', Measure, L, Ok, Bad);
    SelfLineFits('later_save_failed', Measure, L, Ok, Bad);
    SelfLineFits('later_restart_failed', Measure, L, Ok, Bad);
    SelfLineFits('s07_prep_failed', Measure, L, Ok, Bad);
    SelfLineFits('s07_prepared', Measure, L, Ok, Bad);
    BgIndex := 0;
    BgBeganAt := 0;
    Measure.Free;
    SelfRecord('AC-8 every status line text fits on one line', Ok, 'wider than ' + IntToStr(L) + ':' + Bad);
  except
    SelfRecord('AC-8 every status line text fits on one line', False, GetExceptionMessage);
  end;
end;

{ TASK-0097 AC-6 (Designer 1 to 3): S05 says what setup did. The verdict and the subtitle come
  from the helper's codes (before the work: from the C26 values); a WSL already on the PC shows
  its own version; the state with no restart has no restart stage and stands at Your details.
  The owner's check result: Virtual Machine Platform off, WSL 3.0.5.0 present. }
procedure SelfS05;
var
  Stages, Saved: String;
  Count, I: Integer;
begin
  try
    ParseCheck(ReadText(ExpandConstant('{tmp}\check-owner.json')));
    SelfRecord('AC-6 S05 verdict enabled_now installed', S05VerdictKey('enabled_now', 'installed') = 's05_done', S05VerdictKey('enabled_now', 'installed'));
    SelfRecord('AC-6 S05 verdict enabled_now present', S05VerdictKey('enabled_now', 'present') = 's05_done_vmp', S05VerdictKey('enabled_now', 'present'));
    SelfRecord('AC-6 S05 verdict enabled installed', (S05VerdictKey('enabled', 'installed') = 's05_done_wsl') and (S05VerdictKey('pending', 'installed') = 's05_done_wsl'),
      S05VerdictKey('enabled', 'installed') + ', ' + S05VerdictKey('pending', 'installed'));
    SelfRecord('AC-6 S05 verdict pending present', S05VerdictKey('pending', 'present') = 's05_done_pending', S05VerdictKey('pending', 'present'));
    PrepFeature := '';
    PrepWsl := '';
    SelfRecord('AC-6 S05 subtitle before the work', S05SubtitleKey = 's05_subtitle_vmp', S05SubtitleKey);
    PrepFeature := 'enabled';
    PrepWsl := 'installed';
    Saved := S05SubtitleKey;
    PrepFeature := 'enabled_now';
    PrepWsl := 'installed';
    SelfRecord('AC-6 S05 subtitle after the work', (Saved = 's05_subtitle_wsl') and (S05SubtitleKey = 's05_subtitle'), Saved + ', ' + S05SubtitleKey);
    PrepFeature := 'enabled';
    PrepWsl := 'present';
    SelfRecord('AC-6 S05 subtitle with no restart', S05SubtitleKey = 's05_subtitle_ready', S05SubtitleKey);
    Saved := WslVersion;
    WslVersion := '2.6.1.0';
    PrepFeature := '';
    PrepWsl := '';
    Stages := S05WslVersion;
    PrepWsl := 'present';
    SelfRecord('AC-6 S05 installed WSL version', (Stages = '3.0.5.0') and (S05WslVersion = '3.0.5.0'), Stages + ', ' + S05WslVersion);
    WslVersion := Saved;
    PrepState := 'done';
    PrepFeature := 'enabled';
    PrepWsl := 'present';
    RenderRestart;
    Stages := S05NoRestartStages;
    Count := 1;
    for I := 1 to Length(Stages) do
      if Stages[I] = '|' then
        Count := Count + 1;
    SelfRecord('AC-6 S05 no restart: 4 stages, at 3', (Count = 4) and (WaitDrawn = 3) and (Pos(CM('s05_stage_restart'), Stages) = 0),
      IntToStr(Count) + ' stages, at ' + IntToStr(WaitDrawn));
    SelfFits('AC-6 S05 no restart', P_RESTART);
  except
    SelfRecord('AC-6 S05', False, GetExceptionMessage);
  end;
  PrepState := '';
  PrepFeature := '';
  PrepWsl := '';
  { The draws after this one ran with the state that the S06 block left. }
  SetArrayLength(Items, 0);
  CheckVerdict := 'ready';
end;

{ W14-D7 (closed; the part-1 reset is reverted): S07 on the owner's three fixed drives (C: 28 GB,
  D: 239 GB, E: 896 GB, in that order). The first entry, with no folder chosen, selects the
  largest drive (E:). A drive that the person chose (D:) stays when the list loads again after
  Back and Next. }
procedure SelfDrives;
var
  Text: String;
begin
  try
    Text := '{"code":"listed","message_key":"setup.drives.listed","values":{"drives":[' +
      '{"letter":"C:","drive_type":"Fixed","file_system":"NTFS","free_bytes":30064771072,"compressed":false,"encrypted":false},' +
      '{"letter":"D:","drive_type":"Fixed","file_system":"NTFS","free_bytes":256624295936,"compressed":false,"encrypted":false},' +
      '{"letter":"E:","drive_type":"Fixed","file_system":"NTFS","free_bytes":962072674304,"compressed":false,"encrypted":false}]}}';
    DataRoot := '';
    DataPrepared := False;
    DataStarted := False;
    LoadDataDrives(Text);
    RenderData;
    SelfRecord('S07 first entry selects the largest drive', (DataRoot = 'E:\SlateOps') and (GetArrayLength(DriveRadios) = 3)
      and (DriveLetters[0] = 'E:') and DriveRadios[0].Checked and (not DriveRadios[1].Checked) and (not DriveRadios[2].Checked),
      'selected ' + DataRoot + ', first ' + DriveLetters[0]);
    DriveRadioClick(DriveRadios[1]);
    LoadDataDrives(Text);
    RenderData;
    SelfRecord('S07 a chosen drive stays after Back and Next', (DataRoot = 'D:\SlateOps') and (not DriveRadios[0].Checked)
      and DriveRadios[1].Checked and (not DriveRadios[2].Checked),
      'selected ' + DataRoot);
  except
    SelfRecord('S07 drives', False, GetExceptionMessage);
  end;
end;

{ W14-D8: the background loop after the service step, with the owner's exec-result.json
  (rc.22, run install-20261118T032936Z-56cnu3) in svc-out: step 1 (wslconfig) must be collected
  and step 2 must start. PollJob and PollBackground run as the timer runs them. }
procedure SelfPoll;
var
  Start: Cardinal;
  Created: Boolean;
begin
  Created := not DirExists(ExpandConstant('{commonappdata}\SlateOps'));
  try
    try
      ExtractTemporaryFiles('{tmp}\scripts\*.ps1');
      ExtractTemporaryFiles('{tmp}\scripts\lib\*.ps1');
      HelperScript := ExpandConstant('{tmp}\scripts\setup-helper.ps1');
      ForceDirectories(ExpandConstant('{commonappdata}\SlateOps\svc-out'));
      SaveStringToFile(ExecResultFile, '{"stdout_file":"","job_class":"windows","message_key":"exec.wslconfig.written","job":"wslconfig","pipe_closed":false,"stdout_bytes":0,"stdout_sha256":"","finished_at":"2026-11-18T03:31:41Z","code":"written","exit_code":0,"request_id":"b6b02c87-f769-41b1-8c56-4aabfdc2dd94"}', False);
      SetArrayLength(Items, 0);
      KeptState := '';
      DataPrepared := True;
      BgFailed := False;
      BgIndex := 1;
      JobName := 'wslconfig';
      JobPurpose := 'bg';
      JobRequestId := 'b6b02c87-f769-41b1-8c56-4aabfdc2dd94';
      JobResultOut := '';
      JobPipeOut := False;
      JobStartedAt := GetTickCount;
      JobLimitMs := 15 * 60000;
      JobPollAt := GetTickCount;
      JobState := JOB_WAIT;
      Start := GetTickCount;
      while (BgIndex < 2) and (not BgFailed) and (Elapsed(Start) < 90000) do
      begin
        PollJob;
        PollBackground;
        Sleep(500);
      end;
      SelfRecord('W14-D8 background step 1 collected, step 2 started', BgIndex >= 2,
        'step ' + IntToStr(BgIndex) + ', job state ' + IntToStr(JobState) + ', code ' + JobCode + ', failed ' + BgCode);
    except
      SelfRecord('W14-D8 background step 1 collected, step 2 started', False, GetExceptionMessage);
    end;
  finally
    JobState := JOB_IDLE;
    DataPrepared := False;
    if Created then
      DelTree(ExpandConstant('{commonappdata}\SlateOps'), True, True, True);
  end;
end;

{ W14-D9: "Continue later" runs from the timer. Each call of PollCloseFlow returns at once (no
  call holds the window for 2 s), and the flow ends within its limits. }
procedure SelfCloseFlow;
var
  Start, Call, Longest: Cardinal;
  Created: Boolean;
begin
  Created := not DirExists(ExpandConstant('{commonappdata}\SlateOps'));
  try
    try
      JobState := JOB_IDLE;
      DataPrepared := True;
      StartCloseFlow('later', 'none');
      Start := GetTickCount;
      Longest := 0;
      while CloseFlowRunning and (Elapsed(Start) < 180000) do
      begin
        Call := GetTickCount;
        PollJob;
        PollCloseFlow;
        if Elapsed(Call) > Longest then
          Longest := Elapsed(Call);
        Sleep(200);
      end;
      SelfRecord('W14-D9 continue later never holds the window', (not CloseFlowRunning) and (Longest < 2000),
        'running ' + IntToStr(Ord(CloseFlowRunning)) + ', longest call ' + IntToStr(Longest) + ' ms');
    except
      SelfRecord('W14-D9 continue later never holds the window', False, GetExceptionMessage);
    end;
  finally
    JobState := JOB_IDLE;
    DataPrepared := False;
    if Created then
      DelTree(ExpandConstant('{commonappdata}\SlateOps'), True, True, True);
  end;
end;

{ W14-D5: the progress-line reader takes only the engine's line shape (and digits in the
  helper's keys); every other standard error line is ignored. }
procedure SelfProgressLines;
var
  J, K, S: String;
  N, T: Integer;
  Ok: Boolean;
begin
  try
    Ok := ParseProgressLine('progress install 8/13 provision start', False, J, K, S, N, T);
    Ok := Ok and (J = 'install') and (K = 'provision') and (N = 8) and (T = 13) and (S = 'start');
    Ok := Ok and ParseProgressLine('progress smtp-test 1/2 send done', False, J, K, S, N, T);
    Ok := Ok and (J = 'smtp-test') and (K = 'send') and (S = 'done');
    Ok := Ok and ParseProgressLine('progress check 12/30 c12 start', True, J, K, S, N, T);
    Ok := Ok and (K = 'c12') and (N = 12) and (T = 30);
    Ok := Ok and not ParseProgressLine('progress check 12/30 c12 start', False, J, K, S, N, T);
    Ok := Ok and not ParseProgressLine('progress install 8/13  provision start', False, J, K, S, N, T);
    Ok := Ok and not ParseProgressLine('progress install 8/13 provision started', False, J, K, S, N, T);
    Ok := Ok and not ParseProgressLine('progress Install 8/13 provision start', False, J, K, S, N, T);
    Ok := Ok and not ParseProgressLine('progress install 8 provision start', False, J, K, S, N, T);
    Ok := Ok and not ParseProgressLine('progress install 8/13 provision start extra', False, J, K, S, N, T);
    Ok := Ok and not ParseProgressLine('Traceback (most recent call last):', False, J, K, S, N, T);
    SelfRecord('W14-D5 progress lines', Ok, J + ' ' + K + ' ' + S);
  except
    SelfRecord('W14-D5 progress lines', False, GetExceptionMessage);
  end;
end;

{ W14-D5: S12 shows the step that the install job's standard error names: the last complete
  progress line counts; other lines and a line still being written do not. }
procedure SelfEngineStep;
var
  Created: Boolean;
begin
  Created := not DirExists(ExpandConstant('{commonappdata}\SlateOps'));
  try
    try
      ForceDirectories(ExpandConstant('{commonappdata}\SlateOps\svc-out'));
      JobRequestId := '5d0c9a1e-2b7f-4c3a-8e61-0f2a9b3c4d5e';
      SaveStringToFile(JobErrFile, 'progress install 1/13 release start' + #10 + 'progress install 2/13 folders done' + #10 +
        'Traceback (most recent call last):' + #10 + 'progress install 8/13 provision start' + #13#10 + 'progress install 9/13 api st', False);
      InstallStarted := True;
      InstallDone := False;
      InstallFailed := False;
      InstallStep := 2;
      InstallStartedAt := GetTickCount;
      JobPurpose := 'install';
      JobState := JOB_WAIT;
      JobStepJob := '';
      JobStepKey := '';
      ReadJobProgress;
      RenderInstall;
      SelfRecord('W14-D5 S12 shows the engine step', (WaitNow <> nil) and (WaitNow.Caption = 'Now: Setting up the database.')
        and (WaitDrawn = 4) and (WaitTime <> nil) and (Pos('Time so far: 0:0', WaitTime.Caption) = 1),
        'key ' + JobStepKey + ', stage ' + IntToStr(WaitDrawn));
    except
      SelfRecord('W14-D5 S12 shows the engine step', False, GetExceptionMessage);
    end;
  finally
    JobState := JOB_IDLE;
    JobPurpose := '';
    InstallStarted := False;
    DeleteFile(JobErrFile);
    if Created then
      DelTree(ExpandConstant('{commonappdata}\SlateOps'), True, True, True);
  end;
end;

{ W14-D5: S02 names the check that the helper reports (its progress file beside the result). }
procedure SelfCheckStep;
begin
  try
    CheckOut := ExpandConstant('{tmp}\selftest-check.json');
    DeleteFile(CheckOut);
    SaveStringToFile(ProgressFileOf(CheckOut), 'progress check 11/30 c11 start' + #10 + 'progress check 12/30 c12 start' + #10, False);
    CheckRunning := True;
    CheckDone := False;
    CheckVerdict := '';
    CheckStartedAt := GetTickCount;
    RenderCheckBody;
    SelfRecord('W14-D5 S02 names the check that runs', (WaitNow <> nil) and (WaitNow.Caption = 'Checking: Internet (12 of 30).')
      and (WaitDrawn = 3), 'stage ' + IntToStr(WaitDrawn));
  except
    SelfRecord('W14-D5 S02 names the check that runs', False, GetExceptionMessage);
  end;
  CheckRunning := False;
  CheckDone := True;
end;

{ W14-D5: the timer changes the labels of the page only; a redraw frees them, and the next tick
  must not touch the freed ones. }
procedure SelfWaitRedraw;
begin
  try
    InstallStarted := True;
    InstallStep := 3;
    InstallStartedAt := GetTickCount;
    RenderInstall;
    RefreshWaitLabels;
    BeginBody(P_INSTALL);
    RefreshWaitLabels;
    RenderInstall;
    RefreshWaitLabels;
    SelfRecord('W14-D5 a redraw leaves no freed label to the timer', (WaitTime <> nil) and (WaitDrawn = 8), 'stage ' + IntToStr(WaitDrawn));
  except
    SelfRecord('W14-D5 a redraw leaves no freed label to the timer', False, GetExceptionMessage);
  end;
  InstallStarted := False;
end;

{ W14-D9: a helper step runs from the timer; no call holds the window for 2 s. account-sid only
  reads the state record. }
procedure SelfStepRunner;
var
  Start, Call, Longest: Cardinal;
begin
  try
    StepLastCode := '';
    RunStep('account-sid', '', 'selftest', 'self-test', 0, 0, 60000);
    Start := GetTickCount;
    Longest := 0;
    while StepRunning and (Elapsed(Start) < 90000) do
    begin
      Call := GetTickCount;
      PollStep;
      if Elapsed(Call) > Longest then
        Longest := Elapsed(Call);
      Sleep(200);
    end;
    SelfRecord('W14-D9 a helper step runs from the timer', (not StepRunning) and (Longest < 2000)
      and ((StepLastCode = 'found') or (StepLastCode = 'missing')),
      'code ' + StepLastCode + ', longest call ' + IntToStr(Longest) + ' ms');
  except
    SelfRecord('W14-D9 a helper step runs from the timer', False, GetExceptionMessage);
  end;
end;

{ W14-D9: Save report runs from the timer and ends with its line; no call holds the window. }
procedure SelfReport;
var
  Start, Call, Longest: Cardinal;
begin
  try
    ServiceSid := '';
    ReportLine := '';
    SaveReport(nil);
    Start := GetTickCount;
    Longest := 0;
    while (ReportPhase <> '') and (Elapsed(Start) < 300000) do
    begin
      Call := GetTickCount;
      PollReport;
      if Elapsed(Call) > Longest then
        Longest := Elapsed(Call);
      Sleep(200);
    end;
    SelfRecord('W14-D9 Save report never holds the window', (ReportPhase = '') and (Longest < 2000) and (ReportLine <> ''),
      'phase ' + ReportPhase + ', longest call ' + IntToStr(Longest) + ' ms, line ' + ReportLine);
    if ReportPath <> '' then
      DeleteFile(ReportPath);
  except
    SelfRecord('W14-D9 Save report never holds the window', False, GetExceptionMessage);
  end;
end;

procedure RunSelfTest;
var
  Text, OutFile: String;
begin
  SelfLog := '';
  try
    Text := FM1('s02_needs', '2');
    SelfRecord('FM1', Pos('2', Text) > 0, Text);
  except
    SelfRecord('FM1', False, GetExceptionMessage);
  end;
  try
    Text := FM2('m01_subtitle', '0.2.0', 'https://office-pc.local');
    SelfRecord('FM2', (Pos('0.2.0', Text) > 0) and (Pos('office-pc.local', Text) > 0), Text);
  except
    SelfRecord('FM2', False, GetExceptionMessage);
  end;
  try
    Text := FM3('s07_kept', 'Riverside Learning Center', '0.2.0', '12 November 2026');
    SelfRecord('FM3', (Pos('Riverside', Text) > 0) and (Pos('12 November 2026', Text) > 0), Text);
  except
    SelfRecord('FM3', False, GetExceptionMessage);
  end;
#ifdef SelfTestRed
  try
    Text := OpenArrayFM('s02_needs', ['2']);
    SelfRecord('open-array', True, '');
  except
    SelfRecord('open-array', False, GetExceptionMessage);
  end;
#endif

  { S02 on the owner's check result (rc.20, C04 the only Fix row) and on a ready result. }
  SelfCheck('owner', 'check-owner.json', 'needs_fixes', 1);
  SelfCheck('ready', 'check-ready.json', 'ready', 0);

  { W14-D8 and W14-D9. }
  SelfPoll;
  SelfCloseFlow;

  { W14-D5 and W14-D9 (part 2). SelfPoll put the helper in place. }
  SelfProgressLines;
  SelfEngineStep;
  SelfCheckStep;
  SelfWaitRedraw;
  SelfStepRunner;
  SelfReport;

  { S07 (W14-D7). }
  SelfDrives;
  SelfFits('S07', P_DATA);

  { W14-D3: the button row, the forms and the page states of part 3. }
  SelfButtonRow;
  SelfForms;
  SelfFormPages;
  SelfCheck('owner layout', 'check-owner.json', 'needs_fixes', 1);
  SelfFits('S02 owner', P_CHECK);
  SelfCheck('ready layout', 'check-ready.json', 'ready', 0);
  SelfFits('S02 ready', P_CHECK);
  SelfPageStates;
  SelfS05;
  SelfStatusLine;

  { Sample state for the other pages. }
  OrgName.Text := 'Riverside Learning Center';
  OrgEmail.Text := 'maria@example.com';
  OrgUser.Text := 'maria';
  MailFrom.Text := 'office@example.com';
  MailGmail.Checked := True;
  BackupDrive := 'E:';
  DataRoot := 'D:\SlateOps';
  SecurityCode := '3F:A2:00:9C';
  SelfDraw('S09', P_EMAIL);
  SelfDraw('S11', P_READY);
  KeptState := 'kept';
  KeptUse := True;
  KeptName := 'Riverside Learning Center';
  SelfDraw('S11 kept', P_READY);
  KeptState := '';
  InstallStep := 3;
  SelfDraw('S12', P_INSTALL);
  InstallFailed := True;
  InstallFailStage := CM('s12_stage5');
  InstallFailText := FM1('s13_could_not', CM('s12_fail5'));
  SelfDraw('S12 failed', P_INSTALL);
  InstallFailed := False;
  KeyText := 'ABCD-EFGH-IJKL-MNOP-QRST-UVWX';
  KeyState := 'shown';
  SelfDraw('S14', P_KEY);
  SelfDraw('S15', -1);
  { 6.1 L8: the last S15 line ends inside the finished page. }
  try
    SelfRecord('S15 layout', S15Steps[4].Top + S15Steps[4].Height <= WizardForm.FinishedPage.Height,
      IntToStr(S15Steps[4].Top + S15Steps[4].Height) + ' > ' + IntToStr(WizardForm.FinishedPage.Height));
  except
    SelfRecord('S15 layout', False, GetExceptionMessage);
  end;
  MaintStatus := 'ok';
  MaintState := 'installed';
  MaintBackup := 'ok';
  SelfDraw('M01', P_MAINT);
  MaintBackup := 'backup_target_missing';
  MaintBackupFolder := 'E:\SlateOps-backups';
  SelfDraw('M01 backup drive missing', P_MAINT);
  MaintNetwork := True;
  SelfDraw('M01 network changed', P_MAINT);
  { TASK-0097 AC-5 (Designer B2): Repair running in the tallest M01 state (the backup drive
    sentence): its full form in place of the actions, inside the page (SelfFits, FAIL level). }
  MaintNetwork := False;
  StepFor := 'repair';
  StepOut := '';
  StepAt := GetTickCount;
  SelfDraw('AC-5 M01 Repair running', P_MAINT);
  StepFor := '';
  InstalledVersion := '0.1.0-rc.20';
  UpdPhase := '';
  SelfDraw('M05', P_UPDATE);
  UpdPhase := 'idle';
  SelfDraw('M05 running', P_UPDATE);
  UpdPhase := '';
  UpdFailed := True;
  UpdRetry := True;
  UpdFailStage := CM('m05_stage4');
  UpdFailText := FM1('m05_rolled_back', InstalledVersion);
  SelfDraw('M05 rolled back', P_UPDATE);

  SelfLog := SelfLog + 'DONE' + #13#10;
  OutFile := ExpandConstant('{param:SelfTestOut|}');
  if OutFile = '' then
    OutFile := ExpandConstant('{src}\selftest-result.txt');
  SaveStringToFile(OutFile, AnsiString(SelfLog), False);
  Log(SelfLog);
end;
