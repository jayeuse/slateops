<#
exec-path.ps1 - the real Windows job path of setup, end to end (TASK-0097, W14-D8).

What setup does, with the real parts: setup-helper.ps1 from a helper root shaped like Inno's
{tmp}, the state tree C:\ProgramData\SlateOps, the data folder <system drive>\SlateOps, the real
account slateops-svc and the real task \SlateOps\Exec. Each wslconfig job is submitted with the
helper's "job" action and collected the way the wizard's PollJob does: a plain read of
svc-out\exec-result.json each second, and the "job-result" helper when the read sees the request
ID or every 15 s. The wslconfig job never starts wsl.exe (lib/Exec.ps1 Invoke-WindowsJob), so no
stand-in for it is needed; exec.ps1 always uses System32\wsl.exe and takes no path.

Sequence, in the wizard's S12 order: prepare-data with the address label (state tree, data
folder, install.json, scripts copy), service (the account and both tasks), job 1 (the D8 step,
first Exec job after the account), job 2 left uncollected (its request and result stay, as on the
owner's PC after rc.22), job 3 over that leftover, job 4 at once after job 3 (the background
chain submits its next job in the same tick). Then start-boot: the real \SlateOps\Start task
runs start.ps1 as slateops-svc, whose product mDNS responder (lib/Mdns.ps1,
Start-MdnsResponderThread) must answer <label>.local with this PC's IPv4 to a raw multicast
query and to Resolve-DnsName. Then windows-steps with a CA certificate made here (firewall
rules, hosts entry, trusted CA, power values). Last, the removal as the wizard runs it
(Maintenance.iss: job-stop, uninstall-stop, setup-remove-data, remove-features, remove-windows):
every recorded part must be gone, and a snapshot of this PC taken before setup must match after
(users, tasks, firewall rules, hosts file, root certificates, power values, sign-in list, resume
entries, the folders of the system drive, ProgramData and Users). By design the removal keeps
the state root's logs folder for Save report.

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
# The S08 short name as the address label (DEC-0039; Test-AddressLabel rule).
$label = 'slateops-ci-{0}' -f ([guid]::NewGuid().ToString('N').Substring(0, 8))
$script:ServiceReady = $false
$script:Before = $null
$script:CaThumbprint = ''

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
    try { foreach ($file in @(Get-ChildItem -LiteralPath (Join-Path $stateRoot 'logs\start') -Filter '*.log' -File -ErrorAction Stop)) { Show-Tail -Path $file.FullName -Lines 40 } } catch { Write-Host ('----- logs\start: {0}' -f $_.Exception.Message) }
    $fallback = Join-Path $helperRoot 'logs'
    if (Test-Path -LiteralPath $fallback) {
        Write-Host ('----- helper fallback logs in {0} (a helper that could not use the state tree logs here)' -f $fallback)
        foreach ($file in @(Get-ChildItem -LiteralPath $fallback -Filter '*.log' -File)) { Show-Tail -Path $file.FullName }
    }
    Write-Host '===== End of evidence'
}

function Invoke-Step {
    # -Always: runs after an earlier failure too (the step checks what it needs itself), so the
    # responder, the Windows steps and the removal always leave their evidence.
    param([Parameter(Mandatory = $true)][string]$Name, [Parameter(Mandatory = $true)][scriptblock]$Body, [switch]$Always)
    if ((-not $script:Owned) -or (($script:Failed -gt 0) -and -not $Always)) {
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

# ---------------------------------------------------------------------------
# The PC before and after: what setup may change and the removal must restore
# ---------------------------------------------------------------------------

$hostsPath = Join-Path ([Environment]::SystemDirectory) 'drivers\etc\hosts'
$userListKey = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\SpecialAccounts\UserList'
$runOnceKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce'

function Get-RegistryValueText {
    param([Parameter(Mandatory = $true)][string]$Key)
    if (-not (Test-Path -LiteralPath $Key)) { return '<no key>' }
    $item = Get-ItemProperty -LiteralPath $Key
    return (@($item.PSObject.Properties | Where-Object { $_.Name -notlike 'PS*' } | ForEach-Object { '{0}={1}' -f $_.Name, $_.Value } | Sort-Object) -join "`n")
}

function Get-MachineSnapshot {
    $snapshot = [ordered]@{}
    $snapshot['local users'] = (@(Get-LocalUser | ForEach-Object { $_.Name } | Sort-Object) -join "`n")
    $snapshot['scheduled tasks'] = (@(Get-ScheduledTask | ForEach-Object { $_.TaskPath + $_.TaskName } | Sort-Object) -join "`n")
    $snapshot['firewall rules'] = (@(Get-NetFirewallRule | ForEach-Object { $_.Name } | Sort-Object) -join "`n")
    $snapshot['Hyper-V firewall rules'] = 'not available'
    if (Get-Command -Name 'Get-NetFirewallHyperVRule' -ErrorAction SilentlyContinue) { $snapshot['Hyper-V firewall rules'] = (@(Get-NetFirewallHyperVRule | ForEach-Object { $_.Name } | Sort-Object) -join "`n") }
    $snapshot['hosts file SHA-256'] = (Get-FileHash -LiteralPath $hostsPath -Algorithm SHA256).Hash
    $snapshot['LocalMachine Root certificates'] = (@(Get-ChildItem -LiteralPath 'Cert:\LocalMachine\Root' | ForEach-Object { $_.Thumbprint } | Sort-Object) -join "`n")
    $snapshot['power (active scheme, sleep values)'] = ((@(& powercfg.exe /getactivescheme) + @(& powercfg.exe /q SCHEME_CURRENT SUB_SLEEP)) -join "`n")
    $snapshot['sign-in list (UserList)'] = Get-RegistryValueText -Key $userListKey
    $snapshot['resume entries (RunOnce)'] = Get-RegistryValueText -Key $runOnceKey
    $snapshot['system drive folders'] = (@(Get-ChildItem -LiteralPath ('{0}\' -f $env:SystemDrive) -Force | ForEach-Object { $_.Name } | Sort-Object) -join "`n")
    $snapshot['ProgramData folders (SlateOps apart)'] = (@(Get-ChildItem -LiteralPath (Split-Path -Parent $stateRoot) -Force | Where-Object { $_.Name -ne 'SlateOps' } | ForEach-Object { $_.Name } | Sort-Object) -join "`n")
    $snapshot['Users folders'] = (@(Get-ChildItem -LiteralPath (Split-Path -Parent ([Environment]::GetFolderPath('UserProfile'))) -Force | ForEach-Object { $_.Name } | Sort-Object) -join "`n")
    return $snapshot
}

function Compare-MachineSnapshot {
    # One line per changed item, with what was added and what went.
    param([Parameter(Mandatory = $true)][System.Collections.IDictionary]$Before, [Parameter(Mandatory = $true)][System.Collections.IDictionary]$After)
    $changes = New-Object System.Collections.Generic.List[string]
    foreach ($key in @($Before.Keys)) {
        if ([string]$Before[$key] -ceq [string]$After[$key]) { continue }
        $old = @(([string]$Before[$key]) -split "`n")
        $new = @(([string]$After[$key]) -split "`n")
        $added = @($new | Where-Object { $old -cnotcontains $_ })
        $gone = @($old | Where-Object { $new -cnotcontains $_ })
        $changes.Add(('{0} changed; added [{1}]; gone [{2}]' -f $key, ($added -join ' | '), ($gone -join ' | ')))
    }
    # Plain output: callers wrap it in @(), so no change is an empty list.
    return $changes.ToArray()
}

function Get-RecordValue {
    param([Parameter(Mandatory = $true)]$Record, [Parameter(Mandatory = $true)][string]$Name)
    $property = $Record.PSObject.Properties[$Name]
    # Plain output: a list unrolls, and the callers wrap lists in @().
    if ($property) { return $property.Value }
    return $null
}

function New-TestCaPem {
    # A self-signed CA certificate (basic constraints CA=true), as the engine's install result
    # gives one; only its public part leaves this function.
    param([Parameter(Mandatory = $true)][string]$Path)
    $certificate = New-SelfSignedCertificate -Subject 'CN=Slate Operations CI test CA' -KeyUsage CertSign, CRLSign, DigitalSignature `
        -TextExtension @('2.5.29.19={critical}{text}ca=1&pathlength=0') -KeyAlgorithm RSA -KeyLength 2048 -NotAfter (Get-Date).AddDays(2) `
        -CertStoreLocation 'Cert:\CurrentUser\My'
    try {
        $pem = "-----BEGIN CERTIFICATE-----`r`n" + [Convert]::ToBase64String($certificate.RawData, [Base64FormattingOptions]::InsertLineBreaks) + "`r`n-----END CERTIFICATE-----`r`n"
        [System.IO.File]::WriteAllText($Path, $pem, [System.Text.Encoding]::ASCII)
    } finally { Remove-Item -LiteralPath ('Cert:\CurrentUser\My\{0}' -f $certificate.Thumbprint) -DeleteKey }
    return $certificate.Thumbprint
}

# ---------------------------------------------------------------------------
# A raw mDNS query (RFC 1035, RFC 6762), this test's own code: one A question with the QU bit,
# answers collected on the asking port.
# ---------------------------------------------------------------------------

function ConvertTo-DnsName {
    param([Parameter(Mandatory = $true)][string]$Text)
    $bytes = New-Object System.Collections.Generic.List[byte]
    foreach ($label in $Text.TrimEnd('.').Split('.')) {
        $part = [System.Text.Encoding]::ASCII.GetBytes($label)
        $bytes.Add([byte]$part.Length)
        $bytes.AddRange($part)
    }
    $bytes.Add([byte]0)
    return , $bytes.ToArray()
}

function Read-DnsName {
    param([Parameter(Mandatory = $true)][byte[]]$Data, [Parameter(Mandatory = $true)][int]$Offset)
    $labels = New-Object System.Collections.Generic.List[string]
    $next = -1
    $pos = $Offset
    $jumps = 0
    while ($true) {
        if ($pos -ge $Data.Length) { throw 'dns_truncated' }
        $length = [int]$Data[$pos]
        if ($length -eq 0) { $pos++; break }
        if (($length -band 0xC0) -eq 0xC0) {
            if ($next -lt 0) { $next = $pos + 2 }
            $pos = (($length -band 0x3F) * 256) + [int]$Data[$pos + 1]
            $jumps++
            if ($jumps -gt 32) { throw 'dns_loop' }
            continue
        }
        $labels.Add([System.Text.Encoding]::ASCII.GetString($Data, $pos + 1, $length))
        $pos += 1 + $length
    }
    if ($next -lt 0) { $next = $pos }
    return @{ name = ($labels.ToArray() -join '.'); next = $next }
}

function Get-DnsAddresses {
    # The A records of a DNS response as "<name> <address>"; none for a query.
    param([Parameter(Mandatory = $true)][byte[]]$Data)
    if ($Data.Length -lt 12) { return }
    if (([int]$Data[2] -band 0x80) -eq 0) { return }
    $questionCount = ([int]$Data[4] * 256) + [int]$Data[5]
    $recordCount = (([int]$Data[6] * 256) + [int]$Data[7]) + (([int]$Data[8] * 256) + [int]$Data[9]) + (([int]$Data[10] * 256) + [int]$Data[11])
    $pos = 12
    for ($i = 0; $i -lt $questionCount; $i++) { $pos = (Read-DnsName -Data $Data -Offset $pos).next + 4 }
    $found = @()
    for ($i = 0; $i -lt $recordCount; $i++) {
        $read = Read-DnsName -Data $Data -Offset $pos
        $pos = $read.next
        $type = ([int]$Data[$pos] * 256) + [int]$Data[$pos + 1]
        $length = ([int]$Data[$pos + 8] * 256) + [int]$Data[$pos + 9]
        if (($type -eq 1) -and ($length -eq 4)) { $found += ('{0} {1}.{2}.{3}.{4}' -f $read.name, $Data[$pos + 10], $Data[$pos + 11], $Data[$pos + 12], $Data[$pos + 13]) }
        $pos += 10 + $length
    }
    return $found
}

function Invoke-MdnsQuQuery {
    # Returns "<address> from <responder>" for each A answer for QueryName in WaitMs.
    param([Parameter(Mandatory = $true)][string]$QueryName, [Parameter(Mandatory = $true)][string]$Ip, [int]$WaitMs = 3000)
    $answers = New-Object System.Collections.Generic.List[string]
    $udp = New-Object System.Net.Sockets.UdpClient((New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Parse($Ip), 0)))
    try {
        $udp.Client.SetSocketOption([System.Net.Sockets.SocketOptionLevel]::IP, [System.Net.Sockets.SocketOptionName]::MulticastInterface, [System.Net.IPAddress]::Parse($Ip).GetAddressBytes())
        $query = New-Object System.Collections.Generic.List[byte]
        $query.AddRange([byte[]](0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0))
        $query.AddRange((ConvertTo-DnsName $QueryName))
        $query.AddRange([byte[]](0, 1, 0x80, 1))
        $bytes = $query.ToArray()
        $null = $udp.Send($bytes, $bytes.Length, (New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Parse('224.0.0.251'), 5353)))
        $watch = [System.Diagnostics.Stopwatch]::StartNew()
        while ($watch.ElapsedMilliseconds -lt $WaitMs) {
            if ($udp.Available -le 0) { Start-Sleep -Milliseconds 50; continue }
            $remote = New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Any, 0)
            $data = $udp.Receive([ref]$remote)
            $records = @()
            try { $records = @(Get-DnsAddresses -Data $data) } catch { continue }
            foreach ($record in $records) {
                $parts = $record.Split(' ')
                if ($parts[0] -ieq $QueryName) { $answers.Add(('{0} from {1}' -f $parts[1], $remote)) }
            }
        }
    } finally { $udp.Close() }
    return $answers.ToArray()
}

function Get-RunnerIPv4 {
    # The IPv4 address of the default route's interface (the LAN side of this PC).
    $route = Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Sort-Object -Property RouteMetric, InterfaceMetric | Select-Object -First 1
    return [string](Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $route.InterfaceIndex | Select-Object -First 1).IPAddress
}

$exitCode = 1
try {
    $script:Owned = $true
    Invoke-Step 'preconditions: an administrator, no Slate Operations parts' {
        $script:Owned = $false
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
        Write-Line ('run ID {0}; helper root {1}; data folder {2}; address label {3}' -f $runId, $helperRoot, $dataRoot, $label)
        $script:Before = Get-MachineSnapshot
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

    Invoke-Step 'S12 prepare-data with the address label: the state tree, the data folder, install.json, the scripts copy' {
        $answer = Invoke-HelperAndWait -Action 'prepare-data' -Extra ('-DataRoot "{0}" -Label {1}' -f $dataRoot, $label)
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
        $script:ServiceReady = $true
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

    Invoke-Step 'job 3: wslconfig over the old request and result, collected' {
        $job = Submit-Job -Label 'job 3'
        Receive-Job -Job $job
    }

    Invoke-Step 'job 4: wslconfig submitted at once after job 3 was collected, collected' {
        $job = Submit-Job -Label 'job 4'
        Receive-Job -Job $job
    }

    Invoke-Step -Always 'background step start-boot: the product mDNS responder (start.ps1 as slateops-svc) answers <label>.local with this PC''s IPv4' {
        if (-not $script:ServiceReady) { throw 'the service step did not finish' }
        $answer = Invoke-HelperAndWait -Action 'start-boot'
        if ($answer.code -ne 'started') { throw ('start-boot answered {0}, expected started' -f $answer.code) }
        $task = Get-ScheduledTask -TaskPath '\SlateOps\' -TaskName 'Start'
        Write-Line ('\SlateOps\Start runs as {0} ({1}, {2}): {3}' -f $task.Principal.UserId, $task.Principal.LogonType, $task.Principal.RunLevel, $task.Actions[0].Arguments)
        $expected = Get-RunnerIPv4
        $name = '{0}.local' -f $label
        $watch = [System.Diagnostics.Stopwatch]::StartNew()
        $raw = @()
        while ($watch.Elapsed.TotalSeconds -lt 120) {
            $raw = @(Invoke-MdnsQuQuery -QueryName $name -Ip $expected)
            if (@($raw | Where-Object { $_ -like ('{0} from *' -f $expected) }).Count -gt 0) { break }
            Start-Sleep -Seconds 2
        }
        Write-Line ('raw mDNS QU {0} after {1:N1} s: [{2}] (expected {3})' -f $name, $watch.Elapsed.TotalSeconds, ($raw -join ', '), $expected)
        if (@($raw | Where-Object { $_ -like ('{0} from *' -f $expected) }).Count -eq 0) { throw ('no raw mDNS answer with {0} for {1} in 120 s' -f $expected, $name) }
        # The hosts entry does not exist yet (windows-steps writes it), so this is the mDNS path.
        Clear-DnsClientCache
        $resolved = @()
        try { $resolved = @(Resolve-DnsName -Name $name -Type A -ErrorAction Stop | Where-Object { $_.PSObject.Properties['IPAddress'] -and ($_.Type -eq 'A') } | ForEach-Object { $_.IPAddress }) }
        catch { Write-Line ('Resolve-DnsName {0}: {1}' -f $name, $_.Exception.Message) }
        Write-Line ('Resolve-DnsName {0}: [{1}]' -f $name, ($resolved -join ', '))
        if ($resolved -notcontains $expected) { throw ('Resolve-DnsName gave no {0} for {1}' -f $expected, $name) }
    }

    Invoke-Step -Always 'windows-steps with a CA certificate made here: firewall rules, hosts entry, trusted CA, power values' {
        if (-not $script:ServiceReady) { throw 'the service step did not finish' }
        $pemPath = Join-Path $helperRoot 'ca.pem'
        $script:CaThumbprint = New-TestCaPem -Path $pemPath
        $answer = Invoke-HelperAndWait -Action 'windows-steps' -Extra ('-PemFile "{0}"' -f $pemPath)
        if ($answer.code -ne 'done') { throw ('windows-steps answered {0}, expected done' -f $answer.code) }
        $record = Get-Content -LiteralPath (Join-Path $stateRoot 'state\windows-changes.json') -Raw | ConvertFrom-Json
        $rules = @(Get-RecordValue $record 'firewall_rules')
        $hyperV = @(Get-RecordValue $record 'hyperv_rules')
        Write-Line ('recorded: firewall rules [{0}], Hyper-V rules [{1}], hosts {2}, CA {3}, power scheme {4}' -f ($rules -join ', '), ($hyperV -join ', '), (Get-RecordValue $record 'hosts_name'), (Get-RecordValue $record 'ca_thumbprint'), (Get-RecordValue $record 'power_scheme'))
        foreach ($rule in $rules) { if (-not (Get-NetFirewallRule -Name $rule -ErrorAction SilentlyContinue)) { throw ('the recorded firewall rule {0} does not exist' -f $rule) } }
        if (@(Get-Content -LiteralPath $hostsPath | Where-Object { $_ -like ('*{0}.local*' -f $label) }).Count -ne 1) { throw 'the hosts file has no line for the label' }
        if ([string](Get-RecordValue $record 'ca_thumbprint') -ne $script:CaThumbprint) { throw 'the recorded CA is not the one given' }
        if (-not (Test-Path -LiteralPath ('Cert:\LocalMachine\Root\{0}' -f $script:CaThumbprint))) { throw 'the CA is not in LocalMachine Root' }
    }

    Invoke-Step -Always 'the removal as the wizard runs it; every recorded part gone, nothing else on this PC changed' {
        if (-not (Test-Path -LiteralPath $stateRoot)) { throw 'nothing to remove: the state root does not exist' }
        $record = $null
        $recordPath = Join-Path $stateRoot 'state\windows-changes.json'
        if (Test-Path -LiteralPath $recordPath) { $record = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json }
        $sid = ''
        $account = Get-LocalUser -Name 'slateops-svc' -ErrorAction SilentlyContinue
        if ($account) { $sid = $account.SID.Value }
        $profilePath = ''
        if ($sid) {
            $profileItem = Get-CimInstance -ClassName Win32_UserProfile -Filter ("SID='{0}'" -f $sid) -ErrorAction SilentlyContinue
            if ($profileItem) { $profilePath = $profileItem.LocalPath; Write-Line ('profile {0}, loaded {1}' -f $profileItem.LocalPath, $profileItem.Loaded) }
        }
        # Maintenance.iss PollCloseFlow: each step follows the last whatever its code; only
        # keep_failed stops; -DataLeft when the data step did not remove the data folder.
        $codes = [ordered]@{}
        foreach ($action in @('job-stop', 'uninstall-stop', 'setup-remove-data', 'remove-features')) {
            $codes[$action] = (Invoke-HelperAndWait -Action $action).code
            if ($codes[$action] -eq 'keep_failed') { throw 'setup-remove-data answered keep_failed' }
        }
        $extra = ''
        if (@('removed', 'returned', 'nothing') -notcontains $codes['setup-remove-data']) { $extra = '-DataLeft' }
        $codes['remove-windows'] = (Invoke-HelperAndWait -Action 'remove-windows' -Extra $extra).code
        $problems = New-Object System.Collections.Generic.List[string]
        $expectedCodes = [ordered]@{ 'job-stop' = 'stopped'; 'uninstall-stop' = 'stopped'; 'setup-remove-data' = 'removed'; 'remove-features' = 'kept'; 'remove-windows' = 'removed' }
        foreach ($action in @($expectedCodes.Keys)) { if ($codes[$action] -ne $expectedCodes[$action]) { $problems.Add(('{0} answered {1}, expected {2}' -f $action, $codes[$action], $expectedCodes[$action])) } }
        if (Get-LocalUser -Name 'slateops-svc' -ErrorAction SilentlyContinue) { $problems.Add('the account slateops-svc') }
        if ($sid -and (Get-CimInstance -ClassName Win32_UserProfile -Filter ("SID='{0}'" -f $sid) -ErrorAction SilentlyContinue)) { $problems.Add(('the profile record of {0}' -f $sid)) }
        if ($profilePath -and (Test-Path -LiteralPath $profilePath)) { $problems.Add(('the profile folder {0}' -f $profilePath)) }
        if (@(Get-ScheduledTask -TaskPath '\SlateOps\' -ErrorAction SilentlyContinue).Count -gt 0) { $problems.Add('tasks in \SlateOps\') }
        $schedule = New-Object -ComObject 'Schedule.Service'
        $schedule.Connect()
        $folder = $null
        try { $folder = $schedule.GetFolder('\SlateOps') } catch { $folder = $null }
        if ($folder) { $problems.Add('the task folder \SlateOps') }
        foreach ($name in @('state', 'requests', 'svc-out', 'scripts', 'settings')) { if (Test-Path -LiteralPath (Join-Path $stateRoot $name)) { $problems.Add(('the state folder {0}' -f $name)) } }
        if (Test-Path -LiteralPath $dataRoot) { $problems.Add(('the data folder {0}' -f $dataRoot)) }
        if ($record) {
            foreach ($rule in @(Get-RecordValue $record 'firewall_rules')) { if ($rule -and (Get-NetFirewallRule -Name $rule -ErrorAction SilentlyContinue)) { $problems.Add(('the firewall rule {0}' -f $rule)) } }
            foreach ($rule in @(Get-RecordValue $record 'hyperv_rules')) { if ($rule -and (Get-Command -Name 'Get-NetFirewallHyperVRule' -ErrorAction SilentlyContinue) -and (Get-NetFirewallHyperVRule -Name $rule -ErrorAction SilentlyContinue)) { $problems.Add(('the Hyper-V firewall rule {0}' -f $rule)) } }
        }
        if (@(Get-Content -LiteralPath $hostsPath | Where-Object { $_ -like '*# Slate Operations' }).Count -gt 0) { $problems.Add('the hosts entry') }
        if ($script:CaThumbprint -and (Test-Path -LiteralPath ('Cert:\LocalMachine\Root\{0}' -f $script:CaThumbprint))) { $problems.Add('the trusted CA') }
        if (Test-Path -LiteralPath $stateRoot) { Write-Line ('kept by design for Save report: {0} with [{1}]' -f $stateRoot, ((@(Get-ChildItem -LiteralPath $stateRoot -Force | ForEach-Object { $_.Name })) -join ', ')) }
        foreach ($change in @(Compare-MachineSnapshot -Before $script:Before -After (Get-MachineSnapshot))) { $problems.Add(('outside the recorded parts: {0}' -f $change)) }
        if ($problems.Count -gt 0) { throw ('left over or changed: {0}' -f ($problems.ToArray() -join '; ')) }
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
        foreach ($rule in @('SlateOps-TCP-443-80', 'SlateOps-mDNS-In-UDP')) { Remove-NetFirewallRule -Name $rule -ErrorAction SilentlyContinue }
        if (Get-Command -Name 'Remove-NetFirewallHyperVRule' -ErrorAction SilentlyContinue) { Remove-NetFirewallHyperVRule -Name 'SlateOps-HyperV-TCP-443-80' -ErrorAction SilentlyContinue }
        if ($script:CaThumbprint) { Remove-Item -LiteralPath ('Cert:\LocalMachine\Root\{0}' -f $script:CaThumbprint) -ErrorAction SilentlyContinue }
    }
}

Write-Host '===== Summary'
$script:Results | ForEach-Object { Write-Host $_ }
exit $exitCode
