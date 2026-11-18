{ SelfTest.iss - the [Code] self-test (W14-D1, TASK-0097). Compiled only with /DSelfTest; the
  windows-installer workflow runs the result with /VERYSILENT /SELFTESTOUT=<file>. It runs the
  message helpers, the check reader and the S02 draw on the owner's check result (fixture), and
  the draw routines of S09, S11, S12, S14, S15, M01 and M05 with sample state, so that a runtime
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
  except
    SelfRecord(Name, False, GetExceptionMessage);
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
  MaintStatus := 'ok';
  MaintState := 'installed';
  MaintBackup := 'ok';
  SelfDraw('M01', P_MAINT);
  MaintBackup := 'backup_target_missing';
  MaintBackupFolder := 'E:\SlateOps-backups';
  SelfDraw('M01 backup drive missing', P_MAINT);
  MaintNetwork := True;
  SelfDraw('M01 network changed', P_MAINT);
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
