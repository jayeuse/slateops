<#
exec-path.ps1 - the real Windows job path of setup, end to end (TASK-0097, W14-D8).

What setup does, with the real parts: setup-helper.ps1 from a helper root shaped like Inno's
{tmp}, the state tree C:\ProgramData\SlateOps, the data folder <system drive>\SlateOps, the real
account slateops-svc and the real task \SlateOps\Exec. Each wslconfig job is submitted with the
helper's "job" action and collected the way the wizard's PollJob does: a plain read of
svc-out\exec-result.json each second, and the "job-result" helper when the read sees the request
ID or every 15 s. The wslconfig job never starts wsl.exe (lib/Exec.ps1 Invoke-WindowsJob), so no
stand-in for it is needed; exec.ps1 always uses System32\wsl.exe and takes no path.

Sequence: job 1 (the D8 step, first Exec job after the account), job 2 left uncollected (its
request and result stay, as on the owner's PC after rc.22), prepare-data again (the rc.24
resume), job 3, then job 4 at once after job 3 (the background chain submits its next job in the
same tick).

It creates a real local account and changes C:\ProgramData, so it runs only on a GitHub Actions
Windows runner, as an administrator, on a PC with no Slate Operations parts. It is not a
*.Tests.ps1 file, so run-tests.ps1 never runs it. No password is printed or stored: the helper's
service step makes its own random one.

  powershell.exe -NoProfile -ExecutionPolicy Bypass -File exec-path.ps1

Exit code 0 when every step passes, 1 otherwise. Windows PowerShell 5.1, ASCII only.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# Before anything else: this script creates a real account and changes C:\ProgramData.
if (($env:GITHUB_ACTIONS -ne 'true') -or (-not $env:RUNNER_TEMP)) {
    Write-Host 'FAIL  exec-path.ps1 runs only on a GitHub Actions Windows runner: it creates the real account slateops-svc.'
    exit 1
}

$script:Clock = [System.Diagnostics.Stopwatch]::StartNew()
$script:Failed = 0
$script:Results = New-Object System.Collections.Generic.List[string]
$script:OutSeq = 0
# Set once the preconditions pass: the cleanup removes only what this run created.
$script:Owned = $false

$sourceScripts = Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts'
$powershell = Join-Path ([Environment]::SystemDirectory) 'WindowsPowerShell\v1.0\powershell.exe'
$stateRoot = Join-Path ([Environment]::GetFolderPath('CommonApplicationData')) 'SlateOps'
$dataRoot = '{0}\SlateOps' -f $env:SystemDrive
$resultFile = Join-Path $stateRoot 'svc-out\exec-result.json'
$requestFile = Join-Path $stateRoot 'requests\request.json'
$setupLogDir = Join-Path $stateRoot 'logs\setup'
$execLogDir = Join-Path $stateRoot 'logs\exec'
$runId = 'install-{0}-ciexec' -f ([DateTime]::UtcNow.ToString("yyyyMMdd'T'HHmmss'Z'"))
$helperRoot = Join-Path $env:RUNNER_TEMP 'is-execpath.tmp'
$helperScript = Join-Path $helperRoot 'scripts\setup-helper.ps1'
$version = '0.0.0'

# The wizard's limits (Wizard.iss SUBMIT_LIMIT_MS, JOB_ASK_MS, JOB_ANSWER_MS).
$submitLimitMs = 120000
$askEveryMs = 15000
$answerLimitMs = 120000
# Each job here must be collected in this time; the wizard's own limit is 15 min.
$collectLimitMs = 300000

function Write-Line {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text)
    Write-Host ('[{0,6:N1}s] {1}' -f ($script:Clock.Elapsed.TotalSeconds), $Text)
}

function New-OutFile {
    param([Parameter(Mandatory = $true)][string]$Name)
    $script:OutSeq++
    return (Join-Path $helperRoot ('{0}-{1}.json' -f $Name, $script:OutSeq))
}

function Start-Helper {
    # Wizard.iss HelperParams and StartHelper: the same command line, hidden, no wait.
    param([Parameter(Mandatory = $true)][string]$Action, [Parameter(Mandatory = $true)][string]$OutFile, [string]$Extra = '')
    foreach ($path in @($OutFile, ($OutFile + '.progress'))) { if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force } }
    $arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}" -Action {1} -RunId {2} -OutFile "{3}"' -f $helperScript, $Action, $runId, $OutFile
    if ($Extra) { $arguments = $arguments + ' ' + $Extra }
    return (Start-Process -FilePath $powershell -ArgumentList $arguments -WindowStyle Hidden -PassThru)
}

function Read-ResultCode {
    # Wizard.iss ReadResultCode: the first "code" in the file; '' while there is none.
    param([Parameter(Mandatory = $true)][string]$OutFile)
    if (-not (Test-Path -LiteralPath $OutFile -PathType Leaf)) { return '' }
    try { $text = [System.IO.File]::ReadAllText($OutFile) } catch { return '' }
    $match = [regex]::Match($text, '"code":"([^"]*)"')
    if ($match.Success) { return $match.Groups[1].Value }
    return ''
}

function Invoke-HelperAndWait {
    # Wizard.iss RunHelper: start, wait (with a limit here), read the code.
    param([Parameter(Mandatory = $true)][string]$Action, [string]$Extra = '', [int]$LimitSeconds = 600)
    $out = New-OutFile $Action
    $process = Start-Helper -Action $Action -OutFile $out -Extra $Extra
    if (-not $process.WaitForExit($LimitSeconds * 1000)) { throw ('helper {0} gave no answer in {1} s' -f $Action, $LimitSeconds) }
    $text = ''
    if (Test-Path -LiteralPath $out -PathType Leaf) { $text = [System.IO.File]::ReadAllText($out) }
    Write-Line ('helper {0}: exit code {1}, result {2}' -f $Action, $process.ExitCode, $text)
    return @{ code = (Read-ResultCode $out); text = $text }
}

function Read-AsWizard {
    # The wizard's own read of the result file (LoadStringFromFile in the elevated setup
    # process): read access only, others may only read too.
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return @{ ok = $false; exists = $false; text = ''; error = 'absent' } }
    try {
        $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read)
        try {
            $bytes = New-Object byte[] $stream.Length
            $read = 0
            while ($read -lt $bytes.Length) {
                $count = $stream.Read($bytes, $read, $bytes.Length - $read)
                if ($count -le 0) { break }
                $read += $count
            }
        } finally { $stream.Dispose() }
        return @{ ok = $true; exists = $true; text = [System.Text.Encoding]::UTF8.GetString($bytes, 0, $read); error = '' }
    } catch {
        return @{ ok = $false; exists = $true; text = ''; error = ('{0}: {1}' -f $_.Exception.GetType().Name, $_.Exception.Message) }
    }
}

function Test-ResultNames {
    param([Parameter(Mandatory = $true)][hashtable]$Read, [Parameter(Mandatory = $true)][string]$RequestId)
    return ($Read.ok -and ($Read.text.ToLowerInvariant().Contains(('"request_id":"{0}"' -f $RequestId.ToLowerInvariant()))))
}

function Get-JobResultStartCount {
    # Lines of job-result helper runs in the state tree's setup log, where the owner's Save
    # report reads them.
    $log = Join-Path $setupLogDir ('{0}.log' -f $runId)
    if (-not (Test-Path -LiteralPath $log -PathType Leaf)) { return 0 }
    return @(Get-Content -LiteralPath $log | Where-Object { $_ -like '* helper.job-result INFO start*' }).Count
}

function Show-Tail {
    param([Parameter(Mandatory = $true)][string]$Path, [int]$Lines = 80)
    try {
        if (Test-Path -LiteralPath $Path -PathType Leaf) {
            Write-Host ('----- {0} (last {1} lines)' -f $Path, $Lines)
            Get-Content -LiteralPath $Path -Tail $Lines | ForEach-Object { Write-Host ('  ' + $_) }
        } else { Write-Host ('----- {0}: absent' -f $Path) }
    } catch { Write-Host ('----- {0}: {1}' -f $Path, $_.Exception.Message) }
}

function Show-Evidence {
    param([Parameter(Mandatory = $true)][string]$Why)
    Write-Host ('===== Evidence: {0}' -f $Why)
    foreach ($folder in @((Join-Path $stateRoot 'requests'), (Join-Path $stateRoot 'svc-out'))) {
        try {
            Write-Host ('----- {0}' -f $folder)
            foreach ($item in @(Get-ChildItem -LiteralPath $folder -Force -ErrorAction Stop)) {
                $owner = ''
                try { $owner = (Get-Acl -LiteralPath $item.FullName).Owner } catch { $owner = 'unreadable: ' + $_.Exception.Message }
                Write-Host ('  {0}  {1} bytes  {2:o}  owner {3}' -f $item.Name, $item.Length, $item.LastWriteTimeUtc, $owner)
            }
        } catch { Write-Host ('  {0}' -f $_.Exception.Message) }
    }
    try {
        if (Test-Path -LiteralPath $resultFile) {
            $acl = Get-Acl -LiteralPath $resultFile
            Write-Host ('----- exec-result.json owner {0}; SDDL {1}' -f $acl.Owner, $acl.Sddl)
            $read = Read-AsWizard $resultFile
            Write-Host ('  read as the wizard: ok {0}; {1}{2}' -f $read.ok, $read.text, $read.error)
        }
    } catch { Write-Host ('  exec-result.json: {0}' -f $_.Exception.Message) }
    foreach ($name in @('Exec', 'Start')) {
        try {
            $info = Get-ScheduledTaskInfo -TaskPath '\SlateOps\' -TaskName $name -ErrorAction Stop
            $task = Get-ScheduledTask -TaskPath '\SlateOps\' -TaskName $name -ErrorAction Stop
            Write-Host ('----- task \SlateOps\{0}: state {1}, last run {2:o}, last result 0x{3:X8}, runs as {4} ({5})' -f $name, $task.State, $info.LastRunTime, ([long]$info.LastTaskResult -band 4294967295L), $task.Principal.UserId, $task.Principal.LogonType)
        } catch { Write-Host ('----- task \SlateOps\{0}: {1}' -f $name, $_.Exception.Message) }
    }
    Show-Tail -Path (Join-Path $setupLogDir ('{0}.log' -f $runId))
    try { foreach ($file in @(Get-ChildItem -LiteralPath $execLogDir -Filter '*.log' -File -ErrorAction Stop)) { Show-Tail -Path $file.FullName } } catch { Write-Host ('----- {0}: {1}' -f $execLogDir, $_.Exception.Message) }
    $fallback = Join-Path $helperRoot 'logs'
    if (Test-Path -LiteralPath $fallback) {
        Write-Host ('----- helper fallback logs in {0} (a helper that could not use the state tree logs here)' -f $fallback)
        foreach ($file in @(Get-ChildItem -LiteralPath $fallback -Filter '*.log' -File)) { Show-Tail -Path $file.FullName }
    }
    Write-Host '===== End of evidence'
}

function Invoke-Step {
    param([Parameter(Mandatory = $true)][string]$Name, [Parameter(Mandatory = $true)][scriptblock]$Body)
    if ($script:Failed -gt 0) {
        $script:Results.Add(('SKIP  {0} (an earlier step failed)' -f $Name))
        Write-Line ('SKIP  {0}' -f $Name)
        return
    }
    Write-Line ('---- {0}' -f $Name)
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        & $Body
        $script:Results.Add(('PASS  {0} ({1} ms)' -f $Name, $watch.ElapsedMilliseconds))
        Write-Line ('PASS  {0} ({1} ms)' -f $Name, $watch.ElapsedMilliseconds)
    } catch {
        $script:Failed++
        $script:Results.Add(('FAIL  {0}: {1}' -f $Name, $_.Exception.Message))
        Write-Line ('FAIL  {0}: {1}' -f $Name, $_.Exception.Message)
        if ($_.InvocationInfo) { Write-Host $_.InvocationInfo.PositionMessage }
        Show-Evidence -Why $Name
    }
}

function Submit-Job {
    # Wizard.iss StartJob for a background job: a request ID made by the wizard, an empty input
    # file in {tmp}, the "job" helper with no wait; then PollJob's JOB_SUBMIT state.
    param([Parameter(Mandatory = $true)][string]$Label)
    $id = [guid]::NewGuid().ToString('D')
    $inputPath = Join-Path $helperRoot 'job-input.json'
    [System.IO.File]::WriteAllBytes($inputPath, (New-Object byte[] 0))
    $out = New-OutFile 'job'
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    $null = Start-Helper -Action 'job' -OutFile $out -Extra ('-Job wslconfig -RequestId {0} -InputFile "{1}"' -f $id, $inputPath)
    $code = ''
    while ($code -eq '') {
        if ($watch.ElapsedMilliseconds -gt $submitLimitMs) { throw ('{0}: the job helper gave no result in {1} s (helper_timeout)' -f $Label, ($submitLimitMs / 1000)) }
        Start-Sleep -Milliseconds 1000
        $code = Read-ResultCode $out
    }
    $text = [System.IO.File]::ReadAllText($out)
    Write-Line ('{0}: job helper answered {1} after {2} ms: {3}' -f $Label, $code, $watch.ElapsedMilliseconds, $text)
    if ($code -ne 'started') { throw ('{0}: the job helper answered {1}, not started' -f $Label, $code) }
    if ($text -notlike ('*"request_id":"{0}"*' -f $id)) { throw ('{0}: the job helper started another request ID' -f $Label) }
    return @{ label = $Label; id = $id; watch = $watch }
}

function Wait-ResultSeen {
    # The plain read only, no job-result helper: the result file names the request.
    param([Parameter(Mandatory = $true)][hashtable]$Job)
    while ($true) {
        $read = Read-AsWizard $resultFile
        if (Test-ResultNames -Read $read -RequestId $Job.id) {
            Write-Line ('{0}: the plain read sees the result after {1} ms' -f $Job.label, $Job.watch.ElapsedMilliseconds)
            return
        }
        if ($Job.watch.ElapsedMilliseconds -gt $collectLimitMs) { throw ('{0}: no result for the request in {1} s; last read: ok {2} {3}' -f $Job.label, ($collectLimitMs / 1000), $read.ok, $read.error) }
        Start-Sleep -Milliseconds 1000
    }
}

function Receive-Job {
    # Wizard.iss PollJob in JOB_WAIT, one pass per second: the plain read; the job-result helper
    # when the read sees the request ID, else every 15 s; its answer "done" collects the job.
    param([Parameter(Mandatory = $true)][hashtable]$Job)
    $startsBefore = Get-JobResultStartCount
    $pollAt = [System.Diagnostics.Stopwatch]::StartNew()
    $resultAt = $null
    $resultOut = ''
    $asks = 0
    $seenAt = -1
    $unreadable = 0
    $answers = New-Object System.Collections.Generic.List[string]
    while ($true) {
        if ($Job.watch.ElapsedMilliseconds -gt $collectLimitMs) {
            throw ('{0}: not collected in {1} s; job-result asks {2}, answers [{3}], plain read saw the result at {4} ms, unreadable reads {5}' -f $Job.label, ($collectLimitMs / 1000), $asks, ($answers -join ', '), $seenAt, $unreadable)
        }
        if ($resultOut -eq '') {
            $read = Read-AsWizard $resultFile
            $found = Test-ResultNames -Read $read -RequestId $Job.id
            if ($found -and ($seenAt -lt 0)) { $seenAt = $Job.watch.ElapsedMilliseconds }
            if ((-not $read.ok) -and $read.exists) {
                $unreadable++
                Write-Line ('{0}: the result file exists but this process cannot read it: {1}' -f $Job.label, $read.error)
            }
            if ((-not $found) -and ($pollAt.ElapsedMilliseconds -lt $askEveryMs)) { Start-Sleep -Milliseconds 1000; continue }
            $pollAt.Restart()
            $resultAt = [System.Diagnostics.Stopwatch]::StartNew()
            $resultOut = New-OutFile 'job-result'
            $asks++
            $null = Start-Helper -Action 'job-result' -OutFile $resultOut -Extra ('-RequestId {0}' -f $Job.id)
            Start-Sleep -Milliseconds 1000
            continue
        }
        $code = Read-ResultCode $resultOut
        if (($code -eq '') -and ($resultAt.ElapsedMilliseconds -gt $answerLimitMs)) { throw ('{0}: a job-result helper gave no answer in {1} s (helper_timeout)' -f $Job.label, ($answerLimitMs / 1000)) }
        if ($code -eq '') { Start-Sleep -Milliseconds 1000; continue }
        $answers.Add($code)
        $text = [System.IO.File]::ReadAllText($resultOut)
        if ($code -ne 'done') {
            # The wizard asks again on the next tick (with no limit while its read sees the result).
            Write-Line ('{0}: job-result answered {1}: {2}' -f $Job.label, $code, $text)
            $resultOut = ''
            Start-Sleep -Milliseconds 1000
            continue
        }
        Write-Line ('{0}: collected after {1} ms (plain read saw it at {2} ms; job-result asks {3}): {4}' -f $Job.label, $Job.watch.ElapsedMilliseconds, $seenAt, $asks, $text)
        $answer = $text | ConvertFrom-Json
        $exec = $answer.values.exec
        if ([string]$exec.request_id -ne $Job.id) { throw ('{0}: collected request {1}, expected {2}' -f $Job.label, $exec.request_id, $Job.id) }
        if (([string]$exec.code -ne 'written') -or ([int]$exec.exit_code -ne 0)) { throw ('{0}: the job ended {1} with exit code {2}, expected written and 0' -f $Job.label, $exec.code, $exec.exit_code) }
        if (Test-Path -LiteralPath $requestFile) { throw ('{0}: the collected request is still in requests\ (S91-3: job-result spends it)' -f $Job.label) }
        $startsAfter = Get-JobResultStartCount
        Write-Line ('{0}: job-result runs in the state tree setup log: {1} new for {2} asks' -f $Job.label, ($startsAfter - $startsBefore), $asks)
        if (($startsAfter - $startsBefore) -lt $asks) { throw ('{0}: {1} job-result runs, but only {2} logged in {3}' -f $Job.label, $asks, ($startsAfter - $startsBefore), $setupLogDir) }
        return
    }
}

$exitCode = 1
try {
    Invoke-Step 'preconditions: an administrator, no Slate Operations parts' {
        $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
        if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Not an administrator.' }
        foreach ($path in @($stateRoot, $dataRoot)) { if (Test-Path -LiteralPath $path) { throw ('{0} exists already.' -f $path) } }
        if (Get-LocalUser -Name 'slateops-svc' -ErrorAction SilentlyContinue) { throw 'The account slateops-svc exists already.' }
        $service = New-Object -ComObject 'Schedule.Service'
        $service.Connect()
        $folder = $null
        try { $folder = $service.GetFolder('\SlateOps') } catch { $folder = $null }
        if ($folder) { throw 'The task folder \SlateOps exists already.' }
        Write-Line ('Windows PowerShell {0}; {1}; System32\wsl.exe present: {2} (wslconfig does not start it)' -f $PSVersionTable.PSVersion, [Environment]::OSVersion.VersionString, (Test-Path -LiteralPath (Join-Path ([Environment]::SystemDirectory) 'wsl.exe')))
        Write-Line ('run ID {0}; helper root {1}; data folder {2}' -f $runId, $helperRoot, $dataRoot)
        $script:Owned = $true
    }

    Invoke-Step 'the helper root as setup extracts it ({tmp}\scripts, version.json, payload parts)' {
        if (Test-Path -LiteralPath $helperRoot) { Remove-Item -LiteralPath $helperRoot -Recurse -Force }
        [void][System.IO.Directory]::CreateDirectory($helperRoot)
        Copy-Item -LiteralPath $sourceScripts -Destination (Join-Path $helperRoot 'scripts') -Recurse
        $zero = '0' * 64
        $versionJson = '{{"schema_version":1,"version":"{0}","wsl_version":"2.6.1.0","wsl_msi_sha256":"{1}","linux_image_sha256":"{1}"}}' -f $version, $zero
        [System.IO.File]::WriteAllText((Join-Path $helperRoot 'scripts\version.json'), $versionJson, (New-Object System.Text.UTF8Encoding($false)))
        $payload = Join-Path $helperRoot 'payload'
        [void][System.IO.Directory]::CreateDirectory($payload)
        $parts = @(('slateops-linux-{0}-amd64.tar.gz' -f $version), 'release-manifest.json', 'release-manifest.json.sigstore.json',
            ('slateops-engine-{0}.tar.gz' -f $version), ('slateops-server-{0}-amd64.oci.tar' -f $version), ('slateops-caddy-{0}-amd64.oci.tar' -f $version))
        foreach ($name in $parts) { [System.IO.File]::WriteAllText((Join-Path $payload $name), 'part') }
    }

    Invoke-Step 'S07 prepare-data: the state tree, the data folder, install.json, the scripts copy' {
        $answer = Invoke-HelperAndWait -Action 'prepare-data' -Extra ('-DataRoot "{0}"' -f $dataRoot)
        if ($answer.code -ne 'ready') { throw ('prepare-data answered {0}, expected ready' -f $answer.code) }
    }

    Invoke-Step 'background step 1 service: the account slateops-svc and the tasks \SlateOps\Exec and \SlateOps\Start' {
        $answer = Invoke-HelperAndWait -Action 'service'
        if ($answer.code -ne 'created') { throw ('service answered {0}, expected created' -f $answer.code) }
        $sid = Invoke-HelperAndWait -Action 'account-sid'
        if ($sid.code -ne 'found') { throw ('account-sid answered {0}, expected found' -f $sid.code) }
        $task = Get-ScheduledTask -TaskPath '\SlateOps\' -TaskName 'Exec'
        Write-Line ('\SlateOps\Exec runs as {0} ({1}, {2}): {3} {4}' -f $task.Principal.UserId, $task.Principal.LogonType, $task.Principal.RunLevel, $task.Actions[0].Execute, $task.Actions[0].Arguments)
        if ([string]$task.Principal.LogonType -ne 'Password') { throw ('the Exec task logon type is {0}, expected Password' -f $task.Principal.LogonType) }
    }

    Invoke-Step 'job 1 (the W14-D8 step): background step 2 wslconfig, submitted and collected as the wizard does' {
        $job = Submit-Job -Label 'job 1'
        Receive-Job -Job $job
        $sid = (Get-LocalUser -Name 'slateops-svc').SID.Value
        $profileItem = Get-CimInstance -ClassName Win32_UserProfile -Filter ("SID='{0}'" -f $sid)
        if (-not $profileItem) { throw 'The account has no profile after the job.' }
        $config = Join-Path $profileItem.LocalPath '.wslconfig'
        if (-not (Test-Path -LiteralPath $config -PathType Leaf)) { throw ('{0} is missing.' -f $config) }
        $lines = @(Get-Content -LiteralPath $config)
        Write-Line ('{0}: {1}' -f $config, ($lines -join ' | '))
        if (@($lines | Where-Object { $_ -match '^memory=[0-9]+GB$' }).Count -ne 1) { throw 'The .wslconfig has no memory=<n>GB line.' }
    }

    Invoke-Step 'job 2: submitted, its result written, never collected (the rc.22 leftover request and result)' {
        $job = Submit-Job -Label 'job 2'
        Wait-ResultSeen -Job $job
        if (-not (Test-Path -LiteralPath $requestFile -PathType Leaf)) { throw 'The uncollected request left requests\ (the owner''s rc.22 files kept it).' }
    }

    Invoke-Step 'the rc.24 resume: prepare-data again with the account, the old request and the old result in place' {
        $answer = Invoke-HelperAndWait -Action 'prepare-data' -Extra ('-DataRoot "{0}"' -f $dataRoot)
        if ($answer.code -ne 'ready') { throw ('prepare-data answered {0}, expected ready' -f $answer.code) }
    }

    Invoke-Step 'job 3: wslconfig after the resume, over the old request and result, collected' {
        $job = Submit-Job -Label 'job 3'
        Receive-Job -Job $job
    }

    Invoke-Step 'job 4: wslconfig submitted at once after job 3 was collected, collected' {
        $job = Submit-Job -Label 'job 4'
        Receive-Job -Job $job
    }

    if ($script:Failed -eq 0) { Show-Evidence -Why 'the end of a passing run (logs for comparison with the owner''s report)' }
    if ($script:Failed -eq 0) { $exitCode = 0 }
} finally {
    # The runner is discarded after the job; this cleanup only keeps a rerun on the same runner
    # possible. Each part may be absent. Nothing is removed when the preconditions failed.
    if ($script:Owned) {
        foreach ($name in @('Exec', 'Start')) { Unregister-ScheduledTask -TaskPath '\SlateOps\' -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue }
        try {
            $service = New-Object -ComObject 'Schedule.Service'
            $service.Connect()
            $service.GetFolder('\').DeleteFolder('SlateOps', 0)
        } catch { $null = $_ }
        $user = Get-LocalUser -Name 'slateops-svc' -ErrorAction SilentlyContinue
        if ($user) {
            Get-CimInstance -ClassName Win32_UserProfile -Filter ("SID='{0}'" -f $user.SID.Value) -ErrorAction SilentlyContinue | Remove-CimInstance -ErrorAction SilentlyContinue
            Remove-LocalUser -Name 'slateops-svc' -ErrorAction SilentlyContinue
        }
        foreach ($path in @($stateRoot, $dataRoot)) { if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue } }
    }
}

Write-Host '===== Summary'
$script:Results | ForEach-Object { Write-Host $_ }
exit $exitCode
