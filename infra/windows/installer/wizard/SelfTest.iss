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

{ W14-D7: S07 on the owner's three fixed drives (C: 28 GB, D: 239 GB, E: 896 GB, in that
  order); C: was selected before. The selected radio must be the C07 drive (E:), and the first
  (largest) drive when the check named none. }
procedure SelfDrives(Name: String; WithC07: Boolean);
var
  Text: String;
begin
  try
    if not WithC07 then
      SetArrayLength(Items, 0);
    Text := '{"code":"listed","message_key":"setup.drives.listed","values":{"drives":[' +
      '{"letter":"C:","drive_type":"Fixed","file_system":"NTFS","free_bytes":30064771072,"compressed":false,"encrypted":false},' +
      '{"letter":"D:","drive_type":"Fixed","file_system":"NTFS","free_bytes":256624295936,"compressed":false,"encrypted":false},' +
      '{"letter":"E:","drive_type":"Fixed","file_system":"NTFS","free_bytes":962072674304,"compressed":false,"encrypted":false}]}}';
    DataRoot := 'C:\SlateOps';
    DataPrepared := False;
    DataStarted := False;
    LoadDataDrives(Text);
    RenderData;
    SelfRecord(Name, (DataRoot = 'E:\SlateOps') and (GetArrayLength(DriveRadios) = 3) and (DriveLetters[0] = 'E:')
      and DriveRadios[0].Checked and (not DriveRadios[1].Checked) and (not DriveRadios[2].Checked),
      'selected ' + DataRoot + ', first ' + DriveLetters[0]);
  except
    SelfRecord(Name, False, GetExceptionMessage);
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

  { S07 (W14-D7): the C07 drive of the ready fixture is E:. }
  SelfDrives('S07 drive named by C07', True);
  SelfDrives('S07 largest drive without C07', False);

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
